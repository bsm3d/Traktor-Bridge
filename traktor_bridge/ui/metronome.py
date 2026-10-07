"""A PCM click track, buffered on its own output and following the preview clock."""

from __future__ import annotations

import logging
import math
import time

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QWidget,
)

from ..model import Track
from . import theme

log = logging.getLogger(__name__)
BUFFER_MS = 30
DISCONTINUITY_MS = 100


def valid_grid(track: Track | None) -> bool:
    return (track is not None and math.isfinite(track.bpm) and track.bpm > 0
            and track.grid is not None and math.isfinite(track.grid) and track.grid >= 0)


def click_samples(track: Track, start_ms: float, frames: int, rate: int) -> np.ndarray:
    """Absolute sample positions avoid rounding the beat period or accumulating drift."""
    if not valid_grid(track):
        raise ValueError("The metronome needs a positive BPM and a first-beat marker.")
    positions = start_ms + np.arange(frames, dtype=np.float64) * 1000 / rate
    beat_ms = 60000 / track.bpm
    indices = np.floor((positions - track.grid) / beat_ms).astype(np.int64)
    age = (positions - (track.grid + indices * beat_ms)) / 1000
    active = (positions >= track.grid) & (age < 0.012)
    if track.duration > 0:
        active &= positions < track.duration * 1000
    samples = np.zeros(frames, dtype=np.float32)
    if not active.any():
        return samples
    age = age[active]
    downbeat = indices[active] % 4 == 0
    frequency = np.where(downbeat, 1600.0, 1100.0)
    envelope = np.maximum(0.0, 1 - age / 0.012) ** 2
    samples[active] = np.sin(2 * np.pi * frequency * age) * envelope * np.where(downbeat, 0.28, 0.18)
    return samples


def pcm(samples: np.ndarray, fmt: QAudioFormat) -> bytes:
    if fmt.channelCount() > 1:
        samples = np.repeat(samples, fmt.channelCount())
    kind = fmt.sampleFormat()
    if kind == QAudioFormat.Float:
        return samples.astype("<f4", copy=False).tobytes()
    if kind == QAudioFormat.Int16:
        return np.rint(samples * 32767).astype("<i2").tobytes()
    if kind == QAudioFormat.Int32:
        return np.rint(samples.astype(np.float64) * 2147483647).astype("<i4").tobytes()
    if kind == QAudioFormat.UInt8:
        return np.rint((samples + 1) * 127.5).astype(np.uint8).tobytes()
    raise ValueError("Unsupported metronome audio format.")


class Metronome(QObject):
    changed = Signal()
    failed = Signal(str)

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.enabled = False
        self.volume = 0.4
        self.offset_ms = 0
        self.sink: QAudioSink | None = None
        self.output = None
        self.format = None
        self.rate = self.frame_bytes = self.buffer_frames = 0
        self.signature = None
        self.written = 0
        self.origin_ms = 0.0
        self.clock_ms = 0.0
        self.clock_stamp = time.monotonic()
        self.clock_valid = False
        self.processed_ms = 0.0
        self.correction_stamp = self.clock_stamp
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(5)
        self.timer.timeout.connect(self.feed)

    def position(self) -> float:
        elapsed = (time.monotonic() - self.clock_stamp) * 1000 if self.engine.playing else 0
        return self.clock_ms + elapsed

    def sync(self, ms: float):
        now = time.monotonic()
        if self.clock_valid and self.engine.playing and abs(ms - self.position()) > DISCONTINUITY_MS:
            self.stop_audio()
        self.clock_ms, self.clock_stamp = ms, now
        self.clock_valid = True

    def transport(self):
        self.stop_audio()
        self.sync(float(self.engine.a.position()))
        self.refresh()

    def refresh(self):
        if self.enabled:
            self.timer.start()
        else:
            self.timer.stop()
            self.stop_audio()
        self.changed.emit()

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self.refresh()

    def set_volume(self, value: float):
        self.volume = max(0.0, min(1.0, value))
        if self.sink is not None:
            self.sink.setVolume(self.volume)
        self.changed.emit()

    def set_offset(self, ms: int):
        self.offset_ms = max(-250, min(250, ms))
        self.stop_audio()
        self.changed.emit()

    def stop_audio(self):
        self.signature = None
        self.output = None
        self.format = None
        if self.sink is not None:
            sink, self.sink = self.sink, None
            sink.stop()
            sink.deleteLater()

    def fail(self, message: str):
        log.error("Metronome: %s", message)
        self.set_enabled(False)
        self.failed.emit(message)

    def start_audio(self, track: Track):
        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            self.fail("No audio output is available. Connect an audio device and enable the metronome again.")
            return
        fmt = device.preferredFormat()
        if not fmt.isValid() or fmt.sampleFormat() not in (QAudioFormat.Float, QAudioFormat.Int16,
                                      QAudioFormat.Int32, QAudioFormat.UInt8):
            self.fail("The audio device has an unsupported format. Select another output device.")
            return
        self.sink = QAudioSink(device, fmt, self)
        self.sink.setVolume(self.volume)
        self.sink.setBufferSize(fmt.bytesForDuration(BUFFER_MS * 1000))
        self.output = self.sink.start()
        if self.output is None:
            self.fail("Cannot start the metronome audio output. Check the audio device and try again.")
            return
        self.format = fmt
        self.rate = fmt.sampleRate()
        self.frame_bytes = fmt.bytesPerFrame()
        self.buffer_frames = max(1, round(self.rate * BUFFER_MS / 1000))
        self.origin_ms = self.position()
        self.written = 0
        self.processed_ms = 0.0
        self.correction_stamp = time.monotonic()
        self.signature = (track, track.bpm, track.grid, self.engine.a)

    def feed(self):
        track = self.engine.timing_track
        if not (self.enabled and self.engine.playing and self.engine.path
                and not self.engine.next_path and valid_grid(track)):
            self.stop_audio()
            return
        signature = (track, track.bpm, track.grid, self.engine.a)
        if self.signature != signature:
            self.stop_audio()
            self.start_audio(track)
        if self.sink is None:
            return
        error = self.sink.error()
        if error not in (type(error).NoError, type(error).UnderrunError):
            self.fail(f"Metronome audio output failed ({error.name}). Check the audio device.")
            return
        # Do not restart while the device is priming: some backends need more than
        # one buffer before processedUSecs advances. Correct drift in future PCM.
        processed_ms = self.sink.processedUSecs() / 1000
        now = time.monotonic()
        if processed_ms > self.processed_ms:
            drift = self.position() - (self.origin_ms + processed_ms)
            if error == type(error).UnderrunError and abs(drift) > DISCONTINUITY_MS:
                self.stop_audio()
                self.start_audio(track)
                return
            # Correction depends on elapsed time, not the number of timer callbacks.
            elapsed = max(0.0, now - self.correction_stamp)
            self.origin_ms += drift if abs(drift) > 50 else drift * (1 - math.exp(-elapsed / 0.25))
            self.processed_ms = processed_ms
            self.correction_stamp = now
        fmt = self.format
        consumed = min(self.written, int(processed_ms * self.rate / 1000))
        queued = self.written - consumed
        frames = min(self.sink.bytesFree() // self.frame_bytes, max(0, self.buffer_frames - queued))
        if frames <= 0:
            return
        start = self.origin_ms + self.written * 1000 / self.rate - self.offset_ms
        raw = pcm(click_samples(track, start, frames, self.rate), fmt)
        count = self.output.write(raw)
        if count < 0 or count > len(raw) or count % self.frame_bytes:
            self.fail("Cannot write the metronome audio buffer. Check the audio device and try again.")
            return
        self.written += count // self.frame_bytes

    def close(self):
        self.enabled = False
        self.timer.stop()
        self.stop_audio()


class MetronomeControls(QWidget):
    def __init__(self, engine, track, parent=None, compact: bool = False):
        super().__init__(parent)
        self.engine, self.track = engine, track
        bar = QHBoxLayout(self)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(4 if compact else 6)
        self.button = QPushButton("♩" if compact else "Metronome")
        self.button.setAccessibleName("Metronome")
        if compact:
            self.button.setFixedSize(28, 24)
        self.button.setCheckable(True)
        self.button.setStyleSheet(
            f"QPushButton:checked {{ background: {theme.ACCENT}; font-weight: bold; }}"
        )
        self.button.toggled.connect(engine.metronome.set_enabled)
        self.button.setToolTip("Check the beat grid while playing; the first beat of each bar is accented")
        bar.addWidget(self.button)
        bar.addWidget(QLabel("Vol" if compact else "Click volume"))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(58 if compact else 90)
        self.volume.setToolTip("Metronome volume, independent of the track volume")
        self.volume.setAccessibleName("Metronome volume")
        self.volume.valueChanged.connect(lambda v: engine.metronome.set_volume(v / 100))
        bar.addWidget(self.volume)
        bar.addWidget(QLabel("Offset" if compact else "Click offset"))
        self.offset = QSpinBox()
        self.offset.setRange(-250, 250)
        self.offset.setSuffix(" ms")
        if compact:
            self.offset.setFixedWidth(72)
        self.offset.setAccessibleName("Metronome timing offset")
        self.offset.setToolTip("Positive delays the click; negative advances it to compensate audio-device latency")
        self.offset.valueChanged.connect(engine.metronome.set_offset)
        bar.addWidget(self.offset)
        self.status = QLabel()
        if compact:
            self.status.setVisible(False)
        else:
            bar.addWidget(self.status)
            bar.addStretch(1)
        engine.metronome.changed.connect(self.refresh)
        engine.metronome.failed.connect(self.show_error)
        self.refresh()

    def refresh(self):
        metro, track = self.engine.metronome, self.track()
        self.button.blockSignals(True)
        self.button.setChecked(metro.enabled)
        self.button.blockSignals(False)
        other = self.engine.playing and self.engine.timing_track is not track
        self.button.setEnabled(metro.enabled or (valid_grid(track) and not other))
        self.volume.blockSignals(True)
        self.volume.setValue(round(metro.volume * 100))
        self.volume.blockSignals(False)
        self.offset.blockSignals(True)
        self.offset.setValue(metro.offset_ms)
        self.offset.blockSignals(False)
        self.status.setText("Playing another track" if other else
                            "Set BPM and first beat" if not valid_grid(track) else
                            "Muted during crossfade" if metro.enabled and self.engine.next_path else
                            "On during playback" if metro.enabled and not self.engine.playing else "")

    def show_error(self, message: str):
        if self.isVisible() and self.window().isActiveWindow():
            QMessageBox.warning(self, "Metronome", message)
