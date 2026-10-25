# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Eugene Flanagin
"""Layouts ("visual remote"): loading, validation, hit-testing, Learn-all order,
and moving 1.0.0 data to the 1.1.0 format. No Qt, no dongle."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from irremote import cli, core, layouts  # noqa: E402

# Exactly what IR Remote 1.0.0 writes (shortened code).
V1_FILE = {
    "version": 1,
    "remotes": [{"name": "TV", "buttons": [{
        "name": "Power", "type": "learned", "code": "1effff54ffff358a24ff75",
        "frequency": 38000, "shortcut": "Meta+Ctrl+P", "app_shortcut": ""}]}],
}


class TempConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = {k: os.environ.get(k) for k in ("IRREMOTE_CONFIG", "XDG_CONFIG_HOME")}
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.tmp.name, "config")
        os.environ["IRREMOTE_CONFIG"] = os.path.join(self.tmp.name, "config", "irremote",
                                                     "remotes.json")

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def write(self, data, path=None):
        path = path or os.environ["IRREMOTE_CONFIG"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = cli.main(list(args))
        return rc, out.getvalue()


class BuiltinLayoutTests(TempConfig):
    def test_builtins_load(self):
        ids = [l["id"] for l in layouts.builtin_layouts()]
        self.assertEqual(ids, ["vizio-onn-tv", "onn-4k-pro-google-tv"])
        for lay in layouts.builtin_layouts():
            names = layouts.button_names(lay)
            self.assertEqual(len(names), len({n.casefold() for n in names}), lay["id"])
            for n in ("Power", "Volume Up", "Volume Down", "Mute", "Up", "Down", "Left",
                      "Right", "OK", "Back", "Home", "Netflix"):
                self.assertIn(n, names, lay["id"])
            # Every button sits inside the canvas.
            for h in layouts.hotspots(lay):
                l, t, r, b = h.bounds()
                self.assertTrue(0 <= l and r <= lay["width"] and 0 <= t and b <= lay["height"],
                                (lay["id"], h.name))

    def test_layout_specific_buttons(self):
        tv = layouts.button_names(layouts.get("vizio-onn-tv"))
        for n in ("Input", "Voice", "WatchFree+", "Menu", "Star", "Prime Video",
                  "iHeartRadio", "Stingray Music", "Disney+", "Paramount+"):
            self.assertIn(n, tv)
        box = layouts.button_names(layouts.get("onn-4k-pro-google-tv"))
        for n in ("Assistant", "Profile", "Settings", "Live TV", "Channel Up",
                  "Channel Down", "YouTube"):
            self.assertIn(n, box)

    def test_user_layout_dir(self):
        d = layouts.user_dir()
        os.makedirs(d)
        with open(os.path.join(d, "fan.json"), "w") as f:
            json.dump({"name": "Fan", "width": 50, "height": 100, "buttons": [
                {"shape": "circle", "name": "Power", "x": 25, "y": 20, "r": 8}]}, f)
        with open(os.path.join(d, "broken.json"), "w") as f:
            f.write("{nope")
        self.assertEqual(layouts.get("fan")["name"], "Fan")
        self.assertIsNone(layouts.get("broken"))


class ValidateTests(unittest.TestCase):
    def base(self, *buttons):
        return {"name": "T", "width": 100, "height": 200, "buttons": list(buttons)}

    def test_ok_and_defaults(self):
        lay = layouts.validate(self.base({"shape": "dpad", "x": 50, "y": 50, "r": 40}))
        self.assertEqual(layouts.button_names(lay), ["Up", "Down", "Left", "Right", "OK"])
        self.assertAlmostEqual(lay["buttons"][0]["inner"], 40 * 0.42)

    def test_errors(self):
        bad = [
            self.base({"shape": "hexagon", "name": "A", "x": 1, "y": 1}),
            self.base({"shape": "circle", "name": "", "x": 1, "y": 1, "r": 2}),
            self.base({"shape": "circle", "name": "A", "x": 1, "y": 1, "r": -2}),
            self.base({"shape": "circle", "name": "A", "x": "1", "y": 1, "r": 2}),
            self.base({"shape": "circle", "name": "Up", "x": 1, "y": 1, "r": 2},
                      {"shape": "dpad", "x": 50, "y": 50, "r": 40}),          # duplicate Up
            self.base({"shape": "dpad", "x": 50, "y": 50, "r": 10, "inner": 12}),
            {"name": "T", "width": 100, "buttons": []},                         # no height
            {"format": "something-else", "width": 1, "height": 1, "buttons": []},
            "not a dict",
        ]
        for b in bad:
            with self.assertRaises(ValueError, msg=repr(b)[:80]):
                layouts.validate(b)


class HitTests(unittest.TestCase):
    def setUp(self):
        self.lay = layouts.validate({
            "name": "T", "width": 100, "height": 200, "buttons": [
                {"shape": "circle", "name": "Power", "x": 20, "y": 20, "r": 10},
                {"shape": "dpad", "x": 50, "y": 80, "r": 40, "inner": 15},
                {"shape": "rocker", "x": 20, "y": 160, "w": 20, "h": 50},
                {"shape": "pill", "name": "Netflix", "x": 70, "y": 160, "w": 40, "h": 14},
                {"shape": "rect", "name": "Sq", "x": 70, "y": 185, "w": 20, "h": 10, "radius": 4},
            ]})
        self.spots = layouts.hotspots(self.lay)

    def name_at(self, x, y):
        h = layouts.hit(self.spots, x, y)
        return h.name if h else None

    def test_circle(self):
        self.assertEqual(self.name_at(20, 20), "Power")
        self.assertEqual(self.name_at(29.9, 20), "Power")
        self.assertIsNone(self.name_at(28, 28))        # inside the box, outside the circle

    def test_ring_segments(self):
        cx, cy = 50, 80
        self.assertEqual(self.name_at(cx, cy), "OK")
        self.assertEqual(self.name_at(cx + 14, cy), "OK")
        self.assertEqual(self.name_at(cx, cy - 25), "Up")
        self.assertEqual(self.name_at(cx, cy + 25), "Down")
        self.assertEqual(self.name_at(cx - 25, cy), "Left")
        self.assertEqual(self.name_at(cx + 25, cy), "Right")
        # Near the diagonals the nearer axis wins.
        self.assertEqual(self.name_at(cx + 20, cy - 17), "Right")
        self.assertEqual(self.name_at(cx + 17, cy - 20), "Up")
        self.assertEqual(self.name_at(cx - 17, cy + 20), "Down")
        self.assertEqual(self.name_at(cx - 20, cy + 17), "Left")
        # Outside the ring, and the ring's square corners, are misses.
        self.assertIsNone(self.name_at(cx, cy - 41))
        self.assertIsNone(self.name_at(cx + 35, cy + 35))

    def test_direction_helper(self):
        self.assertEqual(layouts.direction(1, 0), "right")
        self.assertEqual(layouts.direction(0, 1), "down")       # screen y grows downwards
        self.assertEqual(layouts.direction(0, -1), "up")
        self.assertEqual(layouts.direction(-1, 0), "left")

    def test_rocker(self):
        self.assertEqual(self.name_at(20, 145), "Volume Up")
        self.assertEqual(self.name_at(20, 175), "Volume Down")
        self.assertIsNone(self.name_at(20, 186))              # rounded end of the pill
        self.assertIsNone(self.name_at(31, 160))

    def test_pill_and_rounded_rect(self):
        self.assertEqual(self.name_at(70, 160), "Netflix")
        self.assertEqual(self.name_at(89, 160), "Netflix")
        self.assertIsNone(self.name_at(89.8, 153.2))          # rounded corner
        self.assertEqual(self.name_at(62, 182), "Sq")
        self.assertIsNone(self.name_at(60.2, 180.2))          # corner radius 4

    def test_builtin_spot_centres_hit_themselves(self):
        for lay in layouts.builtin_layouts():
            spots = layouts.hotspots(lay)
            for h in spots:
                self.assertEqual(layouts.hit(spots, *h.centre()).name, h.name,
                                 (lay["id"], h.name))


class WizardTests(unittest.TestCase):
    def test_order_learn_first(self):
        lay = layouts.get("vizio-onn-tv")
        order = layouts.learn_order(lay)
        self.assertEqual(order[:5], ["Power", "Volume Up", "Volume Down", "Mute", "Input"])
        self.assertEqual(sorted(order), sorted(layouts.button_names(lay)))
        # The rest keeps the top-to-bottom order of the picture.
        rest = order[5:]
        self.assertLess(rest.index("Up"), rest.index("OK"))
        self.assertLess(rest.index("OK"), rest.index("Back"))
        self.assertLess(rest.index("Back"), rest.index("Netflix"))

    def test_skip_learned(self):
        lay = layouts.get("vizio-onn-tv")
        remote = core.normalize(V1_FILE)["remotes"][0]
        all_steps = layouts.wizard_steps(lay, remote, skip_learned=False)
        todo = layouts.wizard_steps(lay, remote, skip_learned=True)
        self.assertEqual(all_steps[0], "Power")
        self.assertNotIn("Power", todo)
        self.assertEqual(len(todo), len(all_steps) - 1)
        self.assertEqual(todo[0], "Volume Up")

    def test_extra_buttons(self):
        lay = layouts.get("vizio-onn-tv")
        remote = {"name": "TV", "buttons": [core.new_button("power", "aa"),
                                             core.new_button("Sleep", "bb")]}
        self.assertEqual([b["name"] for b in layouts.extra_buttons(lay, remote)], ["Sleep"])


class MigrationTests(TempConfig):
    def test_v1_file_loads_unchanged(self):
        self.write(V1_FILE)
        d = core.load()
        self.assertEqual(d["version"], core.DATA_VERSION)
        r = d["remotes"][0]
        self.assertNotIn("layout", r)
        self.assertEqual(r["buttons"][0]["code"], V1_FILE["remotes"][0]["buttons"][0]["code"])
        self.assertEqual(r["buttons"][0]["shortcut"], "Meta+Ctrl+P")
        rc, out = self.cli("send", "--dry-run", "TV", "Power")
        self.assertEqual(rc, 0)
        self.assertIn("Would send TV / Power", out)

    def test_first_save_keeps_v1_backup(self):
        path = self.write(V1_FILE)
        d = core.load()
        d["remotes"][0]["layout"] = "vizio-onn-tv"
        core.save(d)
        with open(path + ".v1-backup") as f:
            self.assertEqual(json.load(f), V1_FILE)
        with open(path) as f:
            saved = json.load(f)
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["remotes"][0]["layout"], "vizio-onn-tv")
        core.save(core.load())                     # later saves don't touch the backup
        with open(path + ".v1-backup") as f:
            self.assertEqual(json.load(f), V1_FILE)

    def test_layout_refs_round_trip(self):
        photo = layouts.new_photo_layout("photos/x.jpg", 400, 800, "Fan")
        photo["buttons"].append({"shape": "circle", "name": "Power", "x": 50, "y": 20, "r": 6})
        d = {"version": 2, "remotes": [
            {"name": "TV", "layout": "vizio-onn-tv", "buttons": []},
            {"name": "Fan", "layout": photo, "buttons": []},
            {"name": "Odd", "layout": {"buttons": "garbage"}, "buttons": []},
            {"name": "Grid", "layout": "", "buttons": []},
        ]}
        core.save(d)
        back = core.load()["remotes"]
        self.assertEqual(back[0]["layout"], "vizio-onn-tv")
        self.assertEqual(layouts.button_names(layouts.resolve(back[1])), ["Power"])
        self.assertEqual(back[1]["layout"]["height"], 200)
        self.assertEqual(back[2]["layout"], {"buttons": "garbage"})   # kept, not lost
        self.assertIsNone(layouts.resolve(back[2]))                    # shown as grid
        self.assertNotIn("layout", back[3])

    def test_merge_brings_layout(self):
        base = core.normalize(V1_FILE)
        extra = core.normalize({"remotes": [{"name": "tv", "layout": "vizio-onn-tv",
                                             "buttons": []}]})
        m = core.merge(base, extra)
        self.assertEqual(m["remotes"][0]["layout"], "vizio-onn-tv")
        self.assertEqual(m["remotes"][0]["buttons"][0]["shortcut"], "Meta+Ctrl+P")

    def test_cli_layout_commands(self):
        self.write(V1_FILE)
        rc, out = self.cli("layouts")
        self.assertEqual(rc, 0)
        self.assertIn("vizio-onn-tv", out)
        self.assertIn("onn-4k-pro-google-tv", out)
        self.assertEqual(self.cli("layout", "TV", "nope")[0], 1)
        rc, out = self.cli("layout", "TV", "vizio-onn-tv")
        self.assertEqual(rc, 0)
        self.assertEqual(core.load()["remotes"][0]["layout"], "vizio-onn-tv")
        rc, out = self.cli("list")
        self.assertIn("picture: TV remote - VIZIO", out)
        self.assertIn("Power  (learned)  [Meta+Ctrl+P]", out)
        self.assertEqual(self.cli("send", "--dry-run", "tv", "power")[0], 0)
        self.cli("layout", "TV", "none")
        self.assertNotIn("layout", core.load()["remotes"][0])

    def test_import_photo(self):
        src = os.path.join(self.tmp.name, "My Remote.JPG")
        with open(src, "wb") as f:
            f.write(b"\xff\xd8not really a jpeg")
        rel = layouts.import_photo(src)
        self.assertTrue(rel.startswith("photos/my-remote-") and rel.endswith(".jpg"), rel)
        self.assertEqual(layouts.import_photo(src), rel)
        lay = layouts.new_photo_layout(rel, 10, 20)
        self.assertTrue(os.path.exists(layouts.image_path(lay)))
        self.assertTrue(layouts.image_path(lay).startswith(core.config_dir()))


if __name__ == "__main__":
    unittest.main()
