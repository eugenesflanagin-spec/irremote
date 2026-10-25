# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Eugene Flanagin
"""Offline tests (no dongle needed): python -m unittest discover -s tests"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from irremote import cli, core, shortcuts  # noqa: E402

LEARN_OUT = """Reading remote control codes.
Press a remote control button from less than a centimeter.
The dongle may be unusable until it returns some data.
If the code fails to replay, retry the capture.
0102
Full command:
80ffffffffffffc71c5f1bda1b03
Attempted pulse decode:
20df10ef
"""


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["IRREMOTE_CONFIG"] = os.path.join(self.tmp.name, "remotes.json")

    def tearDown(self):
        os.environ.pop("IRREMOTE_CONFIG", None)
        self.tmp.cleanup()

    def test_default_has_tv_power(self):
        d = core.load()
        self.assertEqual(d["remotes"][0]["name"], "TV")
        self.assertEqual(d["remotes"][0]["buttons"][0]["name"], "Power")
        self.assertEqual(d["remotes"][0]["buttons"][0]["code"], "")

    def test_round_trip(self):
        d = core.default_data()
        d["remotes"].append({"name": "Soundbar", "buttons": [
            core.new_button("Vol+", "20df", core.TYPE_NEC, 36000)]})
        core.save(d)
        out = os.path.join(self.tmp.name, "export.json")
        core.export_json(core.load(), out)
        self.assertEqual(core.import_json(out), core.normalize(d))
        with open(out) as f:
            self.assertEqual(json.load(f)["remotes"][1]["buttons"][0]["frequency"], 36000)

    def test_merge(self):
        a = core.default_data()
        b = {"remotes": [{"name": "tv", "buttons": [core.new_button("Power", "aabb")]},
                         {"name": "Fan", "buttons": []}]}
        m = core.merge(a, core.normalize(b))
        self.assertEqual(len(m["remotes"]), 2)
        self.assertEqual(m["remotes"][0]["buttons"][0]["code"], "aabb")

    def test_bad_import(self):
        p = os.path.join(self.tmp.name, "bad.json")
        with open(p, "w") as f:
            f.write('{"hello": 1}')
        with self.assertRaises(ValueError):
            core.import_json(p)

    def test_validate(self):
        self.assertIsNone(core.validate_code("20 DF", core.TYPE_NEC))
        self.assertIsNotNone(core.validate_code("20df10", core.TYPE_NEC))
        self.assertIsNotNone(core.validate_code("xyz0", core.TYPE_LEARNED))
        self.assertIsNotNone(core.validate_code("abc", core.TYPE_LEARNED))
        self.assertEqual(core.clean_hex("0x20 DF"), "20df")

    def test_parse_learn(self):
        code, hint = core.parse_learn_output(LEARN_OUT)
        self.assertEqual(code, "80ffffffffffffc71c5f1bda1b03")
        self.assertEqual(hint, "20df10ef")
        self.assertEqual(core.parse_learn_output("error stuff\n"), ("", ""))

    def test_friendly_errors(self):
        self.assertIn("not found", core.friendly_error("fatal: no suitable device found"))
        self.assertIn("permission", core.friendly_error(
            "fatal: couldn't open device: Access denied (insufficient permissions)"))
        self.assertIn("Reset dongle", core.friendly_error("error: identify/recv: Operation timed out"))
        self.assertIn("1 cm", core.friendly_error("error: learn/recv: unexpected response"))

    def test_send_unlearned_fails_cleanly(self):
        rc = cli.main(["send", "--no-notify", "TV", "Power"])
        self.assertEqual(rc, 1)
        self.assertEqual(cli.main(["send", "--no-notify", "Nope", "Power"]), 1)

    def test_desktop_names(self):
        self.assertEqual(shortcuts.desktop_name("TV", "Power"), "irremote-tv-power.desktop")
        self.assertEqual(shortcuts.desktop_name("Living room TV", "Vol +"),
                         "irremote-living-room-tv-vol.desktop")
        self.assertEqual(shortcuts._exec_quote('a "b" $c'), '"a \\"b\\" \\$c"')

    def test_key_to_int(self):
        self.assertEqual(shortcuts.key_to_int("Meta+Ctrl+P"), 0x10000000 | 0x04000000 | 0x50)


if __name__ == "__main__":
    unittest.main()
