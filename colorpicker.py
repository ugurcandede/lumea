"""Embedded visual color picker: a saturation/value square + a hue bar.

Self-contained: shows its own swatch + hex readout and emits `colorChanged`
on every move (click or drag). The host debounces the actual BLE writes.
"""

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class _SVSquare(QWidget):
    """Saturation (x: 0->255) by Value (y: 255->0) for a fixed hue."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedSize(220, 180)
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
        w, h = self.width(), self.height()
        sat = QLinearGradient(0, 0, w, 0)
        sat.setColorAt(0.0, QColor(255, 255, 255))
        sat.setColorAt(1.0, QColor.fromHsv(self._hue, 255, 255))
        p.fillRect(self.rect(), QBrush(sat))
        val = QLinearGradient(0, 0, 0, h)
        val.setColorAt(0.0, QColor(0, 0, 0, 0))
        val.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(self.rect(), QBrush(val))
        x = self._sat / 255 * w
        y = (1 - self._val / 255) * h
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawEllipse(QPointF(x, y), 7, 7)
        p.setPen(QPen(QColor(0, 0, 0), 2))
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
        self.setFixedSize(26, 180)
        self._hue = 0

    def hue(self):
        return self._hue

    def set_hue(self, hue):
        self._hue = hue
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        grad = QLinearGradient(0, 0, 0, h)
        for i in range(7):
            grad.setColorAt(i / 6, QColor.fromHsv(round(359 * i / 6), 255, 255))
        p.fillRect(self.rect(), QBrush(grad))
        y = int(self._hue / 359 * h)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawLine(0, y, w, y)

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
        self._swatch = QLabel()
        self._swatch.setFixedHeight(26)
        self._hex = QLabel()
        self._sv.changed.connect(self._emit)
        self._bar.changed.connect(self._on_hue)

        top = QHBoxLayout()
        top.addWidget(self._sv)
        top.addWidget(self._bar)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(top)
        root.addWidget(self._swatch)
        root.addWidget(self._hex)

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
        c = self.color()
        self._swatch.setStyleSheet(f"background:{c.name()}; border:1px solid #444;")
        self._hex.setText(
            f"{c.name()}    R{c.red()} G{c.green()} B{c.blue()}    "
            f"H{max(c.hue(), 0)} S{c.saturation()} V{c.value()}"
        )
        self.colorChanged.emit(c)
