# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Eugene Flanagin
"""IR Remote core: storage, dongle status, and the elksmart-comm backend.

Everything here is plain Python (no Qt) so the command line stays fast.
The USB protocol itself is handled by elksmart-comm; we only run it.
"""

from __future__ import annotations

import contextlib
import copy
import fcntl
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field

APP_ID = "irremote"
APP_NAME = "IR Remote"
DEFAULT_FREQUENCY = 38000
VENDOR_ID = "045c"
PRODUCT_IDS = {"0132", "0184", "0195", "0134"}
UDEV_RULE = "/usr/lib/udev/rules.d/70-elksmart-ir.rules"

DATA_VERSION = 2   # 1 = IR Remote 1.0.0; 2 adds an optional "layout" per remote

TYPE_LEARNED = "learned"
TYPE_NEC = "nec"

USBDEVFS_RESET = 0x5514  # _IO('U', 20)


# --- Paths -------------------------------------------------------------------

def config_dir() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, APP_ID)


def config_path() -> str:
    return os.environ.get("IRREMOTE_CONFIG") or os.path.join(config_dir(), "remotes.json")


def comm_binary() -> str:
    return os.environ.get("IRREMOTE_COMM") or shutil.which("elksmart-comm") or "elksmart-comm"


def _lock_path() -> str:
    run = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(run, f"{APP_ID}-{os.getuid()}.lock")


# --- Data model --------------------------------------------------------------

def default_data() -> dict:
    return {
        "version": DATA_VERSION,
        "remotes": [
            {"name": "TV", "buttons": [new_button("Power")]},
        ],
    }


def new_button(name: str, code: str = "", type_: str = TYPE_LEARNED,
               frequency: int = DEFAULT_FREQUENCY) -> dict:
    return {
        "name": name,
        "type": type_,
        "code": code,
        "frequency": frequency,
        "shortcut": "",        # global (KDE) shortcut, e.g. "Meta+Ctrl+P"
        "app_shortcut": "",    # shortcut that works while the window is focused
    }


def normalize(data: dict) -> dict:
    """Validate and fill in defaults. Raises ValueError on bad input."""
    if not isinstance(data, dict) or not isinstance(data.get("remotes"), list):
        raise ValueError("not an IR Remote file (missing \"remotes\" list)")
    out = {"version": DATA_VERSION, "remotes": []}
    for r in data["remotes"]:
        if not isinstance(r, dict) or not str(r.get("name", "")).strip():
            raise ValueError("every remote needs a name")
        remote = {"name": str(r["name"]).strip(), "buttons": []}
        layout = _normalize_layout_ref(r.get("layout"))
        if layout:
            remote["layout"] = layout
        for b in r.get("buttons", []) or []:
            if not isinstance(b, dict) or not str(b.get("name", "")).strip():
                raise ValueError(f"remote {remote['name']!r}: every button needs a name")
            btn = new_button(str(b["name"]).strip())
            btn["type"] = TYPE_NEC if b.get("type") == TYPE_NEC else TYPE_LEARNED
            btn["code"] = clean_hex(str(b.get("code", "") or ""))
            try:
                btn["frequency"] = int(b.get("frequency") or DEFAULT_FREQUENCY)
            except (TypeError, ValueError):
                btn["frequency"] = DEFAULT_FREQUENCY
            btn["shortcut"] = str(b.get("shortcut", "") or "")
            btn["app_shortcut"] = str(b.get("app_shortcut", "") or "")
            remote["buttons"].append(btn)
        out["remotes"].append(remote)
    return out


def _normalize_layout_ref(ref):
    """A remote's picture: a layout id (str), its own photo layout (dict), or None.

    Version 1 files have no "layout" at all and simply show the grid.
    An own-photo layout that doesn't validate is kept as it is (never thrown
    away); the window then falls back to the grid for that remote.
    """
    if isinstance(ref, str):
        return ref.strip() or None
    if isinstance(ref, dict):
        from . import layouts
        try:
            return layouts.validate(ref)
        except ValueError:
            return copy.deepcopy(ref)
    return None


def file_version(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            return int(json.load(f).get("version", 1))
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def load(path: str | None = None) -> dict:
    path = path or config_path()
    if not os.path.exists(path):
        return default_data()
    with open(path, encoding="utf-8") as f:
        return normalize(json.load(f))


def save(data: dict, path: str | None = None) -> None:
    path = path or config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # First save over a 1.0.0 file: keep a copy, in case you go back to 1.0.0.
    if os.path.exists(path) and 0 < file_version(path) < DATA_VERSION:
        backup = f"{path}.v{file_version(path)}-backup"
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(normalize(data), f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def export_json(data: dict, path: str) -> None:
    save(data, path)


def import_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return normalize(json.load(f))


def merge(base: dict, extra: dict) -> dict:
    """Add remotes/buttons from extra; same-named buttons are overwritten."""
    out = copy.deepcopy(base)
    for r in extra["remotes"]:
        target = find_remote(out, r["name"])
        if target is None:
            out["remotes"].append(copy.deepcopy(r))
            continue
        if r.get("layout") and not target.get("layout"):
            target["layout"] = copy.deepcopy(r["layout"])
        for b in r["buttons"]:
            existing = find_button(target, b["name"])
            if existing is None:
                target["buttons"].append(copy.deepcopy(b))
            else:
                existing.update(copy.deepcopy(b))
    return out


def find_remote(data: dict, name: str) -> dict | None:
    for r in data["remotes"]:
        if r["name"] == name:
            return r
    low = name.casefold()
    for r in data["remotes"]:
        if r["name"].casefold() == low:
            return r
    return None


def find_button(remote: dict, name: str) -> dict | None:
    for b in remote["buttons"]:
        if b["name"] == name:
            return b
    low = name.casefold()
    for b in remote["buttons"]:
        if b["name"].casefold() == low:
            return b
    return None


# --- Codes -------------------------------------------------------------------

_HEX_RE = re.compile(r"^[0-9a-f]*$")


def clean_hex(code: str) -> str:
    code = re.sub(r"\s+", "", code.strip().lower())
    if code.startswith("0x"):
        code = code[2:]
    return code


def validate_code(code: str, type_: str) -> str | None:
    """Return a friendly problem description, or None if the code looks fine."""
    code = clean_hex(code)
    if not code:
        return "The code is empty."
    if not _HEX_RE.match(code):
        return "Codes may only contain hex digits (0-9, a-f)."
    if len(code) % 2:
        return "A hex code needs an even number of digits."
    if type_ == TYPE_NEC and len(code) % 4:
        return ("NEC codes are address + command pairs: 4 hex digits per press "
                "(for example 20df for address 20, command df).")
    return None


# --- Dongle status -----------------------------------------------------------

@dataclass
class DongleStatus:
    state: str              # "ready", "no-permission", "not-found"
    node: str = ""
    product: str = ""
    sysfs: str = ""

    @property
    def message(self) -> str:
        if self.state == "ready":
            return f"Dongle ready ({VENDOR_ID}:{self.product})"
        if self.state == "no-permission":
            return ("Dongle found, but you don't have permission to use it. "
                    f"Install the udev rule ({UDEV_RULE}, part of elksmart-comm-git), "
                    "then unplug and replug the dongle.")
        return "Dongle not found - plug the IR blaster into a USB port."


def dongle_status(sysroot: str = "/sys/bus/usb/devices") -> DongleStatus:
    try:
        entries = sorted(os.listdir(sysroot))
    except OSError:
        return DongleStatus("not-found")
    for name in entries:
        d = os.path.join(sysroot, name)
        try:
            with open(os.path.join(d, "idVendor")) as f:
                vendor = f.read().strip()
            if vendor != VENDOR_ID:
                continue
            with open(os.path.join(d, "idProduct")) as f:
                product = f.read().strip()
            if product not in PRODUCT_IDS:
                continue
            with open(os.path.join(d, "busnum")) as f:
                bus = int(f.read())
            with open(os.path.join(d, "devnum")) as f:
                dev = int(f.read())
        except (OSError, ValueError):
            continue
        node = f"/dev/bus/usb/{bus:03d}/{dev:03d}"
        state = "ready" if os.access(node, os.R_OK | os.W_OK) else "no-permission"
        return DongleStatus(state, node, product, d)
    return DongleStatus("not-found")


# --- Running elksmart-comm ---------------------------------------------------

@dataclass
class Result:
    ok: bool
    message: str
    stdout: str = ""
    stderr: str = ""
    code: str = ""                 # learned code (learn only)
    hint: str = ""                 # "attempted pulse decode" (learn only)
    details: list = field(default_factory=list)


_WEDGED = ("identify/recv", "device busy or not supported")


def friendly_error(stderr: str) -> str:
    s = stderr.lower()
    if "no suitable device found" in s:
        return "Dongle not found - plug the IR blaster into a USB port."
    if "access denied" in s or "insufficient permissions" in s:
        return ("No permission to use the dongle. Install elksmart-comm-git (it ships "
                "a udev rule), then unplug and replug the dongle.")
    if "claim interface" in s and "busy" in s:
        return "The dongle is in use by another program (or another IR Remote action). Try again."
    if any(w in s for w in _WEDGED):
        return ("The dongle isn't answering. Use \"Reset dongle\", or unplug it and plug it back in.")
    if "unexpected response" in s:
        return ("The dongle sent something we didn't expect instead of a remote code. "
                "Try again, holding the remote within 1 cm of the dongle.")
    if "invalid hex string" in s:
        return "That code isn't valid hex."
    if "code ends unexpectedly" in s:
        return "That learned code looks cut off. Learn the button again."
    if "requires pairs" in s:
        return "NEC codes need 4 hex digits per press (address + command)."
    if "timed out" in s:
        return "The dongle didn't respond in time. Try again, or reset the dongle."
    line = stderr.strip().splitlines()[-1] if stderr.strip() else "unknown error"
    return f"elksmart-comm: {line}"


def _errors(stderr: str) -> list[str]:
    return [l for l in stderr.splitlines() if l.startswith(("error:", "fatal:"))]


@contextlib.contextmanager
def device_lock(timeout: float = 15.0):
    """Only one elksmart-comm may talk to the dongle at a time (GUI + CLI)."""
    fd = os.open(_lock_path(), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TimeoutError("the dongle is busy with another IR Remote action")
                time.sleep(0.1)
        yield
    finally:
        os.close(fd)


def _run(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run([comm_binary(), *args], capture_output=True, text=True,
                          timeout=timeout, stdin=subprocess.DEVNULL)


def transmit_code(code: str, type_: str = TYPE_LEARNED,
                  frequency: int = DEFAULT_FREQUENCY, auto_reset: bool = True) -> Result:
    problem = validate_code(code, type_)
    if problem:
        return Result(False, problem)
    args = []
    if frequency and int(frequency) != DEFAULT_FREQUENCY:
        args += ["-f", str(int(frequency))]
    if type_ == TYPE_NEC:
        args.append("--nec")
    args.append(clean_hex(code))
    try:
        with device_lock():
            for attempt in range(2):
                try:
                    p = _run(args)
                except subprocess.TimeoutExpired:
                    return Result(False, "elksmart-comm took too long and was stopped.")
                except FileNotFoundError:
                    return Result(False, "elksmart-comm is not installed (package elksmart-comm-git).")
                errs = _errors(p.stderr)
                # elksmart-comm exits 0 even on errors, so stderr is what counts.
                if p.returncode == 0 and not errs:
                    return Result(True, "Sent", p.stdout, p.stderr)
                if attempt == 0 and auto_reset and any(w in p.stderr for w in _WEDGED):
                    _reset_locked()
                    continue
                return Result(False, friendly_error(p.stderr), p.stdout, p.stderr)
    except TimeoutError as e:
        return Result(False, f"Couldn't send: {e}.")
    return Result(False, "Couldn't send.")


def transmit_button(button: dict) -> Result:
    if not button.get("code"):
        return Result(False, f"\"{button['name']}\" isn't learned yet.")
    return transmit_code(button["code"], button.get("type", TYPE_LEARNED),
                         button.get("frequency", DEFAULT_FREQUENCY))


def _probe() -> bool:
    """Ask the dongle to identify itself without sending anything."""
    try:
        p = _run(["zz"], timeout=8)  # identify succeeds, then the bogus hex fails
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return "invalid hex string" in p.stderr


def _usb_reset(node: str) -> bool:
    try:
        fd = os.open(node, os.O_WRONLY)
    except OSError:
        return False
    try:
        fcntl.ioctl(fd, USBDEVFS_RESET, 0)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def _reset_locked(tries: int = 5) -> Result:
    for _ in range(tries):
        st = dongle_status()
        if st.state != "ready":
            return Result(False, st.message)
        _usb_reset(st.node)
        time.sleep(2.0)
        if _probe():
            return Result(True, "Dongle reset and answering again.")
    return Result(False, "The dongle still isn't answering. Unplug it and plug it back in.")


def reset_dongle() -> Result:
    try:
        with device_lock():
            return _reset_locked()
    except TimeoutError as e:
        return Result(False, f"Couldn't reset: {e}.")


def check_dongle() -> Result:
    st = dongle_status()
    if st.state != "ready":
        return Result(False, st.message)
    try:
        with device_lock(timeout=3):
            ok = _probe()
    except TimeoutError:
        return Result(True, "Dongle is busy (in use right now).")
    return Result(ok, "Dongle is answering." if ok else
                  "Dongle found but not answering - try \"Reset dongle\".")


def parse_learn_output(stdout: str) -> tuple[str, str]:
    """Return (full command hex, attempted decode hint) from elksmart-comm output."""
    lines = [l.strip() for l in stdout.splitlines()]
    code = hint = ""
    for i, line in enumerate(lines):
        if line == "Full command:" and i + 1 < len(lines):
            code = clean_hex(lines[i + 1])
        elif line == "Attempted pulse decode:" and i + 1 < len(lines) and not hint:
            hint = lines[i + 1]
    if code and not _HEX_RE.match(code):
        code = ""
    return code, hint


class Learner:
    """Runs one learn attempt. start() / wait() / cancel(); safe from a thread."""

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout
        self.proc: subprocess.Popen | None = None
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True
        p = self.proc
        if p and p.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                p.terminate()

    def run(self) -> Result:
        try:
            with device_lock(timeout=5):
                return self._run_locked()
        except TimeoutError as e:
            return Result(False, f"Couldn't start learning: {e}.")

    def _run_locked(self) -> Result:
        st = dongle_status()
        if st.state != "ready":
            return Result(False, st.message)
        cmd = [comm_binary()]
        if shutil.which("stdbuf"):
            cmd = ["stdbuf", "-oL", *cmd]
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True)
        except FileNotFoundError:
            return Result(False, "elksmart-comm is not installed (package elksmart-comm-git).")
        timed_out = False
        try:
            out, err = self.proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self.proc.terminate()
            try:
                out, err = self.proc.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                out, err = self.proc.communicate()
        code, hint = parse_learn_output(out)
        if code and not _errors(err):
            return Result(True, "Got it!", out, err, code=code, hint=hint)
        # The dongle stays stuck in learn mode until it sees IR; un-stick it.
        if timed_out or self.cancelled or _errors(err):
            _reset_locked()
        if self.cancelled:
            return Result(False, "Learning cancelled.", out, err)
        if timed_out:
            return Result(False, "Nothing was received. Hold the remote within 1 cm of the "
                                 "dongle, aim it straight at the tip, press the button "
                                 "(hold it for about a second), then try again.", out, err)
        if "unexpected response" in err:
            return Result(False, "That didn't come through cleanly. Please try again - hold the "
                                 "remote within 1 cm of the dongle and press the button once.",
                          out, err)
        return Result(False, friendly_error(err), out, err)


# --- Notifications -------------------------------------------------------------

def notify(summary: str, body: str = "", urgency: str = "normal") -> None:
    exe = shutil.which("notify-send")
    if not exe:
        return
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run([exe, "-a", APP_NAME, "-i", APP_ID, "-u", urgency, summary, body],
                       timeout=5, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
