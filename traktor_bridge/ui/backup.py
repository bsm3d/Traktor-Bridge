"""One panel for creating, restoring and verifying ZIP backups."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import backup
from . import theme


class DiskTransfer(QWidget):
    """Disk-transfer animation, separate from actual progress."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(72)
        self.setAccessibleName("Backup in progress: transferring data between disks")
        self.phase = 0
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.advance)
        self.hide()

    def set_running(self, running):
        self.setVisible(running)
        if running:
            self.phase = 0
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def advance(self):
        self.phase = (self.phase + 1) % 24
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.translate((self.width() - 240) // 2, 8)
        painter.setPen(Qt.NoPen)
        for x in (0, 192):
            painter.fillRect(x, 0, 48, 56, QColor(theme.ACCENT))
            painter.fillRect(x + 4, 4, 40, 48, QColor(theme.BG_LIGHT))
            painter.fillRect(x + 12, 4, 24, 16, QColor(theme.FG_MUTED))
            painter.fillRect(x + 28, 4, 4, 12, QColor(theme.BG_DARK))
            painter.fillRect(x + 8, 28, 32, 24, QColor(theme.FG))
            for y in (32, 38, 44):
                painter.fillRect(x + 12, y, 24, 2, QColor(theme.BG_LIGHT))
            led = theme.GREEN if self.phase % 6 < 3 else theme.BG_DARK
            painter.fillRect(x + 4, 22, 4, 4, QColor(led))
        for index in range(3):
            step = (self.phase + index * 8) % 24
            x = 56 + step * 5
            painter.fillRect(x, 23, 8, 8, QColor(theme.ACCENT))
            painter.fillRect(x + 2, 25, 2, 2, QColor(theme.FG))


class BackupPanel(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("Backup")
        self.resize(640, 240)
        self.status = QLabel("Save all loaded playlists and audio, restore a ZIP, or verify its SHA-256.")
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.animation = DiskTransfer(self)
        self.actions = []
        row = QHBoxLayout()
        for label, callback in (("Save backup...", owner.backup_project),
                                ("Load / restore backup...", owner.restore_backup),
                                ("Verify backup...", owner.verify_backup)):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, fn=callback: self.launch(fn))
            self.actions.append(button)
            row.addWidget(button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(owner.cancel)
        self.cancel_button.setEnabled(False)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addLayout(row)
        layout.addWidget(self.progress)
        layout.addWidget(self.animation)
        layout.addStretch(1)
        layout.addLayout(bottom)
        if owner.job is not None:
            self.watch(owner.job)

    def launch(self, callback):
        callback()
        if self.owner.job is not None:
            self.watch(self.owner.job)

    def watch(self, job):
        self.set_busy(True)
        self.animation.set_running(job.fn is backup.create)
        self.progress.setValue(0)
        self.status.setText(self.owner.status.text())
        job.progress.connect(self.update_progress)
        job.finished.connect(self.job_finished)

    def update_progress(self, value, message):
        self.progress.setValue(value)
        self.status.setText(message)

    def set_busy(self, on):
        for button in self.actions:
            button.setEnabled(not on)
        self.cancel_button.setEnabled(on)

    def job_finished(self):
        self.status.setText(self.owner.status.text())
        self.animation.set_running(False)
        self.set_busy(False)

    def reject(self):
        if self.owner.job is not None:
            self.owner.cancel()
            return
        super().reject()

    def closeEvent(self, event):
        if self.owner.job is not None:
            self.owner.cancel()
            event.ignore()
        else:
            super().closeEvent(event)
