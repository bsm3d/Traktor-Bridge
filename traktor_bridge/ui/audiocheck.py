"""Audio verification panel, independent of collection relocation."""

from collections import Counter

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .. import audiocheck
from ..model import unique_tracks
from . import theme
from .worker import Job


class AudioCheck(QDialog):
    def __init__(self, nodes, root="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Verify audio files")
        self.resize(980, 580)
        self.paths = [track.path for track in unique_tracks(nodes)]
        self.job = None
        self.source = QComboBox()
        self.source.addItems(["Loaded collection", "Folder (including subfolders)"])
        self.folder = QLineEdit(root)
        self.folder.setReadOnly(True)
        self.browse = QPushButton("Browse...")
        self.browse.clicked.connect(self.pick_folder)
        self.mode = QComboBox()
        self.mode.addItems(["Quick - headers and metadata", "Full - decode entire audio stream"])
        self.mode.setCurrentIndex(1)
        self.mode.setAccessibleName("Verification mode")
        self.source.setAccessibleName("Files to verify")
        self.source.currentIndexChanged.connect(self.source_changed)
        self.source_changed()
        source_row = QHBoxLayout()
        source_row.addWidget(self.source)
        source_row.addWidget(self.folder, 1)
        source_row.addWidget(self.browse)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Verification"))
        mode_row.addWidget(self.mode, 1)
        self.time_limit = QSpinBox()
        self.time_limit.setRange(5, 3600)
        self.time_limit.setValue(120)
        self.time_limit.setSuffix(" s")
        self.time_limit.setAccessibleName("Maximum analysis time per file")
        self.memory_limit = QSpinBox()
        self.memory_limit.setRange(256, 8192)
        self.memory_limit.setValue(1024)
        self.memory_limit.setSuffix(" MB")
        self.memory_limit.setAccessibleName("Maximum analysis process memory")
        limits = QHBoxLayout()
        limits.addWidget(QLabel("Per-file limits"))
        limits.addWidget(self.time_limit)
        limits.addWidget(self.memory_limit)
        limits.addStretch(1)
        clamav = audiocheck.find_clamav()
        antivirus = QLabel(f"ClamAV detected: {clamav} - antivirus scan not performed."
                           if clamav else "ClamAV not detected - antivirus scan not performed.")
        antivirus.setWordWrap(True)
        note = QLabel("Read-only: original files are never changed. Quick checks do not validate audio data. "
                      "Full checks are slower; some formats (notably M4A/ALAC) may not be supported by the decoder. "
                      "A readable stream is not a guarantee of integrity: decoders can tolerate some damage.")
        note.setText(note.text() + " Analysis runs in a separate process with monitored time/memory limits. "
                     "These limits are not a security sandbox or a malware scan.")
        note.setWordWrap(True)
        self.table = QTreeWidget()
        self.table.setRootIsDecorated(False)
        self.table.setHeaderLabels(["Status", "File", "Details"])
        self.table.setColumnWidth(0, 145)
        self.table.setColumnWidth(1, 380)
        self.progress = QProgressBar()
        self.status = QLabel("Choose the source and verification mode, then start.")
        self.status.setWordWrap(True)
        self.start_button = QPushButton("Start verification")
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addLayout(source_row)
        layout.addLayout(mode_row)
        layout.addLayout(limits)
        layout.addWidget(antivirus)
        layout.addWidget(note)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addLayout(buttons)

    def source_changed(self):
        folder = self.source.currentIndex() == 1
        self.folder.setEnabled(folder)
        self.browse.setEnabled(folder)

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Audio folder", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def start(self):
        folder = self.folder.text() if self.source.currentIndex() == 1 else ""
        if (self.source.currentIndex() == 1 and not folder) or (not folder and not self.paths):
            QMessageBox.information(self, "Verify audio files", "Load a collection or choose an audio folder first.")
            return
        self.table.clear()
        self.progress.setValue(0)
        self.status.setText("Verifying audio files...")
        for widget in (self.source, self.folder, self.browse, self.mode, self.start_button,
                       self.time_limit, self.memory_limit):
            widget.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.job = Job(audiocheck.scan, self.paths, folder, self.mode.currentIndex() == 1,
                       timeout=self.time_limit.value(), memory_mb=self.memory_limit.value())
        self.job.progress.connect(self.update_progress)
        self.job.done.connect(self.completed)
        self.job.failed.connect(self.failed)
        self.job.cancelled.connect(lambda: self.status.setText("Verification cancelled; no files changed."))
        self.job.finished.connect(self.job_finished)
        self.job.start()

    def update_progress(self, value, text):
        self.progress.setValue(value)
        self.status.setText(text)

    def completed(self, results):
        for result in results:
            item = QTreeWidgetItem([result.status, result.path, result.detail])
            item.setToolTip(1, result.path)
            item.setToolTip(2, result.detail)
            color = (theme.RED if result.status in ("Suspect", "Missing", "Unreadable") else
                     theme.YELLOW if result.status == "Not checked" else theme.GREEN)
            item.setForeground(0, QColor(color))
            self.table.addTopLevelItem(item)
        counts = Counter(result.status for result in results)
        self.progress.setValue(100)
        self.status.setText(f"{len(results)} files: " + ", ".join(f"{n} {s}" for s, n in counts.items())
                            if results else "No supported audio files found.")

    def failed(self, message):
        self.status.setText("Verification failed; no files changed.")
        QMessageBox.critical(self, "Audio verification failed", message)

    def cancel(self):
        if self.job is not None:
            self.job.stop.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("Cancelling after the current decoder read...")

    def job_finished(self):
        self.job.deleteLater()
        self.job = None
        for widget in (self.source, self.mode, self.start_button, self.time_limit, self.memory_limit):
            widget.setEnabled(True)
        self.source_changed()
        self.cancel_button.setEnabled(False)

    def reject(self):
        if self.job is not None:
            self.cancel()
            return
        super().reject()

    def closeEvent(self, event):
        if self.job is not None:
            self.cancel()
            event.ignore()
        else:
            super().closeEvent(event)
