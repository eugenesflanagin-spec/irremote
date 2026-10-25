# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Eugene Flanagin
"""Remote layouts ("skins"): a picture of a remote whose buttons you can press.

A layout is plain JSON. Coordinates are in "units" of an imaginary canvas
(`width` x `height`, usually 100 wide); the window scales it to fit.

    {
      "format": "irremote-layout", "version": 1,
      "id": "my-remote", "name": "My remote",
      "width": 100, "height": 300,
      "body": {"x": 0, "y": 0, "w": 100, "h": 300, "radius": 40, "color": "#26282c"},
      "image": "photos/my-remote.jpg",          # optional photo background
      "decorations": [{"type": "text", "text": "hello", "x": 50, "y": 280, "size": 5}],
      "buttons": [
        {"shape": "circle", "name": "Power", "x": 70, "y": 20, "r": 9, "icon": "power"},
        {"shape": "pill",   "name": "Netflix", "x": 30, "y": 200, "w": 30, "h": 12},
        {"shape": "rect",   "name": "Input", "x": 30, "y": 20, "w": 14, "h": 10},
        {"shape": "dpad", "x": 50, "y": 110, "r": 40, "inner": 17,
         "names": {"up": "Up", "down": "Down", "left": "Left", "right": "Right", "ok": "OK"}},
        {"shape": "rocker", "x": 20, "y": 200, "w": 20, "h": 50,
         "names": {"top": "Volume Up", "bottom": "Volume Down"},
         "icons": {"top": "plus", "bottom": "minus"}}
      ]
    }

`x`/`y` are always the centre of a shape. Button names are what the buttons
are saved as in remotes.json, so "irremote send TV Power" works the same
whichever view you use.

No Qt in this module: hit-testing and validation are plain Python (and tested).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
from dataclasses import dataclass, field

from . import core

FORMAT = "irremote-layout"
SHAPES = ("circle", "rect", "pill", "dpad", "rocker")
DPAD_PARTS = ("up", "down", "left", "right", "ok")
ROCKER_PARTS = ("top", "bottom")
DEFAULT_DPAD_NAMES = {"up": "Up", "down": "Down", "left": "Left", "right": "Right", "ok": "OK"}
DEFAULT_ROCKER_NAMES = {"top": "Volume Up", "bottom": "Volume Down"}

# Icons the window knows how to draw (simple vector glyphs, no artwork).
ICONS = ("power", "mic", "settings", "back", "home", "star", "plus", "minus", "mute",
         "tv", "profile", "up", "down", "left", "right", "input", "menu", "play", "dot")


# --- Directories ---------------------------------------------------------------

def builtin_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "layouts")


def user_dir() -> str:
    return os.path.join(core.config_dir(), "layouts")


def photos_dir() -> str:
    return os.path.join(core.config_dir(), "photos")


def image_path(layout: dict) -> str:
    """Absolute path of a layout's background photo ('' if none)."""
    img = layout.get("image") or ""
    if not img:
        return ""
    img = os.path.expanduser(img)
    return img if os.path.isabs(img) else os.path.join(core.config_dir(), img)


# --- Validation ----------------------------------------------------------------

def _num(d: dict, key: str, where: str, default=None, positive=False) -> float:
    v = d.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{where}: \"{key}\" must be a number")
    v = float(v)
    if not math.isfinite(v) or (positive and v <= 0):
        raise ValueError(f"{where}: \"{key}\" must be a positive number" if positive
                         else f"{where}: \"{key}\" must be a finite number")
    return v


def _str(d: dict, key: str, default: str = "") -> str:
    v = d.get(key, default)
    return str(v) if v is not None else default


def validate(data: dict) -> dict:
    """Check a layout and return a cleaned copy. Raises ValueError on problems."""
    if not isinstance(data, dict):
        raise ValueError("a layout must be a JSON object")
    if data.get("format", FORMAT) != FORMAT:
        raise ValueError(f"not an IR Remote layout (format is {data.get('format')!r})")
    out = {
        "format": FORMAT,
        "version": 1,
        "id": _str(data, "id").strip(),
        "name": _str(data, "name").strip() or _str(data, "id").strip() or "Custom remote",
        "description": _str(data, "description"),
        "width": _num(data, "width", "layout", 100, positive=True),
        "height": _num(data, "height", "layout", None, positive=True),
    }
    first = data.get("learn_first") or []
    if not isinstance(first, list):
        raise ValueError("layout: \"learn_first\" must be a list of button names")
    out["learn_first"] = [str(n) for n in first]
    if data.get("image"):
        out["image"] = _str(data, "image")
    body = data.get("body")
    if body is not None:
        if not isinstance(body, dict):
            raise ValueError("layout: \"body\" must be an object")
        out["body"] = {
            "x": _num(body, "x", "body", 0), "y": _num(body, "y", "body", 0),
            "w": _num(body, "w", "body", out["width"], positive=True),
            "h": _num(body, "h", "body", out["height"], positive=True),
            "radius": _num(body, "radius", "body", 0),
            "color": _str(body, "color", "#2b2d31"),
        }
    decos = []
    for i, d in enumerate(data.get("decorations") or []):
        if not isinstance(d, dict) or d.get("type") not in ("text", "dot", "glyph"):
            raise ValueError(f"decoration {i + 1}: type must be text, dot or glyph")
        dd = dict(d)
        dd["x"] = _num(d, "x", f"decoration {i + 1}")
        dd["y"] = _num(d, "y", f"decoration {i + 1}")
        decos.append(dd)
    out["decorations"] = decos

    buttons = data.get("buttons")
    if not isinstance(buttons, list):
        raise ValueError("layout: \"buttons\" must be a list")
    out["buttons"] = []
    for i, b in enumerate(buttons):
        where = f"button {i + 1}"
        if not isinstance(b, dict) or b.get("shape") not in SHAPES:
            raise ValueError(f"{where}: shape must be one of {', '.join(SHAPES)}")
        shape = b["shape"]
        bb = {k: v for k, v in b.items()}
        bb["x"] = _num(b, "x", where)
        bb["y"] = _num(b, "y", where)
        if shape == "circle":
            bb["r"] = _num(b, "r", where, positive=True)
        elif shape in ("rect", "pill", "rocker"):
            bb["w"] = _num(b, "w", where, positive=True)
            bb["h"] = _num(b, "h", where, positive=True)
        if shape == "dpad":
            bb["r"] = _num(b, "r", where, positive=True)
            bb["inner"] = _num(b, "inner", where, bb["r"] * 0.42, positive=True)
            if bb["inner"] >= bb["r"]:
                raise ValueError(f"{where}: the OK button (inner) must be smaller than the ring (r)")
            names = dict(DEFAULT_DPAD_NAMES)
            names.update({k: str(v).strip() for k, v in (b.get("names") or {}).items()
                          if k in DPAD_PARTS})
            bb["names"] = names
        elif shape == "rocker":
            names = dict(DEFAULT_ROCKER_NAMES)
            names.update({k: str(v).strip() for k, v in (b.get("names") or {}).items()
                          if k in ROCKER_PARTS})
            bb["names"] = names
        else:
            bb["name"] = _str(b, "name").strip()
            if not bb["name"]:
                raise ValueError(f"{where}: every button needs a name")
        out["buttons"].append(bb)
    seen: set[str] = set()
    for h in hotspots(out):
        key = h.name.casefold()
        if not h.name:
            raise ValueError("every button needs a name")
        if key in seen:
            raise ValueError(f"two buttons are called \"{h.name}\"")
        seen.add(key)
    return out


# --- Loading -------------------------------------------------------------------

def load_file(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        lay = validate(json.load(f))
    if not lay["id"]:
        lay["id"] = os.path.splitext(os.path.basename(path))[0]
    return lay


def _scan(directory: str) -> list[dict]:
    out = []
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return out
    for n in names:
        if n.endswith(".json"):
            try:
                out.append(load_file(os.path.join(directory, n)))
            except (OSError, ValueError):
                continue
    return out


def builtin_layouts() -> list[dict]:
    return _scan(builtin_dir())


def all_layouts() -> list[dict]:
    """Built-in layouts first, then shareable ones in ~/.config/irremote/layouts."""
    out = builtin_layouts()
    ids = {l["id"] for l in out}
    for l in _scan(user_dir()):
        if l["id"] not in ids:
            ids.add(l["id"])
            out.append(l)
    return out


def get(layout_id: str) -> dict | None:
    for l in all_layouts():
        if l["id"] == layout_id:
            return l
    return None


def resolve(remote: dict) -> dict | None:
    """The layout a remote uses (built-in id or its own photo layout), or None."""
    ref = remote.get("layout")
    if isinstance(ref, str) and ref:
        return get(ref)
    if isinstance(ref, dict):
        try:
            return validate(ref)
        except ValueError:
            return None
    return None


def describe(remote: dict) -> str:
    ref = remote.get("layout")
    if isinstance(ref, dict):
        return "own picture"
    if isinstance(ref, str) and ref:
        lay = get(ref)
        return lay["name"] if lay else f"{ref} (missing)"
    return "grid"


# --- Hotspots and hit-testing --------------------------------------------------

@dataclass
class Hotspot:
    """One pressable area. A D-pad becomes five of these, a rocker two."""
    name: str
    kind: str                       # circle, rect, sector, rocker
    x: float
    y: float
    r: float = 0.0                  # circle radius / sector outer radius
    inner: float = 0.0              # sector inner radius
    w: float = 0.0
    h: float = 0.0
    radius: float = 0.0             # rect corner radius
    part: str = ""                  # up/down/left/right/ok, top/bottom
    element: int = 0                # index into layout["buttons"]
    style: dict = field(default_factory=dict)

    def contains(self, px: float, py: float) -> bool:
        dx, dy = px - self.x, py - self.y
        if self.kind == "circle":
            return dx * dx + dy * dy <= self.r * self.r
        if self.kind == "sector":
            d = math.hypot(dx, dy)
            if d <= self.inner or d > self.r:
                return False
            return direction(dx, dy) == self.part
        if self.kind in ("rect", "rocker"):
            if abs(dx) > self.w / 2 or abs(dy) > self.h / 2:
                return False
            rad = min(self.radius, self.w / 2, self.h / 2)
            # Rounded corners: outside the corner circle means a miss.
            cx = abs(dx) - (self.w / 2 - rad)
            cy = abs(dy) - (self.h / 2 - rad)
            if rad > 0 and cx > 0 and cy > 0 and cx * cx + cy * cy > rad * rad:
                return False
            if self.kind == "rocker":
                return (dy < 0) if self.part == "top" else (dy >= 0)
            return True
        return False

    def bounds(self) -> tuple[float, float, float, float]:
        """(left, top, right, bottom) in layout units."""
        if self.kind in ("circle", "sector"):
            return (self.x - self.r, self.y - self.r, self.x + self.r, self.y + self.r)
        if self.kind == "rocker":
            top = self.y - self.h / 2 if self.part == "top" else self.y
            return (self.x - self.w / 2, top, self.x + self.w / 2, top + self.h / 2)
        return (self.x - self.w / 2, self.y - self.h / 2, self.x + self.w / 2, self.y + self.h / 2)

    def centre(self) -> tuple[float, float]:
        """Where a label or highlight for this hotspot belongs."""
        if self.kind == "sector":
            mid = (self.r + self.inner) / 2
            dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[self.part]
            return (self.x + dx * mid, self.y + dy * mid)
        if self.kind == "rocker":
            off = self.h / 4
            return (self.x, self.y - off if self.part == "top" else self.y + off)
        return (self.x, self.y)


def direction(dx: float, dy: float) -> str:
    """Which D-pad direction a point is in (screen coordinates: y grows down)."""
    ang = math.degrees(math.atan2(dy, dx))      # 0 = right, 90 = down
    if -45 <= ang < 45:
        return "right"
    if 45 <= ang < 135:
        return "down"
    if -135 <= ang < -45:
        return "up"
    return "left"


def hotspots(layout: dict) -> list[Hotspot]:
    """Every pressable area, in the layout's order (the Learn-all order)."""
    out: list[Hotspot] = []
    for i, b in enumerate(layout["buttons"]):
        shape = b["shape"]
        style = {k: b[k] for k in ("color", "text_color", "label", "icon", "ok_color",
                                   "glyph_color", "font", "bold", "icons", "labels",
                                   "outline") if k in b}
        if shape == "circle":
            out.append(Hotspot(b["name"], "circle", b["x"], b["y"], r=b["r"],
                               element=i, style=style))
        elif shape in ("rect", "pill"):
            rad = b.get("radius", min(b["w"], b["h"]) / 2 if shape == "pill" else 0)
            out.append(Hotspot(b["name"], "rect", b["x"], b["y"], w=b["w"], h=b["h"],
                               radius=float(rad), element=i, style=style))
        elif shape == "dpad":
            for part in ("up", "down", "left", "right"):
                out.append(Hotspot(b["names"][part], "sector", b["x"], b["y"], r=b["r"],
                                   inner=b["inner"], part=part, element=i, style=style))
            out.append(Hotspot(b["names"]["ok"], "circle", b["x"], b["y"], r=b["inner"],
                               part="ok", element=i, style=style))
        elif shape == "rocker":
            rad = b.get("radius", min(b["w"], b["h"]) / 2)
            for part in ("top", "bottom"):
                out.append(Hotspot(b["names"][part], "rocker", b["x"], b["y"], w=b["w"],
                                   h=b["h"], radius=float(rad), part=part, element=i,
                                   style=style))
    return out


def hit(spots: list[Hotspot], x: float, y: float) -> Hotspot | None:
    """The hotspot under (x, y), topmost (last drawn) first."""
    for h in reversed(spots):
        if h.contains(x, y):
            return h
    return None


def button_names(layout: dict) -> list[str]:
    return [h.name for h in hotspots(layout)]


def learn_order(layout: dict) -> list[str]:
    """The order "Learn all" walks through.

    The layout's own order, except that a layout may list "learn_first" names
    (usually the buttons most likely to be infrared, like Power and Volume)
    that go to the front.
    """
    names = button_names(layout)
    first = [n for n in layout.get("learn_first", []) or [] if n in names]
    return first + [n for n in names if n not in first]


def wizard_steps(layout: dict, remote: dict, skip_learned: bool = False) -> list[str]:
    steps = learn_order(layout)
    if skip_learned:
        steps = [n for n in steps if not _learned(remote, n)]
    return steps


def _learned(remote: dict, name: str) -> bool:
    b = core.find_button(remote, name)
    return bool(b and b.get("code"))


def extra_buttons(layout: dict, remote: dict) -> list[dict]:
    """Saved buttons of a remote that have no place on its picture."""
    names = {n.casefold() for n in button_names(layout)}
    return [b for b in remote["buttons"] if b["name"].casefold() not in names]


# --- Photo layouts -------------------------------------------------------------

def new_photo_layout(image: str, img_w: int, img_h: int, name: str = "") -> dict:
    """An empty layout over a photo; buttons are added in the editor."""
    w = 100.0
    h = round(w * img_h / max(1, img_w), 3)
    return {"format": FORMAT, "version": 1, "id": "", "name": name or "My remote",
            "description": "Own photo", "width": w, "height": h, "image": image,
            "decorations": [], "buttons": []}


def import_photo(src: str) -> str:
    """Copy a photo into ~/.config/irremote/photos; returns the path to store.

    The copy is named after its content, so importing the same photo twice
    reuses it. Photos are never bundled with IR Remote or put in exports.
    """
    with open(src, "rb") as f:
        digest = hashlib.sha1(f.read()).hexdigest()[:10]
    base = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(os.path.basename(src))[0].casefold())
    ext = os.path.splitext(src)[1].lower() or ".jpg"
    name = f"{base.strip('-') or 'remote'}-{digest}{ext}"
    os.makedirs(photos_dir(), exist_ok=True)
    dst = os.path.join(photos_dir(), name)
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
    return f"photos/{name}"


def clone(layout: dict) -> dict:
    return copy.deepcopy(layout)
