# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Eugene Flanagin
"""KDE Plasma global shortcuts for IR Remote buttons.

Done the same way System Settings > Shortcuts > "Add Command" does it:
a hidden .desktop file in ~/.local/share/applications plus a "_launch"
action registered with kglobalaccel (which saves it to kglobalshortcutsrc
under [services][<file>.desktop]).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

from . import core

ACTION = "_launch"


def apps_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "applications")


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    return s or "x"


def desktop_name(remote: str, button: str) -> str:
    return f"{core.APP_ID}-{slug(remote)}-{slug(button)}.desktop"


def _exec_quote(arg: str) -> str:
    # Desktop Entry spec: quote, and backslash-escape " ` $ \ inside quotes.
    return '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'


def write_desktop_file(remote: str, button: str) -> str:
    path = os.path.join(apps_dir(), desktop_name(remote, button))
    os.makedirs(apps_dir(), exist_ok=True)
    exe = shutil.which(core.APP_ID) or core.APP_ID
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={core.APP_NAME}: {remote} {button}\n"
        f"Comment=Send the \"{button}\" button of \"{remote}\" through the IR blaster\n"
        f"Exec={exe} send {_exec_quote(remote)} {_exec_quote(button)}\n"
        f"Icon={core.APP_ID}\n"
        "NoDisplay=true\n"
        "StartupNotify=false\n"
        "X-KDE-GlobalAccel-CommandShortcut=true\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def key_to_int(key: str) -> int:
    from PyQt6.QtGui import QKeySequence
    seq = QKeySequence.fromString(key, QKeySequence.SequenceFormat.PortableText)
    if seq.count() != 1:
        raise ValueError(f"not a single key combination: {key!r}")
    return seq[0].toCombined()


def _iface():
    import dbus
    bus = dbus.SessionBus()
    obj = bus.get_object("org.kde.kglobalaccel", "/kglobalaccel")
    return dbus.Interface(obj, "org.kde.KGlobalAccel")


def _action_id(remote: str, button: str):
    import dbus
    name = desktop_name(remote, button)
    friendly = f"{core.APP_NAME}: {remote} {button}"
    return dbus.Array([name, ACTION, friendly, friendly], signature="s")


def _keys(ints):
    import dbus
    return dbus.Array([dbus.Struct((dbus.Array([i], signature="i"),), signature=None)
                       for i in ints], signature="(ai)")


def conflict(key: str, remote: str = "", button: str = "") -> str | None:
    """Return a description of who already uses key, or None if it's free."""
    try:
        k = key_to_int(key)
        own = desktop_name(remote, button) if remote else ""
        iface = _iface()
        if bool(iface.isGlobalShortcutAvailable(k, own or "irremote-probe")):
            return None
        users = iface.action(k)
        if users and own and str(users[0]) == own:
            return None
        return f"{users[3] or users[1]} ({users[2] or users[0]})" if users else "another shortcut"
    except Exception:  # noqa: BLE001 - D-Bus/kglobalaccel may be missing outside Plasma
        return None


def _kwrite(*args) -> None:
    exe = shutil.which("kwriteconfig6")
    if exe:
        subprocess.run([exe, "--file", "kglobalshortcutsrc", *args], check=False,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def register(remote: str, button: str, key: str) -> str:
    """Create/refresh the shortcut. Returns the .desktop file path."""
    path = write_desktop_file(remote, button)
    name = os.path.basename(path)
    k = key_to_int(key)
    try:
        iface = _iface()
        aid = _action_id(remote, button)
        iface.doRegister(aid)
        iface.setForeignShortcutKeys(aid, _keys([k]))
    except Exception:  # noqa: BLE001 - fall back to config only (applies next login)
        pass
    # Persist exactly like System Settings would (harmless if kglobalaccel already did).
    _kwrite("--group", "services", "--group", name, "--key", ACTION, key)
    return path


def unregister(remote: str, button: str) -> None:
    name = desktop_name(remote, button)
    try:
        iface = _iface()
        aid = _action_id(remote, button)
        iface.setForeignShortcutKeys(aid, _keys([]))
        iface.unregister(name, ACTION)
    except Exception:  # noqa: BLE001
        pass
    _kwrite("--group", "services", "--group", name, "--key", ACTION, "--delete")
    path = os.path.join(apps_dir(), name)
    if os.path.exists(path):
        os.remove(path)


def current_keys(remote: str, button: str) -> list[str]:
    """Ask kglobalaccel what is live for this button (for tests / display)."""
    from PyQt6.QtGui import QKeySequence
    try:
        res = _iface().shortcutKeys(_action_id(remote, button))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for seq in res:
        ints = [int(x) for x in seq[0] if int(x)]
        if ints:
            out.append(QKeySequence(*ints).toString(QKeySequence.SequenceFormat.PortableText))
    return out
