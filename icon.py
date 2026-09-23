"""App icons and small glyphs, all drawn with QPainter.

`app_icon()` is the static project icon (window / taskbar / default tray).
`make_icon()` is the opt-in tray icon that shows the strip colour: a filled
disc inside a ring drawn dark-over-light so it reads on both menubar shades.
`glyph()` draws the UI's few line icons in a given colour so they follow the
theme without image assets.
"""

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

_ICON_FILE = Path(__file__).resolve().parent / "assets" / "icon.png"


def app_icon() -> QIcon:
    """The static project icon (window / taskbar)."""
    return QIcon(str(_ICON_FILE))


def _canvas(size, dpr=2.0):
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pixmap, painter


def make_icon(color: QColor) -> QIcon:
    """Tray icon reflecting the strip colour: colour disc in a two-tone ring."""
    size = 22
    pixmap, p = _canvas(size)
    p.setBrush(color)
    p.setPen(QPen(QColor(0, 0, 0, 150), 1.6))
    p.drawEllipse(QRectF(2.5, 2.5, size - 5, size - 5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 210), 1.2))
    p.drawEllipse(QRectF(3.9, 3.9, size - 7.8, size - 7.8))
    p.end()
    return QIcon(pixmap)


def swatch(color: QColor, size=14) -> QIcon:
    """A colour dot with a faint outline (menu / preset icons)."""
    pixmap, p = _canvas(size)
    p.setBrush(color)
    p.setPen(QPen(QColor(0, 0, 0, 40), 1))
    p.drawEllipse(QRectF(0.5, 0.5, size - 1, size - 1))
    p.end()
    return QIcon(pixmap)


def glyph(kind: str, color, size=14, width=2.0) -> QIcon:
    """Line icon: power, tune (settings), minus, close, back, down, check."""
    c = QColor(color)
    pixmap, p = _canvas(size)
    p.setPen(QPen(c, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    s = size
    if kind == "power":
        r = QRectF(s * 0.18, s * 0.2, s * 0.64, s * 0.64)
        p.drawArc(r, 130 * 16, 280 * 16)
        p.drawLine(QPointF(s / 2, s * 0.1), QPointF(s / 2, s * 0.48))
    elif kind == "tune":
        p.setPen(QPen(c, width * 0.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for y, knob in ((0.27, 0.62), (0.5, 0.38), (0.73, 0.66)):
            p.drawLine(QPointF(s * 0.16, s * y), QPointF(s * 0.84, s * y))
            p.setBrush(QColor(0, 0, 0, 0))
            p.drawEllipse(QPointF(s * knob, s * y), s * 0.09, s * 0.09)
    elif kind == "minus":
        p.drawLine(QPointF(s * 0.2, s / 2), QPointF(s * 0.8, s / 2))
    elif kind == "close":
        p.drawLine(QPointF(s * 0.25, s * 0.25), QPointF(s * 0.75, s * 0.75))
        p.drawLine(QPointF(s * 0.75, s * 0.25), QPointF(s * 0.25, s * 0.75))
    elif kind == "back":
        p.drawPolyline([QPointF(s * 0.62, s * 0.22), QPointF(s * 0.36, s / 2), QPointF(s * 0.62, s * 0.78)])
    elif kind == "down":
        p.drawPolyline([QPointF(s * 0.25, s * 0.38), QPointF(s / 2, s * 0.64), QPointF(s * 0.75, s * 0.38)])
    elif kind == "check":
        p.drawPolyline([QPointF(s * 0.2, s * 0.52), QPointF(s * 0.42, s * 0.74), QPointF(s * 0.8, s * 0.3)])
    p.end()
    return QIcon(pixmap)
