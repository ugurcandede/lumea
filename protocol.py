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


# --- SteelSeries (USB HID, NOT BLE) --------------------------------------------
#
# Two more USB-HID backends (see steelseries.py), static colour only. No brick
# risk: plain HID output reports, no flash writes. Protocol reproduced from
# OpenRGB (GPLv2) and verified on the user's Apex 3 keyboard and Rival 650 mouse.

# Apex 3 keyboard: 33-byte HID output reports (byte 0 is the report id, 0x00).
# One linear zone of 10 LEDs. The brightness packet MUST be sent or the LEDs stay
# dark, so we send it at full and dim via RGB scaling like every other backend.
APEX3_PACKET_LEN = 33
APEX3_LEDS = 10


def apex3_brightness(level: int) -> bytes:
    """Apex 3 brightness packet (level 0-100). Required or the LEDs stay dark."""
    if not 0 <= level <= 100:
        raise ValueError(f"brightness out of range (0-100): {level}")
    buf = bytearray(APEX3_PACKET_LEN)
    buf[1] = 0x0A
    buf[3] = level
    return bytes(buf)


def apex3_color(r: int, g: int, b: int) -> bytes:
    """Apex 3 solid-colour packet: all 10 zone LEDs set to (r, g, b)."""
    for channel in (r, g, b):
        if not 0 <= channel <= 255:
            raise ValueError(f"color channel out of range (0-255): {channel}")
    buf = bytearray(APEX3_PACKET_LEN)
    buf[1] = 0x0B
    for i in range(APEX3_LEDS):
        off = 3 + i * 3
        buf[off], buf[off + 1], buf[off + 2] = r, g, b
    return bytes(buf)


# Rival 650 mouse: 60-byte payloads, each prefixed with a 0x00 report id -> 61-byte
# HID writes. Each LED (zone_id 0x10-0x17) takes four packets in order: colour,
# config, select, commit. No native brightness (scale RGB client-side).
RIVAL650_ZONES = tuple(range(0x10, 0x18))


def rival650_packets(zone_id: int, r: int, g: int, b: int) -> list[bytes]:
    """The four 61-byte HID writes that set one Rival 650 zone to (r, g, b)."""
    for channel in (r, g, b):
        if not 0 <= channel <= 255:
            raise ValueError(f"color channel out of range (0-255): {channel}")

    color = bytearray(60)
    color[0x00] = 0x03
    color[0x04] = 0x30
    color[0x06] = 0x10
    color[0x07] = 0x27
    color[0x16] = 0x01
    color[0x1E] = 0x04
    color[0x1F], color[0x20], color[0x21] = r, g, b
    color[0x22] = 0xFF
    color[0x27] = 0xFF
    color[0x29] = 0x54
    color[0x2C] = 0xFF
    color[0x2D] = 0x54
    color[0x2E], color[0x2F], color[0x30] = r, g, b
    color[0x31] = 0x56

    config = bytearray(60)
    config[0x00] = 0x03
    config[0x02] = 0x30
    config[0x04] = 0x2C

    select = bytearray(60)
    select[0x00] = 0x05
    select[0x02] = zone_id
    select[0x03] = 0xFF
    select[0x08] = 0x5C

    commit = bytearray(60)
    commit[0x00] = 0x1C
    commit[0x02] = 0x55
    commit[0x04] = 0x46

    # Each write is the 60-byte payload behind a 0x00 report-id byte.
    return [bytes([0x00]) + bytes(p) for p in (color, config, select, commit)]
