# Benoit Saint-Moulin
# Traktor Bridge : options, collection check, log, usage and about

from __future__ import annotations

import html
import logging
import os
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor
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

from .. import APP_NAME, AUTHOR, SITE, VERSION, WEBSITE, keys
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
        self.scan.finished.connect(self.scan_finished)
        self.scan.finished.connect(self.scan.deleteLater)
        self.scan.start()

    def scan_finished(self):
        if self.scan is self.sender():
            self.scan = None

    def done(self, result):
        if self.scan is not None and self.scan.isRunning():
            self.stats.setText("Waiting for the folder scan to finish before closing.")
            return
        super().done(result)

    def closeEvent(self, event):
        if self.scan is not None and self.scan.isRunning():
            self.stats.setText("Waiting for the folder scan to finish before closing.")
            event.ignore()
            return
        super().closeEvent(event)

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
        t = datetime.now().astimezone().strftime("%H:%M:%S")
        self.text.append(f'<span style="color:{col}">[{t}] {level}: {html.escape(msg)}</span>')

    def copy(self):
        QApplication.clipboard().setText(self.text.toPlainText())

    def save(self):
        name = f"traktor_bridge_log_{datetime.now().astimezone():%Y%m%d_%H%M%S}.txt"
        f, _ = QFileDialog.getSaveFileName(self, "Save log", name, "Text (*.txt)")
        if f:
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(f"{APP_NAME} {VERSION} log, {datetime.now().astimezone():%Y-%m-%d %H:%M}\n\n")
                fh.write(self.text.toPlainText())


# ============================================================
# Usage, About
# ============================================================

USAGE = f"""
<h2>{APP_NAME}</h2>
<p>Traktor Bridge was designed for users of Traktor, the DJ software from Native Instruments. It is a
central hub that lets the leading DJ programs exchange playlists. It works alongside Traktor and does
not replace it.</p>
<h3>Getting started</h3>
<ol>
<li>Open a collection with <b>File &gt; Open project / collection</b>: Traktor <b>collection.nml</b>,
rekordbox <b>XML</b>, VirtualDJ <b>database.xml</b> (or a <b>.vdjfolder</b>), Serato
<b>_Serato_/database V2</b> (or a <b>.crate</b>), Mixxx <b>mixxxdb.sqlite</b> or an
<b>M3U / M3U8</b> playlist.</li>
<li>If the files moved since the collection was written, set the <b>music folder</b>.
Missing tracks are looked up there by file name.</li>
<li>Tick the playlists to export (nothing ticked = everything).</li>
<li>Pick the format and the output folder, then <b>Convert</b>.</li>
</ol>
<h3>Formats</h3>
<ul>
<li><b>CDJ/USB</b>: a complete Pioneer key (Contents, export.pdb, ANLZ waveforms, artwork,
player settings and menu pages). Nothing to import.</li>
<li><b>Rekordbox XML</b>: import it in rekordbox (Preferences &gt; View &gt; rekordbox xml).</li>
<li><b>M3U</b>: one M3U8 per playlist, folders kept as folders.</li>
<li><b>Traktor NML</b>: a collection Traktor can import.</li>
</ul>
<p>For CDJ/USB, export to a folder and copy its content to the root of a FAT32 or exFAT key,
or pick the key itself.</p>
<p>Tracks already on the key are not copied again, but their cues and analysis are rewritten,
so a changed cue replaces the old one.</p>
<p>Hot cues carry the colour of their slot. Hot cue colours and hot loops need a CDJ-2000NXS2,
CDJ-3000 or a recent XDJ.</p>
<h3>Preparing a key</h3>
<p><b>Tools &gt; Verify audio files...</b> checks a loaded collection or a folder, and never
changes the originals. Choose <b>Quick</b> (headers and metadata) or <b>Full</b> (decode the
whole audio stream). You can cancel the scan.</p>
<p>The report separates suspected damage, missing or unreadable files, and formats the decoder
cannot check. A file that decodes cleanly is not proven intact: this is not a checksum, and
some decoders tolerate damage.</p>
<p>Each file is analysed in a separate process, with a time limit and a monitored memory limit
that you can change under <b>Per-file limits</b>. A file that goes over a limit, or crashes the
decoder, is reported as Not checked.</p>
<p><b>Tools &gt; Format a USB drive (FAT32)...</b>, or <b>Format...</b> next to Output, erases a
removable drive and writes one FAT32 partition the players can read. It takes drives formatted
for Mac, Linux, NTFS or exFAT, and drives of more than 32 GB.</p>
<p>Pick the drive, check the label, confirm. Windows asks for administrator rights. System disks
are never listed.</p>
<p>After an export to a removable drive without errors, the app offers to <b>eject</b> it. You
can eject at any time with <b>Tools &gt; Eject the output drive</b> (Ctrl+E).</p>
<h3>Checking a key</h3>
<p>Every export writes <b>traktor_bridge_checksums.json</b> next to it, with a SHA-256 of each
file. <b>Tools &gt; Verify an export</b> reads the key back and lists anything damaged or
missing, before a gig for example.</p>
<p><b>Verify the copy</b> (on by default) does the same right after writing. On Windows the
files are read from the drive and not from the system cache, with an ordinary read where that
is not possible. Each file is compared with the SHA-256 of its source. A copy that differs is
written again by the next export to the same place.</p>
<p>Power loss or a failing drive can still damage an export.</p>
<h3>After CDJ use</h3>
<p>A player can update <b>export.pdb</b> and the ANLZ DAT/EXT/2EX files. When you verify an
export later, readable files at those locations are reported as <b>modified since export,
integrity unconfirmed</b> and not as damaged. The checksum cannot tell whether the player made
the change.</p>
<p>Changed audio or artwork, and missing or unreadable files, are still problems. The check
right after an export stays strict. Back up the key before you export to it again, because the
export replaces what the player changed.</p>
<h3>Generated Pioneer files</h3>
<p>Before they are published, the generated files are validated: export.pdb pages, chains and
row bounds, and DAT/EXT sections, beat, cue and waveform counts and track paths.</p>
<p>Every generated PDB, DAT and EXT file is then read back and compared by SHA-256, even when
Verify the copy is off. Invalid analysis caches are recalculated. None of this replaces a test
on your player.</p>
<h3>Security checks and ClamAV</h3>
<p><b>Privacy: your library stays with you.</b> Traktor Bridge processes audio, playlists,
metadata, cues and analysis on your computer. Nothing is sent to the developer or to a cloud
service: no telemetry, no usage analytics, no automatic log upload, no account. Loading,
analysis, editing, backup and export work offline.</p>
<p>Projects, settings, logs and caches stay on your computer or on the storage you chose.
Website links open in your browser. Check the paths and track names in a log before you share
it for support. Antivirus tools and cloud-synced folders have their own privacy settings.</p>
<p>Collection XML that declares entities or external references is rejected. A packaged build
compares its native files with an embedded seal before it loads the compiled core, and refuses
to start when a seal is missing or invalid. This is not publisher signing or a security
sandbox.</p>
<p>The audio check shows whether <b>clamscan</b> is installed and does nothing else with it: it
never runs it, updates signatures or quarantines files. No antivirus scan happens inside
Traktor Bridge.</p>
<p>Install and update ClamAV yourself, then scan untrusted files outside Traktor Bridge. For
example: <code>clamscan --recursive --infected "D:\\Music"</code></p>
<p>Exit code 0 means no infection found, 1 a detection, 2 an error. This command deletes
nothing.</p>
<p>A clean antivirus report does not make a file safe, and neither does a successful decode.
An antivirus may recognize malicious content in an MP3, but it cannot promise to find hidden,
encrypted or unknown payloads. Traktor Bridge has no MP3 steganography detector, and decoding
or checksums do not prove that no data is hidden.</p>
<p>Restoring a backup is protected against ZIP bombs and malicious archive paths (see ZIP
backup for the limits).</p>
<h3>Quitting</h3>
<p>Quit is blocked while Traktor Bridge is writing, analysing, decoding waveforms or scanning
folders. Wait for the job to finish, or cancel it with its own controls. Closing the window
does not cancel a job.</p>
<p>Do not unplug an output drive while it is being written.</p>
<h3>Shortcuts</h3>
<table cellpadding="3">
<tr><td>Ctrl+O</td><td>Open a project or DJ collection/playlist (automatic detection)</td></tr>
<tr><td>Ctrl+R</td><td>Reload</td></tr>
<tr><td>Ctrl+K</td><td>Check collection, relocate missing files</td></tr>
<tr><td>Ctrl+Shift+V</td><td>Verify an export</td></tr>
<tr><td>Ctrl+Z / Ctrl+Y</td><td>Undo / redo the last playlist, cue, grid or ID tag edit (playlist window), or the cue changes in the Cue Editor</td></tr>
<tr><td>Ctrl+N</td><td>New playlist</td></tr>
<tr><td>Ctrl+S / Ctrl+Shift+S</td><td>Save the project / save it as...</td></tr>
<tr><td>Ctrl+Shift+O</td><td>Open a music folder</td></tr>
<tr><td>Ctrl+E</td><td>Eject the output drive</td></tr>
<tr><td>Ctrl+Return</td><td>Convert</td></tr>
<tr><td>Ctrl+,</td><td>Options</td></tr>
<tr><td>Ctrl+L</td><td>Log</td></tr>
<tr><td>F1</td><td>This page</td></tr>
<tr><td>Ctrl+Q</td><td>Quit</td></tr>
</table>
<h3>Keyboard</h3>
<p>Everything in the playlist window works without the mouse. <b>Tab</b> goes from the player to
the filter, the list and the buttons.</p>
<p><b>Up / Down</b> choose a track, <b>Enter</b> plays it, <b>Space</b> or <b>P</b> pauses.
<b>Ctrl+F</b> goes to the filter. In the filter, <b>Esc</b> empties it and returns to the list,
and <b>Enter</b> returns to the list without emptying it.</p>
<table cellpadding="3">
<tr><td>Alt+Up / Alt+Down</td><td>Move the selected tracks up or down</td></tr>
<tr><td>Ctrl+Left / Ctrl+Right</td><td>Go back or forward 5 seconds</td></tr>
<tr><td>Ctrl+I</td><td>ID Tag of the current track</td></tr>
<tr><td>Ctrl+T</td><td>Cue Editor of the current track</td></tr>
<tr><td>Ctrl+Shift+D</td><td>Remove duplicates</td></tr>
<tr><td>A-H / Shift+A-H</td><td>Set or play a hot cue / delete it</td></tr>
<tr><td>S</td><td>Snap on or off, in the playlist window and the Cue Editor (not while typing in a field)</td></tr>
<tr><td>Ctrl+D</td><td>Cue Editor: detect the tempo and the first beat</td></tr>
<tr><td>Alt+Left / Alt+Right</td><td>Cue Editor: move the first beat by 1 ms (Shift: 10 ms)</td></tr>
<tr><td>Ctrl+B</td><td>Cue Editor: snap on or off, same as S</td></tr>
</table>
<h3>Playlist details</h3>
<p>Double click a playlist to open it. Shift+click selects a range of tracks, Ctrl+click single
ones. <b>Del</b>, <b>Copy track info</b> and drag then act on the selection. <b>Save as
M3U8...</b> and <b>Save as NML...</b> do too, when two or more tracks are selected.</p>
<p>Drag rows to reorder. Double click a row to play it, or its <b>Cues</b> cell to open the Cue
Editor. Use the <b>ID Tag</b> button in the last column to edit metadata, or press Ctrl+I.</p>
<p>The <b>Also in</b> column counts the other loaded playlists that already hold the track (same
file by id or path). Hover it for their names, click the header to sort by it.</p>
<p><b>Undo</b> and <b>Redo</b> (Ctrl+Z / Ctrl+Y) step through reorders, removals, added files, ID
tag applications and cue or grid edits. <b>Reload</b> in the playlist window restores the
playlist as it was when you opened the window, and empties that history. Changes made here are
exported.</p>
<h3>Detect grids</h3>
<p><b>Detect grids</b> analyses the selected tracks, or the tracks without a grid when nothing
is selected. It asks for confirmation before it starts.</p>
<p>A reliable result replaces BPM and first beat. Unreliable results, and tracks you edited
during the analysis, are skipped. Errors name the affected files.</p>
<p><b>Cancel detection</b> applies no results. A single Ctrl+Z undoes the whole completed
batch.</p>
<p>In the Cue Editor, <b>Detect</b> (Ctrl+D) analyses one track and asks you to confirm the
result, with a warning when it is unreliable.</p>
<p>Detection assumes a constant tempo and finds an audible pulse, not necessarily a musical
downbeat. Always check the result against the waveform and the metronome.</p>
<h3>ID Tag</h3>
<p><b>Apply to project</b> changes the metadata in the project and leaves the source audio
untouched.</p>
<p><b>Write tags to audio...</b> is a separate action and asks for confirmation. Stop the file's
preview first. It keeps the first <b>.tb-tags.bak</b> backup, keeps the audio and unrelated DJ
data, and clears the tags whose fields are empty.</p>
<p>Rating stays in the project. Reload and Undo cannot reverse a write to a file.</p>
<h3>Player and waveform</h3>
<p>Click or drag on the wave to move the needle without playing, so you can set cues on a
silent track. Space or P plays.</p>
<p>Ctrl+wheel zooms, and the wheel scrolls when zoomed. The bar under the wave scrubs and moves
the zoom window. A white line marks every minute.</p>
<h3>Cues</h3>
<p>Keys <b>A</b> to <b>H</b> set a hot cue at the needle, playing or not. Pressed again, the key
plays from the cue. Shift+A-H deletes it.</p>
<p>Cue pads: click to jump or set, Ctrl+click to delete (playlist window). Right click a pad for a
1, 2, 4 or 8 beat loop, or to remove the cue.</p>
<p>The Cue Editor has the same keys. <b>Del</b> deletes the selected cue, a double click on the
wave adds a cue, and <b>Add 4-beat loop</b> adds a loop.</p>
<p><b>Drag the letter</b> of a hot cue (or the triangle of a memory cue) on the wave to move it.
Shift snaps it to the beat grid. <b>Esc</b>, or releasing the mouse well outside the wave, puts
the cue back where it was.</p>
<p><b>Ctrl+Z</b> undoes the last cue changes of the track (moves, adds, deletes, edits) and
<b>Ctrl+Y</b> redoes them.</p>
<h3>Grid and metronome</h3>
<p>In the Cue Editor, type a <b>Tempo</b> and a <b>First beat</b>, then click <b>Apply</b>.
<b>Set at cursor</b>, <b>Clear</b> and the Nudge buttons apply at once. Alt+Left / Alt+Right
nudges the first beat by 1 ms (Shift: 10 ms).</p>
<p><b>S</b> toggles snap, and so does <b>Ctrl+B</b> in the Cue Editor. Snap puts new and moved
cues on the nearest beat. Changing the grid does not move existing cues.</p>
<p>Both waveforms zoom down to a 500 ms window, with 1 ms detail loaded on demand.</p>
<p>The metronome has its own volume and an offset from -250 to +250 ms. A negative offset
advances the click and a positive one delays it, which lets you compensate for the latency of
your audio device. The metronome follows playback, seeks and loops, and is muted during
crossfades.</p>
<p>Projects, NML and rekordbox XML keep the edited timing. Pioneer beat times use whole
milliseconds and BPM hundredths. M3U8 carries neither grids nor cues.</p>
<h3>Projects</h3>
<p><b>File &gt; Save the project</b> writes your playlists, folders, track order, paths, cues,
beat grids and export settings in one JSON file. <b>File &gt; Open project / collection</b>
brings everything back. Closing with unsaved changes asks first.</p>
<h3>ZIP backup</h3>
<p><b>Tools &gt; Backup</b> opens a panel to save, restore and verify ZIP archives.</p>
<p><b>Save backup...</b> includes all loaded playlists, their applied edits and the audio files
(once per source file), plus an M3U8 copy of each playlist. Missing audio prevents a complete
backup. Cancelling keeps the previous destination. Unapplied editor fields are not included, and
a backup does not replace saving the working project.</p>
<p>Keep the ZIP and its <b>.zip.sha256</b> file together, with their original names. After
saving, you can verify the new archive at once.</p>
<p><b>Verify backup...</b> checks the whole archive. <b>Load / restore backup...</b> checks it
and the audio hashes, extracts to a new folder without overwriting an existing one, and offers
to open the project. Cancelling removes an unfinished extraction.</p>
<p>Restore refuses an archive with:</p>
<ul>
<li>more than 100,000 entries</li>
<li>more than 1 TiB of expanded data</li>
<li>a central directory larger than 128 MiB</li>
<li>an entry with a compression ratio above 100:1</li>
</ul>
<p>It also refuses encrypted entries, unsupported compression, unsafe paths and Windows device
names. Sizes are checked while extracting, and 1 GiB of free space is kept in reserve. A
matching SHA-256 shows the archive is intact, not who made it.</p>
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
                     f"<p>A central hub for DJ collections, designed for Traktor users. It works alongside Traktor.</p>"
                     f"<p>{AUTHOR}<br><a {a} href='https://{WEBSITE}'>{WEBSITE}</a><br>"
                     f"<a {a} href='https://{SITE}'>{SITE}</a></p>"
                     f"<p>Free, open source (PolyForm Noncommercial 1.0.0).</p>")
        lbl.setTextFormat(Qt.RichText)
        lbl.setOpenExternalLinks(True)
        lbl.setAlignment(Qt.AlignCenter)
        legal = QLabel(f"<span style='color:{theme.FG_MUTED}'>Provided as is, without warranty: no liability for data loss or "
                       f"other damage, back up your files. "
                       f"Not affiliated with AlphaTheta / Pioneer DJ, Native Instruments, VirtualDJ, Serato or Mixxx.</span>")
        legal.setWordWrap(True)
        legal.setAlignment(Qt.AlignCenter)
        b = QPushButton("Close")
        b.clicked.connect(self.accept)
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.addWidget(lbl)
        lay.addSpacing(8)
        lay.addWidget(legal)
        lay.addWidget(b, 0, Qt.AlignCenter)
