"""Embedded visual color picker: a saturation/value square + a hue bar.

Emits `colorChanged` on every move (click or drag); the host debounces the
actual BLE writes. Both surfaces are painted with rounded corners and, when
the widget is disabled (no live strip to edit), as flat inset panels in the
theme's colours.
"""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

import theme

HEIGHT = 150
RADIUS = 10


def _clip(p, w, h, radius):
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.setClipPath(path)


def _flat(p, w, h):
    # Disabled look: a quiet inset panel instead of a greyed rainbow.
    p.fillRect(0, 0, w, h, QColor(theme.current["inset"]))


class _SVSquare(QWidget):
    """Saturation (x: 0->255) by Value (y: 255->0) for a fixed hue."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedHeight(HEIGHT)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._hue = 0
        self._sat = 0
        self._val = 255

    def sat(self):
        return self._sat

    def val(self):
        return self._val

    def set_hue(self, hue):
        self._hue = hue
        self.update()

    def set_sv(self, sat, val):
        self._sat, self._val = sat, val
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        _clip(p, w, h, RADIUS)
        if not self.isEnabled():
            _flat(p, w, h)
            return
        sat = QLinearGradient(0, 0, w, 0)
        sat.setColorAt(0.0, QColor(255, 255, 255))
        sat.setColorAt(1.0, QColor.fromHsv(self._hue, 255, 255))
        p.fillRect(self.rect(), QBrush(sat))
        val = QLinearGradient(0, 0, 0, h)
        val.setColorAt(0.0, QColor(0, 0, 0, 0))
        val.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(self.rect(), QBrush(val))
        p.setClipping(False)
        x = self._sat / 255 * w
        y = (1 - self._val / 255) * h
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 115), 1))
        p.drawEllipse(QPointF(x, y), 7.5, 7.5)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawEllipse(QPointF(x, y), 6, 6)

    def mousePressEvent(self, event):
        self._pick(event)

    def mouseMoveEvent(self, event):
        self._pick(event)

    def _pick(self, event):
        w, h = self.width(), self.height()
        x = min(max(event.position().x(), 0), w)
        y = min(max(event.position().y(), 0), h)
        self._sat = round(x / w * 255)
        self._val = round((1 - y / h) * 255)
        self.update()
        self.changed.emit()


class _HueBar(QWidget):
    """Vertical rainbow strip selecting hue 0-359."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedSize(18, HEIGHT)
        self._hue = 0

    def hue(self):
        return self._hue

    def set_hue(self, hue):
        self._hue = hue
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        _clip(p, w, h, w / 2)
        if not self.isEnabled():
            _flat(p, w, h)
            return
        grad = QLinearGradient(0, 0, 0, h)
        for i in range(7):
            grad.setColorAt(i / 6, QColor.fromHsv(round(359 * i / 6), 255, 255))
        p.fillRect(self.rect(), QBrush(grad))
        p.setClipping(False)
        y = self._hue / 359 * h
        marker = QRectF(-2, y - 2.5, w + 4, 5)
        p.setPen(QPen(QColor(0, 0, 0, 115), 1))
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(marker, 2.5, 2.5)

    def mousePressEvent(self, event):
        self._pick(event)

    def mouseMoveEvent(self, event):
        self._pick(event)

    def _pick(self, event):
        h = self.height()
        y = min(max(event.position().y(), 0), h)
        self._hue = round(y / h * 359)
        self.update()
        self.changed.emit()


class ColorPicker(QWidget):
    colorChanged = Signal(QColor)

    def __init__(self):
        super().__init__()
        self._sv = _SVSquare()
        self._bar = _HueBar()
        self._sv.changed.connect(self._emit)
        self._bar.changed.connect(self._on_hue)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self._sv)
        row.addWidget(self._bar)

    def color(self):
        return QColor.fromHsv(self._bar.hue(), self._sv.sat(), self._sv.val())

    def set_color(self, c):
        hue = c.hue() if c.hue() >= 0 else 0  # -1 == achromatic; keep a real hue
        self._bar.set_hue(hue)
        self._sv.set_hue(hue)
        self._sv.set_sv(c.saturation(), c.value())
        self._emit()

    def _on_hue(self):
        self._sv.set_hue(self._bar.hue())
        self._emit()

    def _emit(self):
        self.colorChanged.emit(self.color())
