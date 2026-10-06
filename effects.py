"""Software colour effects for every device: Rainbow, Breathe, Cycle.

Pure colour maths, no I/O -- the UI ticks an Effect at a steady interval and
sends each frame through the same path as the picker (see ui.py). Nothing here is
a device effect command; the strips' own effect bytes are unverified (protocol.py).
"""

import colorsys
import math

MODES = ("rainbow", "breathe", "cycle")
_BREATHE_FLOOR = 0.05             # dimmest point of a breath (fully dark reads as "off")


class Effect:
    """One running effect. ``step(advance, ...)`` moves it on by ``advance`` (the
    speed-mapped fraction of a rainbow turn per tick) and returns (r, g, b)."""

    def __init__(self, mode, base):
        self.mode = mode
        # Rainbow starts from the picked colour's hue, so turning it on doesn't jump.
        hue = colorsys.rgb_to_hsv(*(c / 255 for c in base))[0]
        self._t = hue if mode == "rainbow" else 0.0

    def step(self, advance, base, palette):
        """``base`` is the picker's (r, g, b); ``palette`` the presets Cycle walks."""
        if self.mode == "rainbow":
            self._t = (self._t + advance) % 1.0
            return _rgb(colorsys.hsv_to_rgb(self._t, 1.0, 1.0))
        if self.mode == "breathe":
            self._t = (self._t + 2 * advance) % 1.0           # a breath is quicker than a turn
            level = _BREATHE_FLOOR + (1 - _BREATHE_FLOOR) * (0.5 - 0.5 * math.cos(2 * math.pi * self._t))
            return tuple(round(c * level) for c in base)
        # cycle: glide from one preset to the next, easing in and out of each
        self._t = (self._t + 3 * advance) % len(palette)
        i = int(self._t)
        f = self._t - i
        f = f * f * (3 - 2 * f)                              # smoothstep
        a, b = palette[i], palette[(i + 1) % len(palette)]
        return tuple(round(x + (y - x) * f) for x, y in zip(a, b))


def _rgb(rgb):
    return tuple(round(c * 255) for c in rgb)
