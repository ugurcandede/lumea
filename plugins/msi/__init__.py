"""MSI Mystic Light: the motherboard's RGB (and its RGB/ARGB headers) as a device
in Lumea's list -- Windows, driverless: USB HID through hidapi, no MSI Center.

protocol.py builds the one verified feature report; this file opens the controller
and hands it to the app with api.add_device(). Static colour only, applied live
(never written to flash): the firmware's effect/mode bytes are undocumented and
have bricked boards, so they are never sent. Only the verified 185-byte controller
variant is driven -- any other is detected and left untouched. Read
plugins/README.md for the plugin contract.
"""

import logging

try:
    import hid                      # hidapi: Windows only (plugin_runtime.py bundles it there)
except ImportError:
    hid = None

from . import protocol

log = logging.getLogger(__name__)

MSI_VID = 0x1462
_PRODUCT = "MYSTIC LIGHT"
_USAGE_PAGE = 0x0001


class Plugin:
    def __init__(self, api):
        self.api = api
        self.device = open_controller()
        if self.device is None:
            log.info("MSI Mystic Light: no supported controller found")
            return
        api.add_device(self.device)

    def stop(self):
        if self.device is not None:
            self.api.remove_device(self.device.id)
            self.device.close()


def _find_path():
    """Path of the Mystic Light HID interface, or None if not present."""
    if hid is None:
        return None
    for info in hid.enumerate(MSI_VID, 0):
        product = (info.get("product_string") or "").strip().upper()
        if product == _PRODUCT and info.get("usage_page") == _USAGE_PAGE:
            return info["path"]
    return None


def open_controller():
    """Open the Mystic Light controller, or return None if unavailable."""
    try:
        path = _find_path()          # hid.enumerate can raise on a flaky HID stack
        if path is None:
            return None
        return MysticLight(path)
    except Exception:
        log.exception("MSI Mystic Light open failed")
        return None


class MysticLight:
    """One connection to the motherboard's Mystic Light controller: Lumea's device
    contract (id, name, subtitle, set_color). Writes are synchronous (~1 ms) and
    never read back; like every device in the list, the app shows the last colour
    it sent."""

    id = "msi-mystic-light"
    name = "MSI Mystic Light"
    subtitle = "Motherboard · USB"

    def __init__(self, path):
        self._dev = hid.device()
        self._dev.open_path(path)
        try:
            self._base = self._read_base()
        except Exception:
            self.close()  # don't leak the open handle if the probe fails
            raise

    def _read_base(self):
        # Current 185-byte state; its untouched zones are preserved on every write.
        data = list(self._dev.get_feature_report(protocol.MSI_REPORT_ID, 200))
        if len(data) == protocol.MSI_PACKET_LEN - 1:   # some stacks omit the report id
            data = [protocol.MSI_REPORT_ID] + data
        if len(data) < protocol.MSI_PACKET_LEN:        # verified board returns 185 (PoC allowed 186)
            raise RuntimeError(f"unsupported Mystic Light variant (probe returned {len(data)} bytes)")
        data = data[:protocol.MSI_PACKET_LEN]          # tolerate a trailing extra byte
        data[0] = protocol.MSI_REPORT_ID
        return bytes(data)

    def set_color(self, r, g, b):
        """(r, g, b) with the brightness already applied by the app."""
        self._dev.send_feature_report(protocol.msi_frame(self._base, r, g, b))

    def close(self):
        try:
            self._dev.close()
        except Exception:
            pass
