"""Pure byte encoders for MSI Mystic Light (USB HID). No I/O and no device state.

A different backend from Lumea's BLE strips: the motherboard's Mystic Light
controller is a USB HID device driven by a feature report, not a BLE
characteristic (see __init__.py). Protocol reproduced from OpenRGB's
MSIMysticLight185Controller (GPLv2) and verified on an MSI MPG Z790 CARBON WIFI
(MS-7D89). Only the STATIC color frame is built here; effect/mode bytes are the
class that bricked some boards and are never sent -- don't fabricate bytes,
capture real ones first.
"""

MSI_REPORT_ID = 0x52
MSI_PACKET_LEN = 185
MSI_MODE_STATIC = 0x01
_MSI_SAVE_LIVE = 0x00           # apply to live LEDs only; never persist to flash
_MSI_FULL_BRIGHTNESS = 0x28     # speed/brightness byte: (brightness 10 << 2) | speed 0
# Byte offset of each driven zone's 10-byte block in the 185-byte packet
# (JRGB1, JPIPE1, JRAINBOW1/2/3, onboard). The onboard block needs the
# SYNC_SETTING_ONBOARD bit (0x01) in colorFlags or the firmware keeps running its
# own effect; header blocks use 0x80.
_MSI_ZONE_OFFSETS = (1, 11, 31, 42, 53, 74)
_MSI_ONBOARD_OFFSET = 74


def msi_frame(base: bytes, r: int, g: int, b: int) -> bytes:
    """MSI Mystic Light static-color feature report: report id 0x52, 185 bytes.

    ``base`` is the controller's current 185-byte buffer (read once over HID), so
    zones we don't drive are preserved. Each driven zone is set to a STATIC
    ``(r, g, b)``. Pure -- no device I/O (see __init__.py).
    """
    for channel in (r, g, b):
        if not 0 <= channel <= 255:
            raise ValueError(f"color channel out of range (0-255): {channel}")
    if len(base) != MSI_PACKET_LEN:
        raise ValueError(f"base must be {MSI_PACKET_LEN} bytes, got {len(base)}")

    buf = bytearray(base)
    buf[0] = MSI_REPORT_ID
    for off in _MSI_ZONE_OFFSETS:
        color_flags = 0x81 if off == _MSI_ONBOARD_OFFSET else 0x80
        buf[off:off + 10] = bytes(
            (MSI_MODE_STATIC, r, g, b, _MSI_FULL_BRIGHTNESS, r, g, b, color_flags, 0x00)
        )
    buf[MSI_PACKET_LEN - 1] = _MSI_SAVE_LIVE
    return bytes(buf)

