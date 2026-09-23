"""Qt UI for Lumea -- the ELK-BLEDOM / MELK LED strip controller.

All BLE work goes through ble.DeviceManager and runs on the qasync event loop via
@asyncSlot -- no worker threads. The device never reports state back, so the UI
is optimistic: what it shows is the last command sent, not a readback.

One compact, frameless panel: an editor (target chips, picker, presets,
brightness + power) above the device list, plus a Settings page in the same
window. The UI is achromatic; the only colour on it is the one being sent.
"""

import asyncio
import json
import logging
import plistlib
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, Qt, QSettings, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFrame,
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
    QStackedLayout,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)
from qasync import asyncSlot

import analytics
import ble
import colorpicker
import icon
import msi_mystic
import steelseries
import theme

log = logging.getLogger(__name__)

RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_S = 3.0
COLOR_DEBOUNCE_MS = 80
# Colour ticks fire ~12x/s while dragging; coalesce their settings writes.
SAVE_DEBOUNCE_MS = 1000
# Drop the BLE links after this much idle so they stop contending with BT audio;
# the next command reconnects (see _wake). Local USB controllers are unaffected.
IDLE_DISCONNECT_MS = 60_000
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
PANEL_WIDTH = 400
DEVICE_ROWS_SHOWN = 4          # the list scrolls past this many rows
THEME_MODES = ("auto", "light", "dark")
GITHUB_URL = "https://github.com/ugurcandede/Lumea"
AUTHOR_URL = "https://github.com/ugurcandede"
SITE_URL = "https://ugurcandede.github.io/"


def _bluetooth_blocker():
    """macOS kills any process that touches Bluetooth unless its bundle's Info.plist
    carries NSBluetoothAlwaysUsageDescription. The packaged app has it (added in
    CI); a source run inherits the interpreter's bundle (Python.app), which
    doesn't. Returns the message to show instead of scanning, or None if clear."""
    if sys.platform != "darwin":
        return None
    exe = Path(QCoreApplication.applicationFilePath())
    plist = next((p / "Contents" / "Info.plist" for p in exe.parents
                  if (p / "Contents" / "Info.plist").is_file()), None)
    if plist is None:
        return None  # not inside a bundle; nothing to check
    try:
        with open(plist, "rb") as f:
            if "NSBluetoothAlwaysUsageDescription" in plistlib.load(f):
                return None
    except Exception:
        return None
    return (f"Bluetooth is blocked: {plist} has no NSBluetoothAlwaysUsageDescription, "
            "so macOS would kill the app on scan. One-time fix, then restart:\n"
            "plutil -insert NSBluetoothAlwaysUsageDescription -string "
            f"\"Lumea controls Bluetooth LED strips.\" \"{plist}\"")


def _repolish(widget):
    """Re-evaluate the stylesheet after a dynamic property change."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _rule():
    line = QFrame()
    line.setObjectName("rule")
    line.setFixedHeight(1)
    return line


def _label(text, name):
    lbl = QLabel(text)
    lbl.setObjectName(name)
    return lbl


def _button(text, name, slot=None, tooltip=None):
    btn = QPushButton(text)
    btn.setObjectName(name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot is not None:
        btn.clicked.connect(slot)
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


def _menu(parent=None):
    # Rounded, borderless popup so the QSS radius shows (no square frame behind it).
    menu = QMenu(parent)
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint
                        | Qt.WindowType.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return menu


class _Check(QAbstractButton):
    """16 px rounded checkbox painted from the theme (QSS can't draw the tick
    without an image asset)."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(16, 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event):
        t = theme.current
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.75, 0.75, 14.5, 14.5)
        if self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t["primary_bg"] if self.isEnabled() else t["disabled_bg"]))
            p.drawRoundedRect(r, 4.5, 4.5)
            p.setPen(QPen(QColor(t["primary_fg"] if self.isEnabled() else t["disabled_fg"]), 2,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPolyline([QPointF(3.6, 8.2), QPointF(6.7, 11.2), QPointF(12.4, 5.0)])
        else:
            p.setPen(QPen(QColor(t["line"] if self.isEnabled() else t["disabled_bg"]), 1.5))
            p.setBrush(QColor(t["panel"]))
            p.drawRoundedRect(r, 4.5, 4.5)


class _Switch(QAbstractButton):
    """36x20 toggle switch (Settings)."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(36, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event):
        t = theme.current
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["primary_bg"] if self.isChecked() else t["line"]))
        p.drawRoundedRect(QRectF(0, 0, 36, 20), 10, 10)
        p.setBrush(QColor(t["primary_fg"] if self.isChecked() else t["handle"]))
        x = 18 if self.isChecked() else 2
        p.drawEllipse(QRectF(x, 2, 16, 16))


class _Dot(QLabel):
    """Small filled circle whose colour is set at runtime (title-bar colour,
    row status)."""

    def __init__(self, size):
        super().__init__()
        self.setFixedSize(size, size)
        self._color = None

    def set_color(self, color):
        self._color = QColor(color) if color is not None else None
        self.update()

    def paintEvent(self, _event):
        if self._color is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(QRectF(0, 0, self.width(), self.height()))


class _ElideLabel(QLabel):
    """Single-line label that elides with '…' instead of forcing its row wider.
    Ignored width policy so a long address can't push a device row past the fixed
    window width (which would let the trackpad scroll the list horizontally)."""

    def __init__(self, text=""):
        super().__init__(text)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text):
        self._full = text
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        fm = self.fontMetrics()
        super().setText(fm.elidedText(self._full, Qt.TextElideMode.ElideRight, self.width()))


class _DeviceCard(QFrame):
    """One strip as an inset row: a checkbox (= in the control group), the
    name/address, and a status. Click to focus, double-click to rename."""

    toggled = Signal(str, bool)
    renameRequested = Signal(str)
    removeRequested = Signal(str)
    focusRequested = Signal(str)

    def __init__(self, address, name, checked, sub=None, removable=True):
        super().__init__()
        self.setObjectName("deviceRow")
        self._address = address
        self._removable = removable
        self._selected_pref = checked  # in the control group? (survives going stale)

        self._check = _Check()
        self._check.setChecked(checked)  # set before connecting: no spurious emit
        self._check.toggled.connect(self._on_check)

        self._name = _ElideLabel(name)
        self._name.setObjectName("rowName")
        self._sub = _ElideLabel(sub if sub is not None else address)
        self._sub.setObjectName("rowSub")
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        text.addWidget(self._name)
        text.addWidget(self._sub)

        self._status_dot = _Dot(7)
        self._status = _label("", "rowStatus")

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self._check)
        row.addLayout(text, 1)
        row.addWidget(self._status_dot)
        row.addWidget(self._status)
        self._row = row
        head = QWidget()
        head.setFixedHeight(40)
        head.setLayout(row)

        # Vertical outer so an effect can add an expandable area below the row.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 0, 12, 0)
        outer.setSpacing(0)
        outer.addWidget(head)
        self._outer = outer

        self.set_status(False)

    def _on_check(self, checked):
        self._selected_pref = checked
        self.toggled.emit(self._address, checked)

    def set_name(self, name):
        self._name.setText(name)

    def set_status(self, connected, in_range=True, selectable=True):
        # Three states: Connected (live GATT link), Offline (reachable but not
        # connected), Not in range (known but absent from the last scan -> dimmed).
        stale = not connected and not in_range
        state = "ok" if connected else "stale" if stale else "off"
        self._status.setText("Connected" if connected else "Offline" if in_range else "Not in range")
        self._status_dot.set_color(theme.current["ok_dot"] if connected else None)
        self._status_dot.setVisible(connected)
        if self._status.property("state") != state:
            self._status.setProperty("state", state)
            _repolish(self._status)
        # Only a strip confirmed present this session (connected or found by a scan)
        # can join the control group: otherwise lock the checkbox and show it
        # unticked, but keep the user's choice for when the strip turns up.
        want = self._selected_pref and selectable
        self._check.setEnabled(selectable)
        if self._check.isChecked() != want:
            self._check.blockSignals(True)   # display-only: don't mutate _selected
            self._check.setChecked(want)
            self._check.blockSignals(False)
        unavailable = "true" if stale else "false"
        if self.property("unavailable") != unavailable:
            self.setProperty("unavailable", unavailable)
            _repolish(self)

    def mousePressEvent(self, event):
        # Clicking the row body (not the checkbox, which eats its own clicks)
        # focuses this strip so the editor targets it. BLE rows only.
        if self._removable and event.button() == Qt.MouseButton.LeftButton:
            self.focusRequested.emit(self._address)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, _event):
        if self._removable:
            self.renameRequested.emit(self._address)

    def set_focused(self, on):
        value = "true" if on else "false"
        if self.property("focused") == value:
            return  # every card is asked on each focus change; repolish only the two that flip
        self.setProperty("focused", value)
        _repolish(self)

    def contextMenuEvent(self, event):
        # BLE rows only: forget a saved strip (locals are USB, always present).
        if not self._removable:
            return
        menu = _menu(self)
        menu.addAction("Rename…", lambda: self.renameRequested.emit(self._address))
        menu.addAction("Forget this strip", lambda: self.removeRequested.emit(self._address))
        menu.exec(event.globalPos())

    def set_effect_menu(self, mode, callback, speed, speed_callback):
        """Static/Rainbow dropdown on the row + a Speed slider below it, shown
        only while Rainbow is selected. callback(mode) / speed_callback(value)."""
        self._effect_mode = mode
        self._effect_cb = callback
        self._speed_cb = speed_callback

        self._effect_btn = _button(f"{mode.capitalize()}  ▾", "menuBtn", self._open_effect_menu)
        self._row.insertWidget(self._row.count() - 2, self._effect_btn)  # before the status

        self._speed_value = _label(f"{speed}%", "value")
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(_label("Speed", "sectionLabel"))
        head.addStretch()
        head.addWidget(self._speed_value)

        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setObjectName("brightness")   # reuse the slider style
        self._speed_slider.setRange(1, 100)
        self._speed_slider.setValue(speed)
        self._speed_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._speed_slider.valueChanged.connect(self._on_speed)

        speed_box = QVBoxLayout()
        speed_box.setContentsMargins(0, 0, 0, 10)
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
        menu = _menu(self)
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
        self._effect_btn.setText(f"{mode.capitalize()}  ▾")
        self._speed_area.setVisible(mode == "rainbow")
        self._effect_cb(mode)


class _StackLayout(QStackedLayout):
    """A QStackedLayout sized to its *current* page only. The stock one answers
    sizeHint/heightForWidth with the max over every page (QWidgetItem asks the
    layout directly, so overriding the widget is not enough), which would keep
    the fixed-size window as tall as the tallest page."""

    def sizeHint(self):
        page = self.currentWidget()
        return page.sizeHint() if page else super().sizeHint()

    def minimumSize(self):
        page = self.currentWidget()
        return page.minimumSizeHint() if page else super().minimumSize()

    def hasHeightForWidth(self):
        page = self.currentWidget()
        return bool(page and page.hasHeightForWidth())

    def heightForWidth(self, width):
        page = self.currentWidget()
        return page.heightForWidth(width) if page and page.hasHeightForWidth() else -1


class _Stack(QWidget):
    """Page container (main / settings) that lets the window shrink and grow
    with the page it shows."""

    def __init__(self):
        super().__init__()
        self._layout = _StackLayout(self)
        self._layout.currentChanged.connect(lambda _i: self.updateGeometry())

    def addWidget(self, page):
        self._layout.addWidget(page)

    def setCurrentIndex(self, index):
        self._layout.setCurrentIndex(index)

    def currentIndex(self):
        return self._layout.currentIndex()

    def currentWidget(self):
        return self._layout.currentWidget()

    def widget(self, index):
        return self._layout.widget(index)


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
        # Frameless + translucent: the rounded QFrame#panel is the visible window.
        # Stays a normal top-level window (taskbar entry); fixed-size, so no resize.
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._close_event = close_event
        self._settings = QSettings()
        self._manager = ble.DeviceManager(on_disconnect=self._on_device_disconnect)
        self._msi = msi_mystic.open_controller()  # None unless an MSI board is present
        # Every local USB controller (MSI + SteelSeries), each shown as a Devices row.
        self._locals = ([self._msi] if self._msi is not None else []) + steelseries.open_controllers()
        self._desired: set[str] = set()       # addresses we want connected
        self._in_range: set[str] = set()      # addresses seen in the last scan this session
        self._scanned = False                 # any scan run yet? (before one, range is unknown)
        self._reconnecting: set[str] = set()
        self._cards: dict[str, _DeviceCard] = {}
        self._local_cards: dict[str, _DeviceCard] = {}
        self._chips: dict[str | None, QPushButton] = {}   # None = the "All" chip
        self._power_on = False                 # optimistic: last command sent (active editor)
        self._focus: str | None = None         # focused BLE strip (None unless one is picked)
        self._bulk = True                      # All mode: edits fan out to every ticked strip
        self._loading = False                  # suppress sends while loading editor from state
        self._msi_effect = "static"            # MSI mode: "static" (picker) or "rainbow"
        self._effect_hue = 0.0
        self._effect_timer = QTimer(self)
        self._effect_timer.setInterval(EFFECT_INTERVAL_MS)
        self._effect_timer.timeout.connect(self._effect_tick)
        self._idle = False                     # True once we've released links to idle
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(IDLE_DISCONNECT_MS)
        self._idle_timer.timeout.connect(self._on_idle)
        self._save_timer = QTimer(self)      # coalesces per-tick colour saves
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self._save_state)
        self._closing = False
        self._sending = False                  # a colour send is in flight (see _on_color_timeout)
        self._send_pending = False             # ...and a newer colour arrived meanwhile
        self._wake_lock = asyncio.Lock()       # one idle-wake at a time
        self._ble_blocker = _bluetooth_blocker()  # None, or why a scan must not run

        self._load_state()
        self._base_color = self._load_color()
        theme.apply(QApplication.instance(), self._theme_mode)

        self._build_ui()
        self._setup_tray()
        self._rebuild_list()
        self._update_controls_visibility()
        self._refresh_theme_widgets()

        # Follow the OS when the theme is on Auto (Qt 6.5+ reports scheme changes).
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_system_scheme_changed)

        # Don't auto-connect on launch: opening the app (it lives in the tray)
        # must not seize Bluetooth. The user scans + connects when they want to
        # control the strips; commands reconnect on demand after an idle release.

        # Restore every synced local controller to the last colour.
        self._push_local_colors()

    # ---- construction ----------------------------------------------------

    def _build_ui(self):
        self.setObjectName("window")
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(PANEL_WIDTH)
        self._stack = _Stack()
        self._stack.addWidget(self._build_main_page())
        self._stack.addWidget(self._build_settings_page())
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._stack)

        root = QVBoxLayout(self)
        # Fixed-size: the window fits its content and can't be resized/maximised.
        root.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(panel)

    def _win_button(self, kind, slot, tooltip):
        btn = _button("", "winBtn", slot, tooltip)
        btn.setProperty("glyph", kind)
        return btn

    def _build_main_page(self):
        # Title bar: app icon, name, connection summary, settings/min/close.
        app_mark = QLabel()
        app_mark.setFixedSize(18, 18)
        app_mark.setPixmap(icon.app_icon().pixmap(18, 18))
        app_mark.setScaledContents(True)
        self._conn_label = _label("Not connected", "connLabel")
        self._settings_btn = self._win_button("tune", self._open_settings, "Settings")
        min_btn = self._win_button("minus", self.showMinimized, "Minimize")
        close_btn = self._win_button("close", self.close, "Close to tray")
        bar = _TitleBar()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(44)
        header = QHBoxLayout(bar)
        header.setContentsMargins(16, 0, 8, 0)
        header.setSpacing(8)
        header.addWidget(app_mark)
        header.addWidget(_label("Lumea", "appName"))
        header.addStretch()
        header.addWidget(self._conn_label)
        header.addSpacing(4)
        header.addWidget(self._settings_btn)
        header.addWidget(min_btn)
        header.addWidget(close_btn)

        self._status = _label("Ready. Run a scan to find your strips.", "statusText")
        self._status.setWordWrap(True)
        status_box = QWidget()
        status_lay = QHBoxLayout(status_box)
        status_lay.setContentsMargins(16, 10, 16, 10)
        status_lay.addWidget(self._status)

        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(bar)
        col.addWidget(_rule())
        # The whole editor section is hidden until something live can be edited.
        self._editor_section = self._build_editor()
        self._editor_rule = _rule()
        col.addWidget(self._editor_section)
        col.addWidget(self._editor_rule)
        col.addWidget(self._build_devices())
        col.addWidget(_rule())
        col.addWidget(status_box)
        return page

    def _build_editor(self):
        self._color_timer = QTimer(self)
        self._color_timer.setSingleShot(True)
        self._color_timer.setInterval(COLOR_DEBOUNCE_MS)
        self._color_timer.timeout.connect(self._on_color_timeout)

        # Edit-target row: "All" plus a chip per live strip (rebuilt in
        # _refresh_focus_ui); a hint replaces them while nothing can be edited.
        self._chip_row = QHBoxLayout()
        self._chip_row.setContentsMargins(0, 0, 0, 0)
        self._chip_row.setSpacing(6)
        self._target_hint = _label("", "hint")
        target = QHBoxLayout()
        target.setContentsMargins(0, 0, 0, 0)
        target.setSpacing(10)
        target.addWidget(_label("Editing", "sectionLabel"))
        target.addLayout(self._chip_row)
        target.addWidget(self._target_hint)
        target.addStretch()
        target_box = QWidget()
        target_box.setFixedHeight(26)
        target_box.setLayout(target)

        self._picker = colorpicker.ColorPicker()
        self._picker.set_color(self._base_color)  # before connecting: no spurious send
        self._picker.colorChanged.connect(self._on_picker_changed)

        # Presets as a row of colour dots, then the editable hex readout.
        self._preset_btns = []
        presets = QHBoxLayout()
        presets.setContentsMargins(0, 0, 0, 0)
        presets.setSpacing(7)
        for i in range(len(self._presets)):
            btn = QPushButton()
            btn.setObjectName("preset")
            btn.setFixedSize(18, 18)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, idx=i: self._apply_preset(idx))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda _pos, idx=i: self._save_preset(idx))
            self._preset_btns.append(btn)
            presets.addWidget(btn)
        presets.addStretch()
        self._hex_input = QLineEdit()
        self._hex_input.setObjectName("hexInput")
        self._hex_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hex_input.setMaxLength(7)
        self._hex_input.setToolTip("Type a hex colour, e.g. #33C9A4, and press Enter")
        # editingFinished already covers Enter (and focus-out); returnPressed too
        # would run the apply twice per Enter.
        self._hex_input.editingFinished.connect(self._apply_hex_input)
        presets.addWidget(self._hex_input)

        # Brightness: master dimmer scaling the picked colour client-side
        # (scaled_color); the power pill sits at the row's end.
        self._brightness_value = _label(f"{self._brightness}%", "value")
        self._brightness_value.setFixedWidth(34)
        self._brightness_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self._brightness_slider.setObjectName("brightness")
        self._brightness_slider.setRange(0, 100)
        self._brightness_slider.setValue(self._brightness)
        self._brightness_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._brightness_slider.valueChanged.connect(self._on_brightness_changed)
        self._power_btn = _button("", "power", self._on_power_toggle)
        bright_label = _label("Brightness", "sectionLabel")
        bright_label.setFixedWidth(64)
        bright = QHBoxLayout()
        bright.setContentsMargins(0, 0, 0, 0)
        bright.setSpacing(10)
        bright.addWidget(bright_label)
        bright.addWidget(self._brightness_slider, 1)
        bright.addWidget(self._brightness_value)
        bright.addSpacing(2)
        bright.addWidget(self._power_btn)

        # The editable body is disabled whenever no live strip is targeted.
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        body.addWidget(self._picker)
        body.addLayout(presets)
        body.addLayout(bright)
        self._editor_body = QWidget()
        self._editor_body.setLayout(body)

        editor = QWidget()
        col = QVBoxLayout(editor)
        col.setContentsMargins(16, 12, 16, 14)
        col.setSpacing(12)
        col.addWidget(target_box)
        col.addWidget(self._editor_body)
        self._update_power_visual()
        self._update_hero(self._base_color)
        return editor

    def _build_devices(self):
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

        self._scan_btn = _button("Scan", "ghost", self._on_scan, "Find nearby strips")
        # One primary action: Connect the ticked in-range strips, or, when there is
        # nothing left to connect, Disconnect everything.
        self._link_btn = _button("Connect", "primary", self._on_link_clicked)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        head.addWidget(_label("Devices", "sectionLabel"))
        head.addStretch()
        head.addWidget(self._scan_btn)
        head.addWidget(self._link_btn)

        section = QWidget()
        col = QVBoxLayout(section)
        col.setContentsMargins(16, 12, 16, 14)
        col.setSpacing(8)
        col.addLayout(head)
        col.addWidget(scroll)
        return section

    def _build_settings_page(self):
        back = self._win_button("back", self._close_settings, "Back")
        min_btn = self._win_button("minus", self.showMinimized, "Minimize")
        close_btn = self._win_button("close", self.close, "Close to tray")
        bar = _TitleBar()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(44)
        header = QHBoxLayout(bar)
        header.setContentsMargins(8, 0, 8, 0)
        header.setSpacing(6)
        header.addWidget(back)
        header.addWidget(_label("Settings", "appName"))
        header.addStretch()
        header.addWidget(min_btn)
        header.addWidget(close_btn)

        # Theme: Auto / Light / Dark segmented control.
        self._seg_btns = {}
        segment = QWidget()
        segment.setObjectName("segment")
        seg_lay = QHBoxLayout(segment)
        seg_lay.setContentsMargins(2, 2, 2, 2)
        seg_lay.setSpacing(2)
        for mode, label in (("auto", "Auto"), ("light", "Light"), ("dark", "Dark")):
            btn = _button(label, "segBtn", lambda _c=False, m=mode: self._on_theme_mode(m))
            btn.setCheckable(True)
            btn.setChecked(mode == self._theme_mode)
            self._seg_btns[mode] = btn
            seg_lay.addWidget(btn)

        self._tray_switch = _Switch()
        self._tray_switch.setChecked(self._tray_color_icon)
        self._tray_switch.toggled.connect(self._on_toggle_tray_color_icon)

        appearance = self._section("Appearance", [
            self._pref_row("Theme", "Auto follows the system setting", segment),
            self._pref_row("Tray icon shows the strip color",
                           "Otherwise the tray shows the Lumea icon", self._tray_switch),
        ])

        self._stats_switch = _Switch()
        self._stats_switch.setChecked(analytics.enabled())
        self._stats_switch.toggled.connect(analytics.set_enabled)
        privacy = self._section("Privacy", [
            self._pref_row("Send anonymous usage stats",
                           "One ping a day: a random install id and the app version. Nothing else.",
                           self._stats_switch),
        ])

        open_url = lambda url: (lambda: QDesktopServices.openUrl(QUrl(url)))
        about = self._section("About", [
            self._pref_row("Lumea", "Desktop control for ELK-BLEDOM and MELK LED strips"),
            self._pref_row("Open source", "MIT license. Built with PySide6, bleak and qasync.",
                           _button("View on GitHub", "ghost", open_url(GITHUB_URL))),
        ])
        # Footer, same shape as the author's other apps: slogan, handle · site,
        # then "Lumea · version" (html set in _refresh_theme_widgets).
        self._credits = _label("", "credits")
        self._credits.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._credits.setOpenExternalLinks(True)

        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(bar)
        col.addWidget(_rule())
        col.addWidget(appearance)
        col.addWidget(_rule())
        col.addWidget(privacy)
        col.addWidget(_rule())
        col.addWidget(about)
        col.addStretch()
        col.addWidget(self._credits)
        col.addSpacing(12)
        return page

    def _section(self, title, rows):
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(16, 12, 16, 14)
        col.setSpacing(6)
        col.addWidget(_label(title, "sectionLabel"))
        for row in rows:
            col.addWidget(row)
        return box

    def _pref_row(self, name, sub, right=None):
        # `sub` is a string or a widget (e.g. a link label).
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        text.addWidget(_label(name, "rowName"))
        if isinstance(sub, QWidget):
            text.addWidget(sub)
        elif sub:
            sub_lbl = _label(sub, "rowSub")
            sub_lbl.setWordWrap(True)
            text.addWidget(sub_lbl)
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(12)
        lay.addLayout(text, 1)
        if right is not None:
            lay.addWidget(right, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    # ---- theme -----------------------------------------------------------

    def _on_theme_mode(self, mode):
        self._theme_mode = mode
        for m, btn in self._seg_btns.items():
            btn.setChecked(m == mode)
        self._save_state()
        self._apply_theme()

    def _on_system_scheme_changed(self, _scheme):
        if self._theme_mode == "auto":
            self._apply_theme()

    def _apply_theme(self):
        theme.apply(QApplication.instance(), self._theme_mode)
        self._refresh_theme_widgets()

    def _refresh_theme_widgets(self):
        # Things the stylesheet can't restyle: painted icons, per-colour swatches,
        # custom-painted widgets, and the tray menu header.
        t = theme.current
        for btn in self.findChildren(QPushButton, "winBtn"):
            btn.setIcon(icon.glyph(btn.property("glyph"), t["muted"], 14))
        self._update_power_visual()
        self._refresh_presets()
        version = QCoreApplication.applicationVersion() or "dev"
        version_url = (f"{GITHUB_URL}/releases/tag/v{version}" if not version.startswith("dev")
                       else f"{GITHUB_URL}/commits/master")
        label = version if version.startswith("dev") else "v" + version
        link = lambda url, text: f'<a href="{url}" style="color:{t["muted"]};text-decoration:none">{text}</a>'
        dot = f'<span style="color:{t["line"]}">&nbsp;·&nbsp;</span>'
        self._credits.setText(
            f'<span style="color:{t["faint"]}">built with</span> ❤️ '
            f'<span style="color:{t["faint"]}">for</span> 💡 '
            f'<span style="color:{t["faint"]}">rooms full of colour</span><br>'
            f'{link(AUTHOR_URL, "ugurcandede")}{dot}{link(SITE_URL, "ugurcandede.github.io")}<br>'
            f'<span style="color:{t["faint"]}">Lumea</span>{dot}{link(version_url, label)}')
        for card in list(self._cards.values()) + list(self._local_cards.values()):
            card.set_status(self._manager.is_connected(card._address) if card._removable else True,
                            self._reachable(card._address) if card._removable else True,
                            self._present(card._address) if card._removable else True)
        for w in self.findChildren(QWidget):
            w.update()

    # ---- tray ------------------------------------------------------------

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            return
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._tray_icon())
        self._tray.setToolTip("Lumea")
        self._tray_menu = self._build_tray_menu()
        # macOS: don't hand the menu to the status item. Qt's native path
        # (-[QStatusItemDelegate statusItemMenuBeganTracking:], Qt 6.11) reads
        # NSEvent.clickCount on a non-mouse event and AppKit aborts the process on
        # macOS 26+. We pop our own QMenu on click instead (see _on_tray_activated).
        if sys.platform != "darwin":
            self._tray.setContextMenu(self._tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _build_tray_menu(self):
        menu = _menu()
        self._tray_header = _label("", "menuHeader")
        header = QWidgetAction(menu)
        header.setDefaultWidget(self._tray_header)
        menu.addAction(header)
        menu.addSeparator()
        self._act_show = menu.addAction("Show Lumea", self._toggle_window)
        self._act_power = menu.addAction("Turn on", self._on_power_toggle)
        # Quick colours: the 12 presets as a 6-column grid of dots.
        quick = _menu(menu)
        quick.setTitle("Quick colors")
        grid_box = QWidget()
        grid = QGridLayout(grid_box)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setSpacing(8)
        self._quick_btns = []
        for i in range(len(self._presets)):
            btn = QPushButton()
            btn.setObjectName("preset")
            btn.setFixedSize(18, 18)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, idx=i: (self._apply_preset(idx), menu.close()))
            self._quick_btns.append(btn)
            grid.addWidget(btn, i // 6, i % 6)
        grid_box.setFixedSize(grid.sizeHint())   # QMenu won't size a widget action's grid itself
        grid_action = QWidgetAction(quick)
        grid_action.setDefaultWidget(grid_box)
        quick.addAction(grid_action)
        menu.addMenu(quick)
        menu.addSeparator()
        menu.addAction("Settings…", self._open_settings)
        menu.addSeparator()
        menu.addAction("Quit Lumea", self._quit)
        menu.aboutToShow.connect(self._refresh_tray_menu)
        self._refresh_presets()   # colour the quick-colour dots
        return menu

    def _refresh_tray_menu(self):
        t = theme.current
        connected = len(self._manager.connected_addresses())
        summary = (f"{connected} strip{'s' if connected != 1 else ''} connected" if connected
                   else "Idle" if self._idle and self._desired else "Not connected")
        self._tray_header.setText(
            f'<span style="font-size:13px;font-weight:600;color:{t["ink"]}">Lumea</span><br>'
            f'<span style="font-size:11px;color:{t["muted"]}">{summary}</span>')
        self._act_show.setText("Hide Lumea" if self.isVisible() and not self.isMinimized() else "Show Lumea")
        self._act_power.setText("Turn off" if self._power_on else "Turn on")

    def _tray_icon(self):
        # App icon by default; the coloured ring reflecting the strip colour is opt-in.
        return icon.make_icon(self._base_color) if self._tray_color_icon else icon.app_icon()

    def _on_toggle_tray_color_icon(self, checked):
        self._tray_color_icon = checked
        if self._tray is not None:
            self._tray.setIcon(self._tray_icon())
        self._save_state()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window()
        elif sys.platform == "darwin" and reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.Context,
        ):
            self._tray_menu.popup(QCursor.pos())  # see _setup_tray

    # ---- settings page ---------------------------------------------------

    def _open_settings(self):
        self._stack.setCurrentIndex(1)
        self.show_window()

    def _close_settings(self):
        self._stack.setCurrentIndex(0)

    # ---- device list -----------------------------------------------------

    def _display(self, address):
        return self._aliases.get(address) or self._known.get(address) or address

    def _reachable(self, address):
        # Reachable if connected, or seen in the last scan. Before any scan this
        # session range is unknown, so don't flag anything as out of range yet.
        return (self._manager.is_connected(address)
                or not self._scanned
                or address in self._in_range)

    def _present(self, address):
        # Confirmed here this session: connected, or found by a scan. Before any
        # scan nothing is confirmed, so rows aren't selectable until the user scans.
        return self._manager.is_connected(address) or address in self._in_range

    def _connectable(self):
        # Ticked, found in the current session's scan, not already linked. Empty
        # until a scan runs -- so the user must Scan before Connect does anything
        # (opening the app must never silently seize Bluetooth).
        if not self._scanned:
            return set()
        return {a for a in self._selected if a in self._in_range} \
            - self._manager.connected_addresses()

    def _rebuild_list(self):
        # Drop every existing card, then rebuild: the local USB controllers first
        # (MSI + SteelSeries), then the BLE strips sorted by display name.
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()
        self._local_cards.clear()
        while self._device_vbox.count() > 1:  # keep the trailing stretch
            item = self._device_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._focus is not None and self._focus not in self._known:
            self._focus = None  # focused strip was forgotten

        if not self._known and not self._locals:
            empty = QFrame()
            empty.setObjectName("emptyRow")
            empty.setFixedHeight(40)
            lay = QHBoxLayout(empty)
            lay.setContentsMargins(12, 0, 12, 0)
            lay.addWidget(_label("No strips yet. Scan to find nearby strips.", "hint"),
                          0, Qt.AlignmentFlag.AlignCenter)
            self._device_vbox.insertWidget(0, empty)
            self._fit_device_scroll()
            self._update_controls_visibility()
            self._refresh_focus_ui()
            return

        for controller in self._locals:
            # A local USB device: always "connected", no scan/connect needed. Its
            # checkbox is the colour-mirror toggle (ticked = in the control group).
            card = _DeviceCard(controller.card_id, controller.name,
                               self._is_synced(controller), controller.subtitle,
                               removable=False)
            card.toggled.connect(
                lambda _a, checked, c=controller: self._on_local_sync_toggled(c, checked))
            if controller.effect:      # only MSI: the Static/Rainbow menu + speed slider
                card.set_effect_menu(
                    self._msi_effect, self._on_msi_effect_changed,
                    self._effect_speed, self._on_speed_changed,
                )
            card.set_status(True)
            self._local_cards[controller.card_id] = card
            self._device_vbox.insertWidget(self._device_vbox.count() - 1, card)

        for address in sorted(self._known, key=lambda a: self._display(a).lower()):
            card = _DeviceCard(address, self._display(address), address in self._selected)
            card.toggled.connect(self._on_card_toggled)
            card.renameRequested.connect(self._on_card_rename)
            card.removeRequested.connect(self._on_card_remove)
            card.focusRequested.connect(self._on_card_focus)
            card.set_status(self._manager.is_connected(address),
                            self._reachable(address), self._present(address))
            self._cards[address] = card
            self._device_vbox.insertWidget(self._device_vbox.count() - 1, card)
        self._fit_device_scroll()
        self._update_controls_visibility()
        self._refresh_focus_ui()

    def _fit_device_scroll(self):
        # QScrollArea won't size to its content; fit it to the rows, then scroll
        # past a cap so a long list can't take over the window. Measure the rows
        # (don't guess a row height) so QSS borders/padding and the taller MSI
        # rainbow card are counted exactly.
        gap = self._device_vbox.spacing()
        cards = list(self._local_cards.values()) + list(self._cards.values())
        if not cards:
            self._device_scroll.setFixedHeight(40)
            return
        for card in cards:
            card.ensurePolished()
        shown = min(len(cards), DEVICE_ROWS_SHOWN)
        heights = [card.sizeHint().height() for card in cards[:shown]]
        self._device_scroll.setFixedHeight(sum(heights) + (shown - 1) * gap)

    def _refresh_row(self, address):
        card = self._cards.get(address)
        if card is not None:
            card.set_name(self._display(address))
            card.set_status(self._manager.is_connected(address),
                            self._reachable(address), self._present(address))
        self._update_controls_visibility()

    def _update_controls_visibility(self):
        connected = self._manager.connected_addresses()
        count = len(connected) + len(self._locals)
        if self._idle and self._desired:
            self._conn_label.setText("Idle")
        else:
            self._conn_label.setText(f"{count} connected" if count else "Not connected")
        # One primary action: Connect while something ticked is in range and
        # unlinked; otherwise Disconnect if anything is linked; else a disabled Connect.
        if self._connectable():
            self._link_btn.setText("Connect")
            self._link_btn.setEnabled(True)
        elif connected:
            self._link_btn.setText("Disconnect")
            self._link_btn.setEnabled(True)
        else:
            self._link_btn.setText("Connect")
            self._link_btn.setEnabled(False)
        self._link_btn.setToolTip(
            "Connect the ticked strips" if self._link_btn.text() == "Connect"
            else "Disconnect every strip")
        self._refresh_focus_ui()

    def _on_card_toggled(self, address, checked):
        if checked:
            self._selected.add(address)
        else:
            self._selected.discard(address)
        self._save_state()
        self._update_controls_visibility()  # Connect enables once a strip is ticked

    def _on_card_rename(self, address):
        current = self._aliases.get(address, self._known.get(address, ""))
        text, ok = QInputDialog.getText(self, "Rename strip", f"Name for {address}:", text=current)
        if not ok:
            return
        text = text.strip()
        if text:
            self._aliases[address] = text
        else:
            self._aliases.pop(address, None)
        self._save_state()
        self._refresh_row(address)
        self._refresh_focus_ui()  # keep the chip label in sync

    def _on_card_remove(self, address):
        # Forget a saved strip entirely: drop it from every set and disconnect if
        # live. It reappears (without its alias) on a scan that finds it again.
        self._desired.discard(address)
        self._selected.discard(address)
        self._in_range.discard(address)
        self._known.pop(address, None)
        self._aliases.pop(address, None)
        self._states.pop(address, None)
        if self._manager.is_connected(address):
            asyncio.ensure_future(self._manager.disconnect(address))
        self._save_state()
        self._rebuild_list()
        self._update_controls_visibility()

    # ---- edit target (focus vs All) --------------------------------------

    def _edit_targets(self):
        # Addresses the editor's changes apply to: the focused strip, or (All
        # mode) every ticked strip, or nothing. Sends filter to connected ones.
        if self._focus is not None:
            return [self._focus]
        if self._bulk:
            return list(self._selected)
        return []

    def _state_of(self, address):
        # Stored per-device state, or a fresh default (never sent until edited).
        return self._states.get(address) or {
            "color": DEFAULT_COLOR.name(), "brightness": DEFAULT_BRIGHTNESS, "power": False}

    def _live(self, address):
        # Part of the active control session: connected, or wanted (idle-released
        # but reconnects on the next command). These are the strips you can edit.
        return self._manager.is_connected(address) or address in self._desired

    def _editor_active(self):
        # The editor is usable only when it targets a live strip -- or, in All
        # mode, a synced local USB controller (which needs no BLE link).
        if any(self._live(a) for a in self._edit_targets()):
            return True
        return self._bulk and any(self._is_synced(c) for c in self._locals)

    def _update_editor_enabled(self):
        # Hide, don't grey out: a disabled slider still reads as adjustable.
        self._editor_body.setVisible(self._editor_active())

    def _stamp_targets(self, **fields):
        # Merge only the given field(s) into every targeted strip's stored state.
        # Colour and power are separate frames, so a colour tweak must not clobber
        # a strip's own power (and vice versa); per-device values survive edits to
        # the other attribute.
        for address in self._edit_targets():
            st = self._states.get(address)
            if st is None:
                st = {"color": DEFAULT_COLOR.name(),
                      "brightness": DEFAULT_BRIGHTNESS, "power": False}
                self._states[address] = st
            st.update(fields)

    def _load_editor(self, state):
        # Show a strip's stored state in the editor without sending anything.
        self._loading = True
        color = QColor(state["color"])
        self._base_color = color if color.isValid() else QColor(DEFAULT_COLOR)
        self._brightness = int(state.get("brightness", DEFAULT_BRIGHTNESS))
        self._power_on = bool(state.get("power", False))
        self._picker.set_color(self._base_color)
        self._brightness_slider.setValue(self._brightness)
        self._brightness_value.setText(f"{self._brightness}%")
        self._update_hero(self._base_color)
        self._update_power_visual()
        if self._tray is not None and self._tray_color_icon:
            self._tray.setIcon(self._tray_icon())
        self._loading = False

    def _on_card_focus(self, address):
        if not self._live(address):
            self._set_status(f"{self._display(address)}: connect it first to edit it.")
            return
        if self._focus == address:
            return
        self._focus = address
        self._bulk = False
        self._load_editor(self._state_of(address))
        self._refresh_focus_ui()

    def _on_chip_clicked(self, address):
        # None = the All chip. Clicking the active chip clears the target (edits
        # are inert until you pick one again), same as the old All toggle.
        if address is None:
            self._bulk = not self._bulk
            self._focus = None
            self._refresh_focus_ui()
        elif self._focus == address:
            self._focus = None
            self._bulk = False
            self._refresh_focus_ui()
        else:
            self._on_card_focus(address)

    def _refresh_focus_ui(self):
        # Rebuild the target chips: All + every live strip, in list order.
        live = [a for a in sorted(self._known, key=lambda a: self._display(a).lower())
                if self._live(a)]
        wanted = [None] + live
        if list(self._chips) != wanted:
            while self._chip_row.count():
                item = self._chip_row.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._chips = {}
            for address in wanted:
                label = "All" if address is None else self._display(address)
                btn = _button(label, "chip", lambda _c=False, a=address: self._on_chip_clicked(a))
                btn.setCheckable(True)
                self._chips[address] = btn
                self._chip_row.addWidget(btn)
        else:
            for address, btn in self._chips.items():
                if address is not None:
                    btn.setText(self._display(address))
        active = self._editor_active()
        # No live strip and no synced local: nothing to edit, so no editor at all.
        editable = bool(live) or any(self._is_synced(c) for c in self._locals)
        self._editor_section.setVisible(editable)
        self._editor_rule.setVisible(editable)
        for address, btn in self._chips.items():
            btn.blockSignals(True)
            btn.setChecked(self._bulk if address is None else address == self._focus)
            btn.blockSignals(False)
        self._target_hint.setVisible(not active)
        self._target_hint.setText("Pick a strip, or All")
        for address, card in self._cards.items():
            card.set_focused(address == self._focus)
        if self._focus is None and self._bulk:
            # The strip never reports state, so All mode shows the remembered one:
            # On if any live target was last left on (a focused strip loads its own).
            on = any(self._state_of(a)["power"] for a in self._edit_targets() if self._live(a))
            if on != self._power_on:
                self._power_on = on
                self._update_power_visual()
        self._update_editor_enabled()

    # ---- color -----------------------------------------------------------

    def _on_picker_changed(self, color):
        self._base_color = color
        self._update_hero(color)
        if self._loading:
            return
        self._stamp_targets(color=self._base_color.name(), brightness=self._brightness)
        self._color_timer.start()  # debounced send + tray icon update

    def _update_hero(self, color):
        # setText() doesn't fire editingFinished, so no feedback loop.
        self._hex_input.setText(color.name().upper())

    def _apply_hex_input(self):
        text = self._hex_input.text().strip().lstrip("#")
        color = QColor(f"#{text}")
        if len(text) == 6 and color.isValid() and color.rgb() != self._base_color.rgb():
            self._picker.set_color(color)  # -> _on_picker_changed: updates + sends
        else:
            self._update_hero(self._base_color)  # invalid/unchanged: restore readout

    def _on_brightness_changed(self, value):
        self._brightness = value
        self._brightness_value.setText(f"{value}%")
        if self._loading:
            return
        self._stamp_targets(color=self._base_color.name(), brightness=self._brightness)
        self._color_timer.start()  # debounced send, same path as colour changes

    def _on_speed_changed(self, value):
        self._effect_speed = value

    # ---- color presets ---------------------------------------------------

    def _refresh_presets(self):
        t = theme.current
        for btns in (self._preset_btns, getattr(self, "_quick_btns", [])):
            for btn, hex_color in zip(btns, self._presets):
                btn.setStyleSheet(
                    f"QPushButton {{ background:{hex_color}; border:1px solid {t['swatch_border']};"
                    " border-radius:9px; }"
                    f"QPushButton:hover {{ border:2px solid {t['ink']}; }}"
                    f"QPushButton:disabled {{ background:{t['inset']}; border-color:{t['inset']}; }}"
                )
                btn.setToolTip(f"{hex_color}  (right-click saves the current colour here)")

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
        # One send in flight at a time. A BLE write can outlast the debounce
        # (write-without-response blocks once the link's buffer is full); rather
        # than pile up out-of-order frames, remember that a newer colour is waiting
        # and send the latest once the current write returns.
        if self._sending:
            self._send_pending = True
            return
        self._sending = True
        try:
            await self._send_base_color()
            while self._send_pending:
                self._send_pending = False
                await self._send_base_color()
        finally:
            self._sending = False

    async def _send_base_color(self):
        if self._tray is not None and self._tray_color_icon:
            self._tray.setIcon(self._tray_icon())
        if self._bulk:
            self._push_local_colors()  # locals mirror the bulk colour, not a focus
        await self._wake()             # re-establish links if we released them to idle
        self._save_timer.start()       # persist the stamped state (coalesced; quit flushes)
        targets = [a for a in self._edit_targets() if self._manager.is_connected(a)]
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
        self._touch()

    # ---- rainbow effect --------------------------------------------------

    def _is_synced(self, controller):
        return self._local_sync.get(controller.card_id, False)

    def _push_one(self, controller):
        # Send the picker colour to one local controller. MSI is skipped while it
        # runs its own rainbow (the effect drives it instead of the picker).
        if controller is self._msi and self._msi_effect != "static":
            return
        c = self._base_color
        try:
            controller.set_color(c.red(), c.green(), c.blue(), self._brightness)
        except Exception:
            log.exception("%s color send failed", controller.name)
            self._set_status(f"{controller.name}: color send failed.")

    def _push_local_colors(self):
        for controller in self._locals:
            if self._is_synced(controller):
                self._push_one(controller)

    def _set_local_power(self, on):
        # Locals have no power frame: off sends black (and pauses the MSI rainbow),
        # on re-applies the picker colour (or resumes the rainbow). Returns True if
        # any synced controller was driven.
        targets = [c for c in self._locals if self._is_synced(c)]
        for controller in targets:
            if on:
                if controller is self._msi and self._msi_effect == "rainbow":
                    self._effect_timer.start()
                else:
                    self._push_one(controller)
            else:
                if controller is self._msi:
                    self._effect_timer.stop()
                try:
                    controller.set_color(0, 0, 0)
                except Exception:
                    log.exception("%s power-off send failed", controller.name)
        return bool(targets)

    def _on_local_sync_toggled(self, controller, checked):
        self._local_sync[controller.card_id] = checked
        self._save_state()
        self._refresh_focus_ui()   # a synced local makes the All editor usable
        if controller is self._msi:
            if not checked:
                self._effect_timer.stop()
                return
            if self._msi_effect == "rainbow":
                self._effect_timer.start()
                return
        if checked:
            self._push_one(controller)  # apply the current colour right away

    def _on_msi_effect_changed(self, mode):
        self._set_msi_effect(mode)

    def _set_msi_effect(self, mode):
        self._msi_effect = mode
        self._fit_device_scroll()                  # the card grew/shrank its speed slider
        if mode == "rainbow":
            hue = self._base_color.hueF()          # continue from the current colour
            self._effect_hue = hue if hue >= 0 else 0.0
            if self._is_synced(self._msi):
                self._effect_timer.start()
        else:                                      # static: hand MSI back to the picker
            self._effect_timer.stop()
            self._push_one(self._msi)

    def _effect_step(self):
        # Map Speed 1..100 to the hue advance per tick.
        return EFFECT_MIN_STEP + (self._effect_speed - 1) / 99 * (EFFECT_MAX_STEP - EFFECT_MIN_STEP)

    def _effect_tick(self):
        # MSI-only software rainbow: stream a hue sweep to the motherboard while the
        # BLE strips and other USB devices keep the picker colour.
        if self._msi is None or not self._is_synced(self._msi):
            return
        self._effect_hue = (self._effect_hue + self._effect_step()) % 1.0
        color = QColor.fromHsvF(self._effect_hue, 1.0, 1.0)
        try:
            self._msi.set_color(color.red(), color.green(), color.blue(), self._brightness)
        except Exception:
            log.exception("MSI effect send failed")

    # ---- scan / connect --------------------------------------------------

    @asyncSlot()
    async def _on_scan(self):
        if self._ble_blocker:
            self._set_status(self._ble_blocker)
            return
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

        self._scanned = True
        self._in_range = {d.address for d in devices}
        for d in devices:
            self._known[d.address] = d.name
        self._rebuild_list()
        self._save_state()
        self._set_status(
            f"{len(devices)} strip{'s' if len(devices) != 1 else ''} found." if devices
            else "No strips found. Make sure they're powered and nearby."
        )

    @asyncSlot()
    async def _on_link_clicked(self):
        if self._connectable():
            await self._connect_selected()
        else:
            await self._disconnect_all()

    async def _connect_selected(self):
        targets = list(self._connectable())
        if not targets:
            self._set_status(
                "Scan first, then tick an in-range strip." if not self._scanned
                else "Tick an in-range strip to connect."
            )
            return
        self._idle = False            # explicit connect ends any idle release
        self._desired |= set(targets)
        await self._connect_many(targets)

    async def _connect_many(self, addresses):
        await asyncio.gather(*(self._connect_one(a) for a in addresses))
        connected = sum(self._manager.is_connected(a) for a in addresses)
        self._set_status(f"{connected}/{len(addresses)} strip(s) connected.")

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
        self._touch()  # a live link starts/refreshes the idle countdown

    async def _disconnect_all(self):
        # Disconnect every connected device (checked or not) so nothing is orphaned.
        targets = list(self._manager.connected_addresses())
        self._desired.clear()
        self._idle = False
        self._idle_timer.stop()
        self._focus = None            # nothing to edit individually once disconnected
        self._bulk = True
        await asyncio.gather(
            *(self._manager.disconnect(a) for a in targets), return_exceptions=True
        )
        for address in targets:
            self._refresh_row(address)
        self._refresh_focus_ui()
        self._set_status("All strips disconnected.")

    def _on_device_disconnect(self, address):
        # Called by the manager when a link drops (wanted or not).
        self._refresh_row(address)
        # A drop we caused to idle isn't a fault: don't fight it with a reconnect.
        if self._idle or self._closing:
            return
        if address in self._desired:
            self._set_status(f"{self._display(address)}: link dropped, reconnecting...")
            asyncio.ensure_future(self._reconnect(address))

    # ---- idle release ----------------------------------------------------

    def _touch(self):
        # Any command (or fresh link) restarts the idle countdown; only meaningful
        # once we actually want links.
        if self._desired:
            self._idle_timer.start()

    async def _wake(self):
        # If we released the links to idle, bring the wanted ones back before a
        # command lands. No-op when never connected or still live. Serialised so
        # a colour tick and a power press don't both start reconnecting.
        async with self._wake_lock:
            if self._idle and self._desired:
                self._set_status("Reconnecting...")
                await self._connect_many(list(self._desired))
                if self._manager.connected_addresses():
                    self._idle = False

    @asyncSlot()
    async def _on_idle(self):
        # Release the BLE links after inactivity so they stop contending with BT
        # audio; the next command reconnects (see _wake). Set the flag first so
        # the disconnect callbacks don't treat this as a fault and reconnect.
        targets = list(self._manager.connected_addresses())
        if not targets:
            return
        self._idle = True
        await asyncio.gather(
            *(self._manager.disconnect(a) for a in targets), return_exceptions=True
        )
        for address in targets:
            self._refresh_row(address)
        self._set_status("Idle: Bluetooth released. Adjust anything to reconnect.")

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
                self._touch()  # the fresh link restarts the idle countdown
                self._set_status(f"{self._display(address)}: reconnected.")
                return
            self._set_status(f"{self._display(address)}: reconnect failed.")
        finally:
            self._reconnecting.discard(address)

    # ---- broadcast control ----------------------------------------------

    async def _broadcast(self, action, ok_status):
        """Fan a command out to every targeted-and-connected device (the focused
        strip, or all ticked). Returns True if it reached at least one device."""
        targets = [a for a in self._edit_targets() if self._manager.is_connected(a)]
        if not targets:
            self._set_status("No ticked, connected strip.")
            return False
        results = await self._manager.apply(targets, action)
        failed = [a for a, exc in results.items() if exc is not None]
        if failed:
            names = ", ".join(self._display(a) for a in failed)
            self._set_status(f"{len(targets) - len(failed)}/{len(targets)} applied. Failed: {names}")
        elif ok_status:
            self._set_status(f"{ok_status} ({len(targets)} strip{'s' if len(targets) != 1 else ''})")
        return len(failed) < len(targets)

    def _update_power_visual(self):
        t = theme.current
        on = self._power_on
        self._power_btn.setText("On" if on else "Off")
        self._power_btn.setIcon(icon.glyph("power", t["primary_fg"] if on else t["disabled_fg"], 12, 2.4))
        self._power_btn.setToolTip("Turn off" if on else "Turn on")
        self._power_btn.setProperty("on", "true" if on else "false")
        _repolish(self._power_btn)

    async def _set_power(self, on):
        # No readback: keep an optimistic state and only adopt it if the send
        # actually reached a device. In All mode the local USB controllers are
        # covered too; a focused BLE strip is driven alone.
        local_ok = self._set_local_power(on) if self._bulk else False
        await self._wake()         # re-establish links if we released them to idle
        if [a for a in self._edit_targets() if self._manager.is_connected(a)]:
            ble_ok = await self._broadcast(
                lambda d: d.set_power(on), "Turned on." if on else "Turned off."
            )
        else:
            ble_ok = False
            self._set_status(
                ("Turned on." if on else "Turned off.") if local_ok
                else "No ticked, connected strip."
            )
        if ble_ok or local_ok:
            self._power_on = on
            self._update_power_visual()
            self._stamp_targets(power=on)  # remember this power per targeted strip
            self._save_state()
        self._touch()

    @asyncSlot()
    async def _on_power_toggle(self):
        await self._set_power(not self._power_on)

    # ---- tray / window ---------------------------------------------------

    def _toggle_window(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _close_locals(self):
        for controller in self._locals:
            controller.close()

    def _quit(self):
        self._closing = True
        self._save_state()
        self._close_locals()
        self._close_event.set()

    def closeEvent(self, event):
        # With a tray, closing the window just hides it; the app keeps running.
        if self._tray is not None and not self._closing:
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "Lumea",
                "Still running in the tray. Quit from the tray menu.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            return
        self._closing = True
        self._save_state()
        self._close_locals()
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
        # Per-device output: address -> {"color": "#rrggbb", "brightness": int, "power": bool}.
        self._states = json.loads(self._settings.value("states_json", "{}"))
        self._local_sync = json.loads(self._settings.value("local_sync_json", "{}"))
        if self._settings.contains("msi_sync"):  # migrate the pre-SteelSeries key, then drop it
            if "msi-mystic-light" not in self._local_sync:
                self._local_sync["msi-mystic-light"] = self._settings.value("msi_sync", False, type=bool)
            self._settings.remove("msi_sync")
        self._effect_speed = self._settings.value("effect_speed", DEFAULT_EFFECT_SPEED, type=int)
        mode = self._settings.value("theme_mode", "auto")
        self._theme_mode = mode if mode in THEME_MODES else "auto"

    def _save_state(self):
        self._settings.setValue("known_json", json.dumps(self._known))
        self._settings.setValue("aliases_json", json.dumps(self._aliases))
        self._settings.setValue("selected_json", json.dumps(list(self._selected)))
        self._settings.setValue("presets_json", json.dumps(self._presets))
        self._settings.setValue("color", self._base_color.name())
        self._settings.setValue("tray_color_icon", self._tray_color_icon)
        self._settings.setValue("brightness", self._brightness)
        self._settings.setValue("states_json", json.dumps(self._states))
        self._settings.setValue("local_sync_json", json.dumps(self._local_sync))
        self._settings.setValue("effect_speed", self._effect_speed)
        self._settings.setValue("theme_mode", self._theme_mode)
