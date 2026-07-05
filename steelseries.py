"""SteelSeries RGB (USB HID) transport -- optional keyboard / mouse colour sync.

Like msi_mystic.py, a driverless USB-HID backend: SteelSeries devices are plain
HID and accept output reports, so there is no kernel driver and no brick risk.
Each supported device that is present is returned as its own controller (one
Devices row). Protocol reproduced from OpenRGB (GPLv2), verified on an Apex 3
keyboard and a Rival 650 mouse. Static colour only -- no effect modes.

hidapi is an OPTIONAL dependency; if it is missing, `open_controllers()` returns
an empty list and the UI simply omits the SteelSeries rows.
"""

import logging

try:
    import hid
except ImportError:  # optional; the feature is hidden when absent
    hid = None

import protocol

log = logging.getLogger(__name__)

SS_VID = 0x1038


def _find_path(pid, interface):
    """Path of the given device's control interface, or None if not present."""
    for info in hid.enumerate(SS_VID, pid):
        if info.get("interface_number") == interface:
            return info["path"]
    return None


class _Controller:
    """One connection to a SteelSeries device. Writes are synchronous and never
    read back (optimistic state), mirroring the BLE and MSI backends."""

    pid = 0
    interface = 0
    card_id = ""
    name = ""
    subtitle = "USB"
    effect = False        # no per-device rainbow menu (the picker drives it)

    def __init__(self, path):
        self._dev = hid.device()
        self._dev.open_path(path)

    @classmethod
    def open(cls):
        """Open the device, or return None if hidapi/the device is unavailable."""
        if hid is None:
            return None
        try:
            path = _find_path(cls.pid, cls.interface)  # enumerate can raise on a flaky stack
            if path is None:
                return None
            return cls(path)
        except Exception:
            log.exception("%s open failed", cls.name)
            return None

    def close(self):
        try:
            self._dev.close()
        except Exception:
            pass


class Apex3(_Controller):
    pid = 0x161A
    interface = 3         # vendor control interface (usage_page 0xFFC0)
    card_id = "steelseries-apex-3"
    name = "SteelSeries Apex 3"
    subtitle = "Keyboard · USB"

    def set_color(self, r, g, b, brightness=100):
        r, g, b = protocol.scale_rgb(r, g, b, brightness)
        self._dev.write(protocol.apex3_brightness(100))  # enable; dim via RGB scaling
        self._dev.write(protocol.apex3_color(r, g, b))


class Rival650(_Controller):
    pid = 0x172B
    interface = 0         # vendor control interface (usage_page 0xFFC0)
    card_id = "steelseries-rival-650"
    name = "SteelSeries Rival 650"
    subtitle = "Mouse · USB"

    def set_color(self, r, g, b, brightness=100):
        r, g, b = protocol.scale_rgb(r, g, b, brightness)
        for zone_id in protocol.RIVAL650_ZONES:      # 8 LEDs, 4 packets each
            for pkt in protocol.rival650_packets(zone_id, r, g, b):
                self._dev.write(pkt)


def open_controllers():
    """Every supported SteelSeries device present, as controller objects."""
    if hid is None:
        return []
    return [c for c in (Apex3.open(), Rival650.open()) if c is not None]
