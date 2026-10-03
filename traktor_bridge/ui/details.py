# Benoit Saint-Moulin
# Traktor Bridge : playlist details (player, sortable list, reorder, properties)

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDrag, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import keys, tags
from ..export.m3u import write_list
from ..model import Node, Track
from ..sources import AUDIO_EXT
from ..sources.folder import tracks_from
from . import theme
from .player import Engine, Player, clock
from .timeline import Timeline
from .waveform import Loader

COLS = ["", "#", "Artist", "Title", "Key", "BPM", "Gain", "Grid", "Time", "Cues", "Album"]
WIDTHS = [28, 36, 190, 260, 60, 60, 55, 40, 60, 90, 200]
C_PLAY, C_NUM, C_CUES = 0, 1, 9

# Camelot wheel colours, the usual ones in DJ software
KEY_COLORS = ["#56f1da", "#7df2aa", "#aef589", "#e8daa1", "#fdbfa7", "#fdafb7",
              "#fdaacc", "#f2abe4", "#ddb4fd", "#bed0fd", "#8ee4f9", "#55f1f0"]


def key_color(k: int | None) -> str:
    if k is None:
        return theme.FG
    cam = keys.name(k, "Camelot")
    return KEY_COLORS[(int(cam[:-1]) - 1) % 12]


def cue_summary(t: Track) -> str:
    hot = sum(c.hotcue >= 0 for c in t.cues)
    mem = sum(c.hotcue < 0 for c in t.cues)
    loops = sum(c.is_loop for c in t.cues)
    s = " ".join(f"{k}{n}" for k, n in (("H", hot), ("M", mem), ("L", loops)) if n)
    return s or "-"


class Table(QTreeWidget):
    moved = Signal()
    files = Signal(list)                # files or folders dropped from outside

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path_of = lambda t: ""

    def startDrag(self, actions):
        it = self.currentItem()
        t = it.data(0, Qt.UserRole) if it else None
        p = self.path_of(t) if t else ""
        if not p:
            return super().startDrag(actions)
        md = self.model().mimeData(self.selectedIndexes())
        md.setUrls([QUrl.fromLocalFile(p)])
        d = QDrag(self)
        d.setMimeData(md)
        d.exec(Qt.MoveAction | Qt.CopyAction)

    def outside(self, e) -> bool:
        return e.source() is not self and e.mimeData().hasUrls()

    def dragEnterEvent(self, e):
        if self.outside(e):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self.outside(e):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if self.outside(e):
            e.acceptProposedAction()
            self.files.emit([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
            return
        if self.dropIndicatorPosition() == QAbstractItemView.OnItem:
            e.ignore()
            return
        super().dropEvent(e)
        self.moved.emit()


class Properties(QDialog):
    def __init__(self, t: Track, path: str, key_fmt: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"Properties: {t.artist} - {t.title}")
        self.resize(760, 420)
        rows = [("Title", t.title), ("Artist", t.artist), ("Album", t.album), ("Genre", t.genre),
                ("Label", t.label), ("Remixer", t.remixer), ("Comment", t.comment),
                ("BPM", f"{t.bpm:.3f}" if t.bpm else ""), ("Key", keys.name(t.key, key_fmt)),
                ("Open Key / Camelot", f"{keys.name(t.key, 'Open Key')} / {keys.name(t.key, 'Camelot')}"),
                ("Duration", clock(t.duration * 1000)), ("Bitrate", f"{t.bitrate} kbps" if t.bitrate else ""),
                ("Gain", f"{t.gain:+.2f} dB" if t.gain else ""), ("Rating", "*" * t.rating),
                ("Plays", str(t.plays)), ("Added", t.added), ("Year", str(t.year or "")),
                ("Cues", cue_summary(t)), ("File", path or t.path)]
        form = QFormLayout()
        for k, v in rows:
            e = QLineEdit(v)
            e.setReadOnly(True)
            e.setFrame(False)
            form.addRow(k, e)
        art = QLabel("No artwork")
        art.setFixedSize(220, 220)
        art.setAlignment(Qt.AlignCenter)
        art.setStyleSheet(f"background: {theme.BG_MED};")
        img = tags.artwork(path) if path else None
        pm = QPixmap()
        if img and pm.loadFromData(img):
            art.setPixmap(pm.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        side = QVBoxLayout()
        side.addWidget(art)
        side.addStretch(1)
        ok = QPushButton("Close")
        ok.clicked.connect(self.accept)
        side.addWidget(ok)
        lay = QHBoxLayout(self)
        lay.addLayout(form, 1)
        lay.addLayout(side)


class PlaylistWindow(QWidget):
    """Edits the playlist in place: order, removed tracks and cues go to the next export."""

    edited = Signal()

    def __init__(self, node: Node, engine: Engine, loader: Loader, cfg: dict, music_root: str = "",
                 parent=None):
        super().__init__(parent, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.node, self.engine, self.loader, self.cfg = node, engine, loader, cfg
        self.root = music_root
        # where each track is, one stat per track per window and not per keystroke
        self.where: dict[int, str] = {}
        self.sort_col, self.sort_desc = -1, False
        self.setWindowTitle(f"Details: {node.name}")
        self.resize(1200, 560)

        self.player = Player(engine, loader, cfg)
        self.player.resolve = self.resolve
        self.player.dropped.connect(self.play_file)
        self.player.changed.connect(self.refresh_rows)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by artist, title or album")
        self.typing = QTimer(self)
        self.typing.setSingleShot(True)
        self.typing.setInterval(150)
        self.typing.timeout.connect(self.fill)
        self.search.textChanged.connect(self.typing.start)
        self.key_btn = QPushButton(cfg.get("key_format", "Open Key"))
        menu = QMenu(self)
        for n in keys.NOTATIONS:
            menu.addAction(n, lambda n=n: self.set_key_format(n))
        self.key_btn.setMenu(menu)
        top.addWidget(QLabel("Search"))
        top.addWidget(self.search, 1)
        top.addWidget(QLabel("Keys"))
        top.addWidget(self.key_btn)

        hint = QLabel("Space / P play  |  Del remove from playlist  |  double click: properties, "
                      "on Cues: timeline  |  drag rows to reorder  |  drop files or folders to add")
        hint.setStyleSheet(f"color: {theme.FG_MUTED}; font-size: 8pt;")

        self.table = Table()
        self.table.path_of = self.resolve
        self.table.setHeaderLabels(COLS)
        for i, w in enumerate(WIDTHS):
            self.table.setColumnWidth(i, w)
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setDragDropMode(QAbstractItemView.InternalMove)
        self.table.header().setSectionsClickable(True)
        self.table.header().sectionClicked.connect(self.sort_by)
        self.table.itemClicked.connect(self.clicked)
        self.table.itemDoubleClicked.connect(self.double)
        self.table.currentItemChanged.connect(self.selected)
        self.table.moved.connect(self.reordered)
        self.table.files.connect(self.add_paths)
        self.table.setAcceptDrops(True)         # files from outside can always be dropped

        bottom = QHBoxLayout()
        self.count = QLabel("")
        bottom.addWidget(self.count)
        bottom.addStretch(1)
        for text, fn in (("Add files...", self.pick_files), ("Save as M3U8...", self.save_m3u),
                         ("Copy track info", self.copy_info), ("Close", self.close)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bottom.addWidget(b)

        lay = QVBoxLayout(self)
        lay.addWidget(self.player)
        lay.addLayout(top)
        lay.addWidget(hint)
        lay.addWidget(self.table, 1)
        lay.addLayout(bottom)

        for k in ("Space", "P"):
            QShortcut(QKeySequence(k), self, self.toggle)
        QShortcut(QKeySequence.Delete, self.table, self.remove)
        QShortcut(QKeySequence.Find, self, self.search.setFocus)

        self.fill()
        self.loader.prefetch([p for p in map(self.resolve, node.tracks) if p])

    # ---- data

    def resolve(self, t: Track) -> str:
        p = self.where.get(id(t))
        if p is None:
            p = self.where[id(t)] = self.locate(t)
        return p

    def locate(self, t: Track) -> str:
        if t.path and os.path.isfile(t.path):
            return t.path
        if self.root and t.path:
            alt = os.path.join(self.root, os.path.basename(t.path))
            if os.path.isfile(alt):
                return alt
        return ""

    def rows(self) -> list[Track]:
        q = self.search.text().lower().strip()
        tracks = [t for t in self.node.tracks
                  if not q or q in f"{t.artist} {t.title} {t.album}".lower()]
        if self.sort_col >= 0:
            kf = {2: lambda t: t.artist.lower(), 3: lambda t: t.title.lower(),
                  4: lambda t: keys.name(t.key, "Camelot").zfill(3), 5: lambda t: t.bpm,
                  6: lambda t: t.gain, 7: lambda t: t.grid is not None, 8: lambda t: t.duration,
                  9: lambda t: len(t.cues), 10: lambda t: t.album.lower()}.get(self.sort_col)
            if kf:
                tracks.sort(key=kf, reverse=self.sort_desc)
            elif self.sort_desc:
                tracks.reverse()
        return tracks

    def fill(self):
        cur = self.current()
        self.table.setUpdatesEnabled(False)
        self.table.clear()
        fmt = self.key_btn.text()
        order = {id(t): i for i, t in enumerate(self.node.tracks)}
        items, sel = [], None
        red, colors = QColor(theme.RED), {}
        for t in self.rows():
            it = QTreeWidgetItem(["", str(order[id(t)] + 1), t.artist, t.title, keys.name(t.key, fmt),
                                  f"{t.bpm:.2f}" if t.bpm else "", f"{t.gain:+.1f}" if t.gain else "",
                                  "✓" if t.grid is not None else "", clock(t.duration * 1000)[:5],
                                  cue_summary(t), t.album])
            it.setData(0, Qt.UserRole, t)
            it.setFlags(it.flags() & ~Qt.ItemIsDropEnabled)
            if t.key not in colors:
                colors[t.key] = QColor(key_color(t.key))
            it.setForeground(4, colors[t.key])
            if not self.resolve(t):
                for c in range(len(COLS)):
                    it.setForeground(c, red)
                it.setToolTip(3, f"Missing: {t.path}")
            it.setText(C_PLAY, "⏸" if self.playing(t) else "▶")
            items.append(it)
            if t is cur:
                sel = it
        self.table.addTopLevelItems(items)
        if sel is not None:
            self.table.setCurrentItem(sel)
        self.table.setUpdatesEnabled(True)
        # reordering only means something on the real playlist order
        free = self.sort_col < 0 and not self.search.text()
        self.table.setDragEnabled(free)
        self.count.setText(f"{len(self.node.tracks)} tracks, "
                           f"{clock(sum(t.duration for t in self.node.tracks) * 1000)[:5]} total")

    def playing(self, t: Track) -> bool:
        return self.player.track is t and self.engine.playing and self.engine.path == self.player.path

    def refresh_rows(self):
        for i in range(self.table.topLevelItemCount()):
            it = self.table.topLevelItem(i)
            t = it.data(0, Qt.UserRole)
            it.setText(C_PLAY, "⏸" if self.playing(t) else "▶")
            it.setText(C_CUES, cue_summary(t))

    def current(self) -> Track | None:
        it = self.table.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    # ---- actions

    def set_key_format(self, n: str):
        self.key_btn.setText(n)
        self.cfg["key_format"] = n
        self.fill()

    def sort_by(self, col: int):
        if col == C_PLAY:
            return
        if col == C_NUM:
            self.sort_col, self.sort_desc = -1, False
        elif col == self.sort_col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col, self.sort_desc = col, False
        self.table.header().setSortIndicatorShown(self.sort_col >= 0)
        self.table.header().setSortIndicator(col, Qt.DescendingOrder if self.sort_desc else Qt.AscendingOrder)
        self.fill()

    def reordered(self):
        self.node.tracks = [self.table.topLevelItem(i).data(0, Qt.UserRole)
                            for i in range(self.table.topLevelItemCount())]
        self.fill()
        self.edited.emit()

    def remove(self):
        t = self.current()
        if t is None:
            return
        self.node.tracks.remove(t)
        self.fill()
        self.edited.emit()

    def selected(self, it, _prev=None):
        t = it.data(0, Qt.UserRole) if it else None
        # never cut what is playing, only follow the selection while stopped
        if t is not None and not self.engine.playing:
            self.player.load(t, self.resolve(t))
        self.player.tracks = self.node.tracks

    def clicked(self, it, col):
        if col == C_PLAY:
            self.play(it.data(0, Qt.UserRole))

    def double(self, it, col):
        t = it.data(0, Qt.UserRole)
        if col == C_PLAY:
            return
        if col == C_CUES:
            tl = Timeline(t, self.resolve(t), self.loader, self.cfg, self.engine, self)
            tl.changed.connect(self.cues_changed)
            tl.show()
        else:
            Properties(t, self.resolve(t), self.key_btn.text(), self).show()

    def cues_changed(self):
        self.player.refresh_pads()
        self.refresh_rows()
        self.edited.emit()

    def play(self, t: Track):
        p = self.resolve(t)
        if not p:
            self.player.title.setText(f"File not found: {t.path}")
            return
        if self.player.track is t and self.engine.path == p:
            self.engine.toggle()
        else:
            self.player.load(t, p)
            self.player.tracks = self.node.tracks
            self.player.play()
        self.refresh_rows()

    def toggle(self):
        t = self.current()
        if t is not None and t is not self.player.track:
            self.play(t)
        else:
            self.player.toggle()
        self.refresh_rows()

    def play_file(self, path: str):
        n = os.path.normcase(os.path.abspath(path))
        for t in self.node.tracks:
            p = self.resolve(t)
            if p and os.path.normcase(os.path.abspath(p)) == n:
                self.play(t)
                return
        t = Track(title=os.path.splitext(os.path.basename(path))[0], path=path)
        tags.fill(t)
        self.player.load(t, path)
        self.player.play()

    def pick_files(self):
        exts = " ".join("*" + e for e in sorted(AUDIO_EXT))
        names, _ = QFileDialog.getOpenFileNames(self, "Add files", self.root, f"Audio ({exts});;All (*)")
        if names:
            self.add_paths(names)

    def add_paths(self, paths: list[str]):
        """Files and folders into the playlist, a file already there is not added twice."""
        have = {os.path.normcase(os.path.abspath(t.path)) for t in self.node.tracks if t.path}
        new = []
        for t in tracks_from(paths):
            k = os.path.normcase(os.path.abspath(t.path))
            if k not in have:
                have.add(k)
                new.append(t)
        if not new:
            return
        self.node.tracks += new
        self.loader.prefetch([p for p in map(self.resolve, new) if p])
        self.fill()
        self.edited.emit()

    def save_m3u(self):
        start = os.path.join(self.root or os.path.expanduser("~"), f"{self.node.name}.m3u8")
        f, _ = QFileDialog.getSaveFileName(self, "Save the playlist", start, "M3U8 (*.m3u8)")
        if not f:
            return
        try:
            write_list(self.node, f, {}, False)
        except OSError as e:
            QMessageBox.critical(self, "Cannot save", str(e))
            return
        self.count.setText(f"Saved {os.path.basename(f)}")

    def copy_info(self):
        t = self.current()
        if t is None:
            return
        QApplication.clipboard().setText(
            f"{t.artist} - {t.title}\nAlbum: {t.album}\nBPM: {t.bpm:.2f}\n"
            f"Key: {keys.name(t.key, self.key_btn.text())}\nDuration: {clock(t.duration * 1000)}\n"
            f"Cues: {len(t.cues)}\nFile: {t.path}")

    def closeEvent(self, e):
        if self.engine.path and self.player.track is not None:
            self.engine.stop()
        self.player.timer.stop()
        super().closeEvent(e)
