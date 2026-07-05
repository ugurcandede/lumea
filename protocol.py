"""Pure command encoders for ELK-BLEDOM / MELK BLE LED strips.

Each function/constant returns the exact byte payload to write to the strip's
write characteristic (see ble.py). No I/O and no device state here, so the wire
format can be unit-tested without a Bluetooth connection.

Only the POWER and COLOR frames below are confirmed for this hardware.
Brightness and effect/mode payloads differ between BLEDOM and BLEDOB variants
and are intentionally left unimplemented -- see the notes at the bottom. Do not
fabricate them; capture the real bytes first.
"""

# Confirmed power frames (9 bytes each).
POWER_ON = bytes((0x7E, 0x00, 0x04, 0xF0, 0x00, 0x01, 0xFF, 0x00, 0xEF))
POWER_OFF = bytes((0x7E, 0x00, 0x04, 0x00, 0x00, 0x00, 0xFF, 0x00, 0xEF))
# Some older firmwares ignore POWER_ON above and need this one instead.
POWER_ON_LEGACY = bytes((0x7E, 0x00, 0x04, 0x01, 0x00, 0x00, 0x00, 0x00, 0xEF))


def power(on: bool) -> bytes:
    """Power frame for the strip. ``on=False`` -> POWER_OFF."""
    return POWER_ON if on else POWER_OFF


def color(r: int, g: int, b: int) -> bytes:
    """Static RGB color frame. Each channel must be 0-255."""
    for channel in (r, g, b):
        if not 0 <= channel <= 255:
            raise ValueError(f"color channel out of range (0-255): {channel}")
    return bytes((0x7E, 0x00, 0x05, 0x03, r, g, b, 0x00, 0xEF))


def scale_rgb(r: int, g: int, b: int, brightness: int) -> tuple[int, int, int]:
    """Dim ``(r, g, b)`` by ``brightness`` (0-100). Shared by the BLE and MSI
    paths so both backends render the same visible color."""
    if not 0 <= brightness <= 100:
        raise ValueError(f"brightness out of range (0-100): {brightness}")
    factor = brightness / 100
    return round(r * factor), round(g * factor), round(b * factor)


def scaled_color(r: int, g: int, b: int, brightness: int) -> bytes:
    """Dim ``(r, g, b)`` by ``brightness`` (0-100) on the client side.

    This is NOT the device's PWM dimming command (that payload is unverified for
    this hardware). It scales the RGB channels and reuses the confirmed COLOR
    frame, which works visually on every variant. ``brightness`` 100 returns the
    unmodified color; 0 returns black (visually off).
    """
    return color(*scale_rgb(r, g, b, brightness))


# --- UNVERIFIED -- capture real bytes (BTScan.py / Wireshark) before enabling ---
#
# Native brightness (device PWM). BLEDOB reference frame, may differ on BLEDOM:
#     7e 04 01 <level 0-100> 01 ff 02 01 ef
# def brightness_native(level: int) -> bytes:
#     # TODO: verify byte format for this device
#     return bytes((0x7E, 0x04, 0x01, level, 0x01, 0xFF, 0x02, 0x01, 0xEF))
#
# Effects / modes: preset ids are device-specific. Do not expose in the UI until
# the real bytes are confirmed.
#     # TODO: verify effect preset bytes for this device


# --- MSI Mystic Light (USB HID, NOT BLE) ---------------------------------------
#
# A different backend entirely (see msi_mystic.py): the motherboard's Mystic Light
# controller is a USB HID device driven by a feature report, not a BLE
# characteristic. Protocol reproduced from OpenRGB's MSIMysticLight185Controller
# (GPLv2) and verified on an MSI MPG Z790 CARBON WIFI (MS-7D89). Only the STATIC
# color frame is built here; effect/mode bytes are the class that bricked some
# boards and are never sent -- same "don't fabricate bytes" rule as above.
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
    ``(r, g, b)``. Pure -- no device I/O (see msi_mystic.py).
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
