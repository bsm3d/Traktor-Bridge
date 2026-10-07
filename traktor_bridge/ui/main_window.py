# Benoit Saint-Moulin
# Traktor Bridge : main window

from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, VERSION, backup, drives, export, settings, sources
from ..export import manifest
from ..export.files import Cancelled, Report
from ..model import Node, playlists, prune, unique_tracks
from ..sources import project
from . import theme
from .audiocheck import AudioCheck
from .backup import BackupPanel
from .details import PlaylistWindow
from .dialogs import About, CheckCollection, LogWindow, Options, Usage
from .formatter import FormatDialog
from .player import Engine
from .tageditor import TagEditor
from .waveform import Loader
from .worker import Job, has_active_jobs, stop_all
from .zoomwave import duration_text

log = logging.getLogger(__name__)


def playlist_duration(node: Node) -> str:
    return duration_text(sum(track.duration for track in node.tracks))


def fs_type(path: str) -> str:
    """File system of the drive holding path, Windows only, '' elsewhere."""
    if sys.platform != "win32":
        return ""
    import ctypes
    root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    buf = ctypes.create_unicode_buffer(32)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(root, None, 0, None, None, None, buf, 32)
    return buf.value if ok else ""


def load_job(path: str, root: str, progress=None, cancel=None) -> tuple[list[Node], int, dict]:
    """Load nodes, missing-file count and project settings off the GUI thread."""

    def cb(pct, msg):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if progress:
            progress(pct, msg)

    extra: dict = {}
    if sources.detect(path) == "project":
        nodes, extra = project.read(path, root, cb)
    else:
        nodes = sources.load(path, root, cb)
    cb(100, "Checking files...")
    missing = 0
    for i, t in enumerate(unique_tracks(nodes)):
        if i % 500 == 0:
            cb(100, "Checking files...")
        missing += not os.path.isfile(t.path)
    return nodes, missing, extra


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict, logwin: LogWindow):
        super().__init__()
        self.cfg, self.logwin = cfg, logwin
        self.nodes: list[Node] = []
        self.project = ""          # the project file the playlists were opened from or saved to
        self.dirty = False
        self.job: Job | None = None
        self.again = False
        self.pending_backup_verify = ""
        self.backup_panel = None
        self.engine = Engine()
        self.engine.set_volume(cfg["volume"] / 100)
        self.loader = Loader(self)
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(760, 700)
        self.build_menu()

        paths = QGroupBox("Source")
        g = QGridLayout(paths)
        self.src = QLineEdit(cfg["source_path"])
        self.src.setPlaceholderText("Traktor .nml, rekordbox .xml, VirtualDJ database.xml, Serato database V2, Mixxx, M3U")
        self.root = QLineEdit(cfg["music_root"])
        self.root.setPlaceholderText("optional: where the files are now, if they moved")
        self.out = QLineEdit(cfg["output_path"])
        self.out.setPlaceholderText("export folder or USB key")
        rows = ((self.src, "Collection / project", self.open_source), (self.root, "Music folder", self.pick_root),
                (self.out, "Output", self.pick_out))
        for i, (edit, name, fn) in enumerate(rows):
            b = QPushButton("Browse...")
            b.clicked.connect(fn)
            g.addWidget(QLabel(name), i, 0)
            g.addWidget(edit, i, 1)
            g.addWidget(b, i, 2)
        reload = QPushButton("Reload")
        reload.clicked.connect(self.reload)
        g.addWidget(reload, 0, 3)
        fmt_btn = QPushButton("Format...")
        fmt_btn.setToolTip("Erase a USB key and format it as FAT32 for the Pioneer players")
        fmt_btn.clicked.connect(self.format_usb)
        g.addWidget(fmt_btn, 2, 3)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Playlists", "Tracks", "Duration"])
        self.tree.setColumnWidth(0, 520)
        self.tree.setColumnWidth(1, 90)
        self.tree.itemDoubleClicked.connect(self.details)
        self.tree.itemChanged.connect(self.selection_changed)
        self.info = QLabel("No collection loaded")
        self.info.setStyleSheet(f"color: {theme.FG_MUTED};")

        opts = QHBoxLayout()
        self.fmt = QComboBox()
        self.fmt.addItems(settings.EXPORTS)
        self.fmt.setCurrentText(cfg["export_format"])
        self.fmt.currentTextChanged.connect(self.format_changed)
        self.copy = QCheckBox("Copy audio")
        self.copy.setChecked(cfg["copy_music"])
        self.verify = QCheckBox("Verify the copy (SHA-256)")
        self.verify.setToolTip("After the export, read every file back from the USB key (not from the system cache) and compare\n"
                               "its SHA-256 to the source: all the tracks are there and intact. Takes about as long\n"
                               "as the copy. Tools > Verify an export does it again later.")
        self.verify.setChecked(cfg["verify_copy"])
        opts.addWidget(QLabel("Export"))
        opts.addWidget(self.fmt)
        opts.addWidget(self.copy)
        opts.addWidget(self.verify)
        opts.addStretch(1)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.status = QLabel("Ready")
        self.go = QPushButton("CONVERT")
        self.go.setObjectName("go")
        self.go.clicked.connect(self.convert)
        self.stop = QPushButton("Cancel")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.cancel)
        run = QHBoxLayout()
        run.addWidget(self.status, 1)
        run.addWidget(self.stop)
        run.addWidget(self.go)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(paths)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.info)
        lay.addLayout(opts)
        lay.addWidget(self.bar)
        lay.addLayout(run)
        self.setCentralWidget(w)
        self.format_changed(self.fmt.currentText())

        if cfg["auto_load"]:
            if not self.src.text():
                self.src.setText(settings.default_collection())
            if self.src.text() and os.path.exists(self.src.text()):
                QTimer.singleShot(150, self.reload)

    # ---- menus

    def build_menu(self):
        mb = self.menuBar()
        items = {
            "&File": [("&Open project / collection...", "Ctrl+O", self.open_source), ("&New playlist...", "Ctrl+N", self.new_playlist),
                      ("Open a music &folder...", "Ctrl+Shift+O", self.open_folder),
                      ("&Save the project", "Ctrl+S", self.save_project),
                      ("Save the project &as...", "Ctrl+Shift+S", lambda: self.save_project(True)),
                      None, ("Convert", "Ctrl+Return", self.convert), None, ("E&xit", "Ctrl+Q", self.close)],
            "&Tools": [("&Reload", "Ctrl+R", self.reload),
                      ("Check collection...", "Ctrl+K", self.check),
                      ("Verify audio files...", "", self.check_audio),
                      ("&Verify an export...", "Ctrl+Shift+V", self.verify_export), None,
                      ("Backup", "", self.open_backup), None,
                      ("&Format a USB drive (FAT32)...", None, self.format_usb),
                      ("&Eject the output drive", "Ctrl+E", lambda: self.offer_eject(self.out.text().strip(), False))],
            "&Options": [("&Preferences...", "Ctrl+,", self.options)],
            "&Help": [("View &log", "Ctrl+L", self.show_log),
                      ("&Usage", "F1", lambda: self.show_dialog(Usage)),
                      ("&About", None, lambda: self.show_dialog(About))],
        }
        for title, acts in items.items():
            m = mb.addMenu(title)
            for a in acts:
                if a is None:
                    m.addSeparator()
                    continue
                act = QAction(a[0], self)
                if a[1]:
                    act.setShortcut(QKeySequence(a[1]))
                act.triggered.connect(a[2])
                m.addAction(act)

    # ---- paths

    def open_source(self):
        start = os.path.dirname(self.src.text()) or settings.default_collection()
        f, _ = QFileDialog.getOpenFileName(
            self, "Open project / collection", start,
            "Projects and DJ collections (*.json *.nml *.xml *.sqlite *.db *.m3u *.m3u8 *.vdjfolder *.crate database*);;"
            "Traktor Bridge projects (*.json);;"
            "DJ collections and playlists (*.nml *.xml *.sqlite *.db *.m3u *.m3u8 *.vdjfolder *.crate database*);;All (*)")
        if f:
            if not self.ask_discard():
                return
            self.src.setText(f)
            self.reload()

    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Open a music folder", self.src.text() or self.root.text())
        if d and self.ask_discard():
            self.src.setText(d)
            self.reload()

    def new_playlist(self):
        name, ok = QInputDialog.getText(self, "New playlist", "Name")
        name = name.strip()
        if not ok or not name:
            return
        n = Node("playlist", name)
        self.nodes.append(n)
        self.set_dirty(True)
        self.fill_tree()
        self.info.setText(f"{sum(1 for _ in playlists(self.nodes))} playlists, {len(unique_tracks(self.nodes))} tracks")
        for it in self.tree.findItems(name, Qt.MatchExactly | Qt.MatchRecursive):
            if it.data(0, Qt.UserRole) is n:
                self.details(it)
                break

    # ---- project

    def set_dirty(self, on: bool):
        self.dirty = on
        name = os.path.basename(self.project) if self.project else ""
        self.setWindowTitle(f"{APP_NAME} {VERSION}" + (f" - {name}" if name else "") + (" *" if on else ""))

    def open_project(self):
        self.open_source()

    def save_project(self, ask: bool = False) -> bool:
        if not self.nodes:
            QMessageBox.information(self, "Save the project", "There is nothing to save yet: open a collection "
                                    "or create a playlist first.")
            return False
        path = self.project
        if ask or not path:
            start = path or os.path.join(os.path.expanduser("~"), "Documents", "playlists.json")
            path, _ = QFileDialog.getSaveFileName(self, "Save the project", start, "Traktor Bridge projects (*.json)")
            if not path:
                return False
            if not path.lower().endswith(".json"):
                path += ".json"
        try:
            project.save(path, self.nodes, self.sync())
        except OSError as e:
            QMessageBox.critical(self, "Save the project", f"Cannot write {path}:\n{e}")
            return False
        self.project = path
        self.set_dirty(False)
        self.status.setText(f"Project saved: {path}")
        log.info("Project saved: %s", path)
        return True

    def open_backup(self):
        panel = BackupPanel(self)
        self.backup_panel = panel
        try:
            panel.exec()
        finally:
            self.backup_panel = None
            panel.deleteLater()

    def backup_project(self):
        if self.job is not None:
            QMessageBox.information(self, "ZIP backup", "Wait for the current job to finish.")
            return
        if not self.nodes:
            QMessageBox.information(self, "ZIP backup", "Open a collection or create a playlist first.")
            return
        if any(editor.job is not None
               for window in self.findChildren(PlaylistWindow)
               for editor in window.findChildren(TagEditor)):
            QMessageBox.warning(self, "ZIP backup", "Wait for audio-tag writing to finish before backing up.")
            return
        answer = QMessageBox.question(
            self, "ZIP backup",
            "Back up all loaded playlists, current applied project edits and their audio files?\n\n"
            "This includes unticked playlists. Audio files are included once. Unapplied editor fields "
            "are not included. Missing audio prevents a complete backup.\n\n"
            "After extracting the ZIP, open project.json to restore the project. "
            "The backup may need as much disk space as the audio collection.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        name = os.path.splitext(self.project)[0] + "-backup.zip" if self.project else "TraktorBridge-backup.zip"
        path, _ = QFileDialog.getSaveFileName(self, "ZIP backup", name, "ZIP archives (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        document = project.dump(self.nodes, self.sync())
        self.busy(True)
        self.status.setText("Preparing ZIP backup...")
        self.job = Job(backup.create, path, document)
        self.job.progress.connect(self.on_progress)
        self.job.done.connect(self.backup_finished)
        self.job.failed.connect(self.backup_failed)
        self.job.cancelled.connect(lambda: self.status.setText("Backup cancelled; destination unchanged"))
        self.job.finished.connect(self.job_over)
        self.job.start()

    def backup_finished(self, result):
        self.status.setText("ZIP backup completed")
        answer = QMessageBox.question(self, "ZIP backup completed",
                                f"{result['playlists']} playlists and {result['audio']} audio files backed up.\n"
                                f"{result['size'] / 1e9:.2f} GB\n\n{result['path']}\n\n"
                                f"SHA-256: {result['sha256']}\nChecksum file: {result['checksum_path']}\n\n"
                                "Verify this backup now?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer == QMessageBox.Yes:
            if self.job is None:
                QTimer.singleShot(0, lambda: self.start_backup_verify(result["path"]))
            else:
                self.pending_backup_verify = result["path"]

    def backup_failed(self, message):
        self.status.setText("ZIP backup failed; see error details")
        QMessageBox.critical(self, "ZIP backup failed", message)

    def verify_backup(self):
        self.backup_action(False)

    def restore_backup(self):
        self.backup_action(True)

    def backup_action(self, restoring, path=""):
        if self.job is not None:
            QMessageBox.information(self, "ZIP backup", "Wait for the current job to finish.")
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Restore ZIP backup" if restoring else "Verify ZIP backup",
                                                "", "ZIP archives (*.zip)")
        if not path:
            return
        args = (path,)
        if restoring:
            parent = QFileDialog.getExistingDirectory(self, "Parent folder for restoration")
            if not parent:
                return
            name, ok = QInputDialog.getText(self, "Restoration folder", "New folder name:",
                                           text=os.path.splitext(os.path.basename(path))[0] + "-restored")
            if not ok:
                return
            if not name or name != backup.safe_name(name) or name in (".", ".."):
                QMessageBox.warning(self, "Restoration folder", "Use a simple folder name without path separators.")
                return
            args += (os.path.join(parent, name),)
        self.busy(True)
        self.status.setText("Verifying ZIP backup...")
        self.job = Job(backup.restore if restoring else backup.verify, *args)
        self.job.progress.connect(self.on_progress)
        self.job.done.connect(self.restore_finished if restoring else self.verify_backup_finished)
        self.job.failed.connect(self.backup_failed)
        self.job.cancelled.connect(lambda: self.status.setText("Operation cancelled"))
        self.job.finished.connect(self.job_over)
        self.job.start()

    def verify_backup_finished(self, checksum):
        self.bar.setValue(100)
        self.status.setText("ZIP checksum verified")
        QMessageBox.information(self, "ZIP verified", f"The ZIP matches its SHA-256 checksum.\n\n{checksum}")

    def restore_finished(self, path):
        self.status.setText("Backup restored")
        answer = QMessageBox.question(self, "Backup restored",
                                      f"Project restored at:\n{path}\n\nOpen it now?",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer == QMessageBox.Yes and self.ask_discard():
            self.root.clear()
            self.out.clear()
            self.src.setText(path)
            if self.job is None:
                QTimer.singleShot(0, self.reload)
            else:
                self.again = True

    def ask_discard(self) -> bool:
        """True when it is fine to replace or close the playlists: saved, or given up."""
        if not (self.dirty and self.nodes):
            return True
        r = QMessageBox.question(self, "Unsaved work", "The playlists changed since the last save. Save the project?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save_project()
        return r == QMessageBox.Discard

    def apply_project(self, path: str, saved: dict):
        self.project = path
        for key, widget in (("music_root", self.root), ("output_path", self.out)):
            if saved.get(key):
                widget.setText(str(saved[key]))
        if saved.get("export_format") in settings.EXPORTS:
            self.fmt.setCurrentText(saved["export_format"])
        for key, box in (("copy_music", self.copy), ("verify_copy", self.verify)):
            if isinstance(saved.get(key), bool) and box.isEnabled():
                box.setChecked(saved[key])
        for key in ("key_format", "waveform_color", "crossfade"):
            if key in saved:
                self.cfg[key] = saved[key]

    def pick_root(self):
        d = QFileDialog.getExistingDirectory(self, "Music folder", self.root.text())
        if d:
            self.root.setText(d)
            if self.nodes:
                self.reload()

    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.out.text())
        if d:
            self.out.setText(d)

    def format_usb(self):
        dlg = FormatDialog(self)
        dlg.formatted.connect(self.use_formatted)
        dlg.exec()
        dlg.deleteLater()

    def use_formatted(self, path: str):
        if self.out.text().strip() != path:
            r = QMessageBox.question(self, "Output", f"Use {path} as the export folder?")
            if r == QMessageBox.Yes:
                self.out.setText(path)

    def format_changed(self, fmt: str):
        cdj = fmt == "CDJ/USB"
        self.copy.setEnabled(not cdj)
        if cdj:
            self.copy.setChecked(True)

    # ---- loading

    def busy(self, on: bool):
        self.go.setEnabled(not on)
        self.stop.setEnabled(on)
        self.tree.setEnabled(not on)

    def reload(self):
        path = self.src.text().strip()
        if not path or not os.path.exists(path):
            return
        if self.job is not None:
            # asked while loading (music folder picked from the missing files prompt)
            self.again = True
            return
        for editor in self.findChildren(PlaylistWindow):
            if not editor.close():
                self.status.setText("Wait for playlist editing operations to finish before reloading.")
                return
        self.busy(True)
        self.status.setText("Loading...")
        self.job = Job(load_job, path, self.root.text().strip())
        self.job.progress.connect(self.on_progress)
        self.job.done.connect(self.loaded)
        self.job.failed.connect(self.load_failed)
        self.job.cancelled.connect(lambda: self.status.setText("Loading cancelled"))
        self.job.finished.connect(self.job_over)
        self.job.start()

    def loaded(self, res: tuple[list[Node], int, dict]):
        nodes, missing, saved = res
        self.nodes = nodes
        if sources.detect(self.src.text().strip()) == "project":
            self.apply_project(self.src.text().strip(), saved)
        else:
            self.project = ""
        self.set_dirty(False)
        self.fill_tree()
        tracks = unique_tracks(nodes)
        self.info.setText(f"{sum(1 for _ in playlists(nodes))} playlists, {len(tracks)} tracks"
                          + (f", {missing} missing files" if missing else ""))
        self.status.setText("Ready")
        self.bar.setValue(0)
        log.info("Loaded %s: %d tracks, %d missing", self.src.text(), len(tracks), missing)
        self.cfg["source_path"] = self.src.text()
        if missing and not self.root.text():
            QTimer.singleShot(0, lambda: self.ask_root(missing, len(tracks)))

    def ask_root(self, missing: int, total: int):
        r = QMessageBox.question(self, "Missing files",
                                 f"{missing} of {total} files are not where the collection says.\n"
                                 "Pick the folder where your music is now?")
        if r == QMessageBox.Yes:
            self.pick_root()

    def load_failed(self, msg: str):
        self.status.setText("Loading failed")
        QMessageBox.critical(self, "Cannot read the collection", msg)

    def job_over(self):
        self.job.deleteLater()
        self.job = None
        self.busy(False)
        if self.pending_backup_verify:
            path, self.pending_backup_verify = self.pending_backup_verify, ""
            QTimer.singleShot(0, lambda: self.start_backup_verify(path))
        if self.again:
            self.again = False
            self.reload()

    def start_backup_verify(self, path):
        self.backup_action(False, path)
        if self.job is not None and self.backup_panel is not None:
            self.backup_panel.watch(self.job)

    def fill_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()

        def add(parent, nodes):
            for n in nodes:
                count = "" if n.is_folder else str(len(n.tracks))
                name = n.name + ("  (smart)" if n.kind == "smartlist" else "")
                duration = "" if n.is_folder else playlist_duration(n)
                it = QTreeWidgetItem([name, count, duration])
                it.setData(0, Qt.UserRole, n)
                it.setCheckState(0, Qt.Unchecked)
                if n.is_folder:
                    it.setFlags(it.flags() | Qt.ItemIsAutoTristate)
                    add(it, n.children)
                if parent is None:
                    self.tree.addTopLevelItem(it)
                else:
                    parent.addChild(it)

        add(None, self.nodes)
        self.tree.expandToDepth(0)
        self.tree.blockSignals(False)

    def selection_changed(self, *_):
        sel = self.selected()
        n = len(unique_tracks(sel)) if sel is not self.nodes else len(unique_tracks(self.nodes))
        self.status.setText(f"{n} tracks selected" if sel is not self.nodes else "Everything selected")

    def selected(self) -> list[Node]:
        keep = set()

        def walk(it):
            for i in range(it.childCount()):
                c = it.child(i)
                n = c.data(0, Qt.UserRole)
                if not n.is_folder and c.checkState(0) == Qt.Checked:
                    keep.add(id(n))
                walk(c)

        walk(self.tree.invisibleRootItem())
        return prune(self.nodes, keep) if keep else self.nodes

    # ---- windows

    def details(self, it, _col=0):
        n = it.data(0, Qt.UserRole)
        if n.is_folder:
            return
        w = PlaylistWindow(n, self.engine, self.loader, self.cfg, self.root.text().strip(), self,
                           others=lambda: list(playlists(self.nodes)))
        w.edited.connect(lambda: self.playlist_edited(n))
        w.show()

    def playlist_edited(self, node):
        self.set_dirty(True)
        for item in self.tree.findItems("", Qt.MatchContains | Qt.MatchRecursive):
            if item.data(0, Qt.UserRole) is node:
                item.setText(1, str(len(node.tracks)))
                item.setText(2, playlist_duration(node))
                break

    def check(self):
        if not self.nodes:
            QMessageBox.information(self, "Check collection", "Load a collection first.")
            return
        d = CheckCollection(self.nodes, self.root.text().strip(), self)
        d.relocated.connect(lambda: self.root.setText(d.root))
        try:
            d.exec()
        finally:
            d.deleteLater()

    def check_audio(self):
        panel = AudioCheck(self.nodes, self.root.text().strip(), self)
        try:
            panel.exec()
        finally:
            panel.deleteLater()

    def options(self):
        d = Options(self.cfg, self)
        if d.exec():
            self.fmt.setCurrentText(self.cfg["export_format"])
            self.copy.setChecked(self.cfg["copy_music"])
            self.verify.setChecked(self.cfg["verify_copy"])
            self.engine.set_volume(self.cfg["volume"] / 100)
            logging.getLogger().setLevel(self.cfg["log_level"])
            settings.save(self.sync())
        d.deleteLater()

    def show_log(self):
        self.logwin.show()
        self.logwin.raise_()

    def show_dialog(self, dialog_type):
        dialog = dialog_type(self)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    # ---- export

    def sync(self) -> dict:
        self.cfg.update(source_path=self.src.text(), music_root=self.root.text(), output_path=self.out.text(),
                        export_format=self.fmt.currentText(), copy_music=self.copy.isChecked(),
                        verify_copy=self.verify.isChecked())
        return self.cfg

    def convert(self):
        if self.job is not None:
            return
        if not self.nodes:
            QMessageBox.information(self, "Convert", "Load a collection first.")
            return
        out = self.out.text().strip()
        if not out:
            self.pick_out()
            out = self.out.text().strip()
            if not out:
                return
        cfg = self.sync()
        fmt = cfg["export_format"]
        # Contents and PIONEER must sit side by side at the key root
        if fmt == "CDJ/USB" and os.path.basename(os.path.normpath(out)).lower() in ("contents", "pioneer"):
            out = os.path.dirname(os.path.normpath(out))
            self.out.setText(out)
            cfg["output_path"] = out
            log.info("output moved up to the key root: %s", out)
        if fmt == "CDJ/USB" and fs_type(out).upper() == "NTFS":
            r = QMessageBox.warning(self, "NTFS drive",
                                    "The players don't read NTFS keys (they show NO DISK).\n"
                                    "Export anyway? You can copy the result to a FAT32 or exFAT key,\n"
                                    "or use Format... next to Output to make this key FAT32 (it erases it).",
                                    QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        settings.save(cfg)
        nodes = self.selected()
        log.info("Export %s to %s", fmt, out)
        self.busy(True)
        self.job = Job(export.run, fmt, nodes, out, dict(cfg))
        self.job.progress.connect(self.on_progress)
        self.job.done.connect(self.exported)
        self.job.failed.connect(lambda m: QMessageBox.critical(self, "Export failed", m))
        self.job.cancelled.connect(lambda: self.status.setText("Cancelled"))
        self.job.finished.connect(self.job_over)
        self.job.start()

    def cancel(self):
        if self.job is not None:
            self.job.stop.set()
            self.status.setText("Cancelling...")

    def on_progress(self, pct: int, msg: str):
        self.bar.setValue(pct)
        self.status.setText(msg)

    def exported(self, rep: Report):
        for m in rep.missing:
            log.warning("missing, not exported: %s", m)
        for e in rep.errors:
            log.error(e)
        self.bar.setValue(100)
        lines = [f"{rep.tracks - len(rep.missing)} tracks exported to\n{rep.path}"]
        shown = 8
        if rep.cached:
            lines.append(f"{rep.cached} analyses reused from the cache")
        if rep.missing:
            lines.append(f"{len(rep.missing)} missing files skipped (see the log)")
        if rep.errors:
            lines.append(f"{len(rep.errors)} errors:\n" + "\n".join(rep.errors[:shown])
                         + (f"\n... and {len(rep.errors) - shown} more (see the log)" if len(rep.errors) > shown else "")
                         + "\n\nExport again to the same place: only the files that differ are written again.")
        elif rep.manifest:
            lines.append(f"Integrity checked: all {rep.verified} files read back from the drive match their "
                         f"SHA-256 ({rep.verified_size / 1e9:.2f} GB)" if self.cfg["verify_copy"]
                         else "Checksums saved, Tools > Verify an export checks the key later")
        self.status.setText("Done")
        box = QMessageBox.warning if rep.errors or rep.missing else QMessageBox.information
        box(self, "Export finished", "\n\n".join(lines))
        if not rep.errors:
            self.offer_eject(rep.path)

    # ---- eject

    def offer_eject(self, path: str, ask: bool = True):
        """Looks for the removable drive holding path and offers to eject it. From the menu (ask False)
        it also says so when there is none."""
        if not path:
            return
        self.status.setText("Looking for the drive...")
        job = Job(drives.drive_for, path)
        job.done.connect(lambda d: self.eject_found(d, ask))
        job.failed.connect(lambda m: self.eject_failed(m, ask))
        job.start()

    def eject_found(self, d, ask: bool):
        self.status.setText("Done")
        if d is None:
            if not ask:
                QMessageBox.information(self, "Eject", "The output is not on a removable drive.")
            return
        r = QMessageBox.question(self, "Eject the drive", f"Eject {d.title} now?\nYou can unplug it afterwards.",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r != QMessageBox.Yes:
            return
        self.status.setText("Ejecting...")
        job = Job(drives.eject, d)
        job.done.connect(self.ejected)
        job.failed.connect(lambda m: self.eject_failed(m, False))
        job.start()

    def ejected(self, title: str):
        self.status.setText("Ejected")
        QMessageBox.information(self, "Eject", f"{title} can be unplugged.")

    def eject_failed(self, msg: str, ask: bool):
        self.status.setText("Done")
        log.warning("eject: %s", msg)
        if not ask:
            QMessageBox.warning(self, "Eject", msg)

    # ---- verification

    def verify_export(self):
        if self.job is not None:
            return
        start = self.out.text().strip()
        d = QFileDialog.getExistingDirectory(self, "Export to verify (the key or the output folder)", start)
        if not d:
            return
        if not os.path.isfile(os.path.join(d, manifest.NAME)):
            QMessageBox.information(self, "Verify an export",
                                    f"No checksums in {d}.\nExport to it once with this version to create them.")
            return
        self.busy(True)
        self.job = Job(manifest.verify, d, allow_player_changes=True)
        self.job.progress.connect(self.on_progress)
        self.job.done.connect(self.verified)
        self.job.failed.connect(lambda m: QMessageBox.critical(self, "Verification failed", m))
        self.job.cancelled.connect(lambda: self.status.setText("Verification cancelled"))
        self.job.finished.connect(self.job_over)
        self.job.start()

    def verified(self, chk: manifest.Check):
        self.bar.setValue(100)
        log.info("Verify %s: %s", chk.base, chk.summary())
        for p in chk.damaged:
            log.error("damaged: %s", p)
        for p in chk.missing:
            log.error("missing: %s", p)
        for p in chk.modified:
            log.warning("modified since export, integrity unconfirmed: %s", p)
        problems = bool(chk.error or chk.damaged or chk.missing)
        self.status.setText("Verified" if chk.good else
                            "Verification found problems" if problems else
                            "Pioneer files modified since export; integrity unconfirmed")
        if chk.good:
            QMessageBox.information(self, "Verify an export",
                                    chk.report())
            return
        show_report = QMessageBox.warning if problems else QMessageBox.information
        show_report(self, "Verify an export", chk.report())

    def closeEvent(self, e):
        if (has_active_jobs() or self.job is not None
                or self.loader.th is not None or self.loader.hi_th is not None
                or self.loader.queue or self.loader.hi_queue
                or any(panel.scan is not None for panel in self.findChildren(CheckCollection))):
            self.status.setText("Cannot quit while writing, analysing or scanning. "
                                "Wait for completion or use the operation's Cancel button.")
            e.ignore()
            return
        if not self.ask_discard():
            e.ignore()
            return
        if self.cfg["confirm_exit"] and QMessageBox.question(self, "Quit", f"Quit {APP_NAME}?") != QMessageBox.Yes:
            e.ignore()
            return
        if not stop_all():
            self.status.setText("Waiting for background operations to stop. Try closing again when they finish.")
            e.ignore()
            return
        if not self.loader.stop():
            self.status.setText("Waiting for waveform decoding to finish. Try closing again when it finishes.")
            e.ignore()
            return
        self.engine.close()
        settings.save(self.sync())
        super().closeEvent(e)
