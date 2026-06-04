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

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

import ble
import colorpicker
import icon

log = logging.getLogger(__name__)

RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_S = 3.0
COLOR_DEBOUNCE_MS = 80
DEFAULT_COLOR = QColor(255, 255, 255)
DEFAULT_PRESETS = ["#ff0000", "#00ff00", "#0000ff", "#ffaa00", "#ffffff"]


class LedController(QWidget):
    def __init__(self, close_event):
        super().__init__()
        self.setWindowTitle("Lumea")
        self.setMinimumWidth(420)

        self._close_event = close_event
        self._settings = QSettings()
        self._manager = ble.DeviceManager(on_disconnect=self._on_device_disconnect)
        self._desired: set[str] = set()       # addresses we want connected
        self._reconnecting: set[str] = set()
        self._building = False                 # guard against itemChanged feedback
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

    # ---- construction ----------------------------------------------------

    def _build_ui(self):
        self._list = QListWidget()
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        list_hint = QLabel("Tick: add to control group · double-click: rename")
        list_hint.setStyleSheet("color: gray;")

        self._scan_btn = QPushButton("Scan")
        self._scan_btn.clicked.connect(self._on_scan)
        self._connect_btn = QPushButton("Connect Selected")
        self._connect_btn.clicked.connect(self._on_connect_selected)
        self._disconnect_btn = QPushButton("Disconnect All")
        self._disconnect_btn.clicked.connect(self._on_disconnect_all)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self._scan_btn)
        btn_row.addWidget(self._connect_btn)
        btn_row.addWidget(self._disconnect_btn)

        self._on_btn = QPushButton("On")
        self._on_btn.clicked.connect(self._on_power_on)
        self._off_btn = QPushButton("Off")
        self._off_btn.clicked.connect(self._on_power_off)
        power_row = QHBoxLayout()
        power_row.addWidget(self._on_btn)
        power_row.addWidget(self._off_btn)

        self._color_timer = QTimer(self)
        self._color_timer.setSingleShot(True)
        self._color_timer.setInterval(COLOR_DEBOUNCE_MS)
        self._color_timer.timeout.connect(self._on_color_timeout)

        self._picker = colorpicker.ColorPicker()
        self._picker.set_color(self._base_color)  # before connecting: no spurious send
        self._picker.colorChanged.connect(self._on_picker_changed)

        color_box = QGroupBox("Color")
        color_layout = QVBoxLayout(color_box)
        color_layout.addWidget(self._picker)
        color_layout.addLayout(self._build_presets())

        self._controls = QGroupBox("Controls (checked + connected devices)")
        controls_layout = QVBoxLayout(self._controls)
        controls_layout.addLayout(power_row)
        controls_layout.addWidget(color_box)

        self._status = QLabel("Ready. Run a scan.")
        self._status.setWordWrap(True)

        footer = QLabel(
            '<span style="color:gray">Built with ❤ by </span>'
            '<a href="https://github.com/ugurcandede">@ugurcandede</a>'
        )
        footer.setTextFormat(Qt.TextFormat.RichText)
        footer.setOpenExternalLinks(True)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root = QVBoxLayout(self)
        root.addWidget(self._list, 1)
        root.addWidget(list_hint)
        root.addLayout(btn_row)
        root.addWidget(self._controls)
        root.addWidget(self._status)
        root.addWidget(footer)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            return
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(icon.make_icon(self._base_color))
        self._tray.setToolTip("Lumea")
        menu = QMenu()
        menu.addAction("Show / Hide", self._toggle_window)
        menu.addAction("On", self._on_power_on)
        menu.addAction("Off", self._on_power_off)
        menu.addSeparator()
        menu.addAction("Quit", self._quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    # ---- device list -----------------------------------------------------

    def _display(self, address):
        return self._aliases.get(address) or self._known.get(address) or address

    def _row_text(self, address):
        dot = "●" if self._manager.is_connected(address) else "○"
        return f"{dot} {self._display(address)}  ({address})"

    def _rebuild_list(self):
        self._building = True
        self._list.clear()
        for address in sorted(self._known, key=lambda a: self._display(a).lower()):
            item = QListWidgetItem(self._row_text(address))
            item.setData(Qt.ItemDataRole.UserRole, address)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = address in self._selected
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self._list.addItem(item)
        self._building = False

    def _refresh_row(self, address):
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == address:
                self._building = True
                item.setText(self._row_text(address))
                self._building = False
                break
        self._update_controls_visibility()

    def _update_controls_visibility(self):
        # Power + color are only useful with a live connection.
        self._controls.setVisible(bool(self._manager.connected_addresses()))

    def _on_item_changed(self, item):
        if self._building:
            return
        address = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._selected.add(address)
        else:
            self._selected.discard(address)
        self._save_state()

    def _on_item_double_clicked(self, item):
        address = item.data(Qt.ItemDataRole.UserRole)
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
        self._color_timer.start()  # debounced send + tray icon update

    # ---- color presets ---------------------------------------------------

    def _build_presets(self):
        self._preset_btns = []
        row = QHBoxLayout()
        row.addWidget(QLabel("Presets:"))
        for i in range(len(self._presets)):
            btn = QPushButton()
            btn.setFixedSize(28, 24)
            btn.clicked.connect(lambda _checked=False, idx=i: self._apply_preset(idx))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda _pos, idx=i: self._save_preset(idx))
            self._preset_btns.append(btn)
            row.addWidget(btn)
        row.addStretch()
        self._refresh_presets()
        return row

    def _refresh_presets(self):
        for btn, hex_color in zip(self._preset_btns, self._presets):
            btn.setStyleSheet(f"background:{hex_color}; border:1px solid #444;")
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
        # Tray icon always updates (offline preview); only send if connected.
        if self._tray is not None:
            self._tray.setIcon(icon.make_icon(self._base_color))
        targets = [a for a in self._selected if self._manager.is_connected(a)]
        if not targets:
            return
        c = self._base_color
        results = await self._manager.apply(
            targets, lambda d: d.set_color(c.red(), c.green(), c.blue())
        )
        failed = [a for a, exc in results.items() if exc is not None]
        if failed:
            self._set_status(f"Color send failed: {', '.join(self._display(a) for a in failed)}")

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
            else "No devices found. Is Bluetooth on? Try again."
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
        targets = [a for a in self._selected if self._manager.is_connected(a)]
        if not targets:
            self._set_status("No checked-and-connected device.")
            return
        results = await self._manager.apply(targets, action)
        failed = [a for a, exc in results.items() if exc is not None]
        if failed:
            names = ", ".join(self._display(a) for a in failed)
            self._set_status(f"{len(targets) - len(failed)}/{len(targets)} applied. Failed: {names}")
        elif ok_status:
            self._set_status(f"{ok_status} ({len(targets)} device(s))")

    @asyncSlot()
    async def _on_power_on(self):
        await self._broadcast(lambda d: d.set_power(True), "Turned on.")

    @asyncSlot()
    async def _on_power_off(self):
        await self._broadcast(lambda d: d.set_power(False), "Turned off.")

    # ---- tray / window ---------------------------------------------------

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window()

    def _toggle_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _quit(self):
        self._closing = True
        self._save_state()
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
        self._presets = json.loads(self._settings.value("presets_json", json.dumps(DEFAULT_PRESETS)))

    def _save_state(self):
        self._settings.setValue("known_json", json.dumps(self._known))
        self._settings.setValue("aliases_json", json.dumps(self._aliases))
        self._settings.setValue("selected_json", json.dumps(list(self._selected)))
        self._settings.setValue("presets_json", json.dumps(self._presets))
        self._settings.setValue("color", self._base_color.name())
