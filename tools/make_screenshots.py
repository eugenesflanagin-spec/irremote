#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Eugene Flanagin
"""Render the README screenshots offscreen (no dongle, no real settings touched).

    QT_QPA_PLATFORM=offscreen python tools/make_screenshots.py [outdir]
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
tmp = tempfile.mkdtemp(prefix="irremote-shots-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(tmp, "data")
os.environ["IRREMOTE_CONFIG"] = os.path.join(tmp, "config", "irremote", "remotes.json")
os.environ["IRREMOTE_COMM"] = "/nonexistent/elksmart-comm"   # never talk to a real dongle

from PyQt6.QtCore import QSize  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from irremote import core, gui  # noqa: E402

FAKE = "80ffffffffffffc71c5f1bda1b03"


def demo_data() -> dict:
    def learned(*names):
        return [dict(core.new_button(n, FAKE), shortcut="Meta+Ctrl+P" if n == "Power" else "")
                for n in names]
    return {"version": core.DATA_VERSION, "remotes": [
        {"name": "TV", "layout": "vizio-onn-tv",
         "buttons": learned("Power", "Volume Up", "Volume Down", "Mute", "Input", "Up", "Down",
                            "Left", "Right", "OK", "Back", "Home", "Netflix")},
        {"name": "Android TV box", "layout": "onn-4k-pro-google-tv",
         "buttons": learned("Power", "Volume Up", "Volume Down", "Mute")},
    ]}


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "screenshots")
    os.makedirs(out, exist_ok=True)
    core.save(demo_data())
    app = QApplication(sys.argv[:1])
    w = gui.MainWindow()
    w.resize(QSize(960, 800))
    w.show()
    shots = [(0, "tv-remote-vizio-onn.png"), (1, "android-tv-box-remote-onn-google-tv.png")]
    for row, name in shots:
        w.remote_list.setCurrentRow(row)
        app.processEvents()
        if row == 0:
            w.canvas.hover = "Netflix"
        w.canvas.repaint()
        app.processEvents()
        w.grab().save(os.path.join(out, name))
        print(os.path.join(out, name))
    # The Learn-all wizard, waiting at its first step (nothing is sent).
    w.remote_list.setCurrentRow(1)
    app.processEvents()
    from irremote import layouts, visual
    r = w.current_remote()
    dlg = visual.LearnAllDialog(w, r, layouts.resolve(r), lambda n, c: None, gui.Worker,
                                autostart=False)
    dlg.resize(820, 640)
    dlg.show()
    app.processEvents()
    dlg._show(2)
    dlg.canvas._pulse = 1.5
    app.processEvents()
    path = os.path.join(out, "learn-all.png")
    dlg.grab().save(path)
    print(path)
    dlg.reject()
    w.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
