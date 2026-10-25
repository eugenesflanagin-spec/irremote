# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Eugene Flanagin
"""IR Remote window (PyQt6). Follows the desktop theme (Breeze, dark mode)."""

from __future__ import annotations

import copy
import os
import sys
import time

from PyQt6.QtCore import QSettings, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon, QKeySequence, QShortcut
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QKeySequenceEdit,
    QLabel, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
    QStackedWidget, QStyle, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget,
)

from . import __version__, core, layouts, visual

README = "/usr/share/doc/irremote/README.md"
TILE_W, TILE_H = 168, 92


def icon(name: str, fallback: QStyle.StandardPixmap | None = None) -> QIcon:
    ic = QIcon.fromTheme(name)
    if ic.isNull() and fallback is not None:
        ic = QApplication.style().standardIcon(fallback)
    return ic


class Worker(QThread):
    """Run a blocking function off the GUI thread."""
    done = pyqtSignal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            res = self.fn()
        except Exception as e:  # noqa: BLE001 - always report back to the UI
            res = core.Result(False, f"Unexpected problem: {e}")
        self.done.emit(res)


# --- Learn dialog --------------------------------------------------------------

class LearnDialog(QDialog):
    TIMEOUT = 20

    def __init__(self, parent, remote_name: str, button: dict | None, fixed_name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Learn a button")
        self.setMinimumWidth(460)
        self.button = button
        self.code = ""
        self.learner: core.Learner | None = None
        self.worker: Worker | None = None
        self.test_worker: Worker | None = None

        lay = QVBoxLayout(self)
        title = QLabel(f"<h3>Teach IR Remote a button for “{remote_name}”</h3>")
        lay.addWidget(title)

        form = QFormLayout()
        self.name = QComboBox(editable=True)
        self.name.addItems(["Power", "Volume Up", "Volume Down", "Mute", "Input",
                            "Channel Up", "Channel Down", "OK", "Up", "Down", "Left",
                            "Right", "Back", "Home", "Menu", "Play/Pause"])
        self.name.setCurrentText(fixed_name or (button["name"] if button else ""))
        self.name.lineEdit().setPlaceholderText("Button name, e.g. Power")
        if fixed_name:      # a button on the picture: its name is its place
            self.name.setEnabled(False)
        form.addRow("Button name:", self.name)
        lay.addLayout(form)

        steps = QLabel(
            "<ol>"
            "<li>Click <b>Start listening</b>.</li>"
            "<li>Hold your remote <b>within 1 cm</b> of the dongle, pointing at its tip.</li>"
            "<li>Press the button once (hold it about a second).</li>"
            "</ol>")
        steps.setWordWrap(True)
        lay.addWidget(steps)

        self.status = QLabel("Ready when you are.")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(48)
        f = self.status.font()
        f.setPointSizeF(f.pointSizeF() * 1.1)
        self.status.setFont(f)
        lay.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(0, self.TIMEOUT)
        self.progress.setFormat("%v s left")
        self.progress.hide()
        lay.addWidget(self.progress)

        self.code_view = QPlainTextEdit(readOnly=True)
        self.code_view.setMaximumHeight(70)
        self.code_view.setPlaceholderText("The captured code will appear here.")
        lay.addWidget(self.code_view)

        row = QHBoxLayout()
        self.start_btn = QPushButton(icon("media-record"), "Start listening")
        self.test_btn = QPushButton(icon("media-playback-start"), "Test")
        self.save_btn = QPushButton(icon("document-save"), "Save")
        self.cancel_btn = QPushButton("Cancel")
        self.test_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.save_btn.setDefault(True)
        for b in (self.start_btn, self.test_btn):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.save_btn)
        row.addWidget(self.cancel_btn)
        lay.addLayout(row)

        self.start_btn.clicked.connect(self.start)
        self.test_btn.clicked.connect(self.test)
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self.tick = QTimer(self, interval=1000)
        self.tick.timeout.connect(self._tick)
        self.started_at = 0.0

    def button_name(self) -> str:
        return self.name.currentText().strip()

    def _busy(self, busy: bool):
        self.start_btn.setEnabled(not busy)
        self.test_btn.setEnabled(not busy and bool(self.code))
        self.save_btn.setEnabled(not busy and bool(self.code))

    def start(self):
        self.code = ""
        self.code_view.clear()
        self._busy(True)
        self.status.setText("Listening… press the button on your remote now.")
        self.progress.setValue(self.TIMEOUT)
        self.progress.show()
        self.started_at = time.monotonic()
        self.tick.start()
        self.learner = core.Learner(timeout=self.TIMEOUT)
        self.worker = Worker(self.learner.run, self)
        self.worker.done.connect(self._learned)
        self.worker.start()

    def _tick(self):
        left = max(0, self.TIMEOUT - int(time.monotonic() - self.started_at))
        self.progress.setValue(left)
        if left == 0:
            self.status.setText("Wrapping up…")

    def _learned(self, res: core.Result):
        self.tick.stop()
        self.progress.hide()
        self.learner = None
        if res.ok:
            self.code = res.code
            self.code_view.setPlainText(res.code)
            self.status.setText("✔ Got it! Click <b>Test</b> to check it works with your "
                                "device, then <b>Save</b>.")
            self.start_btn.setText("Retry")
        else:
            self.status.setText(f"✖ {res.message}")
            self.start_btn.setText("Try again")
        self._busy(False)

    def test(self):
        self._busy(True)
        self.status.setText("Sending…")
        code = self.code
        self.test_worker = Worker(lambda: core.transmit_code(code), self)
        self.test_worker.done.connect(self._tested)
        self.test_worker.start()

    def _tested(self, res: core.Result):
        self._busy(False)
        if res.ok:
            self.status.setText("Sent. Did your device react? If yes, <b>Save</b>. "
                                "If not, <b>Retry</b> the capture.")
        else:
            self.status.setText(f"✖ {res.message}")

    def accept(self):
        if not self.code:
            return
        if not self.button_name():
            self.status.setText("Please give the button a name first.")
            self.name.setFocus()
            return
        super().accept()

    def done(self, r):
        if self.learner:
            self.learner.cancel()
        for w in (self.worker, self.test_worker):
            if w and w.isRunning():
                w.wait(15000)
        self.tick.stop()
        super().done(r)


# --- Button edit dialog --------------------------------------------------------

class ButtonDialog(QDialog):
    def __init__(self, parent, remote_name: str, button: dict):
        super().__init__(parent)
        self.setWindowTitle("Edit button" if button.get("name") else "Add button by code")
        self.setMinimumWidth(480)
        self.remote_name = remote_name
        self.btn = copy.deepcopy(button)
        self.worker = None

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QComboBox(editable=True)
        self.name.setCurrentText(button.get("name", ""))
        form.addRow("Name:", self.name)

        self.type = QComboBox()
        self.type.addItem("Learned code (captured from a remote)", core.TYPE_LEARNED)
        self.type.addItem("NEC code (address + command, 4 hex digits)", core.TYPE_NEC)
        self.type.setCurrentIndex(1 if button.get("type") == core.TYPE_NEC else 0)
        form.addRow("Code type:", self.type)

        self.code = QPlainTextEdit(button.get("code", ""))
        self.code.setMaximumHeight(90)
        self.code.setPlaceholderText("Paste a hex code here (spaces are fine)")
        form.addRow("Code:", self.code)

        self.freq = QSpinBox()
        self.freq.setRange(10000, 100000)
        self.freq.setSingleStep(1000)
        self.freq.setSuffix(" Hz")
        self.freq.setValue(int(button.get("frequency") or core.DEFAULT_FREQUENCY))
        self.freq.setToolTip("Carrier frequency. 38000 Hz works for almost every TV.")
        form.addRow("Frequency:", self.freq)

        self.app_key = QKeySequenceEdit(QKeySequence(button.get("app_shortcut", "")))
        self.app_key.setMaximumSequenceLength(1)
        self.app_key.setToolTip("Works while the IR Remote window is focused.")
        form.addRow("In-app key:", self._with_clear(self.app_key))

        self.global_key = QKeySequenceEdit(QKeySequence(button.get("shortcut", "")))
        self.global_key.setMaximumSequenceLength(1)
        self.global_key.setToolTip("Works anywhere in Plasma, even when IR Remote is closed.")
        form.addRow("Global shortcut:", self._with_clear(self.global_key))
        lay.addLayout(form)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                              QDialogButtonBox.StandardButton.Cancel)
        self.test_btn = bb.addButton("Test", QDialogButtonBox.ButtonRole.ActionRole)
        self.test_btn.setIcon(icon("media-playback-start"))
        self.test_btn.clicked.connect(self.test)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    @staticmethod
    def _with_clear(edit: QKeySequenceEdit) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit, 1)
        clear = QToolButton(icon=icon("edit-clear"), text="Clear", toolTip="Clear")
        clear.clicked.connect(edit.clear)
        h.addWidget(clear)
        return w

    def values(self) -> dict:
        b = self.btn
        b["name"] = self.name.currentText().strip()
        b["type"] = self.type.currentData()
        b["code"] = core.clean_hex(self.code.toPlainText())
        b["frequency"] = self.freq.value()
        b["app_shortcut"] = self.app_key.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText)
        b["shortcut"] = self.global_key.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText)
        return b

    def test(self):
        b = self.values()
        problem = core.validate_code(b["code"], b["type"])
        if problem:
            self.hint.setText(f"✖ {problem}")
            return
        self.test_btn.setEnabled(False)
        self.hint.setText("Sending…")
        self.worker = Worker(lambda: core.transmit_code(b["code"], b["type"], b["frequency"]), self)
        self.worker.done.connect(self._tested)
        self.worker.start()

    def _tested(self, res):
        self.test_btn.setEnabled(True)
        self.hint.setText("Sent." if res.ok else f"✖ {res.message}")

    def accept(self):
        b = self.values()
        if not b["name"]:
            self.hint.setText("✖ The button needs a name.")
            return
        if b["code"]:
            problem = core.validate_code(b["code"], b["type"])
            if problem:
                self.hint.setText(f"✖ {problem}")
                return
        if b["shortcut"]:
            from . import shortcuts
            clash = shortcuts.conflict(b["shortcut"], self.remote_name, b["name"])
            if clash and QMessageBox.question(
                    self, "Shortcut in use",
                    f"{b['shortcut']} is already used by {clash}.\nUse it for this button anyway?"
            ) != QMessageBox.StandardButton.Yes:
                return
        super().accept()

    def done(self, r):
        if self.worker and self.worker.isRunning():
            self.worker.wait(15000)
        super().done(r)


# --- Shortcuts overview ------------------------------------------------------

class ShortcutsDialog(QDialog):
    def __init__(self, parent, data: dict):
        super().__init__(parent)
        self.setWindowTitle("Shortcuts")
        self.resize(640, 360)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Global shortcuts work anywhere in Plasma, even with IR Remote closed. "
            "Set one with right-click on a button → <b>Edit…</b>. They also appear in "
            "System Settings → Keyboard → Shortcuts."))
        rows = [(r, b) for r in data["remotes"] for b in r["buttons"]
                if b["shortcut"] or b["app_shortcut"]]
        t = QTableWidget(len(rows), 4)
        t.setHorizontalHeaderLabels(["Global", "In-app", "Button", "Command"])
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.verticalHeader().hide()
        for i, (r, b) in enumerate(rows):
            for j, text in enumerate([b["shortcut"] or "—", b["app_shortcut"] or "—",
                                      f"{r['name']} / {b['name']}",
                                      f'irremote send "{r["name"]}" "{b["name"]}"']):
                t.setItem(i, j, QTableWidgetItem(text))
        t.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        t.resizeColumnsToContents()
        lay.addWidget(t)
        if not rows:
            lay.addWidget(QLabel("No shortcuts yet."))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class AssignShortcutDialog(QDialog):
    """Just the global shortcut of one button (right-click on the picture)."""

    def __init__(self, parent, remote_name: str, button_name: str, current: str):
        super().__init__(parent)
        self.setWindowTitle("Assign shortcut")
        self.remote_name, self.button_name = remote_name, button_name
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Global shortcut for <b>{_esc(remote_name)} / "
                             f"{_esc(button_name)}</b>.<br>It works anywhere in Plasma, "
                             "even with IR Remote closed."))
        self.key = QKeySequenceEdit(QKeySequence(current))
        self.key.setMaximumSequenceLength(1)
        lay.addWidget(ButtonDialog._with_clear(self.key))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def value(self) -> str:
        return self.key.keySequence().toString(QKeySequence.SequenceFormat.PortableText)

    def accept(self):
        key = self.value()
        if key:
            from . import shortcuts
            clash = shortcuts.conflict(key, self.remote_name, self.button_name)
            if clash and QMessageBox.question(
                    self, "Shortcut in use",
                    f"{key} is already used by {clash}.\nUse it for this button anyway?"
            ) != QMessageBox.StandardButton.Yes:
                return
        super().accept()


# --- Main window ---------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(core.APP_NAME)
        self.setWindowIcon(icon(core.APP_ID, QStyle.StandardPixmap.SP_ComputerIcon))
        self.settings = QSettings(core.APP_ID, core.APP_ID)
        self.workers: set[Worker] = set()
        self.app_shortcuts: list[QShortcut] = []
        self.busy = False
        self.quitting = False
        self.columns = 4
        self.view = "grid" if self.settings.value("view", "picture") == "grid" else "picture"

        try:
            self.data = core.load()
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, core.APP_NAME,
                                f"Couldn't read {core.config_path()}:\n{e}\n\nStarting fresh; "
                                "the old file is left untouched until you change something.")
            self.data = core.default_data()

        self._build_ui()
        self._build_menus()
        self._build_tray()
        self.refresh_remotes()
        idx = int(self.settings.value("remote", 0) or 0)
        self.remote_list.setCurrentRow(min(idx, self.remote_list.count() - 1))
        self.resize(self.settings.value("size", QSize(940, 560)))

        self.status_timer = QTimer(self, interval=3000)
        self.status_timer.timeout.connect(self.update_device_status)
        self.status_timer.start()
        self.update_device_status()

    # UI construction
    def _build_ui(self):
        split = QSplitter()
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(6, 6, 0, 6)
        lv.addWidget(QLabel("<b>Remotes</b>"))
        self.remote_list = QListWidget()
        self.remote_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.remote_list.model().rowsMoved.connect(self._remotes_reordered)
        self.remote_list.currentRowChanged.connect(lambda _: self.refresh_buttons())
        self.remote_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.remote_list.customContextMenuRequested.connect(self._remote_menu)
        self.remote_list.itemDoubleClicked.connect(lambda _: self.rename_remote())
        lv.addWidget(self.remote_list)
        add = QPushButton(icon("list-add"), "Add remote")
        add.clicked.connect(self.add_remote)
        lv.addWidget(add)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        head = QHBoxLayout()
        self.remote_title = QLabel()
        head.addWidget(self.remote_title, 1)
        self.learn_all_btn = QPushButton(icon("media-record"), "Learn all…")
        self.learn_all_btn.setToolTip("Go through every button on the picture, one by one")
        self.learn_all_btn.clicked.connect(self.learn_all)
        head.addWidget(self.learn_all_btn, 0, Qt.AlignmentFlag.AlignBottom)
        self.view_btns = {}
        for mode, text, ic in (("picture", "Picture", "view-preview"),
                               ("grid", "Grid", "view-grid")):
            b = QToolButton(text=text, checkable=True, autoRaise=True)
            b.setIcon(icon(ic))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.clicked.connect(lambda _=False, m=mode: self.set_view(m))
            head.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
            self.view_btns[mode] = b
        rv.addLayout(head)
        self.stack = QStackedWidget()
        rv.addWidget(self.stack, 1)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(10)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll = self.scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.grid_host)
        self.stack.addWidget(scroll)

        pic = QWidget()
        ph = QHBoxLayout(pic)
        ph.setContentsMargins(0, 0, 0, 0)
        self.canvas = visual.RemoteCanvas(pic, mode="use")
        self.canvas.pressed.connect(self.press_name)
        self.canvas.menu_requested.connect(self._spot_menu)
        ph.addWidget(self.canvas, 1)
        self.extras = QWidget()
        self.extras.setMaximumWidth(190)
        self.extras_lay = QVBoxLayout(self.extras)
        self.extras_lay.setContentsMargins(0, 0, 0, 0)
        ph.addWidget(self.extras)
        self.stack.addWidget(pic)

        self.tip = tip = QLabel()
        tip.setWordWrap(True)
        tip.setEnabled(False)
        rv.addWidget(tip)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([200, 660])
        self.setCentralWidget(split)

        self.device_label = QLabel()
        self.statusBar().addPermanentWidget(self.device_label)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        cols = max(1, (self.scroll.viewport().width() - 10) // (TILE_W + 10))
        if cols != self.columns:
            self.columns = cols
            QTimer.singleShot(0, self.refresh_buttons)

    def _act(self, menu, text, slot, icon_name=None, shortcut=None, tip=None):
        a = QAction(text, self)
        if icon_name:
            a.setIcon(icon(icon_name))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setStatusTip(tip)
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        self._act(m, "&Import…", self.import_json, "document-import", "Ctrl+I")
        self._act(m, "&Export…", self.export_json, "document-export", "Ctrl+E")
        m.addSeparator()
        self._act(m, "&Quit", self.quit, "application-exit", "Ctrl+Q")

        m = mb.addMenu("&Remote")
        self._act(m, "&Add remote…", self.add_remote, "list-add", "Ctrl+Shift+N")
        self._act(m, "&Picture…", self.change_picture, "view-preview",
                  tip="Show this remote as a picture of a real remote, or as a grid")
        self.edit_photo_action = self._act(m, "&Buttons on my picture…", self.edit_photo,
                                           "document-edit")
        self.learn_all_action = self._act(m, "&Learn all buttons…", self.learn_all,
                                          "media-record", "Ctrl+Shift+L")
        m.addSeparator()
        self._act(m, "&Rename remote…", self.rename_remote, "edit-rename", "F2")
        self._act(m, "&Delete remote…", self.delete_remote, "edit-delete")

        m = mb.addMenu("&Button")
        self._act(m, "&Learn new button…", lambda: self.learn(None), "media-record", "Ctrl+L")
        self._act(m, "Add by &code…", self.add_by_code, "list-add", "Ctrl+N")

        m = mb.addMenu("&Dongle")
        self._act(m, "&Check dongle", self.check_dongle, "dialog-information")
        self._act(m, "&Reset dongle", self.reset_dongle, "view-refresh",
                  tip="USB-reset the dongle if it stops answering")

        m = mb.addMenu("&View")
        group = QActionGroup(self)
        self.view_actions = {}
        for mode, text, key in (("picture", "&Picture", "Ctrl+1"), ("grid", "&Grid", "Ctrl+2")):
            a = QAction(text, self, checkable=True)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(lambda _=False, md=mode: self.set_view(md))
            group.addAction(a)
            m.addAction(a)
            self.view_actions[mode] = a
        m.addSeparator()
        self.tray_action = QAction("Show icon in system &tray", self, checkable=True)
        self.tray_action.setChecked(self.settings.value("tray", False, type=bool))
        self.tray_action.toggled.connect(self._toggle_tray)
        m.addAction(self.tray_action)
        self._act(m, "&Shortcuts…", self.show_shortcuts, "configure-shortcuts")

        m = mb.addMenu("&Help")
        self._act(m, "&Read me", self.open_readme, "help-contents", "F1")
        self._act(m, "&About IR Remote", self.about, "help-about")

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_action.setEnabled(False)
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(core.APP_NAME)
        self.tray_menu = QMenu()
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self._rebuild_tray_menu()
        self.tray.setVisible(self.tray_action.isChecked())

    def _rebuild_tray_menu(self):
        if not self.tray:
            return
        self.tray_menu.clear()
        for r in self.data["remotes"]:
            sub = self.tray_menu.addMenu(r["name"])
            for b in r["buttons"]:
                if b["code"]:
                    a = sub.addAction(b["name"])
                    a.triggered.connect(lambda _=False, b=b, r=r: self.send(r, b))
        self.tray_menu.addSeparator()
        self.tray_menu.addAction("Show window", self.show_window)
        self.tray_menu.addAction("Quit", self.quit)

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.hide() if self.isVisible() else self.show_window()

    def _toggle_tray(self, on):
        self.settings.setValue("tray", on)
        if self.tray:
            self.tray.setVisible(on)

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # Data helpers
    def current_remote(self) -> dict | None:
        i = self.remote_list.currentRow()
        if 0 <= i < len(self.data["remotes"]):
            return self.data["remotes"][i]
        return None

    def save(self):
        try:
            core.save(self.data)
        except OSError as e:
            QMessageBox.critical(self, core.APP_NAME, f"Couldn't save:\n{e}")
        self._rebuild_tray_menu()
        self._rebuild_app_shortcuts()

    def refresh_remotes(self):
        row = self.remote_list.currentRow()
        self.remote_list.blockSignals(True)
        self.remote_list.clear()
        for r in self.data["remotes"]:
            item = QListWidgetItem(icon("input-tablet", QStyle.StandardPixmap.SP_DriveNetIcon),
                                   r["name"])
            self.remote_list.addItem(item)
        self.remote_list.blockSignals(False)
        if self.data["remotes"]:
            self.remote_list.setCurrentRow(max(0, min(row, len(self.data["remotes"]) - 1)))
        self.refresh_buttons()
        self._rebuild_app_shortcuts()

    def current_layout(self) -> dict | None:
        r = self.current_remote()
        return layouts.resolve(r) if r else None

    def set_view(self, mode: str):
        self.view = mode
        self.settings.setValue("view", mode)
        self.refresh_buttons()

    def refresh_buttons(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.hide()
                w.deleteLater()
        r = self.current_remote()
        lay = layouts.resolve(r) if r else None
        picture = lay is not None and self.view == "picture"
        for mode, b in self.view_btns.items():
            b.setVisible(lay is not None)
            b.setChecked(mode == ("picture" if picture else "grid"))
        for mode, a in self.view_actions.items():
            a.setEnabled(lay is not None)
            a.setChecked(mode == ("picture" if picture else "grid"))
        self.learn_all_btn.setVisible(lay is not None)
        self.learn_all_action.setEnabled(lay is not None)
        self.edit_photo_action.setEnabled(bool(r) and isinstance(r.get("layout"), dict))
        self.stack.setCurrentIndex(1 if picture else 0)
        if r is None:
            self.remote_title.setText("<h2>No remotes yet</h2>Click <b>Add remote</b> to start.")
            self.canvas.set_layout(None)
            self.tip.setText("")
            return
        if lay is not None:
            names = layouts.button_names(lay)
            learned = sum(1 for n in names if (core.find_button(r, n) or {}).get("code"))
            self.remote_title.setText(
                f"<h2>{_esc(r['name'])}</h2>{learned} of {len(names)} buttons learned"
                f" &nbsp;·&nbsp; <span style='opacity:.7'>{_esc(lay['name'])}</span>")
        else:
            learned = sum(1 for b in r["buttons"] if b["code"])
            self.remote_title.setText(
                f"<h2>{_esc(r['name'])}</h2>{learned} of {len(r['buttons'])} buttons learned")
        if picture:
            self.tip.setText("Click a button to send it. Dim, dashed buttons aren't learned yet "
                             "- click one to learn it, or use <b>Learn all</b>. "
                             "Right-click for learn again, shortcut and clear.")
            key = (id(r), lay.get("id"), lay.get("image"), len(lay["buttons"]))
            if self.canvas.layout_ is None or key != getattr(self, "_canvas_key", None):
                self._canvas_key = key
                self.canvas.set_layout(lay, r)      # (re)reads a photo only when it changes
            else:
                self.canvas.set_remote(r)
            self._fill_extras(r, lay)
            return
        self.tip.setText("Click a button to send it. Right-click for learn, edit, shortcut, "
                         "move and delete. Grey buttons aren't learned yet - click to learn."
                         + ("" if lay else " Want a picture of your remote instead? "
                            "Remote → Picture…"))
        for i, b in enumerate(r["buttons"]):
            self.grid.addWidget(self._tile(r, b, i), i // self.columns, i % self.columns)
        n = len(r["buttons"])
        add = QToolButton()
        add.setText("＋\nLearn new button")
        add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        add.setFixedSize(TILE_W, TILE_H)
        add.setAutoRaise(True)
        add.clicked.connect(lambda: self.learn(None))
        self.grid.addWidget(add, n // self.columns, n % self.columns)

    def _fill_extras(self, r, lay):
        while self.extras_lay.count():
            w = self.extras_lay.takeAt(0).widget()
            if w:
                w.hide()
                w.deleteLater()
        extra = layouts.extra_buttons(lay, r)
        self.extras.setVisible(bool(extra))
        if not extra:
            return
        head = QLabel("<b>Other buttons</b>")
        head.setToolTip("Saved buttons that have no place on this picture")
        self.extras_lay.addWidget(head)
        for b in extra:
            t = self._tile(r, b, r["buttons"].index(b))
            t.setFixedSize(170, 44)
            t.setText(b["name"] + ("" if b["code"] else "  (not learned)"))
            self.extras_lay.addWidget(t)
        self.extras_lay.addStretch(1)

    def _tile(self, r, b, index) -> QToolButton:
        t = QToolButton()
        t.setFixedSize(TILE_W, TILE_H)
        lines = [b["name"]]
        if b["shortcut"] or b["app_shortcut"]:
            lines.append(b["shortcut"] or b["app_shortcut"])
        if not b["code"]:
            lines.append("(not learned)")
        t.setText("\n".join(lines))
        f = t.font()
        f.setPointSizeF(f.pointSizeF() * 1.1)
        t.setFont(f)
        tip = [f"<b>{_esc(b['name'])}</b>"]
        if b["code"]:
            tip.append(f"{'NEC' if b['type'] == core.TYPE_NEC else 'Learned'} code, "
                       f"{b['frequency']} Hz")
            tip.append("Click to send")
        else:
            tip.append("Not learned yet - click to learn it")
        if b["shortcut"]:
            tip.append(f"Global shortcut: {b['shortcut']}")
        if b["app_shortcut"]:
            tip.append(f"In-app key: {b['app_shortcut']}")
        t.setToolTip("<br>".join(tip))
        if not b["code"]:
            pal = t.palette()
            pal.setColor(t.foregroundRole(), pal.color(pal.ColorGroup.Disabled, pal.ColorRole.ButtonText))
            t.setPalette(pal)
        t.clicked.connect(lambda: self.press(r, b))
        t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        t.customContextMenuRequested.connect(lambda pos: self._button_menu(t, r, b, index, pos))
        return t

    def _rebuild_app_shortcuts(self):
        for s in self.app_shortcuts:
            s.setEnabled(False)
            s.deleteLater()
        self.app_shortcuts = []
        for r in self.data["remotes"]:
            for b in r["buttons"]:
                if b["app_shortcut"] and b["code"]:
                    s = QShortcut(QKeySequence(b["app_shortcut"]), self)
                    s.activated.connect(lambda r=r, b=b: self.send(r, b))
                    self.app_shortcuts.append(s)

    # Context menus
    def _remote_menu(self, pos):
        m = QMenu(self)
        m.addAction(icon("list-add"), "Add remote…", self.add_remote)
        if self.current_remote():
            m.addAction(icon("edit-rename"), "Rename…", self.rename_remote)
            m.addAction(icon("edit-delete"), "Delete…", self.delete_remote)
        m.exec(self.remote_list.mapToGlobal(pos))

    def _button_menu(self, tile, r, b, index, pos):
        m = QMenu(self)
        a = m.addAction(icon("media-playback-start"), "Send", lambda: self.send(r, b))
        a.setEnabled(bool(b["code"]))
        m.addAction(icon("media-record"), "Learn again…" if b["code"] else "Learn…",
                    lambda: self.learn(b))
        m.addAction(icon("document-edit"), "Edit… (code, shortcuts)", lambda: self.edit_button(r, b))
        m.addSeparator()
        a = m.addAction(icon("go-previous"), "Move earlier", lambda: self.move_button(r, index, -1))
        a.setEnabled(index > 0)
        a = m.addAction(icon("go-next"), "Move later", lambda: self.move_button(r, index, 1))
        a.setEnabled(index < len(r["buttons"]) - 1)
        m.addSeparator()
        m.addAction(icon("edit-delete"), "Delete", lambda: self.delete_button(r, b))
        m.exec(tile.mapToGlobal(pos))

    def _spot_menu(self, name, gpos):
        r = self.current_remote()
        if r is None:
            return
        b = core.find_button(r, name)
        learned = bool(b and b["code"])
        m = QMenu(self)
        head = m.addAction(name + ("" if learned else "  (not learned)"))
        head.setEnabled(False)
        m.addSeparator()
        a = m.addAction(icon("media-playback-start"), "Send", lambda: self.send(r, b))
        a.setEnabled(learned)
        m.addAction(icon("media-record"), "Learn again…" if learned else "Learn…",
                    lambda: self.learn(b, name=name))
        m.addAction(icon("configure-shortcuts"),
                    "Assign shortcut…" + (f"  ({b['shortcut']})" if b and b["shortcut"] else ""),
                    lambda: self.assign_shortcut(r, name))
        if b:
            m.addAction(icon("document-edit"), "Edit code…", lambda: self.edit_button(r, b))
            m.addSeparator()
            m.addAction(icon("edit-clear"), "Clear", lambda: self.clear_button(r, name))
        m.exec(gpos)

    def press_name(self, name):
        r = self.current_remote()
        if r is None:
            return
        b = core.find_button(r, name)
        if b and b["code"]:
            self.send(r, b)
        else:
            self.learn(b, name=name)

    def assign_shortcut(self, r, name):
        b = core.find_button(r, name)
        dlg = AssignShortcutDialog(self, r["name"], name, b["shortcut"] if b else "")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        key = dlg.value()
        if b is None:
            if not key:
                return
            b = core.new_button(name)
            r["buttons"].append(b)
        if key == b["shortcut"]:
            return
        self._global_shortcut(r["name"], b["name"], key)
        b["shortcut"] = key
        self.save()
        self.refresh_buttons()
        if key and not b["code"]:
            self.statusBar().showMessage(f"{key} is set - learn {name} so it has something "
                                         "to send.", 6000)

    def clear_button(self, r, name):
        b = core.find_button(r, name)
        if b is None:
            return
        extra = " and its shortcut" if b["shortcut"] else ""
        if QMessageBox.question(self, "Clear button",
                                f"Forget the learned code of “{name}”{extra}?"
                                ) != QMessageBox.StandardButton.Yes:
            return
        if b["shortcut"]:
            self._global_shortcut(r["name"], b["name"], "")
        r["buttons"].remove(b)
        self.save()
        self.refresh_buttons()

    def store_learned(self, r, name, code):
        """Save a code captured by Learn all (straight away, so nothing is lost)."""
        b = core.find_button(r, name)
        if b is None:
            b = core.new_button(name)
            r["buttons"].append(b)
        b.update(code=code, type=core.TYPE_LEARNED,
                 frequency=b.get("frequency") or core.DEFAULT_FREQUENCY)
        self.save()

    def learn_all(self, autostart: bool = True):
        r = self.current_remote()
        lay = self.current_layout()
        if r is None or lay is None:
            QMessageBox.information(self, core.APP_NAME,
                                    "Learn all needs a remote with a picture. Choose one with "
                                    "Remote → Picture…")
            return
        if self.busy:
            self.statusBar().showMessage("Busy - one moment…", 2000)
            return
        if self.view != "picture":
            self.set_view("picture")
        self.busy = True
        self.status_timer.stop()
        try:
            self.wizard = visual.LearnAllDialog(self, r, lay,
                                                lambda n, c: self.store_learned(r, n, c),
                                                Worker, autostart=autostart)
            self.wizard.exec()
        finally:
            self.wizard = None
            self.busy = False
            self.status_timer.start()
            self.refresh_buttons()
            self.update_device_status()

    # Pictures
    def _photo_layout(self, name: str, existing: dict | None = None) -> dict | None:
        if existing is None:
            start = os.path.expanduser("~/Pictures")
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose a photo of your remote",
                start if os.path.isdir(start) else os.path.expanduser("~"),
                "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)")
            if not path:
                return None
            img = visual.load_image(path)
            if img.isNull():
                QMessageBox.warning(self, core.APP_NAME, "That file isn't a picture IR Remote "
                                                         "can read (try JPEG or PNG).")
                return None
            try:
                rel = layouts.import_photo(path)
            except OSError as e:
                QMessageBox.warning(self, core.APP_NAME, f"Couldn't copy the photo:\n{e}")
                return None
            existing = layouts.new_photo_layout(rel, img.width(), img.height(), name)
        dlg = visual.PhotoLayoutDialog(self, existing)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return dlg.result_layout()

    def _apply_choice(self, r, choice) -> bool:
        if choice == visual.KEEP_CHOICE:
            return True
        if choice == visual.PHOTO_CHOICE:
            lay = self._photo_layout(r["name"])
            if lay is None:
                return False
            r["layout"] = lay
        elif choice:
            r["layout"] = choice
        else:
            r.pop("layout", None)
        return True

    def change_picture(self):
        r = self.current_remote()
        if r is None:
            return
        dlg = visual.LayoutDialog(self, r["name"], r.get("layout"), ask_name=False)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if self._apply_choice(r, dlg.choice()):
            if r.get("layout"):
                self.view = "picture"
                self.settings.setValue("view", "picture")
            self.save()
            self.refresh_buttons()

    def edit_photo(self):
        r = self.current_remote()
        if r is None or not isinstance(r.get("layout"), dict):
            return
        lay = self._photo_layout(r["name"], layouts.resolve(r) or r["layout"])
        if lay is not None:
            r["layout"] = lay
            self.save()
            self.canvas.set_layout(None)
            self.refresh_buttons()

    # Actions: remotes
    def add_remote(self):
        dlg = visual.LayoutDialog(self, taken={r["name"] for r in self.data["remotes"]})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        r = {"name": dlg.name.text().strip(), "buttons": []}
        if not self._apply_choice(r, dlg.choice()):
            return
        self.data["remotes"].append(r)
        if r.get("layout"):
            self.view = "picture"
            self.settings.setValue("view", "picture")
        self.save()
        self.refresh_remotes()
        self.remote_list.setCurrentRow(len(self.data["remotes"]) - 1)

    def rename_remote(self):
        r = self.current_remote()
        if not r:
            return
        name, ok = QInputDialog.getText(self, "Rename remote", "New name:", text=r["name"])
        name = name.strip()
        if not ok or not name or name == r["name"]:
            return
        other = core.find_remote(self.data, name)
        if other is not None and other is not r:
            QMessageBox.information(self, core.APP_NAME, f"There's already a remote called {name}.")
            return
        old = r["name"]
        r["name"] = name
        for b in r["buttons"]:
            if b["shortcut"]:
                self._move_global_shortcut(old, b["name"], name, b["name"], b["shortcut"])
        self.save()
        self.refresh_remotes()

    def delete_remote(self):
        r = self.current_remote()
        if not r:
            return
        if QMessageBox.question(self, "Delete remote",
                                f"Delete “{r['name']}” and its {len(r['buttons'])} buttons?"
                                ) != QMessageBox.StandardButton.Yes:
            return
        for b in r["buttons"]:
            if b["shortcut"]:
                self._global_shortcut(r["name"], b["name"], "")
        self.data["remotes"].remove(r)
        self.save()
        self.refresh_remotes()

    def _remotes_reordered(self, *_):
        names = [self.remote_list.item(i).text() for i in range(self.remote_list.count())]
        by_name = {r["name"]: r for r in self.data["remotes"]}
        self.data["remotes"] = [by_name[n] for n in names if n in by_name]
        self.save()
        QTimer.singleShot(0, self.refresh_buttons)

    # Actions: buttons
    def press(self, r, b):
        if b["code"]:
            self.send(r, b)
        else:
            self.learn(b)

    def send(self, r, b):
        if self.busy:
            self.statusBar().showMessage("Busy - one moment…", 2000)
            return
        self.busy = True
        self.statusBar().showMessage(f"Sending {b['name']}…")
        button = copy.deepcopy(b)
        self._run(lambda: core.transmit_button(button),
                  lambda res: self._sent(r, b, res))

    def _sent(self, r, b, res):
        self.busy = False
        if res.ok:
            self.statusBar().showMessage(f"✔ Sent {r['name']} / {b['name']}", 4000)
        else:
            self.statusBar().showMessage(f"✖ {b['name']}: {res.message}", 12000)
        self.update_device_status()

    def learn(self, b, name: str = ""):
        r = self.current_remote()
        if r is None:
            self.add_remote()
            r = self.current_remote()
            if r is None:
                return
        if self.busy:
            self.statusBar().showMessage("Busy - one moment…", 2000)
            return
        self.busy = True
        self.status_timer.stop()
        try:
            dlg = LearnDialog(self, r["name"], b, fixed_name=name)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            name = dlg.button_name()
            target = b
            if target is None:
                target = core.find_button(r, name)
                if target is not None and QMessageBox.question(
                        self, "Replace button?",
                        f"“{name}” already exists. Replace its code?"
                ) != QMessageBox.StandardButton.Yes:
                    return
            if target is None:
                target = core.new_button(name)
                r["buttons"].append(target)
            elif target["name"] != name:
                if target["shortcut"]:
                    self._move_global_shortcut(r["name"], target["name"], r["name"], name,
                                               target["shortcut"])
                target["name"] = name
            target.update(code=dlg.code, type=core.TYPE_LEARNED,
                          frequency=target.get("frequency") or core.DEFAULT_FREQUENCY)
            self.save()
            self.refresh_buttons()
            self.statusBar().showMessage(f"✔ Saved {r['name']} / {name}", 5000)
            if self.view == "picture":
                self.canvas.flash_button(name)
        finally:
            self.busy = False
            self.status_timer.start()
            self.update_device_status()

    def add_by_code(self):
        r = self.current_remote()
        if r is None:
            return self.add_remote()
        self.edit_button(r, None)

    def edit_button(self, r, b):
        dlg = ButtonDialog(self, r["name"], b or core.new_button(""))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new = dlg.values()
        other = core.find_button(r, new["name"])
        if other is not None and other is not b:
            QMessageBox.information(self, core.APP_NAME,
                                    f"“{r['name']}” already has a button called {new['name']}.")
            return
        old_name = b["name"] if b else new["name"]
        old_key = b["shortcut"] if b else ""
        if old_key and (old_name != new["name"] or not new["shortcut"]):
            self._global_shortcut(r["name"], old_name, "")
        if new["shortcut"] and (new["shortcut"] != old_key or old_name != new["name"]):
            self._global_shortcut(r["name"], new["name"], new["shortcut"])
        if b is None:
            r["buttons"].append(new)
        else:
            b.clear()
            b.update(new)
        self.save()
        self.refresh_buttons()

    def move_button(self, r, index, delta):
        j = index + delta
        if 0 <= j < len(r["buttons"]):
            r["buttons"][index], r["buttons"][j] = r["buttons"][j], r["buttons"][index]
            self.save()
            self.refresh_buttons()

    def delete_button(self, r, b):
        if QMessageBox.question(self, "Delete button", f"Delete “{b['name']}”?"
                                ) != QMessageBox.StandardButton.Yes:
            return
        if b["shortcut"]:
            self._global_shortcut(r["name"], b["name"], "")
        r["buttons"].remove(b)
        self.save()
        self.refresh_buttons()

    def _global_shortcut(self, remote, button, key):
        from . import shortcuts
        try:
            if key:
                shortcuts.register(remote, button, key)
            else:
                shortcuts.unregister(remote, button)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, core.APP_NAME, f"Couldn't update the global shortcut:\n{e}")

    def _move_global_shortcut(self, old_r, old_b, new_r, new_b, key):
        self._global_shortcut(old_r, old_b, "")
        self._global_shortcut(new_r, new_b, key)

    # Actions: file / dongle / misc
    def import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import remotes", os.path.expanduser("~"),
                                              "IR Remote files (*.json);;All files (*)")
        if not path:
            return
        try:
            new = core.import_json(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, core.APP_NAME, f"Couldn't import that file:\n{e}")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Import remotes")
        box.setText(f"The file has {len(new['remotes'])} remote(s).")
        merge = box.addButton("Add to mine", QMessageBox.ButtonRole.AcceptRole)
        replace = box.addButton("Replace mine", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is merge:
            self.data = core.merge(self.data, new)
        elif box.clickedButton() is replace:
            self.data = new
        else:
            return
        self.save()
        self.refresh_remotes()
        self.statusBar().showMessage("Imported. Global shortcuts in imported files are "
                                     "not activated - set them with Edit…", 8000)

    def export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export remotes",
                                              os.path.expanduser("~/ir-remotes.json"),
                                              "IR Remote files (*.json)")
        if not path:
            return
        try:
            core.export_json(self.data, path)
            self.statusBar().showMessage(f"Exported to {path}", 5000)
        except OSError as e:
            QMessageBox.warning(self, core.APP_NAME, f"Couldn't export:\n{e}")

    def check_dongle(self):
        self.statusBar().showMessage("Checking the dongle…")
        self._run(core.check_dongle, self._dongle_result)

    def reset_dongle(self):
        if self.busy:
            return
        self.busy = True
        self.statusBar().showMessage("Resetting the dongle (takes a few seconds)…")
        self._run(core.reset_dongle, self._dongle_result)

    def _dongle_result(self, res):
        self.busy = False
        self.statusBar().showMessage(("✔ " if res.ok else "✖ ") + res.message, 8000)
        self.update_device_status()

    def update_device_status(self):
        st = core.dongle_status()
        dot = {"ready": "#27ae60", "no-permission": "#f67400", "not-found": "#da4453"}[st.state]
        text = {"ready": "Dongle ready", "no-permission": "No permission",
                "not-found": "Dongle not found"}[st.state]
        self.device_label.setText(f"<span style='color:{dot}'>●</span> {text}")
        self.device_label.setToolTip(st.message + (f"\n{st.node}" if st.node else ""))

    def show_shortcuts(self):
        ShortcutsDialog(self, self.data).exec()

    def open_readme(self):
        if os.path.exists(README):
            QDesktopServices.openUrl(QUrl.fromLocalFile(README))
        else:
            QMessageBox.information(self, core.APP_NAME, f"README not found at {README}")

    def about(self):
        QMessageBox.about(self, "About IR Remote",
                          f"<h3>IR Remote {__version__}</h3>"
                          "<p>Use a USB infrared blaster (ELK Smart / OCRUSTAR) as a "
                          "remote control.</p>"
                          "<p>The dongle is driven by <b>elksmart-comm</b> by Přemysl Eric "
                          "Janouch (<a href='https://git.janouch.name/p/usb-drivers'>"
                          "usb-drivers</a>).</p>"
                          f"<p>Remotes are stored in <tt>{_esc(core.config_path())}</tt>.</p>")

    def _run(self, fn, on_done):
        w = Worker(fn, self)
        self.workers.add(w)
        w.done.connect(on_done)
        w.finished.connect(lambda: self.workers.discard(w))
        w.start()

    def quit(self):
        self.quitting = True
        self.close()

    def closeEvent(self, ev):
        if self.tray and self.tray.isVisible() and not self.quitting:
            self.hide()
            ev.ignore()
            return
        self.settings.setValue("size", self.size())
        self.settings.setValue("remote", self.remote_list.currentRow())
        for w in list(self.workers):
            w.wait(20000)
        ev.accept()
        QApplication.quit()


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> int:
    QApplication.setApplicationName(core.APP_ID)
    QApplication.setApplicationDisplayName(core.APP_NAME)
    QApplication.setDesktopFileName(core.APP_ID)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    w = MainWindow()
    if os.environ.get("IRREMOTE_SMOKE"):
        QTimer.singleShot(int(os.environ["IRREMOTE_SMOKE"]), w.quit)
    w.show()
    return app.exec()
