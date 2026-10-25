# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Eugene Flanagin
"""The picture of a remote ("visual remote"), its photo editor and the Learn-all wizard.

Everything is drawn with QPainter from the layout JSON (see layouts.py):
vector shapes and simple glyphs, so it stays crisp at any window size and
needs no artwork. A layout may instead have a photo as its background, with
plain hotspot shapes on top.
"""

from __future__ import annotations

import math
import time

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QFontMetricsF, QImage, QImageReader, QPainter, QPainterPath, QPalette, QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
    QToolTip, QVBoxLayout, QWidget,
)

from . import core, layouts

COMMON_NAMES = ["Power", "Volume Up", "Volume Down", "Mute", "Input", "Channel Up",
                "Channel Down", "Up", "Down", "Left", "Right", "OK", "Back", "Home", "Menu",
                "Settings", "Play/Pause", "Stop", "Rewind", "Fast Forward", "Info", "Guide",
                "Exit", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]

PHOTO_CHOICE = "__photo__"
KEEP_CHOICE = "__keep__"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def load_image(path: str, max_side: int = 1800) -> QImage:
    """Read a photo the right way up (EXIF) and not bigger than needed."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    img = reader.read()
    if not img.isNull() and max(img.width(), img.height()) > max_side:
        img = img.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    return img


# --- Glyphs ----------------------------------------------------------------------

def draw_glyph(p: QPainter, name: str, cx: float, cy: float, size: float, color: QColor) -> None:
    """Draw a simple line icon centred on (cx, cy), `size` units across."""
    s = size
    pen = QPen(color, max(0.01, s * 0.1))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.save()
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    def line(x1, y1, x2, y2):
        p.drawLine(QPointF(cx + x1 * s, cy + y1 * s), QPointF(cx + x2 * s, cy + y2 * s))

    def poly(points, close=True, fill=False):
        pg = QPolygonF([QPointF(cx + x * s, cy + y * s) for x, y in points])
        if fill:
            p.setBrush(color)
        if close:
            p.drawPolygon(pg)
        else:
            p.drawPolyline(pg)
        p.setBrush(Qt.BrushStyle.NoBrush)

    if name == "power":
        r = 0.36 * s
        p.drawArc(QRectF(cx - r, cy - r + 0.04 * s, 2 * r, 2 * r), 120 * 16, 300 * 16)
        line(0, -0.48, 0, -0.06)
    elif name == "mic":
        p.drawRoundedRect(QRectF(cx - 0.13 * s, cy - 0.45 * s, 0.26 * s, 0.5 * s),
                          0.13 * s, 0.13 * s)
        p.drawArc(QRectF(cx - 0.27 * s, cy - 0.32 * s, 0.54 * s, 0.54 * s), 0, -180 * 16)
        line(0, 0.22, 0, 0.42)
        line(-0.14, 0.42, 0.14, 0.42)
    elif name == "settings":
        r = 0.24 * s
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.drawEllipse(QPointF(cx, cy), 0.09 * s, 0.09 * s)
        tooth = QPen(pen)
        tooth.setWidthF(s * 0.13)
        tooth.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(tooth)
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(QPointF(cx + math.cos(a) * r, cy + math.sin(a) * r),
                       QPointF(cx + math.cos(a) * 0.42 * s, cy + math.sin(a) * 0.42 * s))
    elif name == "back":
        line(0.36, 0, -0.34, 0)
        poly([(-0.06, -0.28), (-0.34, 0), (-0.06, 0.28)], close=False)
    elif name == "home":
        poly([(-0.38, -0.02), (0, -0.38), (0.38, -0.02)], close=False)
        poly([(-0.28, -0.1), (-0.28, 0.36), (0.28, 0.36), (0.28, -0.1)], close=False)
        poly([(-0.08, 0.36), (-0.08, 0.12), (0.08, 0.12), (0.08, 0.36)], close=False)
    elif name == "star":
        pts = []
        for i in range(10):
            rr = 0.42 if i % 2 == 0 else 0.18
            a = math.radians(-90 + i * 36)
            pts.append((math.cos(a) * rr, math.sin(a) * rr + 0.03))
        poly(pts)
    elif name == "plus":
        line(-0.3, 0, 0.3, 0)
        line(0, -0.3, 0, 0.3)
    elif name == "minus":
        line(-0.3, 0, 0.3, 0)
    elif name == "mute":
        poly([(-0.42, -0.12), (-0.26, -0.12), (-0.06, -0.3), (-0.06, 0.3), (-0.26, 0.12),
              (-0.42, 0.12)], fill=True)
        line(0.12, -0.14, 0.4, 0.14)
        line(0.12, 0.14, 0.4, -0.14)
    elif name == "tv":
        p.drawRoundedRect(QRectF(cx - 0.38 * s, cy - 0.22 * s, 0.76 * s, 0.52 * s),
                          0.06 * s, 0.06 * s)
        line(-0.16, -0.42, 0, -0.24)
        line(0.16, -0.42, 0, -0.24)
    elif name == "profile":
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy - 0.16 * s), 0.16 * s, 0.16 * s)
        path = QPainterPath()
        path.moveTo(cx - 0.34 * s, cy + 0.36 * s)
        path.cubicTo(cx - 0.34 * s, cy + 0.02 * s, cx + 0.34 * s, cy + 0.02 * s,
                     cx + 0.34 * s, cy + 0.36 * s)
        path.closeSubpath()
        p.drawPath(path)
    elif name in ("up", "down", "left", "right"):
        pts = {"up": [(-0.3, 0.14), (0, -0.16), (0.3, 0.14)],
               "down": [(-0.3, -0.14), (0, 0.16), (0.3, -0.14)],
               "left": [(0.14, -0.3), (-0.16, 0), (0.14, 0.3)],
               "right": [(-0.14, -0.3), (0.16, 0), (-0.14, 0.3)]}[name]
        poly(pts, close=False)
    elif name == "input":
        p.drawRoundedRect(QRectF(cx - 0.36 * s, cy - 0.3 * s, 0.6 * s, 0.6 * s),
                          0.06 * s, 0.06 * s)
        line(-0.1, 0, 0.42, 0)
        poly([(0.08, -0.16), (-0.1, 0), (0.08, 0.16)], close=False)
    elif name == "menu":
        for y in (-0.22, 0, 0.22):
            line(-0.32, y, 0.32, y)
    elif name == "play":
        poly([(-0.2, -0.3), (0.3, 0), (-0.2, 0.3)], fill=True)
    elif name == "dot":
        p.setBrush(color)
        p.drawEllipse(QPointF(cx, cy), 0.12 * s, 0.12 * s)
    p.restore()


def draw_text(p: QPainter, cx: float, cy: float, text: str, size: float, color: QColor,
              bold: bool = False, base_font: QFont | None = None) -> None:
    """Centred (multi-line) text; `size` is the font height in layout units.

    Text is drawn untransformed at the right pixel size so it stays sharp.
    """
    t = p.worldTransform()
    scale = math.hypot(t.m11(), t.m12()) or 1.0
    px = size * scale
    if px < 4:
        return
    pt = t.map(QPointF(cx, cy))
    p.save()
    p.resetTransform()
    f = QFont(base_font) if base_font else QFont()
    f.setPixelSize(max(1, round(px)))
    f.setBold(bold)
    p.setFont(f)
    p.setPen(color)
    fm = QFontMetricsF(f)
    lines = text.split("\n")
    lh = fm.height() * 0.95
    y0 = pt.y() - lh * len(lines) / 2
    for i, ln in enumerate(lines):
        p.drawText(QRectF(pt.x() - 2000, y0 + i * lh, 4000, lh), Qt.AlignmentFlag.AlignCenter, ln)
    p.restore()


# --- Shape paths -----------------------------------------------------------------

def spot_path(h: layouts.Hotspot) -> QPainterPath:
    path = QPainterPath()
    if h.kind == "circle":
        path.addEllipse(QPointF(h.x, h.y), h.r, h.r)
    elif h.kind == "rect":
        path.addRoundedRect(QRectF(h.x - h.w / 2, h.y - h.h / 2, h.w, h.h),
                            min(h.radius, h.w / 2, h.h / 2), min(h.radius, h.w / 2, h.h / 2))
    elif h.kind == "sector":
        start = {"right": -45, "up": 45, "left": 135, "down": 225}[h.part]
        outer = QRectF(h.x - h.r, h.y - h.r, 2 * h.r, 2 * h.r)
        inner = QRectF(h.x - h.inner, h.y - h.inner, 2 * h.inner, 2 * h.inner)
        path.arcMoveTo(outer, start)
        path.arcTo(outer, start, 90)
        path.arcTo(inner, start + 90, -90)
        path.closeSubpath()
    elif h.kind == "rocker":
        full = QPainterPath()
        rad = min(h.radius, h.w / 2, h.h / 2)
        full.addRoundedRect(QRectF(h.x - h.w / 2, h.y - h.h / 2, h.w, h.h), rad, rad)
        half = QPainterPath()
        top = h.y - h.h / 2 if h.part == "top" else h.y
        half.addRect(QRectF(h.x - h.w / 2 - 1, top, h.w + 2, h.h / 2))
        path = full.intersected(half)
    return path


# --- The canvas --------------------------------------------------------------------

class RemoteCanvas(QWidget):
    """Draws a layout; in "use" mode buttons can be pressed, in "edit" mode moved.

    Modes: "use" (main window), "preview" (pickers/wizard: clicks only select),
    "edit" (photo editor: hotspots can be moved, resized and renamed).
    """
    pressed = pyqtSignal(str)                 # use/preview: a hotspot was clicked
    menu_requested = pyqtSignal(str, QPoint)  # use: right-click on a hotspot
    edited = pyqtSignal()                     # edit: shapes changed
    selection_changed = pyqtSignal(int)       # edit: index into layout["buttons"]
    rename_requested = pyqtSignal(int)        # edit: double-click

    PAD = 10

    def __init__(self, parent=None, mode: str = "use"):
        super().__init__(parent)
        self.mode = mode
        self.layout_: dict | None = None
        self.remote: dict | None = None
        self.spots: list[layouts.Hotspot] = []
        self.paths: list[QPainterPath] = []
        self.image = QImage()
        self.hover: str | None = None
        self.flash: str | None = None
        self.highlight: str | None = None
        self.selected = -1
        self._drag = None
        self._pulse = 0.0
        self._pulse_timer = QTimer(self, interval=40)
        self._pulse_timer.timeout.connect(self._animate)
        self._flash_timer = QTimer(self, singleShot=True, interval=220)
        self._flash_timer.timeout.connect(self._end_flash)
        self.setMouseTracking(True)
        self.setMinimumSize(150, 220)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if mode == "edit" else Qt.FocusPolicy.NoFocus)

    def sizeHint(self):
        return QSize(300, 600)

    # data
    def set_layout(self, layout: dict | None, remote: dict | None = None):
        self.layout_ = layout
        self.remote = remote
        self.image = QImage()
        if layout:
            path = layouts.image_path(layout)
            if path:
                self.image = load_image(path)
        self.hover = self.flash = None
        self._rebuild()

    def set_remote(self, remote: dict | None):
        self.remote = remote
        self.update()

    def _rebuild(self):
        self.spots = layouts.hotspots(self.layout_) if self.layout_ else []
        self.paths = [spot_path(h) for h in self.spots]
        self.update()

    def set_highlight(self, name: str | None):
        self.highlight = name
        if name and not self._pulse_timer.isActive():
            self._pulse_timer.start()
        elif not name:
            self._pulse_timer.stop()
        self.update()

    def flash_button(self, name: str):
        self.flash = name
        self._flash_timer.start()
        self.update()

    def _end_flash(self):
        self.flash = None
        self.update()

    def _animate(self):
        self._pulse = (self._pulse + 0.06) % (2 * math.pi)
        self.update()

    def button(self, name: str) -> dict | None:
        return core.find_button(self.remote, name) if self.remote else None

    def learned(self, name: str) -> bool:
        if self.remote is None:
            return True     # previews show the remote as it looks for real
        b = self.button(name)
        return bool(b and b.get("code"))

    # geometry
    def _xf(self) -> tuple[float, float, float]:
        lw, lh = self.layout_["width"], self.layout_["height"]
        w, h = self.width() - 2 * self.PAD, self.height() - 2 * self.PAD
        s = max(0.01, min(w / lw, h / lh))
        return s, (self.width() - lw * s) / 2, (self.height() - lh * s) / 2

    def to_units(self, pos) -> tuple[float, float]:
        s, ox, oy = self._xf()
        return (pos.x() - ox) / s, (pos.y() - oy) / s

    def spot_at(self, pos) -> layouts.Hotspot | None:
        if not self.layout_:
            return None
        x, y = self.to_units(pos)
        return layouts.hit(self.spots, x, y)

    def spot_rect(self, name: str) -> QRectF:
        """Where a hotspot is on screen (for tests and tooltips)."""
        s, ox, oy = self._xf()
        for h in self.spots:
            if h.name == name:
                l, t, r, b = h.bounds()
                return QRectF(ox + l * s, oy + t * s, (r - l) * s, (b - t) * s)
        return QRectF()

    def spot_centre(self, name: str) -> QPoint:
        s, ox, oy = self._xf()
        for h in self.spots:
            if h.name == name:
                cx, cy = h.centre()
                return QPoint(round(ox + cx * s), round(oy + cy * s))
        return QPoint()

    # painting
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing |
                         QPainter.RenderHint.SmoothPixmapTransform |
                         QPainter.RenderHint.TextAntialiasing)
        pal = self.palette()
        p.fillRect(self.rect(), pal.color(QPalette.ColorRole.Window))
        if not self.layout_:
            p.setPen(pal.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No picture")
            return
        s, ox, oy = self._xf()
        p.translate(ox, oy)
        p.scale(s, s)
        lay = self.layout_
        photo = not self.image.isNull()
        if photo:
            p.drawImage(QRectF(0, 0, lay["width"], lay["height"]), self.image)
        elif lay.get("image"):
            draw_text(p, lay["width"] / 2, lay["height"] / 2,
                      "Photo not found:\n" + layouts.image_path(lay), 4,
                      pal.color(QPalette.ColorRole.WindowText), base_font=self.font())
        body = lay.get("body")
        if body and not photo:
            rect = QRectF(body["x"], body["y"], body["w"], body["h"])
            shadow = QColor(0, 0, 0, 60)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(shadow)
            p.drawRoundedRect(rect.translated(0.8, 1.6), body["radius"], body["radius"])
            p.setBrush(QColor(body["color"]))
            outline = QPen(pal.color(QPalette.ColorRole.Mid), 1)
            outline.setCosmetic(True)
            p.setPen(outline)
            p.drawRoundedRect(rect, body["radius"], body["radius"])
        for d in lay.get("decorations", []):
            self._decoration(p, d)
        for h, path in zip(self.spots, self.paths):
            self._spot(p, h, path, photo)
        self._overlays(p, s)

    def _decoration(self, p: QPainter, d: dict):
        color = QColor(d.get("color", "#cccccc"))
        if d["type"] == "text":
            draw_text(p, d["x"], d["y"], str(d.get("text", "")), float(d.get("size", 5)),
                      color, bool(d.get("bold")), self.font())
        elif d["type"] == "dot":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            r = float(d.get("r", 1))
            p.drawEllipse(QPointF(d["x"], d["y"]), r, r)
        elif d["type"] == "glyph":
            draw_glyph(p, str(d.get("icon", "")), d["x"], d["y"], float(d.get("size", 6)), color)

    def _spot(self, p: QPainter, h: layouts.Hotspot, path: QPainterPath, photo: bool):
        st = h.style
        learned = self.learned(h.name) or self.mode == "edit"
        hl = self.accent()
        if photo or self.mode == "edit" and not st.get("color"):
            # Hotspots over a photo: just outlines, the photo shows the button.
            fill = QColor(hl)
            fill.setAlpha(55 if self.learned(h.name) and self.mode != "edit" else 25)
            p.fillPath(path, fill)
            pen = QPen(QColor(255, 255, 255, 230), 2)
            pen.setCosmetic(True)
            if not self.learned(h.name) or self.mode == "edit":
                pen.setStyle(Qt.PenStyle.DashLine)
            p.strokePath(path, _cosmetic(QColor(0, 0, 0, 150), 3.5))
            p.strokePath(path, pen)
            if self.mode == "edit" or not self.learned(h.name):
                l, t, r, b = h.bounds()
                self._tag(p, h.name, (l + r) / 2, b + 2.2)
            return
        base = QColor(st.get("ok_color" if h.part == "ok" and st.get("ok_color") else "color",
                             "#3a3d42"))
        fg = QColor(st.get("text_color", "#f2f2f2"))
        if h.kind == "sector" and st.get("glyph_color"):
            fg = QColor(st["glyph_color"])
        if not learned:
            base.setAlphaF(base.alphaF() * 0.38)
            fg.setAlphaF(0.6)
        p.fillPath(path, base)
        if not learned:
            pen = _cosmetic(QColor(255, 255, 255, 150), 1.2)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.strokePath(path, pen)
        cx, cy = h.centre()
        if h.kind == "sector":
            draw_glyph(p, h.part, cx, cy, (h.r - h.inner) * 0.42, fg)
            return
        if h.kind == "rocker":
            icon = (st.get("icons") or {}).get(h.part, "")
            label = (st.get("labels") or {}).get(h.part, "")
            size = min(h.w, h.h / 2) * 0.62
        else:
            icon = st.get("icon", "")
            label = st.get("label", "")
            size = (h.r * 1.05) if h.kind == "circle" else min(h.w, h.h) * 0.62
        if h.part == "ok" and not label and not icon:
            return
        if icon:
            draw_glyph(p, icon, cx, cy, size, fg)
        elif label:
            fsize = float(st.get("font", size * 0.36))
            draw_text(p, cx, cy, label, fsize, fg, bool(st.get("bold")), self.font())

    def _tag(self, p: QPainter, text: str, cx: float, top: float):
        """A small name tag (photo layouts), drawn in pixels for legibility."""
        t = p.worldTransform()
        pt = t.map(QPointF(cx, top))
        p.save()
        p.resetTransform()
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() * 0.85))
        p.setFont(f)
        fm = QFontMetricsF(f)
        w = fm.horizontalAdvance(text) + 8
        r = QRectF(pt.x() - w / 2, pt.y(), w, fm.height() + 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(r, 3, 3)
        p.setPen(QColor("white"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        p.restore()

    def accent(self) -> QColor:
        """The theme's highlight colour, or Breeze blue if the theme's is grey."""
        hl = self.palette().color(QPalette.ColorRole.Highlight)
        return hl if hl.hsvSaturation() >= 60 else QColor("#3daee9")

    def _overlays(self, p: QPainter, s: float):
        hl = self.accent()
        for h, path in zip(self.spots, self.paths):
            if h.name == self.flash:
                c = QColor(hl)
                c.setAlpha(170)
                p.fillPath(path, c)
            if h.name == self.highlight:
                glow = QColor(hl)
                glow.setAlpha(int(95 + 45 * math.sin(self._pulse)))
                p.fillPath(path, glow)
                p.strokePath(path, _cosmetic(hl, 3.0 + 1.5 * (1 + math.sin(self._pulse))))
            elif h.name == self.hover and self.mode != "edit":
                p.strokePath(path, _cosmetic(hl, 2.5))
        if self.mode == "edit" and 0 <= self.selected < len(self.layout_["buttons"]):
            for h, path in zip(self.spots, self.paths):
                if h.element == self.selected:
                    p.strokePath(path, _cosmetic(hl, 3))
                    l, t, r, b = h.bounds()
                    hs = 7 / s
                    p.setPen(_cosmetic(QColor("white"), 1))
                    p.setBrush(hl)
                    p.drawRect(QRectF(r - hs / 2, b - hs / 2, hs, hs))

    # interaction
    def _tooltip(self, h: layouts.Hotspot | None, gpos):
        if h is None or self.mode == "edit":
            QToolTip.hideText()
            return
        lines = [f"<b>{_esc(h.name)}</b>"]
        if self.mode == "use":
            b = self.button(h.name)
            if b and b.get("code"):
                lines.append("Click to send")
            else:
                lines.append("Not learned - click to learn it")
            if b and b.get("shortcut"):
                lines.append(f"Shortcut: {_esc(b['shortcut'])}")
            if b and b.get("app_shortcut"):
                lines.append(f"In-app key: {_esc(b['app_shortcut'])}")
            lines.append("<i>Right-click for more</i>")
        QToolTip.showText(gpos, "<br>".join(lines), self)

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        if self.mode == "edit" and self._drag:
            self._drag_to(pos)
            return
        h = self.spot_at(pos)
        name = h.name if h else None
        if name != self.hover:
            self.hover = name
            self.setCursor(Qt.CursorShape.PointingHandCursor if h else Qt.CursorShape.ArrowCursor)
            self._tooltip(h, ev.globalPosition().toPoint())
            self.update()
        if self.mode == "edit":
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if self._on_handle(pos)
                           else Qt.CursorShape.SizeAllCursor if h else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, ev):
        if self.hover:
            self.hover = None
            self.update()

    def mousePressEvent(self, ev):
        pos = ev.position()
        if self.mode == "edit":
            self._edit_press(pos)
            return
        h = self.spot_at(pos)
        if h is None:
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            if self.mode == "use":
                self.flash_button(h.name)
            self.pressed.emit(h.name)
        elif ev.button() == Qt.MouseButton.RightButton and self.mode == "use":
            self.menu_requested.emit(h.name, ev.globalPosition().toPoint())

    def mouseReleaseEvent(self, ev):
        if self._drag:
            self._drag = None
            self.edited.emit()

    def mouseDoubleClickEvent(self, ev):
        if self.mode == "edit":
            h = self.spot_at(ev.position())
            if h:
                self.rename_requested.emit(h.element)

    def keyPressEvent(self, ev):
        if self.mode == "edit" and ev.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            return
        super().keyPressEvent(ev)

    # edit mode
    def select(self, index: int):
        self.selected = index
        self.update()
        self.selection_changed.emit(index)

    def _on_handle(self, pos) -> bool:
        if not (0 <= self.selected < len(self.spots)):
            return False
        h = next((x for x in self.spots if x.element == self.selected), None)
        if h is None:
            return False
        s, ox, oy = self._xf()
        l, t, r, b = h.bounds()
        return abs(pos.x() - (ox + r * s)) <= 7 and abs(pos.y() - (oy + b * s)) <= 7

    def _edit_press(self, pos):
        x, y = self.to_units(pos)
        if self._on_handle(pos):
            self._drag = ("resize", self.selected)
            return
        h = self.spot_at(pos)
        if h is None:
            self.select(-1)
            return
        b = self.layout_["buttons"][h.element]
        self.select(h.element)
        self._drag = ("move", h.element, x - b["x"], y - b["y"])

    def _drag_to(self, pos):
        x, y = self.to_units(pos)
        lay = self.layout_
        b = lay["buttons"][self._drag[1]]
        if self._drag[0] == "move":
            b["x"] = round(min(max(x - self._drag[2], 0), lay["width"]), 2)
            b["y"] = round(min(max(y - self._drag[3], 0), lay["height"]), 2)
        elif b["shape"] == "circle":
            b["r"] = round(max(1.5, math.hypot(x - b["x"], y - b["y"]) / math.sqrt(2)), 2)
        else:
            b["w"] = round(max(3.0, 2 * abs(x - b["x"])), 2)
            b["h"] = round(max(3.0, 2 * abs(y - b["y"])), 2)
        self._rebuild()

    def add_shape(self, shape: str, name: str):
        lay = self.layout_
        cx, cy = lay["width"] / 2, lay["height"] / 2
        if shape == "circle":
            b = {"shape": "circle", "name": name, "x": cx, "y": cy, "r": 6.0}
        else:
            b = {"shape": "rect", "name": name, "x": cx, "y": cy, "w": 18.0, "h": 10.0,
                 "radius": 2.0}
        lay["buttons"].append(b)
        self._rebuild()
        self.select(len(lay["buttons"]) - 1)
        self.edited.emit()

    def delete_selected(self):
        if 0 <= self.selected < len(self.layout_["buttons"]):
            del self.layout_["buttons"][self.selected]
            self._rebuild()
            self.select(-1)
            self.edited.emit()

    def rebuild(self):
        self._rebuild()


def _cosmetic(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCosmetic(True)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


# --- Choose a picture (new remote / change picture) -------------------------------

class LayoutDialog(QDialog):
    """Pick a name and a picture for a remote."""

    def __init__(self, parent, name: str = "", current=None, ask_name: bool = True,
                 taken: set[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add remote" if ask_name else "Remote picture")
        self.resize(640, 520)
        self.taken = {t.casefold() for t in (taken or set())}
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        form = QFormLayout()
        self.name = QLineEdit(name)
        self.name.setPlaceholderText("e.g. Living room TV")
        if ask_name:
            form.addRow("Name:", self.name)
        left.addLayout(form)
        left.addWidget(QLabel("<b>What should it look like?</b>"))
        self.list = QListWidget()
        self._add("No picture - a grid of buttons", None)
        self.layouts = layouts.all_layouts()
        for l in self.layouts:
            self._add(l["name"], l["id"])
        if isinstance(current, dict):
            self._add("My own picture (keep it)", KEEP_CHOICE)
        self._add("Use my own picture…", PHOTO_CHOICE)
        left.addWidget(self.list, 1)
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.desc.setMinimumHeight(60)
        left.addWidget(self.desc)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        left.addWidget(bb)
        lay.addLayout(left, 3)
        self.preview = RemoteCanvas(self, mode="preview")
        self.preview.setMinimumWidth(200)
        lay.addWidget(self.preview, 2)
        self.list.currentRowChanged.connect(self._changed)
        want = KEEP_CHOICE if isinstance(current, dict) else current
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == want:
                self.list.setCurrentRow(i)
                break
        else:
            self.list.setCurrentRow(1 if ask_name and self.layouts else 0)
        self.current = current
        self.list.itemDoubleClicked.connect(lambda _: self.accept())

    def _add(self, text, data):
        it = QListWidgetItem(text)
        it.setData(Qt.ItemDataRole.UserRole, data)
        self.list.addItem(it)

    def choice(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _changed(self, _row):
        c = self.choice()
        lay = next((l for l in self.layouts if l["id"] == c), None)
        if lay:
            self.preview.set_layout(lay)
            self.desc.setText(_esc(lay.get("description", "")))
        elif c == KEEP_CHOICE:
            self.preview.set_layout(layouts.resolve({"layout": self.current}))
            self.desc.setText("The photo and buttons you set up before.")
        elif c == PHOTO_CHOICE:
            self.preview.set_layout(None)
            self.desc.setText("Pick a photo of your remote, then draw a shape over each "
                              "button. The photo is copied to your IR Remote settings folder.")
        else:
            self.preview.set_layout(None)
            self.desc.setText("Plain buttons in a grid, like IR Remote 1.0.")

    def accept(self):
        if self.name.isVisibleTo(self) or self.windowTitle() == "Add remote":
            n = self.name.text().strip()
            if not n:
                self.name.setFocus()
                return
            if n.casefold() in self.taken:
                QMessageBox.information(self, core.APP_NAME, f"There's already a remote called {n}.")
                return
        super().accept()


# --- Photo editor ------------------------------------------------------------------

class PhotoLayoutDialog(QDialog):
    """Draw hotspots on a photo of a remote: add, move, resize, rename, delete."""

    def __init__(self, parent, layout: dict):
        super().__init__(parent)
        self.setWindowTitle("Buttons on my picture")
        self.resize(820, 680)
        self.layout_ = layouts.clone(layout)
        root = QHBoxLayout(self)
        self.canvas = RemoteCanvas(self, mode="edit")
        self.canvas.set_layout(self.layout_)
        root.addWidget(self.canvas, 3)

        side = QVBoxLayout()
        help_ = QLabel("<b>How:</b> click <b>Add round</b> or <b>Add square</b>, give it the "
                       "button's name, then drag it onto that button in the photo. Drag the "
                       "small square corner to resize. Double-click to rename, "
                       "<b>Delete</b> key to remove.")
        help_.setWordWrap(True)
        side.addWidget(help_)
        row = QHBoxLayout()
        b1 = QPushButton("Add round")
        b2 = QPushButton("Add square")
        b1.clicked.connect(lambda: self._add("circle"))
        b2.clicked.connect(lambda: self._add("rect"))
        row.addWidget(b1)
        row.addWidget(b2)
        side.addLayout(row)
        self.list = QListWidget()
        side.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.rename_btn = QPushButton("Rename…")
        self.delete_btn = QPushButton("Delete")
        self.rename_btn.clicked.connect(lambda: self._rename(self.canvas.selected))
        self.delete_btn.clicked.connect(self.canvas.delete_selected)
        row.addWidget(self.rename_btn)
        row.addWidget(self.delete_btn)
        side.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        side.addWidget(bb)
        root.addLayout(side, 2)

        self.canvas.edited.connect(self._refresh)
        self.canvas.selection_changed.connect(self._selected)
        self.canvas.rename_requested.connect(self._rename)
        self.list.currentRowChanged.connect(self._list_row)
        self.list.itemDoubleClicked.connect(lambda _: self._rename(self.list.currentRow()))
        self._refresh()

    def result_layout(self) -> dict:
        return self.layout_

    def _names(self, skip: int = -1) -> set[str]:
        return {b["name"].casefold() for i, b in enumerate(self.layout_["buttons"]) if i != skip}

    def _ask_name(self, title: str, current: str = "", skip: int = -1) -> str:
        used = self._names(skip)
        options = [n for n in COMMON_NAMES if n.casefold() not in used]
        if current:
            options.insert(0, current)
        while True:
            name, ok = QInputDialog.getItem(self, title, "Button name:", options, 0, True)
            name = name.strip() if ok else ""
            if not name:
                return ""
            if name.casefold() in used:
                QMessageBox.information(self, title, f"There's already a button called {name}.")
                continue
            return name

    def _add(self, shape: str):
        name = self._ask_name("Add button")
        if name:
            self.canvas.add_shape(shape, name)
            self.canvas.setFocus()

    def _rename(self, index: int):
        if not (0 <= index < len(self.layout_["buttons"])):
            return
        b = self.layout_["buttons"][index]
        name = self._ask_name("Rename button", b["name"], skip=index)
        if name:
            b["name"] = name
            self.canvas.rebuild()
            self._refresh()

    def _refresh(self):
        self.list.blockSignals(True)
        self.list.clear()
        for b in self.layout_["buttons"]:
            self.list.addItem(b["name"])
        self.list.setCurrentRow(self.canvas.selected)
        self.list.blockSignals(False)
        has = 0 <= self.canvas.selected < len(self.layout_["buttons"])
        self.rename_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)

    def _selected(self, index: int):
        self._refresh()

    def _list_row(self, row: int):
        self.canvas.select(row)

    def accept(self):
        if not self.layout_["buttons"] and QMessageBox.question(
                self, "No buttons yet",
                "You haven't marked any buttons on the photo. Save anyway?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.layout_ = layouts.validate(self.layout_)
        except ValueError as e:
            QMessageBox.warning(self, core.APP_NAME, str(e))
            return
        super().accept()


# --- Learn all ---------------------------------------------------------------------

class LearnAllDialog(QDialog):
    """Walk through every button of a picture remote, one after the other."""
    TIMEOUT = 20

    def __init__(self, parent, remote: dict, layout: dict, on_learned, worker_cls,
                 autostart: bool = True):
        super().__init__(parent)
        self.setWindowTitle(f"Learn all buttons - {remote['name']}")
        self.resize(760, 640)
        self.remote = remote
        self.layout_ = layout
        self.on_learned = on_learned
        self.Worker = worker_cls
        self.autostart = autostart
        self.learner: core.Learner | None = None
        self.worker = None
        self.test_worker = None
        self.pending: int | None = None
        self.closing = False
        self.code = ""
        self.learned_now = 0
        self.index = 0

        root = QHBoxLayout(self)
        self.canvas = RemoteCanvas(self, mode="preview")
        self.canvas.set_layout(layout, remote)
        self.canvas.setMinimumWidth(240)
        self.canvas.pressed.connect(self._jump_to)
        root.addWidget(self.canvas, 2)

        side = QVBoxLayout()
        self.counter = QLabel()
        side.addWidget(self.counter)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        side.addWidget(self.bar)
        self.prompt = QLabel()
        self.prompt.setWordWrap(True)
        f = self.prompt.font()
        f.setPointSizeF(f.pointSizeF() * 1.5)
        self.prompt.setFont(f)
        self.prompt.setMinimumHeight(70)
        side.addWidget(self.prompt)
        hint = QLabel("Hold your remote <b>within 1 cm</b> of the dongle, pointing at its tip, "
                      "and press the button once (about a second). Buttons that only work "
                      "over Bluetooth can't be learned - just <b>Skip</b> them.")
        hint.setWordWrap(True)
        side.addWidget(hint)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(60)
        side.addWidget(self.status)
        self.countdown = QProgressBar()
        self.countdown.setRange(0, self.TIMEOUT)
        self.countdown.setFormat("%v s left")
        self.countdown.hide()
        side.addWidget(self.countdown)
        self.skip_learned = QCheckBox("Skip buttons that are already learned")
        self.skip_learned.setChecked(True)
        self.skip_learned.toggled.connect(self._resteps)
        side.addWidget(self.skip_learned)
        self.auto_next = QCheckBox("Go to the next button automatically")
        self.auto_next.setChecked(True)
        side.addWidget(self.auto_next)
        side.addStretch(1)

        row1 = QHBoxLayout()
        self.back_btn = QPushButton("◀ Back")
        self.listen_btn = QPushButton("Listen")
        self.test_btn = QPushButton("Test")
        row1.addWidget(self.back_btn)
        row1.addWidget(self.listen_btn)
        row1.addWidget(self.test_btn)
        side.addLayout(row1)
        row2 = QHBoxLayout()
        self.skip_btn = QPushButton("Skip ▶")
        self.next_btn = QPushButton("Next ▶")
        self.finish_btn = QPushButton("Finish")
        row2.addWidget(self.skip_btn)
        row2.addWidget(self.next_btn)
        row2.addStretch(1)
        row2.addWidget(self.finish_btn)
        side.addLayout(row2)
        root.addLayout(side, 3)

        self.back_btn.clicked.connect(lambda: self._go(self.index - 1))
        self.skip_btn.clicked.connect(lambda: self._go(self.index + 1))
        self.next_btn.clicked.connect(lambda: self._go(self.index + 1))
        self.listen_btn.clicked.connect(self._listen)
        self.test_btn.clicked.connect(self._test)
        self.finish_btn.clicked.connect(self.accept)

        self.tick = QTimer(self, interval=500)
        self.tick.timeout.connect(self._tick)
        self.next_timer = QTimer(self, singleShot=True, interval=1500)
        self.next_timer.timeout.connect(lambda: self._go(self.index + 1))
        self.started_at = 0.0

        self.steps = layouts.wizard_steps(layout, remote, True)
        if not self.steps:      # everything learned already: walk them all
            self.skip_learned.blockSignals(True)
            self.skip_learned.setChecked(False)
            self.skip_learned.blockSignals(False)
            self.steps = layouts.wizard_steps(layout, remote, False)
        QTimer.singleShot(0, lambda: self._show(0))

    # steps
    def current_name(self) -> str | None:
        return self.steps[self.index] if 0 <= self.index < len(self.steps) else None

    def _resteps(self, skip: bool):
        name = self.current_name()
        self.steps = layouts.wizard_steps(self.layout_, self.remote, skip)
        if name in self.steps:
            self.index = self.steps.index(name)
        else:
            self.index = min(self.index, len(self.steps))
        self._go(self.index)

    def _jump_to(self, name: str):
        if name not in self.steps:
            self.skip_learned.setChecked(False)
        if name in self.steps:
            self._go(self.steps.index(name))

    def _go(self, index: int):
        self.next_timer.stop()
        index = max(0, min(index, len(self.steps)))
        if self.worker and self.worker.isRunning():
            self.pending = index
            self.status.setText("One moment…")
            if self.learner:
                self.learner.cancel()
            return
        self._show(index)

    def _show(self, index: int):
        self.index = index
        self.code = ""
        n = len(self.steps)
        name = self.current_name()
        self.bar.setRange(0, max(1, n))
        self.bar.setValue(min(index, n))
        self.canvas.set_remote(self.remote)
        self.canvas.set_highlight(name)
        if name is None:
            self.counter.setText(f"<b>Done</b> - {n} of {n}")
            self.prompt.setText("All done!")
            self.status.setText(f"Learned {self.learned_now} button(s) in this round. "
                                "Click a button on the picture to send it, or right-click "
                                "it to learn it again.")
            self._buttons(idle=True, done=True)
            return
        self.counter.setText(f"Button <b>{index + 1}</b> of {n}")
        self.prompt.setText(f"Press <b>{_esc(name.upper())}</b> on your remote")
        b = core.find_button(self.remote, name)
        if b and b.get("code"):
            # Already learned (or we came Back to it): offer Test, don't overwrite.
            self.code = b["code"]
            self.listen_btn.setText("Learn again")
            self.status.setText("Already learned. <b>Test</b> it, <b>Learn again</b> to "
                                "replace it, or go on with <b>Next</b>.")
            self._buttons(idle=True)
            return
        self.listen_btn.setText("Listen")
        self.status.setText("")
        self._buttons(idle=True)
        if self.autostart:
            self._listen()

    def _buttons(self, idle: bool, done: bool = False):
        self.back_btn.setEnabled(self.index > 0)
        self.listen_btn.setEnabled(idle and not done)
        self.test_btn.setEnabled(idle and bool(self.code))
        self.skip_btn.setEnabled(not done)
        self.skip_btn.setVisible(not self.code)
        self.next_btn.setVisible(bool(self.code))
        self.next_btn.setDefault(bool(self.code))
        self.finish_btn.setDefault(done)

    # learning
    def _listen(self):
        if self.worker and self.worker.isRunning() or self.current_name() is None:
            return
        self.code = ""
        self.listen_btn.setText("Retry")
        self.status.setText("Listening… press the button now.")
        self.countdown.setValue(self.TIMEOUT)
        self.countdown.show()
        self.started_at = time.monotonic()
        self.tick.start()
        self.learner = core.Learner(timeout=self.TIMEOUT)
        self.worker = self.Worker(self.learner.run, self)
        self.worker.done.connect(self._learned)
        self.worker.start()
        self._buttons(idle=False)

    def _tick(self):
        self.countdown.setValue(max(0, self.TIMEOUT - int(time.monotonic() - self.started_at)))

    def _learned(self, res: core.Result):
        self.tick.stop()
        self.countdown.hide()
        self.learner = None
        if self.closing:
            return
        if self.pending is not None:
            i, self.pending = self.pending, None
            self._show(i)
            return
        name = self.current_name()
        if res.ok and name:
            self.code = res.code
            self.on_learned(name, res.code)
            self.learned_now += 1
            self.canvas.set_remote(self.remote)
            self.status.setText(f"✔ Got {_esc(name)}! <b>Test</b> it, or go on.")
            self._buttons(idle=True)
            if self.auto_next.isChecked():
                self.status.setText(f"✔ Got {_esc(name)}! Next button in a moment… "
                                    "(<b>Back</b> to test it)")
                self.next_timer.start()
        else:
            self.status.setText(f"✖ {_esc(res.message)}<br>Click <b>Retry</b>, or <b>Skip</b> "
                                "if this button doesn't use infrared.")
            self._buttons(idle=True)

    def _test(self):
        self.next_timer.stop()
        name = self.current_name()
        b = core.find_button(self.remote, name) if name else None
        if not (b and b.get("code")):
            return
        button = dict(b)
        self._buttons(idle=False)
        self.status.setText("Sending…")
        self.test_worker = self.Worker(lambda: core.transmit_button(button), self)
        self.test_worker.done.connect(self._tested)
        self.test_worker.start()

    def _tested(self, res):
        self._buttons(idle=True)
        self.status.setText("Sent. Did it work? <b>Next</b> if yes, <b>Retry</b> if not."
                            if res.ok else f"✖ {_esc(res.message)}")

    def done(self, r):
        self.closing = True
        self.next_timer.stop()
        self.canvas.set_highlight(None)
        if self.learner:
            self.learner.cancel()
        for w in (self.worker, self.test_worker):
            if w and w.isRunning():
                w.wait(20000)
        self.tick.stop()
        super().done(r)
