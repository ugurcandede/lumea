"""LumeaAPI: the one surface plugins use to read and drive the app (see plugin_host.py).

`state()` is a plain, JSON-ready snapshot; `changed` fires (coalesced, once per
event-loop turn) whenever any of it may have moved, and `frame` carries each
effect / music colour. Commands go through the same widgets and handlers as a
click in the window, so the desktop UI follows whatever a plugin does -- and a
command the UI wouldn't allow right now (a locked checkbox, a disabled button)
is ignored the same way.

This module is the only plugin-side code allowed to touch LedController's
private members; keeping that in one place is what lets the UI change freely.
"""

import asyncio

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QSlider

import effects
import updates


# (major, minor). Additions to LumeaAPI bump the minor; anything that could break an
# existing plugin (a removed or renamed member, a changed meaning) bumps the major
# and resets the minor. A plugin declares the version it was written against as
# "api" in plugins/version.json; see plugin_host.compatible().
# 2.0: music mode became a plugin -- music_modes / music / sensitivity / bands and
# set_music / set_sensitivity / set_band are gone. New: "live" and "plugins" in
# state(), begin_live / live_frame / end_live, register / unregister / call, and
# the optional Plugin.editor_widget() (a row under Effect, like settings_widget).
API_VERSION = (2, 0)


class LumeaAPI(QObject):
    changed = Signal()
    frame = Signal(str)           # "#rrggbb" the devices show (effect / music, brightness applied)

    def __init__(self, controller):
        super().__init__(controller)
        self._c = controller
        self._notify_timer = QTimer(self)
        self._notify_timer.setSingleShot(True)
        self._notify_timer.setInterval(0)          # coalesce a burst of changes into one signal
        self._notify_timer.timeout.connect(self.changed)
        self._plugins = {}                         # name -> (state fn, {command: fn}), see register()

    def notify(self):
        """Called by the controller whenever state may have changed."""
        self._notify_timer.start()

    # ---- reading ----------------------------------------------------------

    def state(self):
        c = self._c
        devices = [{"id": ctl.card_id, "name": ctl.name, "kind": "usb", "connected": True,
                    "in_range": True, "selectable": True, "checked": c._is_synced(ctl)}
                   for ctl in c._locals]
        for address in sorted(c._known, key=lambda a: c._display(a).lower()):
            devices.append({"id": address, "name": c._display(address), "kind": "ble",
                            "connected": c._manager.is_connected(address),
                            "in_range": c._reachable(address), "selectable": c._present(address),
                            "checked": address in c._selected})
        link = c._link_btn
        return {
            "version": QCoreApplication.applicationVersion() or "dev",
            "summary": c._conn_summary(),
            "status": c._status.text(),
            "power": c._power_on,
            "color": c._base_color.name(),
            "brightness": c._brightness,
            "presets": list(c._presets),
            "editable": c._editor_active(),          # False: nothing to edit (the desktop hides the editor)
            "target": c._focus if c._focus is not None else ("all" if c._bulk else None),
            "effects": list(effects.MODES),
            "effect": c._fx.mode if c._fx is not None else None,
            "effect_speed": c._fx_speed,
            "live": c._live_label,                   # what a plugin drives the lights with (begin_live), or None
            "plugins": {name: state() for name, (state, _) in self._plugins.items()},   # see register()
            "msi_effect": c._msi_effect if c._msi is not None else None,
            "devices": devices,
            "scanning": not c._scan_btn.isEnabled(),
            "link": link.text().lower() if link.isEnabled() else None,   # "connect" | "disconnect" | None
            # Settings (1.1)
            "theme": c._theme_mode,                  # "auto" | "light" | "dark"
            "tray_color_icon": c._tray_color_icon,
            "update": {                              # mirrors Settings > About > Updates
                "latest": c._update.version if c._update is not None else None,
                "state": c._update_state,            # idle | updating | not_in_brew_yet | failed
                "checking": c._update_checking,
                "note": c._update_note,              # the row's text when no update is known
                "can_install": updates.install_kind() is not None,
            },
        }

    # ---- commands ---------------------------------------------------------

    def set_power(self, on):
        asyncio.ensure_future(self._c._set_power(bool(on)))

    def set_color(self, hex_color):
        color = QColor(hex_color)
        if color.isValid():
            self._c._picker.set_color(color)        # -> _on_picker_changed: stamps + sends

    def set_brightness(self, value):
        self._c._brightness_slider.setValue(int(value))

    def apply_preset(self, index):
        if 0 <= index < len(self._c._presets):
            self._c._apply_preset(index)

    def save_preset(self, index):
        if 0 <= index < len(self._c._presets):
            self._c._save_preset(index)

    def set_target(self, target):
        """"all", a strip address, or None (nothing targeted)."""
        c = self._c
        if target in c._known:
            c._on_card_focus(target)
            return
        c._focus = None
        c._bulk = target == "all"
        c._refresh_focus_ui()

    def set_effect(self, mode):
        if mode is None or mode in effects.MODES:
            self._c._set_fx_mode(mode)

    def set_effect_speed(self, value):
        self._c._fx_speed_row.findChild(QSlider).setValue(int(value))

    def set_checked(self, device_id, on):
        """Tick a strip into the control group, or sync a USB device."""
        card = self._c._cards.get(device_id) or self._c._local_cards.get(device_id)
        if card is not None and card._check.isEnabled():
            card._check.setChecked(bool(on))        # -> the card's toggled handler

    def scan(self):
        self._c._scan_btn.click()                   # no-op while disabled (scanning, BT blocked)

    def link(self):
        """The primary Connect / Disconnect action, as state()["link"] names it."""
        self._c._link_btn.click()

    def rename(self, address, name):
        if address in self._c._known:
            self._c._rename(address, name)

    def forget(self, address):
        if address in self._c._known:
            self._c._on_card_remove(address)

    def set_msi_effect(self, mode):
        c = self._c
        card = c._local_cards.get(c._msi.card_id) if c._msi is not None else None
        if card is not None and mode in ("static", "rainbow") and card._effect_btn.isEnabled():
            card._select_effect(mode)

    def show_status(self, text):
        self._c._set_status(text)

    # ---- settings (1.1) ------------------------------------------------------

    def set_theme(self, mode):
        if mode in ("auto", "light", "dark"):
            self._c._on_theme_mode(mode)

    def set_tray_color_icon(self, on):
        self._c._tray_switch.setChecked(bool(on))     # -> _on_toggle_tray_color_icon

    def check_updates(self):
        c = self._c
        if c._update is None and not c._update_checking:
            c._on_update_row_clicked()

    def install_update(self):
        """Only where Lumea updates itself; elsewhere the desktop button opens the
        release page in a browser, which a remote press shouldn't do on the PC."""
        if self._c._update is not None and updates.install_kind() is not None:
            self._c._start_update()

    # ---- driving the lights (2.0) --------------------------------------------

    def begin_live(self, label, status=None):
        """Take the lights over, as an effect does: every live_frame() goes to the
        picker's targets with the brightness applied, and the picker stands back.
        ``label`` ("Music: Pulse") is what state()["live"] and the tray show. It
        ends with end_live() -- or when an effect starts, the power goes off or
        another plugin takes over: then state()["live"] no longer names ``label``
        (watch `changed`), and the plugin should stop producing frames."""
        c = self._c
        c._stop_live()                              # one driver at a time
        c._live_label = str(label)
        c._start_live(status or f"{label}.")

    def live_frame(self, rgb):
        """One (r, g, b) frame, ignored unless begin_live() is in force."""
        if self._c._live_label is not None:
            self._c._drive(tuple(int(v) for v in rgb))

    def end_live(self):
        c = self._c
        if c._live_label is not None:
            c._stop_live()
            c._color_timer.start()                  # hand every device back to the picker

    # ---- a plugin's own state and commands (2.0) ------------------------------

    def register(self, name, state, commands):
        """Publish ``state()`` (a JSON-ready dict) as state()["plugins"][name] and
        ``commands`` ({command: callable}) for call(): how other plugins -- the
        remote control -- read and drive yours. Call notify() when the state moves."""
        self._plugins[name] = (state, commands)
        self.notify()

    def unregister(self, name):
        self._plugins.pop(name, None)
        self.notify()

    def call(self, plugin, command, args=()):
        """Run a registered command; False if there is no such plugin or command.
        The arguments come from whoever calls (a phone): the command checks them."""
        entry = self._plugins.get(plugin)
        if entry is None or command not in entry[1]:
            return False
        entry[1][command](*args)
        return True
