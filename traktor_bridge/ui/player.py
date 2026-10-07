# Benoit Saint-Moulin
# Traktor Bridge : preview player (two decks for the crossfade, waveform, cue pads)

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import keys, tags
from ..model import CUE, LOOP, LOOP_BEATS, Cue, Track
from . import cuehistory, theme
from .metronome import Metronome, MetronomeControls
from .waveform import Loader
from .zoomwave import (  # noqa: F401, re-exported
    ZoomControls,
    ZoomWave,
    clock,
    cue_color,
    paint_cues,
    paint_wave,
    quantize_to_beat,
)

# ============================================================
# Audio
# ============================================================

class Engine(QObject):
    """Deck A plays, deck B only exists during a crossfade."""

    metadata_changed = Signal(object)

    def __init__(self):
        super().__init__(QApplication.instance())
        self.decks = []
        for _ in range(2):
            pl, out = QMediaPlayer(self), QAudioOutput(self)
            pl.setAudioOutput(out)
            self.decks.append((pl, out))
        self.volume = 0.7
        self._closed = False
        self.path = ""
        self.next_path = ""
        self.loop: tuple[Track, Cue] | None = None
        self.snap_to_beat = False
        self.timing_track: Track | None = None
        self.next_track: Track | None = None
        self.metronome = Metronome(self)
        self.metronome.setParent(self)
        for pl, _ in self.decks:
            pl.positionChanged.connect(self.position_changed)
            pl.playbackStateChanged.connect(self.state_changed)

    @Slot(int)
    def position_changed(self, ms):
        if self.sender() is self.a:
            self.metronome.sync(ms)

    @Slot(QMediaPlayer.PlaybackState)
    def state_changed(self, _state):
        if self.sender() is self.a:
            self.metronome.transport()

    @property
    def a(self) -> QMediaPlayer:
        return self.decks[0][0]

    def set_volume(self, v: float):
        self.volume = max(0.0, min(1.0, v))
        self.decks[0][1].setVolume(self.volume)

    def play(self, path: str, track: Track | None = None) -> bool:
        if not os.path.isfile(path):
            return False
        source = QUrl.fromLocalFile(path)
        if (self.path == path and not self.next_path and self.a.source() == source
                and self.a.mediaStatus() != QMediaPlayer.InvalidMedia):
            self.a.stop()
            self.a.setPosition(0)
            self.timing_track = track
            self.decks[0][1].setVolume(self.volume)
            self.a.play()
            return True
        self.stop()
        self.timing_track = track
        self.path = path
        self.a.setSource(source)
        self.decks[0][1].setVolume(self.volume)
        self.a.play()
        return True

    def toggle(self):
        if self.playing:
            self.a.pause()
        else:
            self.a.play()

    def stop(self):
        for pl, _ in self.decks:
            pl.stop()
            pl.setSource(QUrl())
        self.decks[1][1].setVolume(0)
        self.path = self.next_path = ""
        self.timing_track = self.next_track = None
        self.metronome.stop_audio()

    def seek(self, ms: float):
        self.a.setPosition(max(0, int(ms)))
        self.metronome.transport()

    @property
    def playing(self) -> bool:
        return self.a.playbackState() == QMediaPlayer.PlayingState

    def fade_to(self, path: str, track: Track | None = None):
        b, out = self.decks[1]
        out.setVolume(0)
        b.setSource(QUrl.fromLocalFile(path))
        b.play()
        self.next_path = path
        self.next_track = track
        self.metronome.stop_audio()

    def fade(self, k: float) -> bool:
        """k 0..1, returns True once B took over."""
        self.decks[0][1].setVolume(self.volume * (1 - k))
        self.decks[1][1].setVolume(self.volume * k)
        if k < 1:
            return False
        self.a.stop()
        self.a.setSource(QUrl())
        self.decks.reverse()
        self.path, self.next_path = self.next_path, ""
        self.timing_track, self.next_track = self.next_track, None
        self.metronome.transport()
        return True

    def close(self):
        if self._closed:
            return
        self._closed = True
        for pl, _ in self.decks:
            pl.positionChanged.disconnect(self.position_changed)
            pl.playbackStateChanged.disconnect(self.state_changed)
        self.metronome.close()
        for pl, _ in self.decks:
            pl.stop()
            pl.setSource(QUrl())


# ============================================================
# Widgets
# ============================================================

class WaveView(ZoomWave):
    dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.dropped.emit(u.toLocalFile())
                return


class Player(QFrame):
    """Needs a playlist context to continue; resolve(track) gives the file to play."""

    dropped = Signal(str)
    changed = Signal()          # the track moved on (continue mode) or its cues changed
    touched = Signal()          # the cues were edited here (a project has to be saved)

    def __init__(self, engine: Engine, loader: Loader, cfg: dict, parent=None):
        super().__init__(parent)
        self.engine, self.loader, self.cfg = engine, loader, cfg
        self.track: Track | None = None
        self._shown_loop: Cue | None = None
        self.path = ""
        self.tracks: list[Track] = []
        self.resolve = lambda t: t.path
        self.loop: Cue | None = None
        self.fading = 0.0
        # Cue position when this track is not playing.
        self.mark = 0.0

        self.setStyleSheet("QFrame { background: #12121c; }")
        self.setAcceptDrops(True)
        top = QHBoxLayout()
        self.art = QLabel("")
        self.art.setFixedSize(52, 52)
        self.art.setStyleSheet(f"background: {theme.BG_MED};")
        info = QVBoxLayout()
        self.title = QLabel("No track loaded, pick one in the list or drop a file")
        self.title.setStyleSheet("font-weight: bold;")
        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color: {theme.FG_MUTED}; font-size: 9pt;")
        self.view = WaveView()
        self.view.setMinimumHeight(86)
        info.addWidget(self.title)
        info.addWidget(self.meta)
        wave_row = QHBoxLayout()
        wave_row.addWidget(self.view, 1)
        self.zoom_controls = ZoomControls(self.view, vertical=True)
        wave_row.addWidget(self.zoom_controls)
        info.addLayout(wave_row, 1)
        top.addWidget(self.art)
        top.addLayout(info, 1)

        self.transport_controls = QWidget()
        bar = QHBoxLayout(self.transport_controls)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(5)
        self.btn = QToolButton()
        self.btn.setText("▶")
        self.btn.setFixedWidth(34)
        self.btn.setAccessibleName("Play or pause playback")
        self.btn.setToolTip("Start or pause preview playback (Space/P)")
        self.btn.clicked.connect(self.toggle)
        self.time = QLabel(clock(0))
        self.time.setStyleSheet("font-family: Consolas, monospace;")
        bar.addWidget(self.btn)
        bar.addWidget(self.time)
        bar.addWidget(QLabel("Hot cues"))
        self.pads = []
        for i in range(8):
            b = QPushButton("ABCDEFGH"[i])
            b.setFixedSize(26, 26)
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.clicked.connect(lambda _=False, s=i: self.pad(s))
            b.customContextMenuRequested.connect(lambda pos, s=i: self.show_pad_menu(s, pos))
            self.pads.append(b)
            bar.addWidget(b)
        self.snap_btn = QPushButton("S")
        self.snap_btn.setFixedSize(30, 26)
        self.snap_btn.setAccessibleName("Snap cues to beat")
        self.snap_btn.setCheckable(True)
        self.snap_btn.setChecked(engine.snap_to_beat)
        self.snap_btn.setToolTip("Snap new and moved cues to the nearest beat (S)")
        self.snap_btn.toggled.connect(self.set_snap_to_beat)
        self.set_snap_to_beat(engine.snap_to_beat)
        bar.addWidget(self.snap_btn)
        self.metronome_controls = MetronomeControls(engine, lambda: self.track, compact=True)
        bar.addWidget(self.metronome_controls)
        playback = QHBoxLayout()
        playback.addStretch(1)
        self.mode = QComboBox()
        self.mode.addItems(["Single", "Continue"])
        self.fade_box = QSpinBox()
        self.fade_box.setRange(0, 10)
        self.fade_box.setSuffix(" s")
        self.fade_box.setValue(int(cfg.get("crossfade", 3)))
        self.fade_box.valueChanged.connect(lambda v: cfg.__setitem__("crossfade", v))
        playback.addWidget(self.mode)
        playback.addWidget(QLabel("Fade"))
        playback.addWidget(self.fade_box)
        self.toolbar = QGridLayout()
        self.toolbar.setColumnStretch(1, 1)
        self.toolbar.addWidget(self.transport_controls, 0, 0)
        self.toolbar.addLayout(playback, 0, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 4)
        lay.addLayout(top, 1)
        lay.addLayout(self.toolbar)

        self.view.seek.connect(self.seek)
        self.view.need_hi.connect(self.want_hi)
        self.view.cue_moved.connect(self.cue_moved)
        self.view.grid_moved.connect(self.grid_moved)
        self.view.dropped.connect(self.dropped)
        loader.ready.connect(self.wave_ready)
        loader.hi_ready.connect(self.hi_ready)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(40)
        self.refresh_pads()

    # ---- loading

    def load(self, t: Track, path: str):
        self.engine.loop = None
        self.track, self.path, self.mark = t, path, 0.0
        self.title.setText(f"{t.artist}  -  {t.title}" if t.artist else t.title)
        self.refresh_meta()
        self.metronome_controls.refresh()
        self.view.mode = self.cfg.get("waveform_color", "RGB")
        self.view.show_track(t, self.loader.get(path) if path else None)
        self.view.set_pos(0.0)
        self.set_art(path)
        self.refresh_pads()

    def refresh_meta(self):
        if not self.track:
            self.meta.clear()
            return
        t = self.track
        k = keys.name(t.key, self.cfg.get("key_format", "Open Key"))
        self.meta.setText("  |  ".join(s for s in (f"BPM {t.bpm:.2f}" if t.bpm else "", k,
                                                   f"{t.gain:+.1f} dB" if t.gain else "",
                                                   clock(t.duration * 1000)) if s))

    def set_art(self, path: str):
        img = tags.artwork(path) if path else None
        pm = QPixmap()
        if img and pm.loadFromData(img):
            self.art.setPixmap(pm.scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.art.clear()

    def wave_ready(self, path: str, wave):
        if path == self.path:
            self.view.show_track(self.track, wave)

    def want_hi(self):
        if self.path:
            h = self.loader.get_hi(self.path)
            if h is not None:
                self.view.set_hi(h)

    def hi_ready(self, path: str, arr):
        if path == self.path and arr is not None:
            self.view.set_hi(arr)

    # ---- transport

    def position(self) -> float:
        """The playing position, or the needle where the user put it."""
        return float(self.engine.a.position()) if self.engine.path == self.path else self.mark

    def seek(self, ms: float):
        """Moves the needle, without playing when the track is not the one playing."""
        self.mark = max(0.0, ms)
        if self.engine.path == self.path:
            self.engine.seek(ms)
        self.view.set_pos(self.mark)

    def play(self):
        if not self.track:
            return
        if self.engine.path == self.path:
            self.engine.timing_track = self.track
            if not self.engine.playing:
                self.engine.toggle()
        else:
            self.engine.play(self.path, self.track)
            if self.mark > 0:
                self.engine.seek(self.mark)

    def toggle(self):
        if self.engine.path == self.path and self.engine.playing:
            self.engine.toggle()
        else:
            self.play()

    def stop(self):
        self.engine.stop()
        self.loop = None

    def tick(self):
        self.metronome_controls.refresh()
        self.snap_btn.setChecked(self.engine.snap_to_beat)
        self.view.snap_to_beat = self.engine.snap_to_beat
        if self.loop is not self._shown_loop:
            self.refresh_pads()
        on = self.engine.playing and self.engine.path == self.path
        self.btn.setText("⏸" if on else "▶")
        if self.engine.path != self.path:
            self.time.setText(f"{clock(self.mark)} / {clock(self.view.dur)}")
            return
        pos = self.engine.a.position()
        self.time.setText(f"{clock(pos)} / {clock(self.view.dur)}")
        if pos != self.view.needle:
            self.view.set_pos(pos)
        if self.engine.timing_track is not self.track:
            self.fading = 0.0
            return
        if self.loop and on and pos >= self.loop.start + self.loop.length:
            self.engine.seek(self.loop.start)
            return
        if self.fading:
            self.step_fade()
        elif on and self.mode.currentIndex() == 1 and self.view.dur > 0:
            fade_ms = self.fade_box.value() * 1000
            if pos >= self.view.dur - max(fade_ms, 300):
                self.start_next(fade_ms)

    def start_next(self, fade_ms: int):
        if not self.track or self.track not in self.tracks:
            return
        i = self.tracks.index(self.track)
        for t in self.tracks[i + 1:]:
            p = self.resolve(t)
            if p and os.path.isfile(p):
                break
        else:
            return
        self.next = (t, p)
        if fade_ms <= 0:
            self.load(t, p)
            self.engine.play(p, t)
            self.changed.emit()
            return
        self.engine.fade_to(p, t)
        self.fading = 0.001
        self.fade_len = fade_ms

    def step_fade(self):
        self.fading += 40 / self.fade_len
        if self.engine.fade(min(1.0, self.fading)):
            self.fading = 0.0
            t, p = self.next
            self.load(t, p)
            self.changed.emit()

    # ---- cues

    def pad(self, slot: int, play: bool = False, delete: bool | None = None):
        """A pad or key: sets the cue when the slot is free, otherwise goes to it (and plays
        from it when play is set). delete: remove it, by default when ctrl is held."""
        if not self.track:
            return
        c = next((c for c in self.track.cues if c.hotcue == slot), None)
        if delete is None:
            delete = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        if c is not None and delete:
            cuehistory.mark(self.track)
            self.track.cues.remove(c)
            if self.loop is c:
                self.loop = None
        elif c is None:
            cuehistory.mark(self.track)
            pos = quantize_to_beat(self.track, self.position()) if self.engine.snap_to_beat else self.position()
            self.track.cues.append(Cue(kind=CUE, start=pos, hotcue=slot))
        elif c.is_loop:
            self.loop = None if self.loop is c else c
            if self.loop:
                self.seek(c.start)
                if play:
                    self.play()
            self.refresh_pads()
            return
        else:
            # a pad only moves the needle, a key also plays from the cue
            self.seek(c.start)
            if play:
                self.play()
            return
        self.refresh_pads()
        self.changed.emit()
        self.touched.emit()

    def cue_moved(self, _c: Cue):
        self.refresh_pads()
        self.changed.emit()
        self.touched.emit()

    def grid_moved(self, _track: Track):
        self.refresh_meta()
        self.metronome_controls.refresh()
        self.refresh_pads()
        self.changed.emit()
        self.touched.emit()

    def undo(self, redo: bool = False) -> bool:
        """Ctrl+Z / Ctrl+Y on the cues of the loaded track."""
        if not self.track or not (cuehistory.redo if redo else cuehistory.undo)(self.track):
            return False
        self.refresh_meta()
        self.refresh_pads()
        self.changed.emit()
        self.touched.emit()
        return True

    def pad_menu(self, slot: int) -> QMenu:
        menu = QMenu(self.pads[slot])
        for beats in LOOP_BEATS:
            menu.addAction(
                f"Set {beats}-beat loop",
                lambda _checked=False, s=slot, n=beats: self.set_loop(s, n),
            )
        if self.track and any(c.hotcue == slot for c in self.track.cues):
            menu.addSeparator()
            menu.addAction(
                f"Remove cue {chr(ord('A') + slot)}",
                lambda _checked=False, s=slot: self.remove_pad(s),
            )
        return menu

    def show_pad_menu(self, slot: int, pos):
        menu = self.pad_menu(slot)
        try:
            menu.exec(self.pads[slot].mapToGlobal(pos))
        finally:
            menu.deleteLater()

    def remove_pad(self, slot: int):
        if not self.track:
            return
        cue = next((c for c in self.track.cues if c.hotcue == slot), None)
        if cue is None:
            return
        cuehistory.mark(self.track)
        self.track.cues.remove(cue)
        if self.loop is cue:
            self.loop = None
        self.refresh_pads()
        self.changed.emit()
        self.touched.emit()

    def set_loop(self, slot: int, beats: int = 4):
        if not self.track:
            return
        if beats not in LOOP_BEATS:
            raise ValueError(f"Loop length must be one of {LOOP_BEATS} beats")
        pos = self.position()
        if self.engine.snap_to_beat:
            pos = quantize_to_beat(self.track, pos)
        beat = 60000 / self.track.bpm if self.track.bpm else 500
        cuehistory.mark(self.track)
        previous = next((c for c in self.track.cues if c.hotcue == slot), None)
        was_active = previous is not None and self.loop is previous
        self.track.cues = [c for c in self.track.cues if c.hotcue != slot]
        cue = Cue(kind=LOOP, start=pos, length=beats * beat, hotcue=slot)
        self.track.cues.append(cue)
        if was_active:
            self.loop = cue
        self.refresh_pads()
        self.changed.emit()
        self.touched.emit()

    def set_snap_to_beat(self, enabled: bool):
        self.engine.snap_to_beat = enabled
        self.view.snap_to_beat = enabled
        self.snap_btn.setText("S")
        self.snap_btn.setStyleSheet(
            f"QPushButton:checked {{ background: {theme.ACCENT}; font-weight: bold; }}"
        )

    def refresh_pads(self):
        active_loop = self.loop
        if self.engine.loop is not None and self.engine.loop[0] is self.track and active_loop is None:
            self.engine.loop = None
        self._shown_loop = active_loop
        if active_loop is not None and not (self.track and any(c is active_loop for c in self.track.cues)):
            self.loop = None
        self.view.update()
        used = {c.hotcue: c for c in self.track.cues} if self.track else {}
        for i, b in enumerate(self.pads):
            c = used.get(i)
            if c is None:
                b.setStyleSheet(f"background: {theme.BG_MED}; color: {theme.FG_MUTED}; padding: 0;")
                b.setToolTip(f"click or key {'ABCDEFGH'[i]}: set a cue at the needle (playing or not), "
                             "right-click: create a 1, 2, 4 or 8 beat loop")
            else:
                col = cue_color(c)
                active = c.is_loop and active_loop is c
                border = (" border: 2px solid white;" if active else
                          f" border: 1px solid {theme.FG_MUTED};" if c.is_loop else "")
                b.setStyleSheet(
                    f"background: {col}; color: black; font-weight: bold; padding: 0;{border}"
                )
                action = "click to deactivate" if active else "click to activate"
                b.setToolTip(
                    f"{c.name or 'Cue'} at {clock(c.start)}"
                    + (f" ({clock(c.length)}, {action} loop)" if c.is_loop else "")
                    + f"; key {chr(ord('A') + i)}: jump/play"
                    "; right-click: loop length or remove; ctrl+click or shift+key: delete"
                )
        self.view.update()

    @property
    def loop(self) -> Cue | None:
        state = self.engine.loop
        if state is None or state[0] is not self.track:
            return None
        return state[1]

    @loop.setter
    def loop(self, cue: Cue | None):
        if cue is None:
            if self.engine.loop is not None and self.engine.loop[0] is self.track:
                self.engine.loop = None
        elif self.track is not None:
            self.engine.loop = (self.track, cue)

    # ---- drops

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.dropped.emit(u.toLocalFile())
                return

    def closeEvent(self, e):
        self.timer.stop()
        super().closeEvent(e)
