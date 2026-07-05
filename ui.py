"""Qt UI for Lumea -- the ELK-BLEDOM / MELK LED strip controller.

All BLE work goes through ble.DeviceManager and runs on the qasync event loop via
@asyncSlot -- no worker threads. The device never reports state back, so the UI
is optimistic: what it shows is the last command sent, not a readback.

Multiple strips can be controlled at once: tick devices in the list, connect the
ticked ones, and power/color commands fan out to every ticked-and-connected
device. Brightness is the V axis of the color picker (the actual RGB is sent).
"""

import asyncio
import json
import logging

from PySide6.QtCore import Qt, QSettings, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

import ble
import colorpicker
import icon
import msi_mystic

log = logging.getLogger(__name__)

RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_S = 3.0
COLOR_DEBOUNCE_MS = 80
EFFECT_INTERVAL_MS = 80
EFFECT_MIN_STEP = 0.004        # hue advance/tick at Speed 1 (~20 s per rainbow cycle)
EFFECT_MAX_STEP = 0.05         # at Speed 100 (~1.6 s per cycle)
DEFAULT_EFFECT_SPEED = 30
DEFAULT_COLOR = QColor(255, 255, 255)
DEFAULT_BRIGHTNESS = 100
DEFAULT_PRESETS = [
    "#ff0000", "#ff7a00", "#ffd400", "#7ed321", "#00c000", "#00c9a4",
    "#00bcd4", "#2563eb", "#7e22ce", "#ec4899", "#ff8a3d", "#ffffff",
]
PRESET_COLUMNS = 6
MSI_CARD_ID = "msi-mystic-light"
MSI_CARD_NAME = "MSI Mystic Light"
MSI_CARD_SUB = "Motherboard · USB"


def _repolish(widget):
    """Re-evaluate the stylesheet after a dynamic property change."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _card_shadow(widget):
    """Soft drop shadow so white cards float on the grey page (figure/ground)."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(34)
    shadow.setColor(QColor(30, 41, 59, 60))
    shadow.setOffset(0, 12)
    widget.setGraphicsEffect(shadow)


class _DeviceCard(QFrame):
    """One strip as an inset row: a checkbox (= in the control group, tinted blue
    when ticked), the name/address, and a connection chip. Double-click to rename."""

    toggled = Signal(str, bool)
    renameRequested = Signal(str)

    def __init__(self, address, name, checked, sub=None):
        super().__init__()
        self.setObjectName("deviceRow")
        self._address = address
        self.setProperty("selected", "true" if checked else "false")

        self._check = QCheckBox()
        self._check.setChecked(checked)  # set before connecting: no spurious emit
        self._check.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check.toggled.connect(self._on_check)

        self._name = QLabel(name)
        self._name.setObjectName("cardTitle")
        self._sub = QLabel(sub if sub is not None else address)
        self._sub.setObjectName("cardSub")
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        text.addWidget(self._name)
        text.addWidget(self._sub)

        self._chip = QLabel()
        self._chip.setObjectName("chip")

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        row.addWidget(self._check)
        row.addLayout(text, 1)
        row.addWidget(self._chip)
        self._row = row

        # Vertical outer so an effect can add an expandable area below the row.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 13, 16, 13)
        outer.setSpacing(10)
        outer.addLayout(row)
        self._outer = outer

        self.set_connected(False)

    def _on_check(self, checked):
        self.setProperty("selected", "true" if checked else "false")
        _repolish(self)
        self.toggled.emit(self._address, checked)

    def set_name(self, name):
        self._name.setText(name)

    def set_connected(self, on):
        self._chip.setText("Connected" if on else "Offline")
        self._chip.setProperty("connected", "true" if on else "false")
        _repolish(self._chip)

    def mouseDoubleClickEvent(self, _event):
        self.renameRequested.emit(self._address)

    def set_effect_menu(self, mode, callback, speed, speed_callback):
        """Static/Rainbow dropdown on the row + a Speed slider below it, shown
        only while Rainbow is selected. callback(mode) / speed_callback(value)."""
        self._effect_mode = mode
        self._effect_cb = callback
        self._speed_cb = speed_callback

        self._effect_btn = QPushButton(f"{mode.capitalize()} ▾")
        self._effect_btn.setObjectName("effectMenu")
        self._effect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._effect_btn.clicked.connect(self._open_effect_menu)
        self._row.insertWidget(self._row.count() - 1, self._effect_btn)  # before the chip

        speed_label = QLabel("Speed")
        speed_label.setObjectName("cardSub")
        self._speed_value = QLabel(f"{speed}%")
        self._speed_value.setObjectName("cardSub")
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(speed_label)
        head.addStretch()
        head.addWidget(self._speed_value)

        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setObjectName("brightness")   # reuse the slider style
        self._speed_slider.setRange(1, 100)
        self._speed_slider.setValue(speed)
        self._speed_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._speed_slider.valueChanged.connect(self._on_speed)

        speed_box = QVBoxLayout()
        speed_box.setContentsMargins(0, 0, 0, 0)
        speed_box.setSpacing(6)
        speed_box.addLayout(head)
        speed_box.addWidget(self._speed_slider)
        self._speed_area = QWidget()
        self._speed_area.setLayout(speed_box)
        self._speed_area.setVisible(mode == "rainbow")
        self._outer.addWidget(self._speed_area)

    def _on_speed(self, value):
        self._speed_value.setText(f"{value}%")
        self._speed_cb(value)

    def _open_effect_menu(self):
        menu = QMenu(self)
        for label, mode in (("Static", "static"), ("Rainbow", "rainbow")):
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self._effect_mode == mode)
            act.triggered.connect(lambda _checked=False, m=mode: self._select_effect(m))
        menu.exec(self._effect_btn.mapToGlobal(self._effect_btn.rect().bottomLeft()))

    def _select_effect(self, mode):
        if mode == self._effect_mode:
            return
        self._effect_mode = mode
        self._effect_btn.setText(f"{mode.capitalize()} ▾")
        self._speed_area.setVisible(mode == "rainbow")
        self._effect_cb(mode)


class _TitleBar(QWidget):
    """Drag area for the frameless window: press-and-drag relocates the window.
    Presses on child buttons are consumed by them, so only empty areas drag."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
            event.accept()


class LedController(QWidget):
    def __init__(self, close_event):
        super().__init__()
        self.setWindowTitle("Lumea")
        # Frameless: we draw our own title bar (see _build_header). Stays a normal
        # top-level window (taskbar entry); fixed-size, so no resize/maximise.
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)

        self._close_event = close_event
        self._settings = QSettings()
        self._manager = ble.DeviceManager(on_disconnect=self._on_device_disconnect)
        self._msi = msi_mystic.open_controller()  # None unless an MSI board is present
        self._desired: set[str] = set()       # addresses we want connected
        self._reconnecting: set[str] = set()
        self._cards: dict[str, _DeviceCard] = {}
        self._msi_card = None
        self._power_on = False                 # optimistic: last command sent
        self._msi_effect = "static"            # MSI mode: "static" (picker) or "rainbow"
        self._effect_hue = 0.0
        self._effect_timer = QTimer(self)
        self._effect_timer.setInterval(EFFECT_INTERVAL_MS)
        self._effect_timer.timeout.connect(self._effect_tick)
        self._closing = False

        self._load_state()
        self._base_color = self._load_color()

        self._build_ui()
        self._setup_tray()
        self._rebuild_list()
        self._update_controls_visibility()

        # Reconnect to whatever was ticked last session.
        if self._selected:
            self._desired = set(self._selected)
            asyncio.ensure_future(self._connect_many(list(self._desired)))

        # Restore the MSI motherboard to the last colour if sync was left on.
        if self._msi is not None and self._msi_sync:
            self._push_msi_color()

    # ---- construction ----------------------------------------------------

    def _build_ui(self):
        self.setObjectName("root")

        # Everything lives in a fixed-width column so wrap-able labels can never
        # widen the window; the outer SetFixedSize then pins width and fits height.
        content = QWidget()
        content.setFixedWidth(520)
        col = QVBoxLayout(content)
        col.setContentsMargins(20, 20, 20, 16)
        col.setSpacing(16)
        col.addWidget(self._build_header())
        col.addWidget(self._build_devices_card())
        col.addWidget(self._build_controls_card())

        self._status = QLabel("Ready. Run a scan to find your strips.")
        self._status.setObjectName("status")
        self._status.setWordWrap(True)
        col.addWidget(self._status)

        footer = QLabel(
            "<span>Developed by </span>"
            '<a href="https://github.com/ugurcandede">@ugurcandede</a>'
        )
        footer.setObjectName("footer")
        footer.setTextFormat(Qt.TextFormat.RichText)
        footer.setOpenExternalLinks(True)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(footer)

        root = QVBoxLayout(self)
        # Fixed-size: the window fits its content and can't be resized/maximised.
        root.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(content)

    def _build_header(self):
        # Our own title bar (the OS one is hidden): title + chip + window buttons,
        # and the whole strip is the drag handle for the frameless window.
        title = QLabel("Lumea")
        title.setObjectName("h1")
        subtitle = QLabel("LED strip control")
        subtitle.setObjectName("subtitle")
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(2)
        left.addWidget(title)
        left.addWidget(subtitle)

        self._conn_chip = QLabel("Not connected")
        self._conn_chip.setObjectName("chip")

        min_btn = QPushButton("–")  # en dash
        min_btn.setObjectName("winBtn")
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.setToolTip("Minimize")
        min_btn.clicked.connect(self.showMinimized)
        close_btn = QPushButton("✕")  # multiplication x
        close_btn.setObjectName("winClose")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close to tray")
        close_btn.clicked.connect(self.close)

        bar = _TitleBar()
        bar.setObjectName("titleBar")
        header = QHBoxLayout(bar)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addLayout(left)
        header.addStretch()
        header.addWidget(self._conn_chip, 0, Qt.AlignmentFlag.AlignTop)
        header.addSpacing(4)
        header.addWidget(min_btn, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)
        return bar

    def _build_devices_card(self):
        # Inset device rows live in a (rarely-scrolling) column.
        self._device_container = QWidget()
        self._device_vbox = QVBoxLayout(self._device_container)
        self._device_vbox.setContentsMargins(0, 0, 0, 0)
        self._device_vbox.setSpacing(8)
        self._device_vbox.addStretch()

        scroll = QScrollArea()
        scroll.setObjectName("deviceScroll")
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._device_container)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._device_scroll = scroll

        hint = QLabel("Check the strips you want to control · double-click to rename")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        self._scan_btn = QPushButton("Scan")
        self._scan_btn.setObjectName("pill")
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.clicked.connect(self._on_scan)
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setObjectName("primary")
        self._connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._connect_btn.clicked.connect(self._on_connect_selected)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setObjectName("pill")
        self._disconnect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._disconnect_btn.clicked.connect(self._on_disconnect_all)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addWidget(self._scan_btn)
        btn_row.addWidget(self._connect_btn, 1)
        btn_row.addWidget(self._disconnect_btn)

        card = QFrame()
        card.setObjectName("card")
        _card_shadow(card)
        box = QVBoxLayout(card)
        box.setContentsMargins(20, 18, 20, 20)
        box.setSpacing(12)
        label = QLabel("Devices")
        label.setObjectName("fieldLabel")
        box.addWidget(label)
        box.addWidget(scroll)
        box.addWidget(hint)
        box.addLayout(btn_row)
        return card

    def _build_controls_card(self):
        # Compact power toggle, then a full-width colour editor with a small
        # active-colour readout, then the preset grid.
        self._power_btn = QPushButton()
        self._power_btn.setObjectName("power")
        self._power_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._power_btn.clicked.connect(self._on_power_toggle)

        self._color_timer = QTimer(self)
        self._color_timer.setSingleShot(True)
        self._color_timer.setInterval(COLOR_DEBOUNCE_MS)
        self._color_timer.timeout.connect(self._on_color_timeout)

        self._picker = colorpicker.ColorPicker(show_preview=False)
        self._picker.set_color(self._base_color)  # before connecting: no spurious send
        self._picker.colorChanged.connect(self._on_picker_changed)

        # Power row: label left, the compact toggle right (mirrors the Color row).
        power_label = QLabel("Power")
        power_label.setObjectName("fieldLabel")
        power_row = QHBoxLayout()
        power_row.addWidget(power_label)
        power_row.addStretch()
        power_row.addWidget(self._power_btn)

        # Colour row: label, then the active swatch + an editable hex field.
        self._swatch = QFrame()
        self._swatch.setObjectName("swatch")
        self._swatch.setFixedSize(46, 26)
        self._hex_input = QLineEdit()
        self._hex_input.setObjectName("hexInput")
        self._hex_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hex_input.setMaxLength(7)
        self._hex_input.setToolTip("Type a hex colour, e.g. #33C9A4, and press Enter")
        self._hex_input.returnPressed.connect(self._apply_hex_input)
        self._hex_input.editingFinished.connect(self._apply_hex_input)
        color_label = QLabel("Color")
        color_label.setObjectName("fieldLabel")
        color_head = QHBoxLayout()
        color_head.setSpacing(10)
        color_head.addWidget(color_label)
        color_head.addStretch()
        color_head.addWidget(self._swatch)
        color_head.addWidget(self._hex_input)

        self._controls = QFrame()
        self._controls.setObjectName("card")
        _card_shadow(self._controls)
        box = QVBoxLayout(self._controls)
        box.setContentsMargins(20, 18, 20, 20)
        box.setSpacing(14)
        box.addLayout(power_row)
        box.addLayout(color_head)
        box.addWidget(self._picker)
        box.addLayout(self._build_brightness())
        box.addLayout(self._build_presets())

        self._update_power_visual()
        self._update_hero(self._base_color)
        return self._controls

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            return
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._tray_icon())
        self._tray.setToolTip("Lumea")
        menu = QMenu()
        menu.addAction("Show / Hide", self._toggle_window)
        menu.addAction("On", self._on_power_on)
        menu.addAction("Off", self._on_power_off)
        menu.addSeparator()
        color_icon_action = menu.addAction("Color tray icon")
        color_icon_action.setCheckable(True)
        color_icon_action.setChecked(self._tray_color_icon)
        color_icon_action.toggled.connect(self._on_toggle_tray_color_icon)
        menu.addSeparator()
        menu.addAction("Quit", self._quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _tray_icon(self):
        # App icon by default; the colored dot reflecting the strip color is opt-in.
        return icon.make_icon(self._base_color) if self._tray_color_icon else icon.app_icon()

    def _on_toggle_tray_color_icon(self, checked):
        self._tray_color_icon = checked
        if self._tray is not None:
            self._tray.setIcon(self._tray_icon())
        self._save_state()

    # ---- device list -----------------------------------------------------

    def _display(self, address):
        return self._aliases.get(address) or self._known.get(address) or address

    def _rebuild_list(self):
        # Drop every existing card, then rebuild: the MSI controller first (if
        # present), then the BLE strips sorted by display name.
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()
        self._msi_card = None
        while self._device_vbox.count() > 1:  # keep the trailing stretch
            item = self._device_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._known and self._msi is None:
            empty = QLabel("No devices yet. Run a scan.")
            empty.setObjectName("hint")
            self._device_vbox.insertWidget(0, empty)
            self._fit_device_scroll()
            return

        count = 0
        if self._msi is not None:
            # A local USB device: always "connected", no scan/connect needed. Its
            # checkbox is the colour-mirror toggle (ticked = in the control group).
            self._msi_card = _DeviceCard(MSI_CARD_ID, MSI_CARD_NAME, self._msi_sync, MSI_CARD_SUB)
            self._msi_card.toggled.connect(lambda _a, checked: self._on_msi_sync_toggled(checked))
            self._msi_card.set_effect_menu(
                self._msi_effect, self._on_msi_effect_changed,
                self._effect_speed, self._on_speed_changed,
            )
            self._msi_card.set_connected(True)
            self._device_vbox.insertWidget(self._device_vbox.count() - 1, self._msi_card)

        for address in sorted(self._known, key=lambda a: self._display(a).lower()):
            card = _DeviceCard(address, self._display(address), address in self._selected)
            card.toggled.connect(self._on_card_toggled)
            card.renameRequested.connect(self._on_card_rename)
            card.set_connected(self._manager.is_connected(address))
            self._cards[address] = card
            self._device_vbox.insertWidget(self._device_vbox.count() - 1, card)
        self._fit_device_scroll()

    def _fit_device_scroll(self):
        # QScrollArea won't size to its content; fit it to the rows, then scroll
        # past a cap so a long list can't take over the window. The MSI card is
        # taller while it shows the rainbow speed slider.
        row_h, gap, cap = 66, 8, 5
        count = len(self._known) + (1 if self._msi is not None else 0)
        shown = min(max(count, 1), cap)
        extra = 56 if (self._msi is not None and self._msi_effect == "rainbow") else 0
        self._device_scroll.setFixedHeight(shown * row_h + (shown - 1) * gap + extra)

    def _refresh_row(self, address):
        card = self._cards.get(address)
        if card is not None:
            card.set_name(self._display(address))
            card.set_connected(self._manager.is_connected(address))
        self._update_controls_visibility()

    def _update_controls_visibility(self):
        # Power + colour need a live BLE link; but when an MSI controller is present
        # the colour editor is useful on its own (it can drive the motherboard).
        connected = self._manager.connected_addresses()
        count = len(connected) + (1 if self._msi is not None else 0)
        self._controls.setVisible(bool(connected) or self._msi is not None)
        self._conn_chip.setText(f"{count} connected" if count else "Not connected")
        self._conn_chip.setProperty("connected", "true" if count else "false")
        _repolish(self._conn_chip)

    def _on_card_toggled(self, address, checked):
        if checked:
            self._selected.add(address)
        else:
            self._selected.discard(address)
        self._save_state()

    def _on_card_rename(self, address):
        current = self._aliases.get(address, self._known.get(address, ""))
        text, ok = QInputDialog.getText(self, "Alias", f"Name for {address}:", text=current)
        if not ok:
            return
        text = text.strip()
        if text:
            self._aliases[address] = text
        else:
            self._aliases.pop(address, None)
        self._save_state()
        self._refresh_row(address)

    # ---- color -----------------------------------------------------------

    def _on_picker_changed(self, color):
        self._base_color = color
        self._update_hero(color)
        self._color_timer.start()  # debounced send + tray icon update

    def _update_hero(self, color):
        self._swatch.setStyleSheet(
            f"background:{color.name()}; border:1px solid rgba(0,0,0,0.10);"
            " border-radius:8px;"
        )
        # setText() doesn't fire returnPressed/editingFinished, so no feedback loop.
        self._hex_input.setText(color.name().upper())

    def _apply_hex_input(self):
        text = self._hex_input.text().strip().lstrip("#")
        color = QColor(f"#{text}")
        if len(text) == 6 and color.isValid() and color.rgb() != self._base_color.rgb():
            self._picker.set_color(color)  # -> _on_picker_changed: updates + sends
        else:
            self._update_hero(self._base_color)  # invalid/unchanged: restore readout

    # ---- brightness ------------------------------------------------------

    def _build_brightness(self):
        # Master dimmer: scales the picked colour client-side (scaled_color).
        # Independent of the picker's V axis, which also dims -- the two compound.
        label = QLabel("Brightness")
        label.setObjectName("fieldLabel")
        self._brightness_value = QLabel(f"{self._brightness}%")
        self._brightness_value.setObjectName("cardSub")
        head = QHBoxLayout()
        head.addWidget(label)
        head.addStretch()
        head.addWidget(self._brightness_value)

        self._brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self._brightness_slider.setObjectName("brightness")
        self._brightness_slider.setRange(0, 100)
        self._brightness_slider.setValue(self._brightness)
        self._brightness_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._brightness_slider.valueChanged.connect(self._on_brightness_changed)

        box = QVBoxLayout()
        box.setSpacing(8)
        box.addLayout(head)
        box.addWidget(self._brightness_slider)
        return box

    def _on_brightness_changed(self, value):
        self._brightness = value
        self._brightness_value.setText(f"{value}%")
        self._color_timer.start()  # debounced send, same path as colour changes

    def _on_speed_changed(self, value):
        self._effect_speed = value

    # ---- color presets ---------------------------------------------------

    def _build_presets(self):
        # A grid of equal-width colour pills under a field label.
        self._preset_btns = []
        box = QVBoxLayout()
        box.setSpacing(8)
        presets_label = QLabel("Presets")
        presets_label.setObjectName("fieldLabel")
        box.addWidget(presets_label)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i in range(len(self._presets)):
            btn = QPushButton()
            btn.setFixedHeight(30)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, idx=i: self._apply_preset(idx))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda _pos, idx=i: self._save_preset(idx))
            self._preset_btns.append(btn)
            grid.addWidget(btn, i // PRESET_COLUMNS, i % PRESET_COLUMNS)
        box.addLayout(grid)
        self._refresh_presets()
        return box

    def _refresh_presets(self):
        for btn, hex_color in zip(self._preset_btns, self._presets):
            btn.setStyleSheet(
                f"QPushButton {{ background:{hex_color}; border:1px solid #D6DCE5;"
                "  border-radius:10px; }"
                "QPushButton:hover { border:2px solid #2563EB; }"
            )
            btn.setToolTip(f"{hex_color}  ·  left-click: apply · right-click: save current")

    def _apply_preset(self, index):
        color = QColor(self._presets[index])
        if not color.isValid():
            return
        self._picker.set_color(color)  # emits colorChanged -> _on_picker_changed

    def _save_preset(self, index):
        self._presets[index] = self._base_color.name()
        self._refresh_presets()
        self._save_state()
        self._set_status(f"Saved to slot {index + 1}: {self._base_color.name()}")

    @asyncSlot()
    async def _on_color_timeout(self):
        await self._send_base_color()

    async def _send_base_color(self):
        if self._tray is not None and self._tray_color_icon:
            self._tray.setIcon(self._tray_icon())
        self._push_msi_color()  # mirror to the motherboard even with no BLE target
        targets = [a for a in self._selected if self._manager.is_connected(a)]
        if not targets:
            return
        c = self._base_color
        b = self._brightness
        results = await self._manager.apply(
            targets, lambda d: d.set_color(c.red(), c.green(), c.blue(), b)
        )
        failed = [a for a, exc in results.items() if exc is not None]
        if failed:
            self._set_status(f"Color send failed: {', '.join(self._display(a) for a in failed)}")

    # ---- rainbow effect --------------------------------------------------

    def _on_msi_effect_changed(self, mode):
        self._set_msi_effect(mode)

    def _set_msi_effect(self, mode):
        self._msi_effect = mode
        self._fit_device_scroll()                  # the card grew/shrank its speed slider
        if mode == "rainbow":
            hue = self._base_color.hueF()          # continue from the current colour
            self._effect_hue = hue if hue >= 0 else 0.0
            if self._msi_sync:
                self._effect_timer.start()
        else:                                      # static: hand MSI back to the picker
            self._effect_timer.stop()
            self._push_msi_color()

    def _effect_step(self):
        # Map Speed 1..100 to the hue advance per tick.
        return EFFECT_MIN_STEP + (self._effect_speed - 1) / 99 * (EFFECT_MAX_STEP - EFFECT_MIN_STEP)

    def _effect_tick(self):
        # MSI-only software rainbow: stream a hue sweep to the motherboard while the
        # BLE strips keep the picker colour.
        if self._msi is None or not self._msi_sync:
            return
        self._effect_hue = (self._effect_hue + self._effect_step()) % 1.0
        color = QColor.fromHsvF(self._effect_hue, 1.0, 1.0)
        try:
            self._msi.set_color(color.red(), color.green(), color.blue(), self._brightness)
        except Exception:
            log.exception("MSI effect send failed")

    def _on_msi_sync_toggled(self, checked):
        self._msi_sync = checked
        self._save_state()
        if not checked:
            self._effect_timer.stop()
            return
        if self._msi_effect == "rainbow":
            self._effect_timer.start()
        else:
            self._push_msi_color()  # apply the current colour right away

    def _push_msi_color(self):
        # Static path: drive MSI from the picker only when it isn't running rainbow.
        if self._msi is None or not self._msi_sync or self._msi_effect != "static":
            return
        c = self._base_color
        try:
            self._msi.set_color(c.red(), c.green(), c.blue(), self._brightness)
        except Exception:
            log.exception("MSI color send failed")
            self._set_status("MSI motherboard: color send failed.")

    # ---- scan / connect --------------------------------------------------

    @asyncSlot()
    async def _on_scan(self):
        self._scan_btn.setEnabled(False)
        self._set_status("Scanning...")
        try:
            devices = await ble.scan(timeout=5.0)
        except Exception as e:  # Bluetooth off, adapter busy, etc.
            self._set_status(f"Scan error: {e}")
            log.exception("scan failed")
            return
        finally:
            self._scan_btn.setEnabled(True)

        for d in devices:
            self._known[d.address] = d.name
        self._rebuild_list()
        self._save_state()
        self._set_status(
            f"{len(devices)} device(s) found." if devices
            else "No devices found."
        )

    @asyncSlot()
    async def _on_connect_selected(self):
        targets = list(self._selected)
        if not targets:
            self._set_status("Tick a device in the list first.")
            return
        self._desired |= set(targets)
        await self._connect_many(targets)

    async def _connect_many(self, addresses):
        await asyncio.gather(*(self._connect_one(a) for a in addresses))
        connected = sum(self._manager.is_connected(a) for a in addresses)
        self._set_status(f"{connected}/{len(addresses)} device(s) connected.")

    async def _connect_one(self, address):
        if self._manager.is_connected(address):
            return
        try:
            await self._manager.connect(address)
        except Exception as e:
            self._set_status(f"{self._display(address)}: connection failed ({e})")
            log.exception("connect failed for %s", address)
            return
        self._refresh_row(address)

    @asyncSlot()
    async def _on_disconnect_all(self):
        # Disconnect every connected device (checked or not) so nothing is orphaned.
        targets = list(self._manager.connected_addresses())
        self._desired.clear()
        await asyncio.gather(
            *(self._manager.disconnect(a) for a in targets), return_exceptions=True
        )
        for address in targets:
            self._refresh_row(address)
        self._set_status("All devices disconnected.")

    def _on_device_disconnect(self, address):
        # Called by the manager when a link drops (wanted or not).
        self._refresh_row(address)
        if address in self._desired and not self._closing:
            self._set_status(f"{self._display(address)}: link dropped, reconnecting...")
            asyncio.ensure_future(self._reconnect(address))

    async def _reconnect(self, address):
        if address in self._reconnecting:
            return
        self._reconnecting.add(address)
        try:
            for attempt in range(1, RECONNECT_ATTEMPTS + 1):
                if address not in self._desired:
                    return
                self._set_status(
                    f"{self._display(address)}: reconnecting ({attempt}/{RECONNECT_ATTEMPTS})..."
                )
                try:
                    await self._manager.connect(address)
                except Exception:
                    log.warning("reconnect attempt %d failed for %s", attempt, address)
                    await asyncio.sleep(RECONNECT_DELAY_S)
                    continue
                self._refresh_row(address)
                self._set_status(f"{self._display(address)}: reconnected.")
                return
            self._set_status(f"{self._display(address)}: reconnect failed.")
        finally:
            self._reconnecting.discard(address)

    # ---- broadcast control ----------------------------------------------

    async def _broadcast(self, action, ok_status):
        """Fan a command out to every checked-and-connected device. Returns True
        if it reached at least one device."""
        targets = [a for a in self._selected if self._manager.is_connected(a)]
        if not targets:
            self._set_status("No checked-and-connected device.")
            return False
        results = await self._manager.apply(targets, action)
        failed = [a for a, exc in results.items() if exc is not None]
        if failed:
            names = ", ".join(self._display(a) for a in failed)
            self._set_status(f"{len(targets) - len(failed)}/{len(targets)} applied. Failed: {names}")
        elif ok_status:
            self._set_status(f"{ok_status} ({len(targets)} device(s))")
        return len(failed) < len(targets)

    def _update_power_visual(self):
        self._power_btn.setText("On" if self._power_on else "Off")
        self._power_btn.setProperty("on", "true" if self._power_on else "false")
        _repolish(self._power_btn)

    async def _set_power(self, on):
        # No readback: keep an optimistic state and only adopt it if the send
        # actually reached a device.
        if await self._broadcast(
            lambda d: d.set_power(on), "Turned on." if on else "Turned off."
        ):
            self._power_on = on
            self._update_power_visual()

    @asyncSlot()
    async def _on_power_toggle(self):
        await self._set_power(not self._power_on)

    @asyncSlot()
    async def _on_power_on(self):
        await self._set_power(True)

    @asyncSlot()
    async def _on_power_off(self):
        await self._set_power(False)

    # ---- tray / window ---------------------------------------------------

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window()

    def _toggle_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _close_msi(self):
        if self._msi is not None:
            self._msi.close()

    def _quit(self):
        self._closing = True
        self._save_state()
        self._close_msi()
        self._close_event.set()

    def closeEvent(self, event):
        # With a tray, closing the window just hides it; the app keeps running.
        if self._tray is not None and not self._closing:
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "Lumea",
                "Still running in the tray. Quit via the tray menu.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            return
        self._closing = True
        self._save_state()
        self._close_msi()
        self._close_event.set()
        super().closeEvent(event)

    # ---- helpers / persistence ------------------------------------------

    def _set_status(self, text):
        self._status.setText(text)
        log.info("status: %s", text)

    def _load_color(self):
        color = QColor(self._settings.value("color", DEFAULT_COLOR.name()))
        return color if color.isValid() else QColor(DEFAULT_COLOR)

    def _load_state(self):
        self._known = json.loads(self._settings.value("known_json", "{}"))
        self._aliases = json.loads(self._settings.value("aliases_json", "{}"))
        self._selected = set(json.loads(self._settings.value("selected_json", "[]")))
        presets = json.loads(self._settings.value("presets_json", json.dumps(DEFAULT_PRESETS)))
        if len(presets) < len(DEFAULT_PRESETS):  # grow older saves to the new count
            presets += DEFAULT_PRESETS[len(presets):]
        self._presets = presets
        self._tray_color_icon = self._settings.value("tray_color_icon", False, type=bool)
        self._brightness = self._settings.value("brightness", DEFAULT_BRIGHTNESS, type=int)
        self._msi_sync = self._settings.value("msi_sync", False, type=bool)
        self._effect_speed = self._settings.value("effect_speed", DEFAULT_EFFECT_SPEED, type=int)

    def _save_state(self):
        self._settings.setValue("known_json", json.dumps(self._known))
        self._settings.setValue("aliases_json", json.dumps(self._aliases))
        self._settings.setValue("selected_json", json.dumps(list(self._selected)))
        self._settings.setValue("presets_json", json.dumps(self._presets))
        self._settings.setValue("color", self._base_color.name())
        self._settings.setValue("tray_color_icon", self._tray_color_icon)
        self._settings.setValue("brightness", self._brightness)
        self._settings.setValue("msi_sync", self._msi_sync)
        self._settings.setValue("effect_speed", self._effect_speed)
