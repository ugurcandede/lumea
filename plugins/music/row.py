"""The Music row in the editor, under Effect: Off plus one chip per mode and a
preview dot, then, while a mode runs, the Sensitivity slider and the Low / Mid /
High faders. The widgets carry the same object names as the app's own rows
(chip, sectionLabel, value, brightness), so the app's stylesheet styles them."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from .engine import BANDS, MODES

_TIPS = {
    "low": "Bass, 20-250 Hz (red in Spectrum): turn it down if the bass drowns out the rest",
    "mid": "Mids, 250 Hz-2 kHz (green in Spectrum): vocals and most instruments",
    "high": "Treble, 2-8 kHz (blue in Spectrum): hi-hats and cymbals",
}


class Row(QWidget):
    def __init__(self, plugin):
        super().__init__()
        self._plugin = plugin

        chips = QHBoxLayout()
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(6)
        chips.addWidget(_label("Music", "sectionLabel", 48))
        self._chips = {}
        for mode in (None,) + MODES:
            chip = QPushButton("Off" if mode is None else mode.capitalize())
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _c=False, m=mode: plugin.set_mode(m))
            self._chips[mode] = chip
            chips.addWidget(chip)
        chips.addStretch()
        self._preview = _Dot()
        self._preview.setToolTip("What the lights show right now")
        policy = self._preview.sizePolicy()
        policy.setRetainSizeWhenHidden(True)   # keep the chips still when it appears
        self._preview.setSizePolicy(policy)
        chips.addWidget(self._preview)

        self._sensitivity, self._sensitivity_value = _slider(Qt.Orientation.Horizontal)
        self._sensitivity.setToolTip("How loud the music must be to light up fully: higher reacts to quieter sounds")
        self._sensitivity.valueChanged.connect(plugin.set_sensitivity)
        sens = QHBoxLayout()
        sens.setContentsMargins(0, 0, 0, 0)
        sens.setSpacing(10)
        sens.addWidget(_label("Sensitivity", "sectionLabel", 64))
        sens.addWidget(self._sensitivity, 1)
        sens.addWidget(self._sensitivity_value)
        self._sens_row = QWidget()
        self._sens_row.setLayout(sens)

        # Low / Mid / High: three faders side by side, like an equaliser.
        self._faders = []
        faders = QHBoxLayout()
        faders.setContentsMargins(0, 0, 0, 0)
        faders.setSpacing(10)
        for band in BANDS:
            slider, readout = _slider(Qt.Orientation.Vertical)
            slider.setFixedHeight(72)
            slider.setToolTip(_TIPS[band])
            slider.valueChanged.connect(lambda v, b=band: plugin.set_band(b, v))
            readout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            name = _label(band.capitalize(), "sectionLabel")
            name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(4)
            col.addWidget(readout)
            col.addWidget(slider, 0, Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(name)
            faders.addLayout(col, 1)
            self._faders.append((slider, readout))
        self._bands_row = QWidget()
        self._bands_row.setLayout(faders)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addLayout(chips)
        lay.addWidget(self._sens_row)
        lay.addWidget(self._bands_row)
        # A bound method of this widget: Qt drops the connection when the row is deleted.
        plugin.api.frame.connect(self._show_frame)
        self.refresh()

    def refresh(self):
        p = self._plugin
        for mode, chip in self._chips.items():
            chip.setChecked(mode == p.mode)
        running = p.mode is not None
        self._preview.setVisible(running)
        self._sens_row.setVisible(running)
        self._bands_row.setVisible(running)
        _set(self._sensitivity, self._sensitivity_value, p.sensitivity)
        for (slider, readout), value in zip(self._faders, p.bands):
            _set(slider, readout, value)

    def _show_frame(self, color):
        self._preview.set_color(color)


class _Dot(QLabel):
    """Filled circle showing the colour being sent, ringed so black still reads."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(16, 16)
        self._color = None

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event):
        if self._color is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._color)
        p.setPen(QPen(QColor(128, 128, 128, 128), 1))
        p.drawEllipse(QRectF(0.5, 0.5, 15, 15))


def _label(text, name, width=None):
    label = QLabel(text)
    label.setObjectName(name)
    if width is not None:
        label.setFixedWidth(width)
    return label


def _slider(orientation):
    """A 1-100 slider in the app's style, with its readout label."""
    slider = QSlider(orientation)
    slider.setObjectName("brightness")
    slider.setRange(1, 100)
    slider.setCursor(Qt.CursorShape.PointingHandCursor)
    readout = _label("", "value", 34)
    readout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return slider, readout


def _set(slider, readout, value):
    slider.blockSignals(True)              # a remote change must not echo back as a command
    slider.setValue(value)
    slider.blockSignals(False)
    readout.setText(f"{value}%")
