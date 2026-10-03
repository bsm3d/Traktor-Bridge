# Benoit Saint-Moulin
# Traktor Bridge : preview player (two decks for the crossfade, waveform, cue pads)

from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import keys, tags
from ..model import CUE, LOOP, Cue, Track
from . import theme
from .waveform import Loader, Wave


def clock(ms: float) -> str:
    if ms < 0:
        return "--:--.-"
    s = ms / 1000
    return f"{int(s // 60):02d}:{s % 60:04.1f}"


_pix: dict = {}


def paint_wave(p: QPainter, rect: QRectF, wave: Wave | None, mode: str):
    """Drawn once per wave, size and colour mode, then blitted: the player repaints
    25 times a second only to move the needle."""
    if not wave:
        draw_wave(p, rect, wave, mode)
        return
    k = (id(wave), int(rect.width()), int(rect.height()), mode)
    hit = _pix.get(k)
    # the wave is kept next to its pixmap, a freed wave could hand its id to another
    pm = hit[1] if hit is not None and hit[0] is wave else None
    if pm is None:
        if len(_pix) > 16:
            _pix.clear()
        pm = QPixmap(k[1], k[2])
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        draw_wave(q, QRectF(0, 0, k[1], k[2]), wave, mode)
        q.end()
        _pix[k] = (wave, pm)
    p.drawPixmap(int(rect.left()), int(rect.top()), pm)


def draw_wave(p: QPainter, rect: QRectF, wave: Wave | None, mode: str):
    mid = rect.center().y()
    half = rect.height() / 2 - 1
    w = int(rect.width())
    if not wave:
        p.setPen(QColor(theme.BG_LIGHT))
        p.drawLine(int(rect.left()), int(mid), int(rect.right()), int(mid))
        return
    n = len(wave)
    for x in range(w):
        a, b = x * n // w, max(x * n // w + 1, (x + 1) * n // w)
        lo = max(v[0] for v in wave[a:b])
        mi = max(v[1] for v in wave[a:b])
        hi = max(v[2] for v in wave[a:b])
        top = max(lo, mi, hi)
        if mode == "Blue":
            c = QColor.fromRgbF(0.2 + 0.6 * hi, 0.4 + 0.5 * hi, 1.0)
        elif mode == "IR":
            c = QColor.fromRgbF(1.0, 0.3 + 0.6 * hi, 0.1 + 0.4 * hi)
        else:
            # squared shares: whichever band leads sets the hue, like the players' RGB
            s = (lo * lo + mi * mi + hi * hi) or 1
            c = QColor.fromRgbF(min(1, 1.6 * lo * lo / s), min(1, 1.3 * mi * mi / s), min(1, 1.8 * hi * hi / s))
        h = half * top
        p.setPen(c)
        p.drawLine(int(rect.left()) + x, int(mid - h), int(rect.left()) + x, int(mid + h))


def cue_color(c: Cue) -> str:
    if c.color:
        return c.color if c.color.startswith("#") else "#" + c.color[-6:]
    if 0 <= c.hotcue < 8:
        return theme.CUE_COLORS[c.hotcue]
    return theme.LOOP_COLOR if c.is_loop else theme.MEMORY_COLOR


def paint_cues(p: QPainter, rect: QRectF, t: Track, dur_ms: float):
    if dur_ms <= 0:
        return
    for c in t.cues:
        x = rect.left() + rect.width() * c.start / dur_ms
        col = QColor(cue_color(c))
        if c.is_loop:
            w = rect.width() * c.length / dur_ms
            p.fillRect(QRectF(x, rect.top(), max(2, w), rect.height()), QColor(col.red(), col.green(), col.blue(), 50))
        p.setPen(QPen(col, 1))
        p.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
        if c.hotcue >= 0:
            p.fillRect(QRectF(x, rect.top(), 11, 11), col)
            p.setPen(Qt.black)
            p.drawText(QRectF(x, rect.top() - 1, 11, 12), Qt.AlignCenter, "ABCDEFGH"[c.hotcue % 8])
        else:
            # memory cue: small triangle on the bottom edge, like the players
            b = rect.bottom()
            p.setBrush(col)
            p.drawPolygon(QPolygonF([QPointF(x - 4, b), QPointF(x + 4, b), QPointF(x, b - 7)]))
            p.setBrush(Qt.NoBrush)


# ============================================================
# Audio
# ============================================================

class Engine:
    """Deck A plays, deck B only exists during a crossfade."""

    def __init__(self):
        self.decks = []
        for _ in range(2):
            pl, out = QMediaPlayer(), QAudioOutput()
            pl.setAudioOutput(out)
            self.decks.append((pl, out))
        self.volume = 0.7
        self.path = ""
        self.next_path = ""

    @property
    def a(self) -> QMediaPlayer:
        return self.decks[0][0]

    def set_volume(self, v: float):
        self.volume = max(0.0, min(1.0, v))
        self.decks[0][1].setVolume(self.volume)

    def play(self, path: str) -> bool:
        if not os.path.isfile(path):
            return False
        self.stop()
        self.a.setSource(QUrl.fromLocalFile(path))
        self.decks[0][1].setVolume(self.volume)
        self.a.play()
        self.path = path
        return True

    def toggle(self):
        if self.playing:
            self.a.pause()
        else:
            self.a.play()

    def stop(self):
        for pl, _ in self.decks:
            pl.stop()
        self.decks[1][1].setVolume(0)
        self.path = self.next_path = ""

    def seek(self, ms: float):
        self.a.setPosition(max(0, int(ms)))

    @property
    def playing(self) -> bool:
        return self.a.playbackState() == QMediaPlayer.PlayingState

    def fade_to(self, path: str):
        b, out = self.decks[1]
        out.setVolume(0)
        b.setSource(QUrl.fromLocalFile(path))
        b.play()
        self.next_path = path

    def fade(self, k: float) -> bool:
        """k 0..1, returns True once B took over."""
        self.decks[0][1].setVolume(self.volume * (1 - k))
        self.decks[1][1].setVolume(self.volume * k)
        if k < 1:
            return False
        self.a.stop()
        self.decks.reverse()
        self.path, self.next_path = self.next_path, ""
        return True

    def close(self):
        for pl, _ in self.decks:
            pl.stop()
            pl.setSource(QUrl())


# ============================================================
# Widgets
# ============================================================

class WaveView(QWidget):
    seek = Signal(float)
    dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(56)
        self.setAcceptDrops(True)
        self.track: Track | None = None
        self.wave: Wave | None = None
        self.dur = 0.0
        self.pos = 0.0
        self.mode = "RGB"

    def show_track(self, t: Track | None, wave: Wave | None):
        self.track, self.wave = t, wave
        self.dur = (t.duration * 1000) if t else 0
        self.pos = 0
        self.update()

    def set_pos(self, ms: float):
        self.pos = ms
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.fillRect(r, QColor("#14141e"))
        paint_wave(p, r.adjusted(0, 12, 0, 0), self.wave, self.mode)
        if self.track:
            paint_cues(p, r, self.track, self.dur)
        if self.dur > 0:
            x = r.left() + r.width() * self.pos / self.dur
            p.setPen(QPen(Qt.white, 2))
            p.drawLine(int(x), int(r.top()), int(x), int(r.bottom()))

    def mousePressEvent(self, e):
        if self.dur > 0:
            self.seek.emit(self.dur * e.position().x() / max(1, self.width()))

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

    def __init__(self, engine: Engine, loader: Loader, cfg: dict, parent=None):
        super().__init__(parent)
        self.engine, self.loader, self.cfg = engine, loader, cfg
        self.track: Track | None = None
        self.path = ""
        self.tracks: list[Track] = []
        self.resolve = lambda t: t.path
        self.loop: Cue | None = None
        self.fading = 0.0

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
        info.addWidget(self.title)
        info.addWidget(self.meta)
        info.addWidget(self.view, 1)
        top.addWidget(self.art)
        top.addLayout(info, 1)

        bar = QHBoxLayout()
        self.btn = QToolButton()
        self.btn.setText("▶")
        self.btn.setFixedWidth(34)
        self.btn.clicked.connect(self.toggle)
        self.time = QLabel(clock(0))
        self.time.setStyleSheet("font-family: Consolas, monospace;")
        bar.addWidget(self.btn)
        bar.addWidget(self.time)
        self.pads = []
        for i in range(8):
            b = QPushButton("ABCDEFGH"[i])
            b.setFixedSize(26, 20)
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.clicked.connect(lambda _=False, s=i: self.pad(s))
            b.customContextMenuRequested.connect(lambda _=None, s=i: self.set_loop(s))
            self.pads.append(b)
            bar.addWidget(b)
        bar.addStretch(1)
        self.mode = QComboBox()
        self.mode.addItems(["Single", "Continue"])
        self.fade_box = QSpinBox()
        self.fade_box.setRange(0, 10)
        self.fade_box.setSuffix(" s")
        self.fade_box.setValue(int(cfg.get("crossfade", 3)))
        self.fade_box.valueChanged.connect(lambda v: cfg.__setitem__("crossfade", v))
        bar.addWidget(self.mode)
        bar.addWidget(QLabel("Fade"))
        bar.addWidget(self.fade_box)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 4)
        lay.addLayout(top, 1)
        lay.addLayout(bar)

        self.view.seek.connect(self.engine.seek)
        self.view.dropped.connect(self.dropped)
        loader.ready.connect(self.wave_ready)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(40)
        self.refresh_pads()

    # ---- loading

    def load(self, t: Track, path: str):
        self.track, self.path, self.loop = t, path, None
        self.title.setText(f"{t.artist}  -  {t.title}" if t.artist else t.title)
        k = keys.name(t.key, self.cfg.get("key_format", "Open Key"))
        self.meta.setText("  |  ".join(s for s in (f"BPM {t.bpm:.2f}" if t.bpm else "", k,
                                                   f"{t.gain:+.1f} dB" if t.gain else "",
                                                   clock(t.duration * 1000)) if s))
        self.view.mode = self.cfg.get("waveform_color", "RGB")
        self.view.show_track(t, self.loader.get(path) if path else None)
        self.set_art(path)
        self.refresh_pads()

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

    # ---- transport

    def play(self):
        if not self.track:
            return
        if self.engine.path == self.path:
            if not self.engine.playing:
                self.engine.toggle()
        else:
            self.engine.play(self.path)

    def toggle(self):
        if self.engine.path == self.path and self.engine.playing:
            self.engine.toggle()
        else:
            self.play()

    def stop(self):
        self.engine.stop()
        self.loop = None

    def tick(self):
        on = self.engine.playing and self.engine.path == self.path
        self.btn.setText("⏸" if on else "▶")
        if self.engine.path != self.path:
            return
        pos = self.engine.a.position()
        self.time.setText(f"{clock(pos)} / {clock(self.view.dur)}")
        self.view.set_pos(pos)
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
            self.engine.play(p)
            self.changed.emit()
            return
        self.engine.fade_to(p)
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

    def pad(self, slot: int):
        if not self.track:
            return
        c = next((c for c in self.track.cues if c.hotcue == slot), None)
        if c is not None and QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.track.cues.remove(c)
            if self.loop is c:
                self.loop = None
        elif c is None:
            pos = self.engine.a.position() if self.engine.path == self.path else 0
            self.track.cues.append(Cue(kind=CUE, start=float(pos), hotcue=slot))
        elif c.is_loop:
            self.loop = None if self.loop is c else c
            if self.loop:
                self.engine.seek(c.start)
            return
        else:
            self.play()
            self.engine.seek(c.start)
            return
        self.refresh_pads()
        self.changed.emit()

    def set_loop(self, slot: int):
        if not self.track:
            return
        pos = self.engine.a.position() if self.engine.path == self.path else 0
        beat = 60000 / self.track.bpm if self.track.bpm else 500
        self.track.cues = [c for c in self.track.cues if c.hotcue != slot]
        self.track.cues.append(Cue(kind=LOOP, start=float(pos), length=4 * beat, hotcue=slot))
        self.refresh_pads()
        self.changed.emit()

    def refresh_pads(self):
        used = {c.hotcue: c for c in self.track.cues} if self.track else {}
        for i, b in enumerate(self.pads):
            c = used.get(i)
            if c is None:
                b.setStyleSheet(f"background: {theme.BG_MED}; color: {theme.FG_MUTED}; padding: 0;")
                b.setToolTip("click: set cue here, right click: 4 beat loop")
            else:
                col = cue_color(c)
                b.setStyleSheet(f"background: {col}; color: black; font-weight: bold; padding: 0;"
                                + (" border: 2px solid white;" if c.is_loop else ""))
                b.setToolTip(f"{c.name or 'Cue'} at {clock(c.start)}"
                             + (" (loop)" if c.is_loop else "") + ", ctrl+click to delete")
        self.view.update()

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
