"""Where the audio comes from: a never-blocking `read()` of what the PC plays,
polled by the plugin's timer, so there is no audio thread of our own.

Windows: WASAPI loopback through PyAudioWPatch (no microphone, no virtual
device). macOS 13+: ScreenCaptureKit through pyobjc; it hands buffers to a
callback on its own queue, which only decodes and queues them for `read()`.
That needs the Screen & System Audio Recording permission: macOS asks on the
first start, and the app must be relaunched after granting.

Lumea bundles these libraries for its platform (plugin_runtime.py); the
`sys.platform` guards keep the other platform's out of the plugin's "requires"
(see plugins/README.md).
"""

import logging
import sys
from collections import deque

import numpy as np
from PySide6.QtCore import QSysInfo

from .engine import WINDOW

if sys.platform == "win32":
    import pyaudiowpatch as pyaudio
elif sys.platform == "darwin":
    import objc
    import CoreMedia
    import ScreenCaptureKit as sck
    from Foundation import NSObject

log = logging.getLogger(__name__)


class CaptureError(Exception):
    """The capture can't start or was lost; the message is for the user."""


def open_capture():
    """A capture of the current default output; raises CaptureError if there is none."""
    if sys.platform == "win32":
        pa = pyaudio.PyAudio()
        try:
            return Capture(pa, pa.get_default_wasapi_loopback())
        except Exception:
            log.exception("no WASAPI loopback device")
            pa.terminate()
            raise CaptureError("No audio output to listen to.") from None
    if sys.platform == "darwin" and int(QSysInfo.productVersion().split(".")[0]) >= 13:
        return Capture()
    raise CaptureError("Music mode needs Windows or macOS 13+.")


if sys.platform == "win32":

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

elif sys.platform == "darwin":
    RATE = 48000
    PERMISSION = ("Can't listen to the system audio. Allow Lumea under System Settings > Privacy & "
                  "Security > Screen & System Audio Recording, then relaunch Lumea.")

    # The Objective-C side: receives the stream's audio buffers (SCStreamOutput) and
    # its end (SCStreamDelegate), and hands both to the Capture. An Objective-C class
    # is registered once per process, and this module runs again whenever the plugin
    # is switched on, so a class left by an earlier run is reused.
    try:
        LumeaMusicOutput = objc.lookUpClass("LumeaMusicOutput")
    except objc.nosuchclass_error:
        class LumeaMusicOutput(NSObject, protocols=[objc.protocolNamed("SCStreamOutput"),
                                                    objc.protocolNamed("SCStreamDelegate")]):
            def stream_didOutputSampleBuffer_ofType_(self, stream, sample, kind):
                if kind == sck.SCStreamOutputTypeAudio:
                    self.capture._push(sample)

            def stream_didStopWithError_(self, stream, error):
                self.capture._error = f"Music stopped: {error.localizedDescription()}"

    class Capture:
        """ScreenCaptureKit audio of the whole display, mono. `read()` is empty until
        the stream is up (the display list, then the start, come back on
        ScreenCaptureKit's threads)."""

        rate = RATE

        def __init__(self):
            self._chunks = deque()               # mono float32 arrays, oldest first
            self._error = None                   # set from the callbacks; read() raises it
            self._closed = False
            self._stream = None
            self._output = LumeaMusicOutput.alloc().init()
            self._output.capture = self
            sck.SCShareableContent.getShareableContentWithCompletionHandler_(self._on_content)

        def _on_content(self, content, error):
            if self._closed:
                return
            if error is not None:                # almost always: permission not granted
                log.error("shareable content: %s", error)
                self._error = PERMISSION
                return
            display = content.displays()[0]
            filt = sck.SCContentFilter.alloc().initWithDisplay_excludingWindows_(display, [])
            config = sck.SCStreamConfiguration.alloc().init()
            config.setCapturesAudio_(True)
            config.setExcludesCurrentProcessAudio_(True)
            config.setSampleRate_(RATE)
            config.setChannelCount_(1)
            # Video is captured regardless; make it as cheap as it gets (nothing reads it).
            config.setWidth_(2)
            config.setHeight_(2)
            config.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1, 1))
            stream = sck.SCStream.alloc().initWithFilter_configuration_delegate_(filt, config, self._output)
            ok, err = stream.addStreamOutput_type_sampleHandlerQueue_error_(
                self._output, sck.SCStreamOutputTypeAudio, None, None)
            if not ok:
                log.error("add audio output: %s", err)
                self._error = f"Can't listen to the system audio: {err.localizedDescription()}"
                return
            self._stream = stream
            stream.startCaptureWithCompletionHandler_(lambda error: self._on_started(stream, error))

        def _on_started(self, stream, error):
            if error is not None:
                log.error("start capture: %s", error)
                self._error = PERMISSION
            elif self._closed:                   # closed while starting: don't leave it recording
                stream.stopCaptureWithCompletionHandler_(lambda error: None)

        def _push(self, sample):
            block = CoreMedia.CMSampleBufferGetDataBuffer(sample)
            status, data = CoreMedia.CMBlockBufferCopyDataBytes(
                block, 0, CoreMedia.CMBlockBufferGetDataLength(block), None)
            if status != 0:
                return
            frames = CoreMedia.CMSampleBufferGetNumSamples(sample)
            # Float32, one channel as configured; more would arrive as planes, averaged here.
            self._chunks.append(np.frombuffer(data, dtype=np.float32).reshape(-1, frames).mean(axis=0))

        def read(self):
            """Mono float samples delivered since the last call."""
            if self._error is not None:
                raise CaptureError(self._error)
            chunks = [self._chunks.popleft() for _ in range(len(self._chunks))]
            return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)

        def close(self):
            self._closed = True
            if self._stream is not None:
                self._stream.stopCaptureWithCompletionHandler_(lambda error: None)
                self._stream = None
