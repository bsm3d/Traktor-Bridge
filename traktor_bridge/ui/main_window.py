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

from .. import APP_NAME, VERSION, export, settings, sources
from ..export import manifest
from ..export.files import Cancelled, Report
from ..model import Node, playlists, prune, unique_tracks
from . import theme
from .details import PlaylistWindow
from .dialogs import About, CheckCollection, LogWindow, Options, Usage, import_reference
from .player import Engine
from .waveform import Loader
from .worker import Job

log = logging.getLogger(__name__)


def fs_type(path: str) -> str:
    """File system of the drive holding path, Windows only, '' elsewhere."""
    if sys.platform != "win32":
        return ""
    import ctypes
    root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    buf = ctypes.create_unicode_buffer(32)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(root, None, 0, None, None, None, buf, 32)
    return buf.value if ok else ""


def load_job(path: str, root: str, progress=None, cancel=None) -> tuple[list[Node], int]:
    """Collection and its count of missing files, both off the GUI thread
    (a stat per track freezes the window on a slow or network drive)."""

    def cb(pct, msg):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if progress:
            progress(pct, msg)

    nodes = sources.load(path, root, cb)
    cb(100, "Checking files...")
    missing = 0
    for i, t in enumerate(unique_tracks(nodes)):
        if i % 500 == 0:
            cb(100, "Checking files...")
        missing += not os.path.isfile(t.path)
    return nodes, missing


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict, logwin: LogWindow):
        super().__init__()
        self.cfg, self.logwin = cfg, logwin
        self.nodes: list[Node] = []
        self.job: Job | None = None
        self.again = False
        self.engine = Engine()
        self.engine.set_volume(cfg["volume"] / 100)
        self.loader = Loader(self)
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(760, 700)
        self.build_menu()

        paths = QGroupBox("Collection")
        g = QGridLayout(paths)
        self.src = QLineEdit(cfg["source_path"])
        self.src.setPlaceholderText("Traktor .nml, rekordbox .xml, VirtualDJ database.xml, Serato database V2, Mixxx, M3U")
        self.root = QLineEdit(cfg["music_root"])
        self.root.setPlaceholderText("optional: where the files are now, if they moved")
        self.out = QLineEdit(cfg["output_path"])
        self.out.setPlaceholderText("export folder or USB key")
        rows = ((self.src, "Collection", self.open_source), (self.root, "Music folder", self.pick_root),
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

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Playlists", "Tracks"])
        self.tree.setColumnWidth(0, 520)
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
        self.verify = QCheckBox("Verify after export")
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
            "&File": [("&Open collection...", "Ctrl+O", self.open_source), ("&New playlist...", "Ctrl+N", self.new_playlist),
                      ("Open a music &folder...", "Ctrl+Shift+O", self.open_folder), ("&Reload", "Ctrl+R", self.reload),
                      ("Check collection...", "Ctrl+K", self.check),
                      ("&Verify an export...", "Ctrl+Shift+V", self.verify_export), None,
                      ("Convert", "Ctrl+Return", self.convert), None, ("E&xit", "Ctrl+Q", self.close)],
            "&Options": [("&Preferences...", "Ctrl+,", self.options)],
            "&Help": [("View &log", "Ctrl+L", self.show_log), ("&Usage", "F1", lambda: Usage(self).exec()),
                      ("&About", None, lambda: About(self).exec())],
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
        f, _ = QFileDialog.getOpenFileName(self, "Open collection", start,
                                           "Collections (*.nml *.xml *.sqlite *.db *.m3u *.m3u8 *.vdjfolder *.crate database*);;All (*)")
        if f:
            self.src.setText(f)
            self.reload()

    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Open a music folder", self.src.text() or self.root.text())
        if d:
            self.src.setText(d)
            self.reload()

    def new_playlist(self):
        name, ok = QInputDialog.getText(self, "New playlist", "Name")
        name = name.strip()
        if not ok or not name:
            return
        n = Node("playlist", name)
        self.nodes.append(n)
        self.fill_tree()
        self.info.setText(f"{sum(1 for _ in playlists(self.nodes))} playlists, {len(unique_tracks(self.nodes))} tracks")
        # open it right away: drop files or folders on its list, or Add files
        for it in self.tree.findItems(name, Qt.MatchExactly | Qt.MatchRecursive):
            if it.data(0, Qt.UserRole) is n:
                self.details(it)
                break

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
        self.busy(True)
        self.status.setText("Loading...")
        self.job = Job(load_job, path, self.root.text().strip())
        self.job.progress.connect(self.on_progress)
        self.job.done.connect(self.loaded)
        self.job.failed.connect(self.load_failed)
        self.job.cancelled.connect(lambda: self.status.setText("Loading cancelled"))
        self.job.finished.connect(self.job_over)
        self.job.start()

    def loaded(self, res: tuple[list[Node], int]):
        nodes, missing = res
        self.nodes = nodes
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
        if self.again:
            self.again = False
            self.reload()

    def fill_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()

        def add(parent, nodes):
            for n in nodes:
                count = "" if n.is_folder else str(len(n.tracks))
                name = n.name + ("  (smart)" if n.kind == "smartlist" else "")
                it = QTreeWidgetItem([name, count])
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
        w = PlaylistWindow(n, self.engine, self.loader, self.cfg, self.root.text().strip(), self)
        w.edited.connect(lambda: it.setText(1, str(len(n.tracks))))
        w.show()

    def check(self):
        if not self.nodes:
            QMessageBox.information(self, "Check collection", "Load a collection first.")
            return
        d = CheckCollection(self.nodes, self.root.text().strip(), self)
        d.relocated.connect(lambda: self.root.setText(d.root))
        d.exec()

    def options(self):
        d = Options(self.cfg, self)
        if d.exec():
            self.fmt.setCurrentText(self.cfg["export_format"])
            self.copy.setChecked(self.cfg["copy_music"])
            self.verify.setChecked(self.cfg["verify_copy"])
            self.engine.set_volume(self.cfg["volume"] / 100)
            logging.getLogger().setLevel(self.cfg["log_level"])
            settings.save(self.sync())

    def show_log(self):
        self.logwin.show()
        self.logwin.raise_()

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
        if fmt == "CDJ/USB":
            from ..export.cdj import reference
            if not reference.ready() and not import_reference(self):
                return
        if fmt == "CDJ/USB" and fs_type(out).upper() == "NTFS":
            r = QMessageBox.warning(self, "NTFS drive",
                                    "The players don't read NTFS keys (they show NO DISK).\n"
                                    "Export anyway? You can copy the result to a FAT32 or exFAT key.",
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
        if rep.cached:
            lines.append(f"{rep.cached} analyses reused from the cache")
        if rep.missing:
            lines.append(f"{len(rep.missing)} missing files skipped (see the log)")
        if rep.errors:
            lines.append(f"{len(rep.errors)} errors (see the log)")
        elif rep.manifest:
            lines.append("Every file read back and checked" if self.cfg["verify_copy"]
                         else "Checksums saved, File > Verify an export checks the key later")
        self.status.setText("Done")
        box = QMessageBox.warning if rep.errors or rep.missing else QMessageBox.information
        box(self, "Export finished", "\n\n".join(lines))

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
        self.job = Job(manifest.verify, d)
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
        self.status.setText("Verified" if chk.good else "Verification found problems")
        if chk.good:
            QMessageBox.information(self, "Verify an export",
                                    f"{chk.summary()}.\n\nExport of {chk.created.replace('T', ' ')}, "
                                    "nothing changed since.")
            return
        bad = [f"damaged: {p}" for p in chk.damaged] + [f"missing: {p}" for p in chk.missing]
        more = f"\n... and {len(bad) - 15} more (see the log)" if len(bad) > 15 else ""
        QMessageBox.warning(self, "Verify an export",
                            f"{chk.summary()}.\n\n" + "\n".join(bad[:15]) + more
                            + "\n\nExport again with Verify after export checked to rewrite them.")

    def closeEvent(self, e):
        if self.cfg["confirm_exit"] and QMessageBox.question(self, "Quit", f"Quit {APP_NAME}?") != QMessageBox.Yes:
            e.ignore()
            return
        if self.job is not None:
            self.job.stop.set()
            self.job.wait(5000)
        self.loader.stop()
        self.engine.close()
        settings.save(self.sync())
        super().closeEvent(e)
