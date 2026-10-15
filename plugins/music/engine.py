"""Turns audio into one colour per tick. Pure maths over numpy, no I/O.

A band's level is its loudness (dBFS) placed in a fixed window: dark at the
bottom, full _RANGE_DB higher. Nothing adapts to the track, so a setting means
the same light at the same volume. Sensitivity slides the window (1: full only
near a full-scale signal, 100: full on the faintest sound); each band's slider
cuts that band before it is placed (100 = as captured).
"""

import colorsys
import math
from collections import deque

import numpy as np

MODES = ("pulse", "spectrum", "beat", "flow")
BANDS = ("low", "mid", "high")
WINDOW = 2048                     # samples analysed per tick (~43 ms at 48 kHz)
_BANDS = ((20, 250), (250, 2000), (2000, 8000))   # Hz, in BANDS order
_SILENCE = 1e-4                   # RMS below this is treated as no audio
_ATTACK = 0.6                     # per-tick rise toward a higher level (1 = instant)
_RELEASE = 0.8                    # per-tick fall-off once a level drops
_RANGE_DB = 30
_FULL_DB = (18, -60)              # dBFS at which a band reads full, at sensitivity 1 and 100 (50: -21)
_BAND_STEP_DB = 0.4               # cut per band-slider step below 100 (1 = -40 dB)
_KICK_BAND = (30, 150)            # Hz watched for beats
_KICK_WINDOW = 1024               # newest samples the kick is read from: shorter = less lag
_BEAT_HISTORY = 45                # ticks of kick flux the beat threshold adapts to (~1.5 s)
_BEAT_GAP = 6                     # min ticks between beats (~200 ms at 33 ms/tick)
_BEAT_K = 1.5                     # std devs the kick flux must rise above its mean to count
# Beat look: each beat jumps _BEAT_STRIDE presets ahead (coprime with the 12
# presets, so all are visited, and neighbours in the default palette are far apart
# on the hue wheel), flashes to full and settles at _BEAT_REST. A slow-ish fade
# reads better over BLE, which skips frames.
_BEAT_STRIDE = 5
_BEAT_FADE = 0.85
_BEAT_REST = 0.45
DEFAULT_SENSITIVITY = 50          # 1-100, see Engine
DEFAULT_BANDS = (100, 100, 100)   # 1-100 per band, see Engine


class Engine:
    """Turns successive sample chunks into a colour for the chosen mode.

    All rates are per tick, so call `step` at a steady interval. ``sensitivity``
    (1-100) sets how loud a band must be to light up, ``bands`` (1-100 each, in
    BANDS order) cut the low / mid / high band before that; see _RANGE_DB above.
    """

    def __init__(self, rate, sensitivity=DEFAULT_SENSITIVITY, bands=DEFAULT_BANDS):
        self.sensitivity = sensitivity
        self.bands = list(bands)
        self._buf = np.zeros(WINDOW, dtype=np.float32)
        self._empty = 0                      # consecutive reads with no samples
        self._window = np.hanning(WINDOW).astype(np.float32)
        # Band magnitudes -> RMS in full-scale units (Parseval over the band's
        # bins): a full-scale sine reads -3 dBFS whatever the band's width.
        self._norm = WINDOW * float(np.sqrt(np.mean(self._window ** 2)))
        freqs = np.fft.rfftfreq(WINDOW, 1 / rate)
        self._masks = [(freqs >= lo) & (freqs < hi) for lo, hi in _BANDS]
        kick_freqs = np.fft.rfftfreq(_KICK_WINDOW, 1 / rate)
        self._kick = (kick_freqs >= _KICK_BAND[0]) & (kick_freqs < _KICK_BAND[1])
        self._kick_window = np.hanning(_KICK_WINDOW).astype(np.float32)
        self._levels = [0.0] * len(_BANDS)   # smoothed 0..1 per band
        self._prev_kick = None
        self._flux = deque(maxlen=_BEAT_HISTORY)
        self._since_beat = _BEAT_GAP
        self._flash = 0.0
        self._beat_index = 0
        self._hue = 0.0

    def step(self, samples, mode, base, palette):
        """(r, g, b) for this tick. ``base`` is the picker's (r, g, b);
        ``palette`` is a list of (r, g, b) that Beat steps through."""
        beat = self._analyse(samples)
        bass, mid, treble = self._levels
        level = max(self._levels)
        if mode == "pulse":
            return _scale(base, level)
        if mode == "spectrum":
            return tuple(round(255 * v) for v in (bass, mid, treble))
        if mode == "beat":
            if beat:
                self._beat_index = (self._beat_index + _BEAT_STRIDE) % len(palette)
                self._flash = 1.0
            else:
                self._flash *= _BEAT_FADE
            # The flash-and-settle look, as bright as the music reads.
            return _scale(palette[self._beat_index], level * max(self._flash, _BEAT_REST))
        # flow: the hue turns faster the louder the music
        self._hue = (self._hue + 0.002 + 0.03 * level) % 1.0
        r, g, b = colorsys.hsv_to_rgb(self._hue, 1.0, 0.3 + 0.7 * level)
        return round(r * 255), round(g * 255), round(b * 255)

    def _analyse(self, samples):
        # Slide the newest samples into the window. A tick can land between two
        # audio packets and read nothing, so only a run of empty reads (playback
        # stopped) clears the window and lets the lights fade out.
        fresh = len(samples) > 0
        if fresh:
            self._buf = np.concatenate((self._buf, samples))[-WINDOW:]
            self._empty = 0
        else:
            self._empty += 1
            if self._empty >= 3:
                self._buf[:] = 0
        silent = float(np.sqrt(np.mean(self._buf ** 2))) < _SILENCE
        mags = np.abs(np.fft.rfft(self._buf * self._window))

        dark_db = _FULL_DB[0] - (self.sensitivity - 1) / 99 * (_FULL_DB[0] - _FULL_DB[1]) - _RANGE_DB
        raw = []
        for i, m in enumerate(self._masks):
            x = 0.0
            if not silent:
                rms = math.sqrt(2 * float(np.sum(mags[m] ** 2))) / self._norm
                db = 20 * math.log10(max(rms, 1e-6)) - (100 - self.bands[i]) * _BAND_STEP_DB
                x = min(1.0, max(0.0, (db - dark_db) / _RANGE_DB))
            raw.append(x)
            lvl = self._levels[i]
            self._levels[i] = lvl + (x - lvl) * _ATTACK if x > lvl else max(x, lvl * _RELEASE)

        # Beat: a jump in kick-band energy (spectral flux) well above its recent
        # spread -- adapts to tracks with a constant bassline, unlike a raw level.
        # It only counts while the low band reads at all, so the sensitivity and
        # the Low slider decide which kicks are loud enough.
        self._since_beat += 1
        if not fresh or silent:
            return False
        # Own short window over the newest audio: the main window's taper all but
        # hides a kick that just landed.
        kick = np.abs(np.fft.rfft(self._buf[-_KICK_WINDOW:] * self._kick_window))[self._kick]
        flux = 0.0 if self._prev_kick is None else float(np.sum(np.maximum(kick - self._prev_kick, 0)))
        self._prev_kick = kick
        history = self._flux
        beat = False
        if len(history) >= 10:
            threshold = float(np.mean(history)) + _BEAT_K * float(np.std(history))
            beat = flux > threshold and self._since_beat >= _BEAT_GAP and raw[0] > 0
        history.append(flux)
        if beat:
            self._since_beat = 0
        return beat


def _scale(rgb, factor):
    return tuple(round(c * factor) for c in rgb)
