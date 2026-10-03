# Benoit Saint-Moulin
# Traktor Bridge : options, collection check, log, usage and about

from __future__ import annotations

import html
import logging
import os
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, AUTHOR, GITHUB, KOFI, VERSION, WEBSITE, keys
from ..model import Node, Track, playlists
from ..settings import EXPORTS, cache_dir
from ..sources import index_folder
from . import theme

# ============================================================
# Options
# ============================================================

class Options(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle(f"{APP_NAME} - Options")
        self.resize(520, 420)
        tabs = QTabWidget()

        ex = QWidget()
        f = QFormLayout(ex)
        self.fmt = QComboBox()
        self.fmt.addItems(EXPORTS)
        self.fmt.setCurrentText(cfg["export_format"])
        self.keyfmt = QComboBox()
        self.keyfmt.addItems(keys.NOTATIONS)
        self.keyfmt.setCurrentText(cfg["key_format"])
        self.copy = QCheckBox("Copy audio files with the export")
        self.copy.setChecked(cfg["copy_music"])
        self.verify = QCheckBox("Read the whole export back and check it")
        self.verify.setChecked(cfg["verify_copy"])
        f.addRow("Export format", self.fmt)
        f.addRow("Key notation", self.keyfmt)
        f.addRow(self.copy)
        f.addRow(self.verify)
        f.addRow(QLabel("CDJ/USB always copies the audio: the players only read the key."))
        tabs.addTab(ex, "Export")

        cdj = QWidget()
        f = QFormLayout(cdj)
        self.procs = QSpinBox()
        self.procs.setRange(0, 32)
        self.procs.setSpecialValueText("Auto (up to 8)")
        self.procs.setValue(int(cfg["anlz_processes"]))
        self.cache_lbl = QLabel("")
        clear = QPushButton("Clear analysis cache")
        clear.clicked.connect(self.clear_cache)
        f.addRow("Analysis processes", self.procs)
        f.addRow(self.cache_lbl)
        f.addRow(clear)
        self.ref_lbl = QLabel("")
        ref = QPushButton("Import a key exported by rekordbox...")
        ref.clicked.connect(lambda: import_reference(self) and self.show_reference())
        f.addRow(self.ref_lbl)
        f.addRow(ref)
        f.addRow(QLabel("Target: CDJ-2000NXS2 and compatible players,\n"
                        "FAT32 or exFAT key (NTFS is not read by the players)."))
        tabs.addTab(cdj, "CDJ")

        pl = QWidget()
        f = QFormLayout(pl)
        self.wave = QComboBox()
        self.wave.addItems(["RGB", "Blue", "IR"])
        self.wave.setCurrentText(cfg["waveform_color"])
        self.fade = QSpinBox()
        self.fade.setRange(0, 10)
        self.fade.setSuffix(" s")
        self.fade.setValue(int(cfg["crossfade"]))
        self.vol = QSpinBox()
        self.vol.setRange(0, 100)
        self.vol.setSuffix(" %")
        self.vol.setValue(int(cfg["volume"]))
        f.addRow("Waveform colours", self.wave)
        f.addRow("Crossfade (continue mode)", self.fade)
        f.addRow("Preview volume", self.vol)
        tabs.addTab(pl, "Player")

        app = QWidget()
        f = QFormLayout(app)
        self.auto = QCheckBox("Load the last collection on startup")
        self.auto.setChecked(cfg["auto_load"])
        self.confirm = QCheckBox("Ask before quitting")
        self.confirm.setChecked(cfg["confirm_exit"])
        self.level = QComboBox()
        self.level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.level.setCurrentText(cfg["log_level"])
        f.addRow(self.auto)
        f.addRow(self.confirm)
        f.addRow("Log level", self.level)
        tabs.addTab(app, "Application")

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)
        self.show_cache()
        self.show_reference()

    def show_reference(self):
        from ..export.cdj import reference
        self.ref_lbl.setText("rekordbox reference: imported" if reference.ready()
                             else "rekordbox reference: missing, needed for CDJ keys")

    def show_cache(self):
        n = size = 0
        for sub in ("anlz", "wave"):
            d = cache_dir() / sub
            if d.is_dir():
                for f in d.iterdir():
                    n += 1
                    size += f.stat().st_size
        self.cache_lbl.setText(f"Cache: {n} files, {size / 1e6:.1f} MB")

    def clear_cache(self):
        if QMessageBox.question(self, "Clear cache", "Delete all cached analysis and waveforms?") != QMessageBox.Yes:
            return
        for sub in ("anlz", "wave"):
            d = cache_dir() / sub
            if d.is_dir():
                for f in d.iterdir():
                    f.unlink(missing_ok=True)
        self.show_cache()

    def accept(self):
        self.cfg.update(export_format=self.fmt.currentText(), key_format=self.keyfmt.currentText(),
                        copy_music=self.copy.isChecked(), verify_copy=self.verify.isChecked(),
                        anlz_processes=self.procs.value(), waveform_color=self.wave.currentText(),
                        crossfade=self.fade.value(), volume=self.vol.value(),
                        auto_load=self.auto.isChecked(), confirm_exit=self.confirm.isChecked(),
                        log_level=self.level.currentText())
        super().accept()


def import_reference(parent) -> bool:
    """Ask for a key (or folder) exported by rekordbox and take the player files from it."""
    from ..export.cdj import reference
    QMessageBox.information(
        parent, "rekordbox reference",
        "A CDJ key needs the player settings and menu pages that only rekordbox writes.\n"
        "Traktor Bridge does not ship them: export any playlist to a USB key with your own\n"
        "rekordbox once, then pick that key (or its PIONEER folder). This is needed only once.")
    d = QFileDialog.getExistingDirectory(parent, "Key or folder exported by rekordbox")
    if not d:
        return False
    try:
        reference.import_from(d)
    except reference.MissingReference as e:
        QMessageBox.warning(parent, "rekordbox reference", str(e))
        return False
    QMessageBox.information(parent, "rekordbox reference", "Reference imported, CDJ keys can be exported.")
    return True


# ============================================================
# Check collection
# ============================================================

class _Scan(QThread):
    found = Signal(object)

    def __init__(self, root: str):
        super().__init__()
        self.root = root

    def run(self):
        self.found.emit(index_folder(self.root))


class CheckCollection(QDialog):
    """Missing files and their relocation. Tracks are shared between playlists,
    so relocating one entry fixes it everywhere."""

    relocated = Signal()

    def __init__(self, nodes: list[Node], music_root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Check collection")
        self.resize(940, 560)
        self.root = music_root
        self.scan = None
        seen, self.items = set(), []
        for pl in playlists(nodes):
            for t in pl.tracks:
                if id(t) not in seen:
                    seen.add(id(t))
                    self.items.append((t, pl.name))

        self.stats = QLabel("")
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by artist, title or path")
        self.typing = QTimer(self)
        self.typing.setSingleShot(True)
        self.typing.setInterval(150)
        self.typing.timeout.connect(self.fill)
        self.search.textChanged.connect(self.typing.start)
        self.which = QComboBox()
        self.which.addItems(["All tracks", "Missing only", "Found only"])
        self.which.setCurrentIndex(1)
        self.which.currentIndexChanged.connect(self.fill)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.which)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["", "Artist", "Title", "Playlist", "File"])
        self.table.setRootIsDecorated(False)
        for i, w in enumerate((28, 170, 220, 130, 360)):
            self.table.setColumnWidth(i, w)

        folder = QHBoxLayout()
        self.folder = QLineEdit(music_root)
        self.folder.setReadOnly(True)
        pick = QPushButton("Browse...")
        pick.clicked.connect(self.pick)
        folder.addWidget(QLabel("Search folder"))
        folder.addWidget(self.folder, 1)
        folder.addWidget(pick)

        btns = QHBoxLayout()
        for text, fn in (("Relocate all missing", self.auto), ("Locate selected...", self.locate)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        btns.addWidget(close)

        lay = QVBoxLayout(self)
        lay.addWidget(self.stats)
        lay.addLayout(bar)
        lay.addWidget(self.table, 1)
        lay.addLayout(folder)
        lay.addLayout(btns)
        self.check()

    def check(self):
        self.ok = {id(t): bool(t.path) and os.path.isfile(t.path) for t, _ in self.items}
        miss = sum(not v for v in self.ok.values())
        self.stats.setText(f"{len(self.items)} tracks, {len(self.items) - miss} found, {miss} missing")
        self.fill()

    def fill(self):
        q = self.search.text().lower()
        mode = self.which.currentIndex()
        green, red = QColor(theme.GREEN), QColor(theme.RED)
        self.table.setUpdatesEnabled(False)
        self.table.clear()
        items = []
        for t, pl in self.items:
            ok = self.ok[id(t)]
            if (mode == 1 and ok) or (mode == 2 and not ok):
                continue
            if q and q not in f"{t.artist} {t.title} {t.path}".lower():
                continue
            it = QTreeWidgetItem(["✓" if ok else "✗", t.artist, t.title, pl, t.path])
            it.setForeground(0, green if ok else red)
            if not ok:
                for c in range(1, 5):
                    it.setForeground(c, red)
            it.setToolTip(4, t.path)
            it.setData(0, Qt.UserRole, t)
            items.append(it)
        self.table.addTopLevelItems(items)
        self.table.setUpdatesEnabled(True)

    def pick(self):
        d = QFileDialog.getExistingDirectory(self, "Folder to search", self.root)
        if d:
            self.root = d
            self.folder.setText(d)

    def auto(self):
        if not self.root or not os.path.isdir(self.root):
            QMessageBox.warning(self, "Relocate", "Pick the folder to search first.")
            return
        missing = [t for t, _ in self.items if not self.ok[id(t)]]
        if not missing:
            QMessageBox.information(self, "Relocate", "Nothing is missing.")
            return
        self.stats.setText(f"Scanning {self.root}...")
        self.setEnabled(False)
        self.scan = _Scan(self.root)
        self.scan.found.connect(lambda idx: self.apply(missing, idx))
        self.scan.start()

    def apply(self, missing: list[Track], idx: dict):
        self.setEnabled(True)
        done = skipped = 0
        for t in missing:
            hits = idx.get(os.path.basename(t.path).lower(), [])
            if len(hits) > 1:
                pick, ok = QInputDialog.getItem(self, "Several matches", f"{t.artist} - {t.title}", hits, 0, False)
                hits = [pick] if ok else []
            if hits:
                t.path = os.path.normpath(hits[0])
                done += 1
            else:
                skipped += 1
        self.check()
        if done:
            self.relocated.emit()
        QMessageBox.information(self, "Relocate", f"Relocated: {done}\nNot found or skipped: {skipped}")

    def locate(self):
        it = self.table.currentItem()
        if it is None:
            return
        t = it.data(0, Qt.UserRole)
        start = os.path.dirname(t.path) if os.path.isdir(os.path.dirname(t.path)) else self.root
        f, _ = QFileDialog.getOpenFileName(self, f"Locate {t.artist} - {t.title}", start,
                                           "Audio (*.mp3 *.flac *.aiff *.aif *.wav *.m4a *.mp4 *.aac *.ogg);;All (*)")
        if f:
            t.path = os.path.normpath(f)
            self.check()
            self.relocated.emit()


# ============================================================
# Log
# ============================================================

LEVEL_COLORS = {"DEBUG": theme.FG_MUTED, "INFO": theme.FG, "WARNING": theme.YELLOW,
                "ERROR": theme.RED, "CRITICAL": theme.RED}


class LogBridge(QObject, logging.Handler):
    """logging.Handler usable from any thread: records cross into the GUI by signal."""

    line = Signal(str, str)

    def __init__(self):
        QObject.__init__(self)
        logging.Handler.__init__(self)
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, rec):
        try:
            self.line.emit(self.format(rec), rec.levelname)
        except RuntimeError:
            pass    # window already gone at shutdown


class LogWindow(QDialog):
    MAX = 5000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log")
        self.resize(820, 500)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet("font-family: Consolas, monospace; font-size: 9pt;")
        self.text.document().setMaximumBlockCount(self.MAX)
        btns = QHBoxLayout()
        for label, fn in (("Clear", self.text.clear), ("Copy all", self.copy), ("Save...", self.save)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.hide)
        btns.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(self.text)
        lay.addLayout(btns)

    def add(self, msg: str, level: str):
        col = LEVEL_COLORS.get(level, theme.FG)
        t = datetime.now().strftime("%H:%M:%S")
        self.text.append(f'<span style="color:{col}">[{t}] {level}: {html.escape(msg)}</span>')

    def copy(self):
        QApplication.clipboard().setText(self.text.toPlainText())

    def save(self):
        name = f"traktor_bridge_log_{datetime.now():%Y%m%d_%H%M%S}.txt"
        f, _ = QFileDialog.getSaveFileName(self, "Save log", name, "Text (*.txt)")
        if f:
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(f"{APP_NAME} {VERSION} log, {datetime.now():%Y-%m-%d %H:%M}\n\n")
                fh.write(self.text.toPlainText())


# ============================================================
# Usage, About
# ============================================================

USAGE = f"""
<h2>{APP_NAME}</h2>
<h3>Getting started</h3>
<ol>
<li>File &gt; Open a collection: Traktor <b>collection.nml</b>, rekordbox <b>XML</b>,
VirtualDJ <b>database.xml</b> (or a <b>.vdjfolder</b>), Serato <b>_Serato_/database V2</b>
(or a <b>.crate</b>), Mixxx <b>mixxxdb.sqlite</b> or an <b>M3U / M3U8</b> playlist.</li>
<li>If the files moved since the collection was written, set the <b>music folder</b>:
missing tracks are looked up there by file name.</li>
<li>Tick the playlists to export (nothing ticked = everything).</li>
<li>Pick the format and the output folder, then <b>Convert</b>.</li>
</ol>
<h3>Formats</h3>
<ul>
<li><b>CDJ/USB</b>: complete Pioneer key (Contents, export.pdb, ANLZ waveforms, artwork).
Needs, once, a key exported by your own rekordbox: Options &gt; CDJ &gt; Import. The player
settings and menu pages only rekordbox writes are taken from it.
Export to a folder then copy its content to the root of a FAT32 or exFAT key,
or pick the key itself.</li>
<li><b>Rekordbox XML</b>: import in rekordbox (Preferences &gt; View &gt; rekordbox xml).</li>
<li><b>M3U</b>: one M3U8 per playlist, folders kept as folders.</li>
<li><b>Traktor NML</b>: a collection Traktor can import.</li>
</ul>
<h3>Checking a key</h3>
<p>Every export writes <b>traktor_bridge_checksums.json</b> next to it, with a SHA-256 of each
file. File &gt; Verify an export reads the key back and lists anything damaged or missing,
before a gig for example. <b>Verify after export</b> does the same right after writing and
replaces the copies that differ from their source.</p>
<h3>Shortcuts</h3>
<table cellpadding="3">
<tr><td>Ctrl+O</td><td>Open a collection</td></tr>
<tr><td>Ctrl+R</td><td>Reload</td></tr>
<tr><td>Ctrl+K</td><td>Check collection, relocate missing files</td></tr>
<tr><td>Ctrl+Shift+V</td><td>Verify an export</td></tr>
<tr><td>Ctrl+Return</td><td>Convert</td></tr>
<tr><td>Ctrl+,</td><td>Options</td></tr>
<tr><td>Ctrl+L</td><td>Log</td></tr>
<tr><td>F1</td><td>This page</td></tr>
<tr><td>Ctrl+Q</td><td>Quit</td></tr>
</table>
<h3>Playlist details</h3>
<p>Double click a playlist. Space or P plays, Del removes the track from the playlist,
drag rows to reorder, double click a row for its properties or its Cues cell for the
cue timeline. Cue pads: click to jump or set, right click for a 4 beat loop,
ctrl+click to delete. Changes made there are exported.</p>
<h3>When a CDJ refuses the key</h3>
<ul>
<li>"NO DISK" or nothing shown: the key is NTFS, reformat it FAT32 or exFAT.</li>
<li>Check the log (Ctrl+L) after the export, every skipped track is listed.</li>
</ul>
"""


class Usage(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Usage")
        self.resize(640, 560)
        t = QTextBrowser()
        t.setHtml(USAGE)
        b = QPushButton("Close")
        b.clicked.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(t)
        lay.addWidget(b, 0, Qt.AlignRight)


class About(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        a = f"style='color:{theme.ACCENT}; text-decoration:none'"
        lbl = QLabel(f"<h2>{APP_NAME}</h2><p>Version {VERSION}</p>"
                     f"<p>DJ collection converter: Traktor, rekordbox XML, VirtualDJ, Serato, Mixxx, M3U<br>"
                     f"to Pioneer CDJ keys, rekordbox XML, M3U and Traktor NML.</p>"
                     f"<p>{AUTHOR}<br><a {a} href='https://{WEBSITE}'>{WEBSITE}</a><br>"
                     f"<a {a} href='{GITHUB}'>{GITHUB}</a></p>"
                     f"<p>Traktor Bridge is free and stays free.<br>Tips on Ko-fi help pay for the website hosting.</p>")
        lbl.setTextFormat(Qt.RichText)
        lbl.setOpenExternalLinks(True)
        lbl.setAlignment(Qt.AlignCenter)
        kofi = QPushButton("Support on Ko-fi")
        kofi.setStyleSheet("QPushButton { background: #ff5e5b; color: white; font-weight: bold; padding: 8px 20px; }"
                           "QPushButton:hover { background: #e84f4c; }")
        kofi.setCursor(Qt.PointingHandCursor)
        kofi.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(KOFI)))
        legal = QLabel(f"<span style='color:{theme.FG_MUTED}'>Free for any noncommercial use, PolyForm Noncommercial 1.0.0.<br>"
                       f"Not affiliated with AlphaTheta / Pioneer DJ, Native Instruments,<br>"
                       f"VirtualDJ, Serato or Mixxx.</span>")
        legal.setAlignment(Qt.AlignCenter)
        b = QPushButton("Close")
        b.clicked.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(lbl)
        lay.addWidget(kofi, 0, Qt.AlignCenter)
        lay.addSpacing(8)
        lay.addWidget(legal)
        lay.addWidget(b, 0, Qt.AlignCenter)
