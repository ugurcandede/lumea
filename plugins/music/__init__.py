"""Music mode: the lights follow whatever the PC is playing -- Pulse, Spectrum,
Beat or Flow. Windows (WASAPI loopback) and macOS 13+ (ScreenCaptureKit).

capture.py listens, engine.py turns audio into a colour per tick, row.py is the
row in the editor. Frames go through api.begin_live / live_frame, the same path
as the app's effects. Read plugins/README.md for the plugin contract.
"""

import json
import logging

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QColor

from . import capture, engine
from .row import Row

log = logging.getLogger(__name__)

INTERVAL_MS = 33            # ~30 colour frames/s; slower links get the newest frame
_SETTINGS = "plugin_music"


class Plugin:
    def __init__(self, api):
        self.api = api
        s = QSettings()
        # Defaults from the keys Lumea used while music mode was built in.
        self.sensitivity = s.value(f"{_SETTINGS}/sensitivity",
                                   s.value("music_sensitivity", engine.DEFAULT_SENSITIVITY, type=int), type=int)
        self.bands = json.loads(s.value(f"{_SETTINGS}/bands_json",
                                        s.value("music_bands_json", json.dumps(engine.DEFAULT_BANDS))))
        self.mode = None                     # None, or one of engine.MODES
        self._capture = None
        self._engine = None
        self._base = (255, 255, 255)         # the picker's colour and the presets, kept
        self._palette = []                   # from state() on `changed` (not read per tick)
        self._row = None
        self._timer = QTimer()
        self._timer.setInterval(INTERVAL_MS)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)   # coarse timers run ~20 fps
        self._timer.timeout.connect(self._tick)
        api.changed.connect(self._on_changed)
        self._on_changed()
        api.register("music", self.state, {"set_mode": self.set_mode, "set_sensitivity": self.set_sensitivity,
                                           "set_band": self.set_band})

    def stop(self):
        self.api.changed.disconnect(self._on_changed)
        self.set_mode(None)
        self.api.unregister("music")

    def editor_widget(self):
        self._row = Row(self)
        return self._row

    def state(self):
        return {"modes": list(engine.MODES), "mode": self.mode, "sensitivity": self.sensitivity,
                "bands": dict(zip(engine.BANDS, self.bands))}

    # ---- commands (the row, and the remote through api.call) ----------------

    def set_mode(self, mode):
        if mode is None:
            if self.mode is not None:
                self._halt()
                self.api.end_live()
            self._refresh()                  # re-check Off: clicking a checked chip unchecks it
            return
        if mode not in engine.MODES:
            return
        if self._capture is None:
            try:
                self._capture = capture.open_capture()
            except capture.CaptureError as e:
                self.api.show_status(str(e))
                self._refresh()              # drop the clicked chip's check
                return
            self._engine = engine.Engine(self._capture.rate, self.sensitivity, self.bands)
        self.mode = mode
        self._timer.start()
        self.api.begin_live(self._label(), f"{self._label()}. Bluetooth strips may lag behind the music.")
        self._refresh()

    def set_sensitivity(self, value):
        if isinstance(value, int) and 1 <= value <= 100:
            self.sensitivity = value
            if self._engine is not None:
                self._engine.sensitivity = value
            QSettings().setValue(f"{_SETTINGS}/sensitivity", value)
            self._refresh()

    def set_band(self, band, value):
        if band in engine.BANDS and isinstance(value, int) and 1 <= value <= 100:
            i = engine.BANDS.index(band)
            self.bands[i] = value
            if self._engine is not None:
                self._engine.bands[i] = value
            QSettings().setValue(f"{_SETTINGS}/bands_json", json.dumps(self.bands))
            self._refresh()

    # ---- running ---------------------------------------------------------------

    def _label(self):
        return f"Music: {self.mode.capitalize()}"

    def _halt(self):
        """Stop ticking and listening; the lights are the app's business."""
        self.mode = None
        self._timer.stop()
        if self._capture is not None:
            self._capture.close()
            self._capture = self._engine = None

    def _refresh(self):
        self.api.notify()                    # state()["plugins"]["music"] moved
        if self._row is not None:
            self._row.refresh()

    def _on_changed(self):
        s = self.api.state()
        c = QColor(s["color"])
        self._base = (c.red(), c.green(), c.blue())
        self._palette = [QColor(h).getRgb()[:3] for h in s["presets"]]
        if self.mode is not None and s["live"] != self._label():
            # The app ended the session: an effect started, the power went off, ...
            self._halt()
            self._refresh()

    def _tick(self):
        try:
            samples = self._capture.read()
        except capture.CaptureError as e:    # the backend says why (macOS: permission, stream ended)
            log.error("%s", e)
            self._lost(str(e))
            return
        except Exception:                    # the output device went away
            log.exception("audio capture failed")
            self._lost("Music stopped: the audio device went away.")
            return
        self.api.live_frame(self._engine.step(samples, self.mode, self._base, self._palette))

    def _lost(self, why):
        self._halt()
        self.api.end_live()
        self.api.show_status(why)
        self._refresh()
