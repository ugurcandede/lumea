"""Music-reactive colour -- optional, Windows only.

Captures whatever the system is playing through WASAPI loopback (PyAudioWPatch)
and turns it into one RGB colour per tick. The stream is polled from a Qt timer
with non-blocking reads (get_read_available + read), so like the rest of the app
there is no audio thread and no callback.

PyAudioWPatch and numpy are OPTIONAL dependencies. If either is missing, or there
is no loopback device, `open_capture()` returns None and the UI hides the mode.
"""

import colorsys
import logging
from collections import deque

try:
    import numpy as np
    import pyaudiowpatch as pyaudio
except ImportError:  # optional; the feature is hidden when absent
    np = pyaudio = None

log = logging.getLogger(__name__)

MODES = ("pulse", "spectrum", "beat", "flow")
WINDOW = 2048                     # samples analysed per tick (~43 ms at 48 kHz)
_BANDS = ((20, 250), (250, 2000), (2000, 8000))   # bass, mid, treble (Hz)
_SILENCE = 1e-4                   # RMS below this is treated as no audio
_PEAK_DECAY = 0.99                # per-tick decay of each band's running peak
_FLOOR_RATE = 0.02                # per-tick pull of each band's background toward its level
_MIN_RANGE = 0.5                  # swings under this fraction of the background are ignored
_ATTACK = 0.6                     # per-tick rise toward a higher level (1 = instant)
_RELEASE = 0.8                    # per-tick fall-off once a level drops
_KICK_BAND = (30, 150)            # Hz watched for beats
_KICK_WINDOW = 1024               # newest samples the kick is read from: shorter = less lag
_BEAT_HISTORY = 45                # ticks of kick flux the beat threshold adapts to (~1.5 s)
_BEAT_GAP = 6                     # min ticks between beats (~200 ms at 33 ms/tick)
# Beat look: each beat jumps _BEAT_STRIDE presets ahead (coprime with the 12
# presets, so all are visited, and neighbours in the default palette are far apart
# on the hue wheel), flashes to full and settles at _BEAT_REST. A slow-ish fade
# reads better over BLE, which skips frames.
_BEAT_STRIDE = 5
_BEAT_FADE = 0.85
_BEAT_REST = 0.45
DEFAULT_SENSITIVITY = 50          # 1-100, see Engine.sensitivity


def available() -> bool:
    return pyaudio is not None


class Capture:
    """Loopback of the default output device. Reads never block."""

    def __init__(self, pa, device):
        self._pa = pa
        self._channels = device["maxInputChannels"]
        self.rate = int(device["defaultSampleRate"])
        self._stream = pa.open(format=pyaudio.paInt16, channels=self._channels, rate=self.rate,
                               input=True, input_device_index=device["index"],
                               frames_per_buffer=WINDOW)

    def read(self):
        """Mono float samples captured since the last call (empty while silent:
        WASAPI loopback delivers nothing when nothing is playing)."""
        n = self._stream.get_read_available()
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        raw = self._stream.read(n, exception_on_overflow=False)
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
        return data.reshape(-1, self._channels).mean(axis=1)

    def close(self):
        try:
            self._stream.close()
        finally:
            self._pa.terminate()


def open_capture():
    """A Capture on the current default output, or None if unavailable."""
    if pyaudio is None:
        return None
    pa = pyaudio.PyAudio()
    try:
        return Capture(pa, pa.get_default_wasapi_loopback())
    except Exception:
        log.exception("no WASAPI loopback device")
        pa.terminate()
        return None


class Engine:
    """Turns successive sample chunks into a colour for the chosen mode.

    All rates are per tick, so call `step` at a steady interval. Levels are
    normalised against each band's decaying peak, so it adapts to the volume.

    ``sensitivity`` (1-100) moves four things together: how much of the steady
    background is subtracted, the gate below which a band reads as dark, how much
    quiet parts are lifted, and how far a kick must stand out to count as a beat.
    """

    def __init__(self, rate, sensitivity=DEFAULT_SENSITIVITY):
        self.sensitivity = sensitivity
        self._buf = np.zeros(WINDOW, dtype=np.float32)
        self._empty = 0                      # consecutive reads with no samples
        self._window = np.hanning(WINDOW).astype(np.float32)
        freqs = np.fft.rfftfreq(WINDOW, 1 / rate)
        self._masks = [(freqs >= lo) & (freqs < hi) for lo, hi in _BANDS]
        kick_freqs = np.fft.rfftfreq(_KICK_WINDOW, 1 / rate)
        self._kick = (kick_freqs >= _KICK_BAND[0]) & (kick_freqs < _KICK_BAND[1])
        self._kick_window = np.hanning(_KICK_WINDOW).astype(np.float32)
        self._peaks = [1e-3] * len(_BANDS)
        self._floors = [0.0] * len(_BANDS)   # steady background, read as dark
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
            return _scale(palette[self._beat_index], max(self._flash, _BEAT_REST))
        # flow: the hue turns faster the louder the music
        self._hue = (self._hue + 0.002 + 0.03 * level) % 1.0
        r, g, b = colorsys.hsv_to_rgb(self._hue, 1.0, 0.3 + 0.7 * level)
        return round(r * 255), round(g * 255), round(b * 255)

    def _analyse(self, samples):
        # Slide the newest samples into the window. A tick can land between two
        # WASAPI packets and read nothing, so only a run of empty reads (playback
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
        energies = [0.0 if silent else float(np.sqrt(np.mean(mags[m] ** 2))) for m in self._masks]

        s = self.sensitivity / 100
        gate = 0.5 * (1 - s)                 # 0.5 at 1 ... 0 at 100
        boost = 1 - 0.6 * s                  # level exponent: 1 (linear) ... 0.4 (lifts quiet parts)
        keep = 1 - 0.8 * s * s               # share of the background subtracted: all ... a fifth (mostly at the top)
        for i, e in enumerate(energies):
            # Level = where e sits between the band's background and its recent
            # peak, so a constant hum or bassline doesn't hold the band at full.
            self._peaks[i] = peak = max(e, self._peaks[i] * _PEAK_DECAY, 1e-3)
            floor = self._floors[i]
            self._floors[i] = floor = floor + (e - floor) * _FLOOR_RATE
            base = floor * keep
            x = (e - base) / max(peak - base, _MIN_RANGE * floor, 1e-6)
            x = max(0.0, (x - gate) / (1 - gate)) ** boost
            lvl = self._levels[i]
            self._levels[i] = lvl + (x - lvl) * _ATTACK if x > lvl else max(x, lvl * _RELEASE)

        # Beat: a jump in kick-band energy (spectral flux) well above its recent
        # spread -- adapts to tracks with a constant bassline, unlike a raw level.
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
            k = 2.5 - 2.5 * s                # std devs above the mean: 2.5 at 1 ... 0 at 100
            threshold = float(np.mean(history)) + k * float(np.std(history))
            beat = flux > threshold and self._since_beat >= _BEAT_GAP
        history.append(flux)
        if beat:
            self._since_beat = 0
        return beat


def _scale(rgb, factor):
    return tuple(round(c * factor) for c in rgb)
