# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Eugene Flanagin
"""Command line for IR Remote (also the entry point that starts the GUI)."""

from __future__ import annotations

import argparse
import sys

from . import __version__, core

EPILOG = """\
examples:
  irremote                              open the window
  irremote send "TV" "Power"            press a saved button (good for KDE shortcuts)
  irremote send-code --nec 20df         send a raw NEC code (address 20, command df)
  irremote learn                        capture one button and print its code
  irremote list                         show remotes and buttons
  irremote layouts                      list the remote pictures (layouts)
  irremote layout TV vizio-onn-tv       show TV as a picture of that remote
  irremote shortcut set TV Power Meta+Ctrl+P
  irremote status | reset               check / un-stick the dongle
"""


def _p(*a, **kw):
    print(*a, **kw, flush=True)


def _fail(msg: str, notify: bool, title: str = "IR Remote") -> int:
    print(f"irremote: {msg}", file=sys.stderr, flush=True)
    if notify:
        core.notify(title, msg)
    return 1


def cmd_send(a) -> int:
    data = core.load()
    remote = core.find_remote(data, a.remote)
    if remote is None:
        names = ", ".join(r["name"] for r in data["remotes"]) or "none"
        return _fail(f"no remote called \"{a.remote}\" (have: {names})", a.notify)
    button = core.find_button(remote, a.button)
    if button is None:
        names = ", ".join(b["name"] for b in remote["buttons"]) or "none"
        return _fail(f"\"{remote['name']}\" has no button \"{a.button}\" (have: {names})", a.notify)
    if not button["code"]:
        msg = (f"{remote['name']} {button['name']} isn't learned yet - "
               "open IR Remote and learn it")
        return _fail(msg, a.notify)
    if a.dry_run:
        kind = "NEC" if button["type"] == core.TYPE_NEC else "learned"
        _p(f"Would send {remote['name']} / {button['name']} ({kind} code, "
           f"{len(button['code']) // 2} bytes, {button['frequency']} Hz) "
           f"x{max(1, a.repeat)} - nothing sent")
        return 0
    for _ in range(max(1, a.repeat)):
        res = core.transmit_button(button)
        if not res.ok:
            return _fail(res.message, a.notify, f"{remote['name']} {button['name']}")
    if not a.quiet:
        _p(f"Sent {remote['name']} / {button['name']}")
    return 0


def cmd_send_code(a) -> int:
    res = core.transmit_code(a.code, core.TYPE_NEC if a.nec else core.TYPE_LEARNED, a.frequency)
    if not res.ok:
        return _fail(res.message, False)
    _p("Sent")
    return 0


def cmd_learn(a) -> int:
    _p("Hold the remote within 1 cm of the dongle and press the button...")
    res = core.Learner(timeout=a.timeout).run()
    if not res.ok:
        return _fail(res.message, False)
    _p(res.code)
    if a.save:
        remote_name, button_name = a.save
        data = core.load()
        remote = core.find_remote(data, remote_name)
        if remote is None:
            remote = {"name": remote_name, "buttons": []}
            data["remotes"].append(remote)
        button = core.find_button(remote, button_name)
        if button is None:
            button = core.new_button(button_name)
            remote["buttons"].append(button)
        button.update(code=res.code, type=core.TYPE_LEARNED, frequency=a.frequency)
        core.save(data)
        _p(f"Saved as {remote['name']} / {button['name']}", file=sys.stderr)
    return 0


def cmd_list(a) -> int:
    data = core.load()
    from . import layouts
    for r in data["remotes"]:
        _p(f"{r['name']}  [picture: {layouts.describe(r)}]" if r.get("layout") else r["name"])
        for b in r["buttons"]:
            state = (b["type"] if b["code"] else "not learned")
            extra = f"  [{b['shortcut']}]" if b["shortcut"] else ""
            _p(f"  {b['name']}  ({state}){extra}")
    return 0


def cmd_layouts(a) -> int:
    from . import layouts
    for lay in layouts.all_layouts():
        _p(f"{lay['id']:<24} {lay['name']}  ({len(layouts.hotspots(lay))} buttons)")
        if a.verbose:
            _p(f"    {', '.join(layouts.learn_order(lay))}")
    return 0


def cmd_layout(a) -> int:
    from . import layouts
    data = core.load()
    remote = core.find_remote(data, a.remote)
    if remote is None:
        return _fail(f"no remote called \"{a.remote}\"", False)
    if a.layout is None:
        _p(f"{remote['name']}: {layouts.describe(remote)}")
        return 0
    if a.layout.casefold() in ("none", "grid"):
        if isinstance(remote.get("layout"), dict) and not a.force:
            return _fail("this remote uses your own picture; add --force to drop it", False)
        remote.pop("layout", None)
    else:
        lay = layouts.get(a.layout)
        if lay is None:
            ids = ", ".join(l["id"] for l in layouts.all_layouts())
            return _fail(f"no layout \"{a.layout}\" (have: {ids})", False)
        remote["layout"] = lay["id"]
    core.save(data)
    _p(f"{remote['name']}: {layouts.describe(remote)}")
    return 0


def cmd_status(a) -> int:
    st = core.dongle_status()
    _p(st.message)
    if st.node:
        _p(f"  device node: {st.node}")
    if st.state != "ready":
        return 1
    res = core.check_dongle()
    _p(res.message)
    return 0 if res.ok else 1


def cmd_reset(a) -> int:
    res = core.reset_dongle()
    (_p if res.ok else lambda m: print(m, file=sys.stderr))(res.message)
    return 0 if res.ok else 1


def cmd_export(a) -> int:
    core.export_json(core.load(), a.file)
    _p(f"Exported to {a.file}")
    return 0


def cmd_import(a) -> int:
    try:
        new = core.import_json(a.file)
    except (OSError, ValueError) as e:
        return _fail(f"can't import {a.file}: {e}", False)
    data = core.merge(core.load(), new) if a.merge else new
    core.save(data)
    _p(f"Imported {len(new['remotes'])} remote(s)" + (" (merged)" if a.merge else ""))
    return 0


def cmd_shortcut(a) -> int:
    from . import shortcuts
    data = core.load()
    if a.action == "list":
        for r in data["remotes"]:
            for b in r["buttons"]:
                if b["shortcut"]:
                    _p(f"{b['shortcut']:<16} {r['name']} / {b['name']}")
        return 0
    remote = core.find_remote(data, a.remote)
    if remote is None:
        if a.action != "set":
            return _fail(f"no remote called \"{a.remote}\"", False)
        remote = {"name": a.remote, "buttons": []}
        data["remotes"].append(remote)
    button = core.find_button(remote, a.button)
    if button is None:
        if a.action != "set":
            return _fail(f"no button \"{a.button}\"", False)
        button = core.new_button(a.button)
        remote["buttons"].append(button)
    if a.action == "clear":
        shortcuts.unregister(remote["name"], button["name"])
        button["shortcut"] = ""
        core.save(data)
        _p("Shortcut removed")
        return 0
    if not a.key:
        return _fail("give a key, e.g. Meta+Ctrl+P", False)
    clash = shortcuts.conflict(a.key, remote["name"], button["name"])
    if clash and not a.force:
        return _fail(f"{a.key} is already used by {clash} (use --force to take it anyway)", False)
    shortcuts.register(remote["name"], button["name"], a.key)
    button["shortcut"] = a.key
    core.save(data)
    _p(f"{a.key} now presses {remote['name']} / {button['name']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="irremote", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="IR Remote - use a USB infrared blaster as a TV/soundbar remote.",
        epilog=EPILOG)
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("gui", help="open the window (default)")

    s = sub.add_parser("send", help="press a saved button")
    s.add_argument("remote")
    s.add_argument("button")
    s.add_argument("-r", "--repeat", type=int, default=1, help="send it N times")
    s.add_argument("-q", "--quiet", action="store_true")
    s.add_argument("--dry-run", action="store_true",
                   help="only check that the button exists and is learned; send nothing")
    s.add_argument("--no-notify", dest="notify", action="store_false",
                   help="don't show a desktop notification on problems")
    s.set_defaults(func=cmd_send)

    s = sub.add_parser("send-code", help="send a raw hex code")
    s.add_argument("code")
    s.add_argument("-n", "--nec", action="store_true", help="code is NEC address+command pairs")
    s.add_argument("-f", "--frequency", type=int, default=core.DEFAULT_FREQUENCY)
    s.set_defaults(func=cmd_send_code)

    s = sub.add_parser("learn", help="capture one remote button and print its code")
    s.add_argument("-t", "--timeout", type=float, default=20.0, help="seconds to wait (20)")
    s.add_argument("-f", "--frequency", type=int, default=core.DEFAULT_FREQUENCY)
    s.add_argument("--save", nargs=2, metavar=("REMOTE", "BUTTON"), help="also save it")
    s.set_defaults(func=cmd_learn)

    sub.add_parser("list", help="list remotes and buttons").set_defaults(func=cmd_list)
    s = sub.add_parser("layouts", help="list remote pictures (layouts)")
    s.add_argument("-v", "--verbose", action="store_true", help="also list their buttons")
    s.set_defaults(func=cmd_layouts)
    s = sub.add_parser("layout", help="show or set the picture a remote uses")
    s.add_argument("remote")
    s.add_argument("layout", nargs="?", help="layout id from 'irremote layouts', or none")
    s.add_argument("--force", action="store_true", help="allow dropping your own photo layout")
    s.set_defaults(func=cmd_layout)
    sub.add_parser("status", help="check the dongle").set_defaults(func=cmd_status)
    sub.add_parser("reset", help="un-stick the dongle (USB reset)").set_defaults(func=cmd_reset)

    s = sub.add_parser("export", help="save all remotes to a JSON file")
    s.add_argument("file")
    s.set_defaults(func=cmd_export)
    s = sub.add_parser("import", help="load remotes from a JSON file")
    s.add_argument("file")
    s.add_argument("-m", "--merge", action="store_true", help="add to existing remotes")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("shortcut", help="KDE global shortcuts: set / clear / list")
    s.add_argument("action", choices=["set", "clear", "list"])
    s.add_argument("remote", nargs="?")
    s.add_argument("button", nargs="?")
    s.add_argument("key", nargs="?", help="e.g. Meta+Ctrl+P")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_shortcut)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = build_parser()
    a = p.parse_args(argv)
    if a.command in (None, "gui"):
        from . import gui
        return gui.main()
    if a.command == "shortcut" and a.action != "list" and not (a.remote and a.button):
        p.error("shortcut set/clear needs REMOTE and BUTTON")
    return a.func(a)
