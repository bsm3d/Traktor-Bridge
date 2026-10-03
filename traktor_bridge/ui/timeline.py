# Benoit Saint-Moulin
# Traktor Bridge : cue timeline of one track, cues can be edited, moved, deleted

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import keys
from ..model import CUE, FADE_IN, FADE_OUT, LOAD, LOOP, Cue, Track
from . import theme
from .player import clock, cue_color, paint_cues, paint_wave
from .waveform import Loader

KIND_NAMES = {CUE: "Cue", FADE_IN: "Fade in", FADE_OUT: "Fade out", LOAD: "Load", LOOP: "Loop"}


def label(c: Cue) -> str:
    base = KIND_NAMES.get(c.kind, "Cue")
    return f"Hot {'ABCDEFGH'[c.hotcue]} ({base.lower()})" if 0 <= c.hotcue < 8 else f"Memory {base.lower()}"


def parse_clock(s: str) -> float | None:
    """'mm:ss.mmm' or plain seconds, in ms."""
    s = s.strip()
    try:
        if ":" in s:
            m, sec = s.split(":", 1)
            return (int(m) * 60 + float(sec)) * 1000
        return float(s) * 1000
    except ValueError:
        return None


class Canvas(QWidget):
    seek = Signal(float)

    def __init__(self, t: Track, parent=None):
        super().__init__(parent)
        self.t = t
        self.wave = None
        self.mode = "RGB"
        self.pos = -1.0
        self.setMinimumHeight(120)

    def paintEvent(self, e):
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(0, 0, -1, -16)
        p.fillRect(self.rect(), QColor(theme.BG_DARK))
        paint_wave(p, r.adjusted(0, 14, 0, -4), self.wave, self.mode)
        dur = self.t.duration * 1000
        if dur <= 0:
            return
        if self.t.grid is not None:
            x = r.width() * self.t.grid / dur
            p.setPen(QPen(QColor("#00e5ff"), 1, Qt.DashLine))
            p.drawLine(int(x), int(r.top()), int(x), int(r.bottom()))
        paint_cues(p, r, self.t, dur)
        p.setPen(QColor(theme.FG_MUTED))
        for i in range(6):
            x = r.width() * i / 5
            p.drawText(QRectF(min(x, r.width() - 60), r.bottom() + 2, 60, 14),
                       Qt.AlignLeft, clock(dur * i / 5))
        if self.pos >= 0:
            x = r.width() * self.pos / dur
            p.setPen(QPen(Qt.white, 2))
            p.drawLine(int(x), int(r.top()), int(x), int(r.bottom()))

    def mousePressEvent(self, e):
        if self.t.duration:
            self.seek.emit(self.t.duration * 1000 * e.position().x() / max(1, self.width()))


class CueEdit(QDialog):
    def __init__(self, c: Cue, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit cue")
        f = QFormLayout(self)
        self.time = QLineEdit(clock(c.start).replace("--:--.-", "00:00.0"))
        self.name = QLineEdit(c.name)
        self.slot = QComboBox()
        self.slot.addItems(["Memory"] + [f"Hot {x}" for x in "ABCDEFGH"])
        self.slot.setCurrentIndex(c.hotcue + 1 if 0 <= c.hotcue < 8 else 0)
        self.length = QLineEdit(f"{c.length / 1000:.3f}" if c.is_loop else "")
        self.length.setPlaceholderText("seconds, empty = no loop")
        f.addRow("Time (mm:ss.s)", self.time)
        f.addRow("Name", self.name)
        f.addRow("Slot", self.slot)
        f.addRow("Loop length", self.length)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def apply(self, c: Cue, dur_ms: float):
        ms = parse_clock(self.time.text())
        if ms is not None:
            c.start = max(0.0, min(ms, dur_ms or ms))
        c.name = self.name.text()
        c.hotcue = self.slot.currentIndex() - 1
        ln = parse_clock(self.length.text()) if self.length.text().strip() else 0.0
        c.length = max(0.0, ln or 0.0)
        if c.length > 0:
            c.kind = LOOP
        elif c.kind == LOOP:
            c.kind = CUE


class Timeline(QDialog):
    changed = Signal()

    def __init__(self, t: Track, path: str, loader: Loader, cfg: dict, engine=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.t, self.path, self.loader, self.engine = t, path, loader, engine
        self.setWindowTitle(f"Cues: {t.artist} - {t.title}")
        self.resize(820, 540)

        head = QLabel(f"<b>{t.artist} - {t.title}</b><br><span style='color:{theme.FG_MUTED}'>"
                      f"BPM {t.bpm:.2f} | {clock(t.duration * 1000)} | "
                      f"{keys.name(t.key, cfg.get('key_format', 'Open Key'))} | grid "
                      f"{clock(t.grid) if t.grid is not None else 'none'}</span>")
        self.canvas = Canvas(t)
        self.canvas.mode = cfg.get("waveform_color", "RGB")
        self.canvas.wave = loader.get(path) if path else None
        loader.ready.connect(self.wave_ready)
        if engine is not None:
            self.canvas.seek.connect(self.seek)

        filt = QHBoxLayout()
        self.show_hot = QCheckBox("Hot cues")
        self.show_mem = QCheckBox("Memory cues")
        self.show_loop = QCheckBox("Loops")
        for b in (self.show_hot, self.show_mem, self.show_loop):
            b.setChecked(True)
            b.toggled.connect(self.fill)
            filt.addWidget(b)
        filt.addStretch(1)
        self.stats = QLabel("")
        filt.addWidget(self.stats)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Time", "Type", "Length", "Name"])
        self.table.setRootIsDecorated(False)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 90)
        self.table.itemDoubleClicked.connect(self.edit)

        btns = QHBoxLayout()
        for text, fn in (("Add at 0", self.add), ("Edit", self.edit), ("Delete", self.delete),
                         ("Copy list", self.copy)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        btns.addWidget(close)

        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(self.canvas, 1)
        lay.addLayout(filt)
        lay.addWidget(self.table, 1)
        lay.addLayout(btns)
        self.fill()

    def wave_ready(self, path, wave):
        if path == self.path:
            self.canvas.wave = wave
            self.canvas.update()

    def seek(self, ms: float):
        if self.engine.path != self.path:
            self.engine.play(self.path)
        self.engine.seek(ms)
        self.canvas.pos = ms
        self.canvas.update()

    def visible(self, c: Cue) -> bool:
        if c.is_loop:
            return self.show_loop.isChecked()
        return self.show_hot.isChecked() if c.hotcue >= 0 else self.show_mem.isChecked()

    def fill(self):
        self.table.clear()
        cues = sorted(self.t.cues, key=lambda c: c.start)
        for c in cues:
            if not self.visible(c):
                continue
            it = QTreeWidgetItem([clock(c.start), label(c), clock(c.length) if c.is_loop else "", c.name])
            it.setForeground(1, QColor(cue_color(c)))
            it.setData(0, Qt.UserRole, c)
            self.table.addTopLevelItem(it)
        hot = sum(c.hotcue >= 0 for c in cues)
        loops = sum(c.is_loop for c in cues)
        self.stats.setText(f"{len(cues)} cues, {hot} hot, {len(cues) - hot} memory, {loops} loop{'s' if loops != 1 else ''}")
        self.canvas.update()

    def selected(self) -> list[Cue]:
        return [it.data(0, Qt.UserRole) for it in self.table.selectedItems()]

    def touched(self):
        self.fill()
        self.changed.emit()

    def add(self):
        c = Cue(kind=CUE, start=max(0.0, self.canvas.pos))
        d = CueEdit(c, self)
        if d.exec():
            d.apply(c, self.t.duration * 1000)
            if c.hotcue >= 0:
                self.t.cues = [x for x in self.t.cues if x.hotcue != c.hotcue]
            self.t.cues.append(c)
            self.touched()

    def edit(self, *_):
        sel = self.selected()
        if not sel:
            return
        c = sel[0]
        d = CueEdit(c, self)
        if d.exec():
            d.apply(c, self.t.duration * 1000)
            if c.hotcue >= 0:
                self.t.cues = [x for x in self.t.cues if x is c or x.hotcue != c.hotcue]
            self.touched()

    def delete(self):
        sel = self.selected()
        if not sel:
            return
        if QMessageBox.question(self, "Delete", f"Delete {len(sel)} cue(s)?") != QMessageBox.Yes:
            return
        self.t.cues = [c for c in self.t.cues if c not in sel]
        self.touched()

    def copy(self):
        lines = [f"{self.t.artist} - {self.t.title}", f"BPM {self.t.bpm:.2f}", ""]
        for c in sorted(self.t.cues, key=lambda c: c.start):
            if self.visible(c):
                ln = f"  length {clock(c.length)}" if c.is_loop else ""
                lines.append(f"{clock(c.start)}  {label(c)}{ln}  {c.name}".rstrip())
        QApplication.clipboard().setText("\n".join(lines))

    def done(self, r):
        # Esc goes through here too, closeEvent would miss it
        self.loader.ready.disconnect(self.wave_ready)
        super().done(r)
