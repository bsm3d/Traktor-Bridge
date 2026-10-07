# Benoit Saint-Moulin
# Traktor Bridge : zoomable waveform (Ctrl+wheel), minute marks, cues and a scrub bar

"""Shared player/Cue Editor waveform, with detail loaded on demand.
Wave clicks move the needle without starting playback. The overview scrubs the
whole track and repositions the zoom window."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..model import Cue, Track
from . import cuehistory, theme

MINUTE = 60000.0
MIN_SPAN = 500.0            # ms, the closest zoom (1 ms detail per column)
STEP = 1.25                 # one wheel notch
STRIP = 14                  # scrub bar height, px
GRID_HEAD = 12              # dedicated handle row, separate from cue letters
HEAD = GRID_HEAD + 12
OUT_X, OUT_Y = 60, 30       # px past the wave where releasing a dragged cue cancels the move


TEXT_INPUTS = (QLineEdit, QAbstractSpinBox, QComboBox, QTextEdit)


def hot_key(e, window: QWidget) -> tuple[int, bool] | None:
    """For an event filter on the application: (slot 0-7, delete) when e is the key A-H
    (Shift = delete) pressed in this window and not typed into a text field."""
    if e.type() != QEvent.KeyPress or e.isAutoRepeat() or not window.isActiveWindow():
        return None
    slot = e.key() - Qt.Key_A
    mods = e.modifiers() & ~Qt.KeypadModifier
    if 0 <= slot < 8 and mods in (Qt.NoModifier, Qt.ShiftModifier) \
            and not isinstance(QApplication.focusWidget(), TEXT_INPUTS):
        return slot, mods == Qt.ShiftModifier
    return None


def duration_text(seconds: float) -> str:
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def clock(ms: float) -> str:
    if ms < 0:
        return "--:--.-"
    s = ms / 1000
    return f"{int(s // 60):02d}:{s % 60:04.1f}"


def quantize_to_beat(t: Track | None, ms: float) -> float:
    if t is None or t.grid is None or t.bpm <= 0:
        return max(0.0, ms)
    beat = MINUTE / t.bpm
    return max(0.0, t.grid + round((ms - t.grid) / beat) * beat)


_pix: dict = {}


def paint_wave(p: QPainter, rect: QRectF, wave, mode: str, a: float = 0.0, b: float = 1.0):
    """Cache the visible waveform; needle updates reuse the pixmap."""
    if wave is None or len(wave) == 0:
        draw_wave(p, rect, wave, mode)
        return
    k = (id(wave), int(rect.width()), int(rect.height()), mode, round(a, 6), round(b, 6))
    hit = _pix.get(k)
    # the wave is kept next to its pixmap, a freed wave could hand its id to another
    pm = hit[1] if hit is not None and hit[0] is wave else None
    if pm is None:
        if len(_pix) > 16:
            _pix.clear()
        pm = QPixmap(k[1], k[2])
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        draw_wave(q, QRectF(0, 0, k[1], k[2]), wave, mode, a, b)
        q.end()
        _pix[k] = (wave, pm)
    p.drawPixmap(int(rect.left()), int(rect.top()), pm)


def draw_wave(p: QPainter, rect: QRectF, wave, mode: str, a: float = 0.0, b: float = 1.0):
    """a..b is the visible part of the wave, 0..1."""
    mid = rect.center().y()
    half = rect.height() / 2 - 1
    w = int(rect.width())
    if wave is None or len(wave) == 0 or w <= 0:
        p.setPen(QColor(theme.BG_LIGHT))
        p.drawLine(int(rect.left()), int(mid), int(rect.right()), int(mid))
        return
    arr = np.asarray(wave, dtype=np.float32)
    n = len(arr)
    seg = arr[:max(1, min(n, int(np.ceil(b * n))))]
    starts = np.minimum(np.floor(np.linspace(a * n, b * n, w + 1)[:-1]).astype(np.intp), len(seg) - 1)
    m = np.maximum.reduceat(seg, starts, axis=0)
    lo, mi, hi = m[:, 0], m[:, 1], m[:, 2]
    if mode == "Blue":
        r, g, bl = 0.2 + 0.6 * hi, 0.4 + 0.5 * hi, np.ones(w)
    elif mode == "IR":
        r, g, bl = np.ones(w), 0.3 + 0.6 * hi, 0.1 + 0.4 * hi
    else:
        # squared shares: whichever band leads sets the hue, like the players' RGB
        s = lo * lo + mi * mi + hi * hi
        s[s == 0] = 1
        r, g, bl = 1.6 * lo * lo / s, 1.3 * mi * mi / s, 1.8 * hi * hi / s
    cols = np.clip(np.stack([r, g, bl], axis=1), 0, 1).tolist()
    h = (half * m.max(axis=1)).tolist()
    left = int(rect.left())
    for x in range(w):
        p.setPen(QColor.fromRgbF(*cols[x]))
        p.drawLine(left + x, int(mid - h[x]), left + x, int(mid + h[x]))


def cue_color(c: Cue) -> str:
    if c.color:
        return c.color if c.color.startswith("#") else "#" + c.color[-6:]
    if 0 <= c.hotcue < 8:
        return theme.CUE_COLORS[c.hotcue]
    return theme.LOOP_COLOR if c.is_loop else theme.MEMORY_COLOR


def beat_grid_marks(t: Track, start: float, span: float, width: float) -> list[tuple[float, bool]]:
    """Visible beat times and bar starts, thinning the grid when beats are too close."""
    if t.grid is None or t.bpm <= 0 or span <= 0 or width <= 0:
        return []
    beat = MINUTE / t.bpm
    beat_px = width * beat / span
    stride = 1 if beat_px >= 8 else 4 * max(1, int(np.ceil(8 / (4 * beat_px))))
    first = max(0, int(np.ceil((start - t.grid) / beat)))
    last = int(np.floor((start + span - t.grid) / beat))
    first = ((first + stride - 1) // stride) * stride
    return [(t.grid + n * beat, n % 4 == 0) for n in range(first, last + 1, stride)]


def paint_cues(p: QPainter, rect: QRectF, t: Track, dur_ms: float, start: float = 0.0, span: float = 0.0):
    """span is the visible length in ms (0 = the whole track), from start."""
    if dur_ms <= 0:
        return
    span = span or dur_ms
    for c in t.cues:
        if c.start > start + span or c.start + c.length < start:
            continue
        x = rect.left() + rect.width() * (c.start - start) / span
        col = QColor(cue_color(c))
        if c.is_loop:
            w = rect.width() * c.length / span
            p.fillRect(QRectF(x, rect.top(), max(2, w), rect.height()), QColor(col.red(), col.green(), col.blue(), 50))
        p.setPen(QPen(col, 1))
        p.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
        if c.hotcue >= 0:
            p.fillRect(QRectF(x, rect.top(), 11, 11), col)
            p.setPen(Qt.black)
            p.drawText(QRectF(x, rect.top() - 1, 11, 12), Qt.AlignCenter, "ABCDEFGH"[c.hotcue % 8])
        else:
            # memory cue: small triangle on the bottom edge, like the players
            bt = rect.bottom()
            p.setBrush(col)
            p.drawPolygon(QPolygonF([QPointF(x - 4, bt), QPointF(x + 4, bt), QPointF(x, bt - 7)]))
            p.setBrush(Qt.NoBrush)


class ZoomWave(QWidget):
    viewport_changed = Signal()
    seek = Signal(float)        # click or drag on the wave or the bar, ms
    activated = Signal(float)   # double click on the wave, ms
    need_hi = Signal()          # first zoom on this track: the detailed wave is wanted
    cue_moved = Signal(object)  # a cue was dragged to a new place (its start is already changed)
    grid_moved = Signal(object)  # the track's first beat marker was repositioned

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(56 + STRIP)
        self.setMouseTracking(True)
        self.track: Track | None = None
        self.wave = None
        self.hi = None
        self.dur = 0.0
        self.needle = -1.0
        self.mode = "RGB"
        self.snap_to_beat = False
        self.start = 0.0
        self.span = 0.0
        self.following = True       # the window follows the needle while it is on screen
        self.drag = ""
        self.hold = 0.0
        self.asked = False
        self.grab: Cue | None = None
        self.origin = 0.0                   # where the grabbed cue was
        self.before: tuple = ()             # the cues before the drag, for undo
        self.outside = False                # the mouse left the wave: releasing there cancels
        self.moved = False
        self.grid_origin: float | None = None

    # ---- state

    def show_track(self, t: Track | None, wave):
        same = t is self.track and t is not None
        if not same and self.drag == "grid":
            self.end_grid_drag(True)
        elif not same and self.drag == "cue":
            self.end_drag(True)
        self.track, self.wave = t, wave
        self.dur = (t.duration * 1000) if t else 0.0
        if not same:
            self.needle = 0.0
            self.start, self.span, self.hi, self.asked = 0.0, self.dur, None, False
            self.following = True
        self.update()
        self.viewport_changed.emit()

    def set_hi(self, arr):
        self.hi = arr
        self.update()

    @property
    def zoomed(self) -> bool:
        return self.dur > 0 and 0 < self.span < self.dur - 1

    def clamp(self):
        lo = min(self.dur, MIN_SPAN)
        self.span = max(lo, min(self.span or self.dur, self.dur))
        self.start = max(0.0, min(self.start, self.dur - self.span))

    def set_pos(self, ms: float):
        self.needle = ms
        if self.zoomed and not self.drag:
            inside = self.start <= ms <= self.start + self.span
            if self.following and not inside:
                self.start = ms - self.span * 0.1
                self.clamp()
                inside = True
            self.following = inside
        self.update()

    def zoom(self, factor: float, x: float):
        if self.dur <= 0:
            return
        main = self.areas()[0]
        anchor = self.ms_of(x, main)
        frac = (anchor - self.start) / (self.span or self.dur)
        self.span = (self.span or self.dur) / factor
        self.clamp()
        self.start = anchor - frac * self.span
        self.clamp()
        self.following = False
        if self.zoomed and not self.asked:
            self.asked = True
            self.need_hi.emit()
        self.update()
        self.viewport_changed.emit()

    # ---- geometry

    def areas(self) -> tuple[QRectF, QRectF]:
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        return (QRectF(r.left(), r.top(), r.width(), r.height() - STRIP - 2),
                QRectF(r.left(), r.bottom() - STRIP, r.width(), STRIP))

    def ms_of(self, x: float, rect: QRectF) -> float:
        return self.start + (self.span or self.dur) * (x - rect.left()) / max(1.0, rect.width())

    def x_of(self, ms: float, rect: QRectF) -> float:
        return rect.left() + rect.width() * (ms - self.start) / (self.span or self.dur)

    # ---- painting

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#14141e"))
        main, strip = self.areas()
        wr = main.adjusted(0, HEAD, 0, 0)
        if self.dur <= 0:
            paint_wave(p, wr, self.wave, self.mode)
            return
        span = self.span or self.dur
        src = self.hi if self.zoomed and self.hi is not None else self.wave
        paint_wave(p, wr, src, self.mode, self.start / self.dur, (self.start + span) / self.dur)
        p.save()
        p.setClipRect(main)
        t = self.track
        if t is not None:
            for beat_ms, downbeat in beat_grid_marks(t, self.start, span, main.width()):
                x = int(self.x_of(beat_ms, main))
                if beat_ms == t.grid:
                    pen = QPen(QColor("#00e5ff"), 2, Qt.DashLine)
                    y_end = int(main.bottom())
                elif downbeat:
                    pen = QPen(QColor(0, 229, 255, 75), 1)
                    y_end = int(main.bottom())
                else:
                    pen = QPen(QColor(0, 229, 255, 125), 1)
                    y_end = min(int(main.bottom()), int(main.top()) + HEAD - 3)
                p.setPen(pen)
                p.drawLine(x, int(main.top()), x, y_end)
            if t.grid is not None and self.start <= t.grid <= self.start + span:
                x = self.x_of(t.grid, main)
                p.setPen(QPen(QColor(theme.ACCENT), 2, Qt.DashLine))
                p.drawLine(int(x), int(main.top()), int(x), int(main.bottom()))
                p.setBrush(QColor(theme.ACCENT))
                p.drawPolygon(QPolygonF([QPointF(x - 5, main.top() + 1),
                                         QPointF(x + 5, main.top() + 1),
                                         QPointF(x, main.top() + GRID_HEAD - 2)]))
                p.setBrush(Qt.NoBrush)
        self.paint_minutes(p, main, span)
        if t is not None:
            paint_cues(p, main.adjusted(0, GRID_HEAD, 0, 0), t, self.dur, self.start, span)
        if self.needle >= 0 and self.start <= self.needle <= self.start + span:
            x = int(self.x_of(self.needle, main))
            p.setPen(QPen(Qt.white, 2))
            p.drawLine(x, int(main.top() + HEAD), x, int(main.bottom()))
        p.restore()
        self.paint_strip(p, strip)

    def paint_minutes(self, p: QPainter, main: QRectF, span: float):
        f = QFont(p.font())
        f.setPointSize(7)
        p.setFont(f)
        pen = QPen(QColor(255, 255, 255, 204), 1)
        m = max(1, int(self.start // MINUTE))
        while m * MINUTE <= self.start + span and m * MINUTE < self.dur:
            if m * MINUTE >= self.start:
                x = int(self.x_of(m * MINUTE, main))
                p.setPen(pen)
                p.drawLine(x, int(main.top()), x, int(main.bottom()))
                p.drawText(x + 3, int(main.bottom()) - 3, f"{m}:00")
            m += 1

    def paint_strip(self, p: QPainter, strip: QRectF):
        p.fillRect(strip, QColor(theme.BG_MED))
        paint_wave(p, strip.adjusted(0, 1, 0, -1), self.wave, self.mode)
        if self.zoomed:
            x0 = strip.left() + strip.width() * self.start / self.dur
            w = max(4.0, strip.width() * self.span / self.dur)
            p.fillRect(QRectF(x0, strip.top(), w, strip.height()), QColor(255, 255, 255, 60))
            p.setPen(QPen(QColor(theme.ACCENT), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(x0, strip.top(), w, strip.height() - 1))
    # ---- mouse

    def window_x(self, strip: QRectF) -> tuple[float, float]:
        return (strip.left() + strip.width() * self.start / self.dur,
                max(4.0, strip.width() * self.span / self.dur))

    def goto(self, ms: float):
        self.needle = max(0.0, min(ms, self.dur))
        self.seek.emit(self.needle)
        self.update()

    def to_strip(self, x: float, strip: QRectF):
        """Scrub: the position follows the mouse and the zoomed window is centred on it."""
        ms = self.dur * (x - strip.left()) / max(1.0, strip.width())
        self.start = ms - (self.span or self.dur) / 2
        self.clamp()
        self.following = True
        self.goto(ms)

    def cue_at(self, x: float, y: float) -> Cue | None:
        """The cue whose letter (hot cue) or triangle (memory cue) is under the mouse."""
        main = self.areas()[0]
        if self.track is None or self.dur <= 0 or not main.contains(x, y):
            return None
        for c in reversed(self.track.cues):
            cx = self.x_of(c.start, main)
            if c.hotcue >= 0:
                hit = QRectF(cx - 2, main.top() + GRID_HEAD, 15, 12).contains(x, y)
            else:
                hit = abs(x - cx) <= 6 and y >= main.bottom() - 10
            if hit:
                return c
        return None

    def grid_at(self, x: float, y: float) -> bool:
        main = self.areas()[0]
        if self.dur <= 0 or self.track is None or self.track.grid is None or not main.contains(x, y):
            return False
        return y < main.top() + GRID_HEAD and abs(x - self.x_of(self.track.grid, main)) <= 6

    def drag_grid(self, x: float):
        if self.track is None:
            return
        main = self.areas()[0]
        ms = max(0.0, min(self.ms_of(x, main) - self.hold, self.dur))
        if ms != self.track.grid:
            self.track.grid = ms
            self.moved = True
            self.update()

    def drag_cue(self, x: float, snap: bool):
        c, main = self.grab, self.areas()[0]
        ms = self.ms_of(x, main) - self.hold
        t = self.track
        if snap or self.snap_to_beat:
            ms = quantize_to_beat(t, ms)
        ms = max(0.0, min(ms, self.dur - (c.length if c.is_loop else 0.0)))
        if ms != c.start:
            c.start = ms
            self.moved = True
            self.update()

    def mousePressEvent(self, e):
        if self.dur <= 0 or e.button() != Qt.LeftButton:
            return
        main, strip = self.areas()
        x, y = e.position().x(), e.position().y()
        if self.grid_at(x, y):
            self.drag, self.moved, self.outside = "grid", False, False
            self.grid_origin = self.track.grid
            self.hold = self.ms_of(x, main) - self.track.grid
            self.before = cuehistory.snap(self.track)
            self.grabKeyboard()
            self.setCursor(Qt.ClosedHandCursor)
            return
        c = self.cue_at(x, y)
        if c is not None:
            self.drag, self.grab, self.moved, self.outside = "cue", c, False, False
            self.hold = self.ms_of(x, main) - c.start
            self.origin, self.before = c.start, cuehistory.snap(self.track)
            self.setCursor(Qt.ClosedHandCursor)
            self.grabKeyboard()             # Esc cancels, whatever has the focus
            return
        if y < strip.top():
            self.drag = "wave"
            self.goto(self.ms_of(x, main))
            return
        x0, w = self.window_x(strip)
        if self.zoomed and x0 <= x <= x0 + w:
            self.drag, self.hold = "window", x - x0
            self.following = False
        else:
            self.drag = "strip"
            self.to_strip(x, strip)

    def mouseMoveEvent(self, e):
        main, strip = self.areas()
        x = e.position().x()
        if not self.drag:
            over_cue = self.cue_at(x, e.position().y()) is not None
            over_grid = self.grid_at(x, e.position().y())
            self.setCursor(Qt.OpenHandCursor if over_cue or over_grid else Qt.ArrowCursor)
            return
        if self.drag == "cue":
            gone = not self.rect().adjusted(-OUT_X, -OUT_Y, OUT_X, OUT_Y).contains(e.position().toPoint())
            if gone != self.outside:
                self.outside = gone
                self.setCursor(Qt.ForbiddenCursor if gone else Qt.ClosedHandCursor)
            if gone:
                # shows what releasing here does: the cue goes back where it was
                if self.grab.start != self.origin:
                    self.grab.start = self.origin
                    self.update()
            else:
                self.drag_cue(x, bool(e.modifiers() & Qt.ShiftModifier))
        elif self.drag == "grid":
            gone = not self.rect().adjusted(-OUT_X, -OUT_Y, OUT_X, OUT_Y).contains(e.position().toPoint())
            if gone != self.outside:
                self.outside = gone
                self.setCursor(Qt.ForbiddenCursor if gone else Qt.ClosedHandCursor)
            if gone:
                if self.track is not None and self.grid_origin is not None:
                    self.track.grid = self.grid_origin
                    self.update()
            else:
                self.drag_grid(x)
        elif self.drag == "wave":
            self.goto(self.ms_of(x, main))
        elif self.drag == "strip":
            self.to_strip(x, strip)
        else:
            self.start = self.dur * (x - self.hold - strip.left()) / max(1.0, strip.width())
            self.clamp()
            self.update()

    def mouseReleaseEvent(self, e):
        if self.drag == "cue":
            if self.outside:
                self.end_drag(True)
            else:
                self.end_drag(False)
                self.setCursor(Qt.OpenHandCursor if self.cue_at(e.position().x(), e.position().y()) else Qt.ArrowCursor)
            return
        if self.drag == "grid":
            outside = not self.rect().adjusted(-OUT_X, -OUT_Y, OUT_X, OUT_Y).contains(e.position().toPoint())
            self.end_grid_drag(self.outside or outside)
            return
        self.drag = ""

    def end_drag(self, cancel: bool):
        """Drops the cue where it is, or puts it back where the drag found it."""
        c, moved = self.grab, self.moved
        before = self.before
        self.grab, self.moved, self.outside, self.before = None, False, False, ()
        self.drag = ""
        self.releaseKeyboard()
        self.setCursor(Qt.ArrowCursor)
        if c is None:
            return
        if cancel:
            c.start = self.origin
            self.update()
        elif moved:
            cuehistory.record(self.track, before)
            self.cue_moved.emit(c)

    def end_grid_drag(self, cancel: bool):
        before, origin = self.before, self.grid_origin
        moved = self.moved
        self.before, self.grid_origin = (), None
        self.moved, self.outside, self.drag = False, False, ""
        self.releaseKeyboard()
        self.setCursor(Qt.ArrowCursor)
        if self.track is None or origin is None:
            return
        if cancel:
            self.track.grid = origin
            self.update()
        elif moved and self.track.grid != origin:
            cuehistory.record(self.track, before)
            self.grid_moved.emit(self.track)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self.drag == "cue":
            self.end_drag(True)
            e.accept()
            return
        if e.key() == Qt.Key_Escape and self.drag == "grid":
            self.end_grid_drag(True)
            e.accept()
            return
        super().keyPressEvent(e)

    def hideEvent(self, e):
        if self.drag == "cue":
            self.end_drag(True)
        elif self.drag == "grid":
            self.end_grid_drag(True)
        super().hideEvent(e)

    def mouseDoubleClickEvent(self, e):
        main = self.areas()[0]
        if self.grid_at(e.position().x(), e.position().y()):
            return
        if self.cue_at(e.position().x(), e.position().y()) is not None:
            return
        if self.dur > 0 and e.position().y() < main.bottom():
            self.activated.emit(max(0.0, min(self.ms_of(e.position().x(), main), self.dur)))

    def wheelEvent(self, e):
        d = e.angleDelta()
        dy = d.y() or d.x()
        if self.dur <= 0 or dy == 0:
            e.ignore()
        elif e.modifiers() & Qt.ControlModifier:
            self.zoom(STEP if dy > 0 else 1 / STEP, e.position().x())
            e.accept()
        elif self.zoomed:
            self.start -= self.span * 0.1 * (1 if dy > 0 else -1)
            self.clamp()
            self.following = False
            self.update()
            e.accept()
        else:
            e.ignore()


class ZoomControls(QWidget):
    def __init__(self, wave: ZoomWave, parent=None, vertical: bool = False):
        super().__init__(parent)
        self.wave = wave
        bar = QVBoxLayout(self) if vertical else QHBoxLayout(self)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(2 if vertical else 6)
        self.out_button = QPushButton("−")
        self.in_button = QPushButton("+")
        self.reset_button = QPushButton("↺" if vertical else "Full track")
        self.out_button.setAccessibleName("Zoom out")
        self.in_button.setAccessibleName("Zoom in")
        self.reset_button.setAccessibleName("Show full track")
        if vertical:
            self.setFixedWidth(36)
            for button in (self.in_button, self.reset_button, self.out_button):
                button.setFixedSize(36, 30)
                button.setStyleSheet(
                    "QPushButton { padding: 0; font-family: 'Segoe UI Symbol'; "
                    "font-size: 17pt; font-weight: bold; }"
                )
            bar.addWidget(self.in_button, 0, Qt.AlignHCenter)
            bar.addStretch(1)
            bar.addWidget(self.reset_button, 0, Qt.AlignHCenter)
            bar.addStretch(1)
            bar.addWidget(self.out_button, 0, Qt.AlignHCenter)
        else:
            bar.addWidget(QLabel("Zoom"))
        for button, tip in ((self.out_button, "Zoom out around the cursor"),
                            (self.in_button, "Zoom in around the cursor, down to 500 ms"),
                            (self.reset_button, "Show the whole track")):
            button.setToolTip(tip)
            if not vertical:
                bar.addWidget(button)
        self.out_button.clicked.connect(lambda: self.adjust(0.5))
        self.in_button.clicked.connect(lambda: self.adjust(2))
        self.reset_button.clicked.connect(self.reset)
        self.range_label = QLabel()
        if vertical:
            self.range_label.setVisible(False)
        else:
            bar.addWidget(self.range_label)
            bar.addStretch(1)
        wave.viewport_changed.connect(self.refresh)
        self.refresh()

    def adjust(self, factor: float):
        wave = self.wave
        if wave.dur <= 0:
            return
        main = wave.areas()[0]
        ms = wave.needle if wave.start <= wave.needle <= wave.start + wave.span else wave.start + wave.span / 2
        wave.zoom(factor, wave.x_of(ms, main))

    def reset(self):
        wave = self.wave
        wave.start, wave.span, wave.following = 0.0, wave.dur, True
        wave.update()
        wave.viewport_changed.emit()

    def refresh(self):
        wave = self.wave
        self.in_button.setEnabled(wave.dur > 0 and wave.span > MIN_SPAN)
        self.out_button.setEnabled(wave.zoomed)
        self.reset_button.setEnabled(wave.zoomed)
        self.range_label.setText(f"{wave.span / 1000:.3f} s visible" if wave.dur else "No track")
