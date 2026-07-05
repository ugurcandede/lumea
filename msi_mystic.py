"""MSI Mystic Light (USB HID) transport -- optional Windows motherboard RGB.

Mirrors ble.py's role for a different backend. The motherboard's Mystic Light
controller is a USB HID device that self-identifies as "MYSTIC LIGHT"; we drive it
in pure user space via hidapi (no kernel driver, no MSI software) using the
static-color feature report built in protocol.py.

hidapi is an OPTIONAL dependency. If it is missing, or no supported controller is
present, `open_controller()` returns None and the UI simply omits the MSI sync
toggle. Only the verified 185-byte controller variant is driven -- any other
variant is left untouched, since the wrong byte layout can brick the controller.
"""

import logging

try:
    import hid
except ImportError:  # optional; the feature is hidden when absent
    hid = None

import protocol

log = logging.getLogger(__name__)

MSI_VID = 0x1462
_PRODUCT = "MYSTIC LIGHT"
_USAGE_PAGE = 0x0001


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
    """One connection to the motherboard's Mystic Light controller.

    Writes are synchronous and fast (~1 ms), so the UI calls set_color directly --
    no asyncio needed. Like the BLE strips, the device is never read back for state.
    """

    # Common local-controller interface (shared with steelseries.py) so the UI can
    # list every USB device the same way. MSI alone supports the software rainbow.
    card_id = "msi-mystic-light"
    name = "MSI Mystic Light"
    subtitle = "Motherboard · USB"
    effect = True

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

    def set_color(self, r, g, b, brightness=100):
        r, g, b = protocol.scale_rgb(r, g, b, brightness)
        self._dev.send_feature_report(protocol.msi_frame(self._base, r, g, b))

    def close(self):
        try:
            self._dev.close()
        except Exception:
            pass
