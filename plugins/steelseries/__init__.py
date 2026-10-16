"""SteelSeries RGB: an Apex 3 keyboard and a Rival 650 mouse as devices in Lumea's
list -- Windows, driverless: USB HID through hidapi, no SteelSeries GG.

protocol.py builds the packets; this file opens each supported device that is
plugged in and hands it to the app with api.add_device(). Static colour only. No
brick risk: plain HID output reports, nothing written to onboard flash. Other
SteelSeries models are left alone. Read plugins/README.md for the plugin contract.
"""

import logging

try:
    import hid                      # hidapi: Windows only (plugin_runtime.py bundles it there)
except ImportError:
    hid = None

from . import protocol

log = logging.getLogger(__name__)

SS_VID = 0x1038


class Plugin:
    def __init__(self, api):
        self.api = api
        self.devices = [d for d in (Apex3.open(), Rival650.open()) if d is not None]
        if not self.devices:
            log.info("SteelSeries: no supported device found")
        for device in self.devices:
            api.add_device(device)

    def stop(self):
        for device in self.devices:
            self.api.remove_device(device.id)
            device.close()


def _find_path(pid, interface):
    """Path of the given device's control interface, or None if not present."""
    for info in hid.enumerate(SS_VID, pid):
        if info.get("interface_number") == interface:
            return info["path"]
    return None


class _Device:
    """One connection to a SteelSeries device: Lumea's device contract (id, name,
    subtitle, set_color). Writes are synchronous and never read back."""

    pid = 0
    interface = 0
    id = ""
    name = ""
    subtitle = "USB"

    def __init__(self, path):
        self._dev = hid.device()
        self._dev.open_path(path)

    @classmethod
    def open(cls):
        """Open the device, or return None if hidapi / the device is unavailable."""
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


class Apex3(_Device):
    pid = 0x161A
    interface = 3         # vendor control interface (usage_page 0xFFC0)
    id = "steelseries-apex-3"
    name = "SteelSeries Apex 3"
    subtitle = "Keyboard · USB"

    def set_color(self, r, g, b):
        """(r, g, b) with the brightness already applied by the app."""
        self._dev.write(protocol.apex3_brightness(100))  # enable; the app dims via RGB scaling
        self._dev.write(protocol.apex3_color(r, g, b))


class Rival650(_Device):
    pid = 0x172B
    interface = 0         # vendor control interface (usage_page 0xFFC0)
    id = "steelseries-rival-650"
    name = "SteelSeries Rival 650"
    subtitle = "Mouse · USB"

    def set_color(self, r, g, b):
        """(r, g, b) with the brightness already applied by the app. ~45 ms: 32 HID
        writes; the app spaces its pushes to this device accordingly."""
        for zone_id in protocol.RIVAL650_ZONES:      # 8 LEDs, 4 packets each
            for pkt in protocol.rival650_packets(zone_id, r, g, b):
                self._dev.write(pkt)
