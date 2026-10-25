# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Eugene Flanagin
"""Offscreen GUI smoke tests for the picture view and Learn all (no dongle is used)."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
_TMP = tempfile.TemporaryDirectory()
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP.name, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_TMP.name, "data")
os.environ["IRREMOTE_COMM"] = "/nonexistent/elksmart-comm"

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    QApplication = None

from irremote import core, layouts  # noqa: E402

CODE = "80ffffffffffffc71c5f1bda1b03"


@unittest.skipIf(QApplication is None, "PyQt6 not available")
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from irremote import gui, visual
        cls.gui, cls.visual = gui, visual

    def setUp(self):
        os.environ["IRREMOTE_CONFIG"] = os.path.join(_TMP.name, f"{self.id()}.json")
        tv = {"name": "TV", "layout": "vizio-onn-tv",
              "buttons": [dict(core.new_button("Power", CODE), shortcut="Meta+Ctrl+P"),
                          core.new_button("Sleep", CODE)]}
        box = {"name": "Box", "layout": "onn-4k-pro-google-tv", "buttons": []}
        core.save({"version": 2, "remotes": [tv, box]})
        self.w = self.gui.MainWindow()
        self.w.set_view("picture")
        self.w.resize(900, 760)
        self.w.show()
        self.w.remote_list.setCurrentRow(0)
        QTest.qWait(30)

    def tearDown(self):
        self.w.quitting = True
        self.w.hide()
        self.w.deleteLater()
        QTest.qWait(10)

    def test_picture_is_default_with_extras(self):
        self.assertEqual(self.w.stack.currentIndex(), 1)
        self.assertTrue(self.w.learn_all_btn.isVisible())
        self.assertIn("1 of 22 buttons learned", self.w.remote_title.text())
        self.assertFalse(self.w.extras.isHidden())          # "Sleep" has no place on the picture

    def test_pixel_hit_testing_every_button(self):
        for row in (0, 1):
            self.w.remote_list.setCurrentRow(row)
            QTest.qWait(10)
            c = self.w.canvas
            for name in layouts.button_names(c.layout_):
                h = c.spot_at(c.spot_centre(name).toPointF())
                self.assertIsNotNone(h, name)
                self.assertEqual(h.name, name)

    def test_click_learned_sends_and_unlearned_learns(self):
        sent, learn = [], []
        orig = core.transmit_button
        core.transmit_button = lambda b: (sent.append(b["name"]), core.Result(True, "Sent"))[1]
        self.w.learn = lambda b, name="": learn.append(name)
        try:
            c = self.w.canvas
            QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=c.spot_centre("Power"))
            for _ in range(100):
                if not self.w.busy:
                    break
                QTest.qWait(10)
            QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=c.spot_centre("Volume Up"))
            QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=c.spot_centre("Left"))
        finally:
            core.transmit_button = orig
        self.assertEqual(sent, ["Power"])
        self.assertEqual(learn, ["Volume Up", "Left"])
        self.assertIn("Sent TV / Power", self.w.statusBar().currentMessage())

    def test_view_toggle(self):
        self.w.set_view("grid")
        self.assertEqual(self.w.stack.currentIndex(), 0)
        self.assertEqual(self.w.settings.value("view"), "grid")
        self.w.set_view("picture")
        self.assertEqual(self.w.stack.currentIndex(), 1)

    def test_learn_all_wizard(self):
        r = self.w.current_remote()
        saved = []
        dlg = self.visual.LearnAllDialog(
            self.w, r, layouts.resolve(r),
            lambda n, c: (saved.append(n), self.w.store_learned(r, n, c)), self.gui.Worker,
            autostart=False)
        dlg.show()
        QTest.qWait(20)
        self.assertEqual(len(dlg.steps), 21)                 # Power is learned already
        self.assertIn("Button <b>1</b> of 21", dlg.counter.text())
        self.assertEqual(dlg.canvas.highlight, "Volume Up")
        self.assertIn("VOLUME UP", dlg.prompt.text())
        dlg.auto_next.setChecked(False)
        dlg._learned(core.Result(True, "Got it!", code=CODE))
        self.assertEqual(saved, ["Volume Up"])
        self.assertTrue(core.find_button(r, "Volume Up")["code"])
        self.assertTrue(dlg.next_btn.isVisible())
        dlg.next_btn.click()
        self.assertEqual(dlg.canvas.highlight, "Volume Down")
        dlg._learned(core.Result(False, "Nothing was received."))
        self.assertIn("Skip", dlg.status.text())
        dlg.skip_btn.click()
        self.assertEqual(dlg.current_name(), "Mute")
        dlg.back_btn.click()
        dlg.back_btn.click()
        self.assertEqual(dlg.current_name(), "Volume Up")
        self.assertIn("Already learned", dlg.status.text())  # Back offers Test, no re-listen
        dlg.skip_learned.setChecked(False)
        self.assertEqual(len(dlg.steps), 22)
        self.assertEqual(dlg.current_name(), "Volume Up")
        dlg._go(len(dlg.steps))
        self.assertEqual(dlg.prompt.text(), "All done!")
        dlg.reject()
        self.assertEqual(core.load()["remotes"][0]["buttons"][-1]["name"], "Volume Up")

    def test_photo_editor(self):
        img = QImage(200, 400, QImage.Format.Format_RGB32)
        img.fill(Qt.GlobalColor.darkGray)
        src = os.path.join(_TMP.name, "remote.png")
        img.save(src)
        lay = layouts.new_photo_layout(layouts.import_photo(src), 200, 400, "Fan")
        dlg = self.visual.PhotoLayoutDialog(self.w, lay)
        dlg.show()
        QTest.qWait(10)
        dlg.canvas.add_shape("circle", "Power")
        dlg.canvas.add_shape("rect", "Speed")
        c = dlg.canvas
        # Drag "Speed" somewhere else, then resize it with its corner handle.
        start = c.spot_centre("Speed")
        QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(c, start + type(start)(0, 60))
        QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=start + type(start)(0, 60))
        b = dlg.layout_["buttons"][1]
        self.assertGreater(b["y"], lay["height"] / 2 + 5)
        c.select(0)
        c.delete_selected()
        self.assertEqual([x["name"] for x in dlg.layout_["buttons"]], ["Speed"])
        dlg.accept()
        out = dlg.result_layout()
        self.assertEqual(layouts.button_names(out), ["Speed"])
        self.assertTrue(os.path.exists(layouts.image_path(out)))

    def test_screenshots_render(self):
        out = os.path.join(_TMP.name, "shots")
        p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_screenshots.py"),
                            out], capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        self.assertEqual(p.returncode, 0, p.stderr)
        for name in ("tv-remote-vizio-onn.png", "android-tv-box-remote-onn-google-tv.png",
                     "learn-all.png"):
            img = QImage(os.path.join(out, name))
            self.assertFalse(img.isNull(), name)
            self.assertGreater(img.width(), 500)


if __name__ == "__main__":
    unittest.main()
