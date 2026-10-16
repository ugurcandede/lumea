"""Pure byte encoders for SteelSeries Apex 3 / Rival 650 (USB HID). No I/O.

Static colour only, no brick risk: plain HID output reports, no flash writes.
Protocol reproduced from OpenRGB (GPLv2) and verified on an Apex 3 keyboard and a
Rival 650 mouse (see __init__.py).
"""

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
