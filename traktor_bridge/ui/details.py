# Benoit Saint-Moulin
# Traktor Bridge : playlist details (player, sortable list, reorder, properties)

from __future__ import annotations

import copy
import os
from dataclasses import fields

from PySide6.QtCore import QEvent, QItemSelectionModel, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDrag, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
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

from .. import beatdetect, keys, tags
from ..export import nml
from ..export.m3u import write_list
from ..model import Node, Track
from ..sources import AUDIO_EXT
from ..sources.folder import tracks_from
from . import cuehistory, theme
from .player import Engine, Player, clock
from .tageditor import TagEditor as Properties
from .timeline import Timeline
from .waveform import Loader
from .worker import Job
from .zoomwave import TEXT_INPUTS, duration_text, hot_key

COLS = ["", "#", "Artist", "Title", "Key", "BPM", "Gain", "Grid", "Time", "Cues", "Album", "Also in", "ID Tag"]
WIDTHS = [28, 36, 190, 260, 60, 60, 55, 40, 60, 90, 200, 62, 76]
C_PLAY, C_NUM, C_CUES, C_ALSO, C_TAG = 0, 1, 9, 11, 12
HISTORY = 200        # undo steps kept per playlist window
SEEK_MS = 5000       # Ctrl+Left / Ctrl+Right


def track_identity(t: Track) -> tuple[str, str] | None:
    if t.audio_id:
        return "id", t.audio_id
    if t.path:
        return "path", os.path.normcase(os.path.abspath(t.path))
    return None


def track_identities(t: Track) -> list[tuple[str, str]]:
    """Match tracks by ID or path; collections do not always use the same identity."""
    found = []
    if t.audio_id:
        found.append(("id", t.audio_id))
    if t.path:
        found.append(("path", os.path.normcase(os.path.abspath(t.path))))
    return found


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
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)     # Shift: range, Ctrl: single rows

    def startDrag(self, actions):
        paths = [self.path_of(it.data(0, Qt.UserRole)) for it in self.selectedItems()]
        paths = [p for p in paths if p]
        if not paths:
            return super().startDrag(actions)
        md = self.model().mimeData(self.selectedIndexes())
        md.setUrls([QUrl.fromLocalFile(p) for p in paths])
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


class PlaylistWindow(QWidget):
    """Edits the playlist in place: order, removed tracks and cues go to the next export."""

    edited = Signal()

    def __init__(self, node: Node, engine: Engine, loader: Loader, cfg: dict, music_root: str = "",
                 parent=None, others=None):
        super().__init__(parent, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.node, self.engine, self.loader, self.cfg = node, engine, loader, cfg
        self.others = others or list      # the other loaded playlists, to tell where a track also is
        self.presence: dict[tuple[str, str], list[str]] = {}
        self.undo_stack: list[tuple] = []        # playlist, ID tag and cue edits, oldest first
        self.redo_stack: list[tuple] = []
        self.edits: dict[int, int] = {}
        self.detect_job = None
        self.detect_before: dict[int, tuple[float, float | None]] = {}
        self.closing = False
        self._initial_tracks = [(track, copy.deepcopy(track)) for track in node.tracks]
        self.root = music_root
        # where each track is, one stat per track per window and not per keystroke
        self.where: dict[int, str] = {}
        self.sort_col, self.sort_desc = -1, False
        self.setWindowTitle(f"Details: {node.name}")
        self.resize(1200, 560)

        self.player = Player(engine, loader, cfg)
        self.player.resolve = self.resolve
        self.player.dropped.connect(self.play_file)
        self.player.changed.connect(self.player_changed)
        self.player.touched.connect(self.player_touched)
        self.engine.metadata_changed.connect(self.metadata_changed)

        search_controls = QWidget()
        top = QHBoxLayout(search_controls)
        top.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by artist, title or album")
        self.search.setMaximumWidth(480)
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
        key_controls = QHBoxLayout()
        key_controls.addStretch(1)
        key_controls.addWidget(QLabel("Keys"))
        key_controls.addWidget(self.key_btn)

        hint = QLabel("Space / P play  |  A-H: set a cue, again: play from it, Shift+A-H: delete it  |  "
                      "Del remove from playlist  |  double click: play, on Cues: timeline  |  "
                      "Shift / Ctrl + click: select several  |  drag rows to reorder  |  "
                      "drop files or folders to add")
        hint.setWordWrap(True)
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
        self.table.itemSelectionChanged.connect(self.summary)
        self.table.moved.connect(self.reordered)
        self.table.files.connect(self.add_paths)
        self.table.setAcceptDrops(True)

        bottom = QHBoxLayout()
        tools = QHBoxLayout()
        self.count = QLabel("")
        self.count.setWordWrap(True)
        bottom.addWidget(self.count)
        bottom.addStretch(1)
        self.undo_button = QPushButton("Undo")
        self.undo_button.setToolTip("Undo the last edit of the playlist, the cues or the ID tags (Ctrl+Z)")
        self.undo_button.clicked.connect(lambda: self.undo_cues())
        self.redo_button = QPushButton("Redo")
        self.redo_button.setToolTip("Redo the edit that was undone (Ctrl+Y)")
        self.redo_button.clicked.connect(lambda: self.undo_cues(True))
        bottom.addWidget(self.undo_button)
        bottom.addWidget(self.redo_button)
        self.detect_cancel = QPushButton("Cancel detection")
        self.detect_cancel.setEnabled(False)
        self.detect_cancel.clicked.connect(self.cancel_detection)
        for text, fn in (("Reload", self.reload_playlist), ("Remove duplicates", self.remove_duplicates),
                         ("Detect grids", self.detect_grids),
                         ("Add files...", self.pick_files), ("Save as M3U8...", self.save_m3u),
                         ("Save as NML...", self.save_nml), ("Copy track info", self.copy_info),
                         ("Close", self.close)):
            b = QPushButton(text)
            if text == "Reload":
                b.setToolTip("Discard playlist edits and restore the state from when this window opened")
            elif text == "Remove duplicates":
                b.setToolTip("Keep the lowest playlist number and remove later copies of the same track")
            elif text == "Detect grids":
                b.setToolTip("Find the tempo and first beat of the selected tracks, or of the tracks without a grid")
                self.detect_button = b
            b.clicked.connect(fn)
            if text in ("Reload", "Remove duplicates", "Detect grids", "Add files..."):
                tools.addWidget(b)
                if text == "Detect grids":
                    tools.addWidget(self.detect_cancel)
            else:
                bottom.addWidget(b)
        top.insertLayout(2, tools)
        self.player.toolbar.addWidget(search_controls, 1, 0)
        self.player.toolbar.addLayout(key_controls, 1, 1)

        lay = QVBoxLayout(self)
        lay.addWidget(self.player)
        lay.addWidget(hint)
        lay.addWidget(self.table, 1)
        lay.addLayout(bottom)

        for k in ("Space", "P"):
            QShortcut(QKeySequence(k), self, self.toggle)
        QShortcut(QKeySequence.Delete, self.table, self.remove)
        QShortcut(QKeySequence.Find, self, self.focus_search)
        QShortcut(QKeySequence.Undo, self, self.undo_cues)
        QShortcut(QKeySequence.Redo, self, lambda: self.undo_cues(True))
        for seq, fn in (("Alt+Up", lambda: self.move_selected(-1)), ("Alt+Down", lambda: self.move_selected(1)),
                        ("Ctrl+Left", lambda: self.seek_by(-SEEK_MS)), ("Ctrl+Right", lambda: self.seek_by(SEEK_MS)),
                        ("Ctrl+I", self.edit_current_tags), ("Ctrl+T", self.open_timeline),
                        ("Ctrl+Shift+D", self.remove_duplicates)):
            QShortcut(QKeySequence(seq), self, fn)
        self.search.installEventFilter(self)
        self.table.setAccessibleName("Playlist tracks")
        self.search.setAccessibleName("Filter tracks")
        self.undo_button.setAccessibleName("Undo")
        self.redo_button.setAccessibleName("Redo")

        # letters would reach the table's type-ahead or a text field: only handled here
        QApplication.instance().installEventFilter(self)

        self.fill()
        self.sync_cues(push=False)
        self.refresh_history()
        self.loader.prefetch([p for p in map(self.resolve, node.tracks) if p])

    def eventFilter(self, obj, e):
        if (e.type() == QEvent.KeyPress and e.key() == Qt.Key_S
                and e.modifiers() == Qt.NoModifier and not e.isAutoRepeat()
                and self.isActiveWindow()
                and not isinstance(QApplication.focusWidget(), TEXT_INPUTS)):
            self.player.snap_btn.toggle()
            return True
        if (obj is self.table and e.type() == QEvent.KeyPress
                and e.key() in (Qt.Key_Return, Qt.Key_Enter)
                and e.modifiers() == Qt.NoModifier):
            track = self.current()
            if track is not None and not e.isAutoRepeat():
                self.play(track)
            return True
        if obj is self.search:
            if e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
                self.search.clear()          # Esc empties the filter and gives the keyboard back to the list
                self.table.setFocus()
                return True
            if e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Down, Qt.Key_Return, Qt.Key_Enter):
                self.table.setFocus()
                return True
            return False
        hit = hot_key(e, self) if self.player.track is not None else None
        if hit:
            self.player.pad(hit[0], play=True, delete=hit[1])
            return True
        return super().eventFilter(obj, e)

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def move_selected(self, delta: int):
        """Alt+Up / Alt+Down: moves the selected tracks one place, on the real playlist order."""
        if self.sort_col >= 0 or self.search.text():
            self.count.setText("Clear the sort and the filter (click #) to reorder with the keyboard")
            return
        chosen = {id(t) for t in self.chosen()}
        tracks = list(self.node.tracks)
        if not chosen:
            return
        rng = range(len(tracks)) if delta < 0 else range(len(tracks) - 1, -1, -1)
        moved = False
        for i in rng:
            j = i + delta
            if id(tracks[i]) in chosen and 0 <= j < len(tracks) and id(tracks[j]) not in chosen:
                tracks[i], tracks[j] = tracks[j], tracks[i]
                moved = True
        if not moved:
            return
        self.change_tracks(tracks)
        first = None
        for i in range(self.table.topLevelItemCount()):
            it = self.table.topLevelItem(i)
            if id(it.data(0, Qt.UserRole)) in chosen:
                it.setSelected(True)
                first = first or it
        if first is not None:
            self.table.setCurrentItem(first, 0, QItemSelectionModel.NoUpdate)

    def seek_by(self, ms: float):
        if self.player.track is not None:
            self.player.seek(self.player.position() + ms)

    def edit_current_tags(self):
        t = self.current()
        if t is not None:
            self.edit_tags(t)

    def open_timeline(self):
        t = self.current()
        if t is not None:
            self.double(self.table.currentItem(), C_CUES)

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
                  9: lambda t: len(t.cues), 10: lambda t: t.album.lower(),
                  C_ALSO: lambda t: len(self.also_in(t))}.get(self.sort_col)
            if kf:
                tracks.sort(key=kf, reverse=self.sort_desc)
            elif self.sort_desc:
                tracks.reverse()
        return tracks

    def index_others(self):
        found: dict[tuple[str, str], list[str]] = {}
        for other in self.others():
            if other is self.node:
                continue
            names = set()
            for t in other.tracks:
                for ident in track_identities(t):
                    if (ident, other.name) not in names:
                        names.add((ident, other.name))
                        found.setdefault(ident, []).append(other.name)
        self.presence = found

    def also_in(self, t: Track) -> list[str]:
        names: list[str] = []
        for ident in track_identities(t):
            for name in self.presence.get(ident, ()):
                if name not in names:
                    names.append(name)
        return names

    def fill(self):
        cur = self.current()
        self.index_others()
        self.table.setUpdatesEnabled(False)
        self.table.clear()
        fmt = self.key_btn.text()
        order = {id(t): i for i, t in enumerate(self.node.tracks)}
        items, sel = [], None
        red, colors = QColor(theme.RED), {}
        for t in self.rows():
            elsewhere = self.also_in(t)
            it = QTreeWidgetItem(["", str(order[id(t)] + 1), t.artist, t.title, keys.name(t.key, fmt),
                                  f"{t.bpm:.2f}" if t.bpm else "", f"{t.gain:+.1f}" if t.gain else "",
                                  "✓" if t.grid is not None else "", clock(t.duration * 1000).split(".")[0],
                                  cue_summary(t), t.album, str(len(elsewhere)) if elsewhere else ""])
            it.setData(0, Qt.UserRole, t)
            it.setData(C_ALSO, Qt.UserRole, len(elsewhere))
            if elsewhere:
                it.setToolTip(C_ALSO, "Also in: " + ", ".join(elsewhere))
                it.setTextAlignment(C_ALSO, Qt.AlignCenter)
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
        for it in items:
            t = it.data(0, Qt.UserRole)
            edit_tag = QPushButton("ID Tag", self.table)
            edit_tag.setToolTip(f"Edit ID tag metadata for {t.artist} - {t.title} (Ctrl+I)")
            edit_tag.setAccessibleName(f"ID Tag: {t.artist} - {t.title}")
            edit_tag.setFocusPolicy(Qt.NoFocus)  # Keep row navigation on the table.
            edit_tag.clicked.connect(lambda _checked=False, track=t: self.edit_tags(track))
            self.table.setItemWidget(it, C_TAG, edit_tag)
        if sel is not None:
            self.table.setCurrentItem(sel)
        self.table.setUpdatesEnabled(True)
        # reordering only means something on the real playlist order
        free = self.sort_col < 0 and not self.search.text()
        self.table.setDragEnabled(free)
        self.summary()

    def chosen(self) -> list[Track]:
        """The selected tracks, in the order of the playlist."""
        ids = {id(it.data(0, Qt.UserRole)) for it in self.table.selectedItems()}
        return [t for t in self.node.tracks if id(t) in ids]

    def summary(self):
        sel = self.chosen()
        if len(sel) > 1:
            self.count.setText(f"{len(sel)} of {len(self.node.tracks)} selected, "
                               f"{duration_text(sum(t.duration for t in sel))}")
        elif len(sel) == 1 and self.also_in(sel[0]):
            self.count.setText("Also in: " + ", ".join(self.also_in(sel[0])))
        else:
            self.count.setText(f"{len(self.node.tracks)} tracks, "
                               f"{duration_text(sum(t.duration for t in self.node.tracks))}")

    def playing(self, t: Track) -> bool:
        return self.player.track is t and self.engine.playing and self.engine.path == self.player.path

    def refresh_rows(self):
        for i in range(self.table.topLevelItemCount()):
            it = self.table.topLevelItem(i)
            t = it.data(0, Qt.UserRole)
            it.setText(C_PLAY, "⏸" if self.playing(t) else "▶")
            it.setText(C_CUES, cue_summary(t))
            it.setText(5, f"{t.bpm:.2f}" if t.bpm else "")
            it.setText(7, "✓" if t.grid is not None else "")

    def current(self) -> Track | None:
        it = self.table.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    # ---- actions

    def set_key_format(self, n: str):
        self.key_btn.setText(n)
        self.cfg["key_format"] = n
        self.fill()

    def sort_by(self, col: int):
        if col in (C_PLAY, C_TAG):
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
        self.change_tracks([self.table.topLevelItem(i).data(0, Qt.UserRole)
                            for i in range(self.table.topLevelItemCount())])

    def change_tracks(self, tracks: list[Track]):
        """Replaces the playlist content, one undo step."""
        self.push(("tracks", list(self.node.tracks), list(tracks)))
        self.node.tracks = tracks
        self.player.tracks = tracks
        self.fill()
        self.edited.emit()

    def remove(self):
        gone = {id(t) for t in self.chosen()}
        if not gone:
            return
        self.change_tracks([t for t in self.node.tracks if id(t) not in gone])

    def remove_duplicates(self):
        seen = set()
        duplicates = []
        retained = []
        for t in self.node.tracks:
            identity = track_identity(t)
            if identity is None:
                retained.append(t)
                continue
            if identity in seen:
                duplicates.append(t)
            else:
                seen.add(identity)
                retained.append(t)
        if not duplicates:
            self.count.setText("No duplicate tracks found")
            return
        answer = QMessageBox.question(
            self,
            "Remove duplicates",
            f"Remove {len(duplicates)} duplicate track(s)? "
            "The copy with the lowest playlist number will be kept.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.change_tracks(retained)
        self.count.setText(f"Removed {len(duplicates)} duplicate track(s)")

    def reload_playlist(self):
        answer = QMessageBox.question(
            self,
            "Reload playlist",
            "Discard playlist changes and restore the state from when this window opened?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.cancel_detection()
        self.detect_before.clear()
        self.player.stop()
        for original, saved in self._initial_tracks:
            for field in fields(Track):
                setattr(original, field.name, copy.deepcopy(getattr(saved, field.name)))
        self.node.tracks[:] = [original for original, _saved in self._initial_tracks]
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.sync_cues(push=False)
        self.refresh_history()
        self.where.clear()
        self.fill()
        self.player.tracks = self.node.tracks
        current = self.current()
        if current is not None:
            self.selected(self.table.currentItem())
        else:
            self.player.track = None
            self.player.path = ""
            self.player.mark = 0.0
            self.player.title.setText("No track loaded, pick one in the list or drop a file")
            self.player.meta.clear()
            self.player.view.show_track(None, None)
            self.player.view.set_pos(0.0)
            self.player.set_art("")
            self.player.refresh_pads()
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
        if col == C_CUES:
            tl = Timeline(t, self.resolve(t), self.loader, self.cfg, self.engine, self)
            tl.changed.connect(self.cues_changed)
            tl.show()
        elif col == C_TAG:
            return
        else:
            self.play(t)

    def edit_tags(self, t: Track):
        for editor in self.findChildren(Properties):
            if editor.t is t:
                editor.show()
                editor.raise_()
                editor.activateWindow()
                return
        editor = Properties(t, self.resolve(t), self.key_btn.text(), self, engine=self.engine)
        before = self.fields_of(t)

        def applied():
            nonlocal before
            after = self.fields_of(t)
            if after != before:
                self.push(("fields", t, before, after))
                before = after
            self.sync_cues(push=False)       # a tempo change made there is part of this step
            self.engine.metadata_changed.emit(t)

        editor.changed.connect(applied)
        editor.file_written.connect(lambda _path: self.engine.metadata_changed.emit(t))
        editor.show()

    @staticmethod
    def fields_of(t: Track) -> dict:
        return {f.name: getattr(t, f.name) for f in fields(Track) if f.name not in ("cues", "size")}

    def metadata_changed(self, _track=None):
        self.table.blockSignals(True)
        try:
            self.fill()
        finally:
            self.table.blockSignals(False)
        if self.player.track is not None:
            t = self.player.track
            self.player.title.setText(f"{t.artist}  -  {t.title}" if t.artist else t.title)
            self.player.refresh_meta()
        for timeline in self.findChildren(Timeline):
            timeline.refresh_beatgrid()
            timeline.setWindowTitle(f"Cues: {timeline.t.artist} - {timeline.t.title}")
        self.edited.emit()

    def push(self, entry: tuple):
        self.undo_stack.append(entry)
        del self.undo_stack[:-HISTORY]
        self.redo_stack.clear()
        self.refresh_history()

    def sync_cues(self, push: bool = True):
        """Notes the cue and grid edits made in the player or a timeline since last time."""
        for t in self.node.tracks:
            now = cuehistory.edits(t)
            if now != self.edits.get(id(t), 0) and push and now > 0:
                self.push(("cue", t))
            self.edits[id(t)] = now

    def refresh_history(self):
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.redo_button.setEnabled(bool(self.redo_stack))

    def detect_grids(self):
        """Tempo and first beat of the selected tracks, or of those without a grid."""
        if self.detect_job is not None:
            return
        targets = self.chosen() or [t for t in self.node.tracks if t.grid is None]
        targets = list({id(t): t for t in targets}.values())
        items = [(id(t), p) for t in targets if (p := self.resolve(t))]
        missing = len(targets) - len(items)
        if missing:
            QMessageBox.warning(self, "Detect beat grids",
                                f"{missing} track(s) have no available audio file and cannot be analysed.")
        if not items:
            self.count.setText("No track to analyse (select tracks, or every track has a grid)")
            return
        answer = QMessageBox.question(
            self, "Detect beat grids",
            f"Analyse {len(items)} track(s)? A reliable result replaces the tempo and the first beat, "
            "unreliable ones are skipped. Ctrl+Z undoes the whole batch.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer != QMessageBox.Yes:
            return
        self.detect_before = {id(t): (t.bpm, t.grid) for t in targets}
        job = Job(beatdetect.analyze_many, items)
        job.progress.connect(self.detect_progress)
        job.done.connect(self.grids_detected)
        job.failed.connect(self.detect_failed)
        job.cancelled.connect(self.detect_cancelled)
        job.finished.connect(self.detect_finished)
        self.detect_job = job
        self.detect_button.setEnabled(False)
        self.detect_cancel.setEnabled(True)
        job.start()

    def cancel_detection(self):
        if self.detect_job is not None:
            self.detect_job.stop.set()

    def detect_progress(self, _pct, message):
        if not self.closing:
            self.count.setText(message)

    def detect_failed(self, message):
        if not self.closing:
            QMessageBox.warning(self, "Detect beat grids", message)

    def detect_cancelled(self):
        if not self.closing:
            self.count.setText("Detection cancelled; no grids changed")

    def grids_detected(self, results: list):
        if self.closing or (self.detect_job is not None and self.detect_job.stop.is_set()):
            return
        by_id = {id(t): t for t in self.node.tracks}
        changes, errors = [], []
        skipped = 0
        seen = set()
        for key, result in results:
            t = by_id.get(key)
            if t is None or key in seen:
                continue
            seen.add(key)
            before = self.detect_before.get(key)
            if before is None or (t.bpm, t.grid) != before:
                skipped += 1
                continue
            if isinstance(result, str):
                errors.append(f"{t.title or t.path}: {result}")
            elif not result.reliable:
                skipped += 1
            else:
                after = (result.bpm, result.first_beat_ms)
                if before != after:
                    changes.append((t, before, after))
        if changes:
            self.push(("timing", changes))
            self.apply(self.undo_stack[-1], True)
        self.count.setText(f"Beat grid detected for {len(changes)} track(s), {skipped} skipped "
                           f"(unreliable or edited during analysis), {len(errors)} failed")
        if errors:
            QMessageBox.warning(self, "Detect beat grids", "\n".join(errors))

    def detect_finished(self):
        job, self.detect_job = self.detect_job, None
        if job is not None:
            job.deleteLater()
        self.detect_button.setEnabled(True)
        self.detect_cancel.setEnabled(False)
        self.detect_before.clear()

    def undo_cues(self, redo: bool = False):
        """Ctrl+Z / Ctrl+Y: the last edit of the playlist, of the cues or of the ID tags."""
        src, dst = (self.redo_stack, self.undo_stack) if redo else (self.undo_stack, self.redo_stack)
        while src:
            entry = src.pop()
            if self.apply(entry, redo):
                dst.append(entry)
                self.refresh_history()
                return True
        self.refresh_history()
        return False

    def apply(self, entry: tuple, redo: bool) -> bool:
        kind = entry[0]
        if kind == "timing":
            for t, before, after in entry[1]:
                t.bpm, t.grid = after if redo else before
            self.sync_cues(push=False)
            self.player.refresh_meta()
            self.player.view.update()
            for timeline in self.findChildren(Timeline):
                timeline.refresh_beatgrid()
            self.refresh_rows()
            self.edited.emit()
            return True
        if kind == "tracks":
            tracks = list(entry[2] if redo else entry[1])
            self.node.tracks = tracks
            self.player.tracks = tracks
            self.fill()
            self.edited.emit()
            return True
        if kind == "fields":
            _, t, before, after = entry
            for name, value in (after if redo else before).items():
                setattr(t, name, value)
            self.metadata_changed(t)
            return True
        t = entry[1]
        if not (cuehistory.redo if redo else cuehistory.undo)(t):
            return False
        self.edits[id(t)] = cuehistory.edits(t)
        if t is self.player.track:
            self.player.refresh_meta()
            self.player.refresh_pads()
        for timeline in self.findChildren(Timeline):
            if timeline.t is t:
                timeline.refresh_beatgrid()
                timeline.fill()
        self.refresh_rows()
        self.edited.emit()
        return True

    def player_touched(self):
        self.sync_cues()
        self.edited.emit()

    def player_changed(self):
        self.refresh_rows()
        for tl in self.findChildren(Timeline):
            if tl.t is self.player.track:
                tl.refresh_beatgrid()
                tl.fill()

    def cues_changed(self):
        self.sync_cues()
        self.player.refresh_pads()
        self.player.refresh_meta()
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
        self.loader.prefetch([p for p in map(self.resolve, new) if p])
        self.change_tracks(self.node.tracks + new)

    def to_save(self) -> Node:
        """The selection when several tracks are selected, else the whole playlist."""
        sel = self.chosen()
        if len(sel) < 2:
            return self.node
        return Node("playlist", self.node.name, tracks=sel, uuid=self.node.uuid)

    def found(self, n: Node) -> dict[str, str]:
        return {t.uid: p for t in n.tracks if (p := self.resolve(t))}

    def save_m3u(self):
        n = self.to_save()
        start = os.path.join(self.root or os.path.expanduser("~"), f"{n.name}.m3u8")
        f, _ = QFileDialog.getSaveFileName(self, "Save the playlist", start, "M3U8 (*.m3u8)")
        if not f:
            return
        try:
            write_list(n, f, self.found(n), False)
        except OSError as e:
            QMessageBox.critical(self, "Cannot save", str(e))
            return
        self.count.setText(f"Saved {os.path.basename(f)} ({len(n.tracks)} tracks)")

    def save_nml(self):
        n = self.to_save()
        start = os.path.join(self.root or os.path.expanduser("~"), f"{n.name}.nml")
        f, _ = QFileDialog.getSaveFileName(self, "Save as NML", start, "Traktor NML (*.nml)")
        if not f:
            return
        try:
            nml.export([n], os.path.dirname(f), name=os.path.basename(f), moved=self.found(n))
        except OSError as e:
            QMessageBox.critical(self, "Cannot save", str(e))
            return
        self.count.setText(f"Saved {os.path.basename(f)} ({len(n.tracks)} tracks)")

    def copy_info(self):
        sel = self.chosen() or ([self.current()] if self.current() else [])
        if not sel:
            return
        fmt = self.key_btn.text()
        QApplication.clipboard().setText("\n\n".join(
            f"{t.artist} - {t.title}\nAlbum: {t.album}\nBPM: {t.bpm:.2f}\n"
            f"Key: {keys.name(t.key, fmt)}\nDuration: {clock(t.duration * 1000)}\n"
            f"Cues: {len(t.cues)}\nFile: {t.path}" for t in sel))

    def closeEvent(self, e):
        if any(editor.job is not None for editor in self.findChildren(Properties)):
            e.ignore()
            return
        if self.detect_job is not None:
            self.closing = True
            self.detect_job.stop.set()
            if not self.detect_job.wait(5000):
                self.closing = False
                self.count.setText("Waiting for beat detection to stop. Try closing again when it finishes.")
                e.ignore()
                return
        QApplication.instance().removeEventFilter(self)
        if self.engine.path and self.player.track is not None and self.engine.timing_track is self.player.track:
            self.engine.stop()
        self.player.timer.stop()
        super().closeEvent(e)
