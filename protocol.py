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


def scaled_color(r: int, g: int, b: int, brightness: int) -> bytes:
    """Dim ``(r, g, b)`` by ``brightness`` (0-100) on the client side.

    This is NOT the device's PWM dimming command (that payload is unverified for
    this hardware). It scales the RGB channels and reuses the confirmed COLOR
    frame, which works visually on every variant. ``brightness`` 100 returns the
    unmodified color; 0 returns black (visually off).
    """
    if not 0 <= brightness <= 100:
        raise ValueError(f"brightness out of range (0-100): {brightness}")
    factor = brightness / 100
    return color(round(r * factor), round(g * factor), round(b * factor))


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
