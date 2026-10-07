"""Project metadata first; writing the source audio is a separate, confirmed operation."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import keys, tags, tagwrite
from ..model import Track
from . import cuehistory, theme
from .worker import Job
from .zoomwave import clock

TEXT_LABELS = (("title", "Title"), ("artist", "Artist"), ("album", "Album"),
               ("album_artist", "Album artist"), ("genre", "Genre"), ("label", "Label"),
               ("remixer", "Remixer"), ("composer", "Composer"))
EDIT_FIELDS = (*tagwrite.FILE_FIELDS, "rating")


class TagEditor(QDialog):
    changed = Signal()
    file_written = Signal(str)

    def __init__(self, track: Track, path: str, key_fmt: str, parent=None, engine=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.t, self.path, self.engine = track, path, engine
        self.baseline = {field: getattr(track, field) for field in EDIT_FIELDS}
        self.job: Job | None = None
        self.pending = None
        self.setWindowTitle(f"ID Tag: {track.artist} - {track.title}")
        self.resize(800, 640)
        self.fields = {}
        form = QFormLayout()
        for name, label in TEXT_LABELS:
            edit = QLineEdit(getattr(track, name))
            edit.setAccessibleName(label)
            self.fields[name] = edit
            form.addRow(label, edit)
        self.comment = QPlainTextEdit(track.comment)
        self.comment.setAccessibleName("Comment")
        self.comment.setMaximumHeight(72)
        form.addRow("Comment", self.comment)
        numbers = QGridLayout()
        self.numbers = {}
        for index, (name, label, maximum) in enumerate(
                (("year", "Year", 9999), ("track_no", "Track", 65535),
                 ("disc_no", "Disc", 65535), ("rating", "Rating (project)", 5))):
            box = QSpinBox()
            box.setRange(0, maximum)
            box.setSpecialValueText("Not set")
            box.setValue(getattr(track, name))
            box.setAccessibleName(label)
            self.numbers[name] = box
            numbers.addWidget(QLabel(label), 0, index * 2)
            numbers.addWidget(box, 0, index * 2 + 1)
            numbers.setColumnStretch(index * 2 + 1, 1)
        self.bpm = QDoubleSpinBox()
        self.bpm.setRange(0, max(1000, track.bpm))
        self.bpm.setDecimals(6)
        self.bpm.setSingleStep(0.01)
        self.bpm.setSpecialValueText("Unknown")
        self.bpm.setValue(track.bpm)
        self.shown_bpm = self.bpm.value()
        self.bpm.setAccessibleName("BPM")
        self.key = QComboBox()
        self.key.setAccessibleName("Musical key")
        self.key.addItem("Unknown", None)
        for index in range(24):
            self.key.addItem(f"{keys.name(index, key_fmt)} / {keys.name(index)}", index)
        self.key.setCurrentIndex(self.key.findData(track.key))
        numbers.addWidget(QLabel("BPM"), 1, 0)
        numbers.addWidget(self.bpm, 1, 1, 1, 3)
        numbers.addWidget(QLabel("Key"), 1, 4)
        numbers.addWidget(self.key, 1, 5, 1, 3)
        form.addRow(numbers)
        note = QLabel("BPM changes the spacing of the beat grid, not existing cue/loop positions. "
                      "Edit the first beat in the Cue Editor.")
        note.setWordWrap(True)
        form.addRow(note)
        metadata = QWidget()
        metadata.setLayout(form)
        self.tabs = QTabWidget()
        self.tabs.addTab(metadata, "Metadata")
        technical = QWidget()
        info = QFormLayout(technical)
        for label, value in (("File", path or track.path or "Missing file"),
                              ("Duration", clock(track.duration * 1000)),
                              ("Bitrate", f"{track.bitrate} kbps"),
                              ("Sample rate", f"{track.samplerate} Hz"),
                              ("Gain", f"{track.gain:+.2f} dB"),
                              ("Plays", str(track.plays)), ("Added", track.added),
                              ("Cues / loops", str(len(track.cues))),
                              ("First beat", f"{track.grid:.3f} ms" if track.grid is not None else "Not set")):
            edit = QLineEdit(value)
            edit.setReadOnly(True)
            edit.setAccessibleName(label)
            info.addRow(label, edit)
        self.tabs.addTab(technical, "File information")
        self.art = QLabel("No artwork")
        self.art.setFixedSize(180, 180)
        self.art.setAlignment(Qt.AlignCenter)
        self.art.setStyleSheet(f"background: {theme.BG_MED};")
        image = tags.artwork(path) if path else None
        pixmap = QPixmap()
        if image and pixmap.loadFromData(image):
            self.art.setPixmap(pixmap.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        side = QVBoxLayout()
        side.addSpacing(self.tabs.tabBar().sizeHint().height())
        side.addWidget(self.art)
        art_note = QLabel("Artwork is preserved.\nCues and beatgrid are not written by this editor.")
        art_note.setWordWrap(True)
        art_note.setMaximumWidth(180)
        side.addWidget(art_note)
        side.addStretch(1)
        body = QHBoxLayout()
        body.addWidget(self.tabs, 1)
        body.addLayout(side)
        self.status = QLabel("Apply updates the project and exports only; the source audio stays unchanged.")
        self.status.setWordWrap(True)
        buttons = QHBoxLayout()
        self.write_button = QPushButton("Write tags to audio...")
        self.write_button.setToolTip("Write displayed metadata to the source file, with a backup and confirmation")
        self.write_button.clicked.connect(self.write_file)
        self.apply_button = QPushButton("Apply to project")
        self.apply_button.clicked.connect(self.apply)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        for button in (self.write_button, self.apply_button, self.close_button):
            button.setAutoDefault(False)
        buttons.addWidget(self.write_button)
        buttons.addStretch(1)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        self.refresh_write_button()

    def values(self):
        values = {name: widget.text() for name, widget in self.fields.items()}
        values["comment"] = self.comment.toPlainText()
        values.update({name: box.value() for name, box in self.numbers.items()})
        bpm = self.bpm.value()
        values.update(bpm=self.baseline["bpm"] if bpm == self.shown_bpm else bpm,
                      key=self.key.currentData())
        return values

    def check_conflicts(self, values):
        for name, value in values.items():
            current = getattr(self.t, name)
            if value != self.baseline[name] and current != self.baseline[name] and current != value:
                raise ValueError(f"{name} changed in another editor. Close and reopen ID Tag before applying.")

    def update_track(self, values):
        self.check_conflicts(values)
        changed = {name: value for name, value in values.items()
                   if value != self.baseline[name] and value != getattr(self.t, name)}
        before = cuehistory.snap(self.t)
        for name, value in changed.items():
            setattr(self.t, name, value)
        if "bpm" in changed:
            cuehistory.record(self.t, before)
        if changed:
            self.setWindowTitle(f"ID Tag: {self.t.artist} - {self.t.title}")
            self.changed.emit()
        self.baseline = {name: getattr(self.t, name) for name in EDIT_FIELDS}
        self.reset_fields()

    def reset_fields(self):
        for name, widget in self.fields.items():
            widget.setText(getattr(self.t, name))
        self.comment.setPlainText(self.t.comment)
        for name, widget in self.numbers.items():
            widget.setValue(getattr(self.t, name))
        self.bpm.setValue(self.t.bpm)
        self.shown_bpm = self.bpm.value()
        self.key.setCurrentIndex(self.key.findData(self.t.key))

    def apply(self):
        if self.job is not None:
            return
        try:
            self.update_track(self.values())
        except ValueError as e:
            QMessageBox.warning(self, "ID Tag", str(e))
            return
        self.status.setText("Applied to project and exports. The source audio was not modified.")

    def refresh_write_button(self):
        supported = os.path.splitext(self.path)[1].lower() in tagwrite.EXTENSIONS
        self.write_button.setEnabled(bool(self.path and os.path.isfile(self.path) and supported))
        if not self.write_button.isEnabled():
            self.write_button.setToolTip("Writing needs an existing MP3, WAV, AIFF, FLAC, MP4/M4A or Ogg Vorbis file")

    def write_file(self):
        if self.job is not None:
            return
        if self.engine is not None and os.path.normcase(os.path.abspath(self.path)) in {
            os.path.normcase(os.path.abspath(path))
            for path in (self.engine.path, self.engine.next_path,
                         *(player.source().toLocalFile() for player, _out in self.engine.decks))
            if path
        }:
            QMessageBox.warning(self, "Write audio tags", "Stop the preview and release this audio file before writing tags.")
            return
        values = self.values()
        try:
            self.check_conflicts(values)
        except ValueError as e:
            QMessageBox.warning(self, "ID Tag", str(e))
            return
        answer = QMessageBox.question(
            self, "Write tags to source audio",
            f"Write the displayed metadata to this original audio file?\n\n{self.path}\n\n"
            "Empty fields clear their corresponding tags. Rating is project-only. "
            "Audio, artwork, unrelated tags and DJ cue/grid data are retained.\n\n"
            f"A backup is kept at:\n{self.path}.tb-tags.bak\n"
            "An existing backup is never overwritten. Reload/Undo cannot undo this file write.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        values = {name: value if value != self.baseline[name] else getattr(self.t, name)
                  for name, value in values.items()}
        raw = {name: values[name] for name in tagwrite.FILE_FIELDS}
        raw.update({name: str(values[name]) if values[name] else "" for name in tagwrite.NUMBER_FIELDS})
        raw["bpm"] = f"{values['bpm']:.6f}" if values["bpm"] else ""
        raw["key"] = keys.name(values["key"])
        self.pending = values
        self.job = Job(tagwrite.write, self.path, raw)
        self.job.progress.connect(lambda _pct, message: self.status.setText(message))
        self.job.done.connect(self.written)
        self.job.failed.connect(self.write_failed)
        self.job.cancelled.connect(lambda: self.status.setText("Writing cancelled; the source file was not modified."))
        self.job.finished.connect(self.write_finished)
        self.tabs.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.write_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.status.setText("Writing tags on a copy; please wait...")
        self.job.start()

    def written(self, result: tagwrite.WriteResult):
        self.t.size = result.size
        try:
            for name in tagwrite.FILE_FIELDS:
                current = getattr(self.t, name)
                if current != self.baseline[name] and current != self.pending[name]:
                    raise ValueError(f"{name} changed in another editor while writing.")
            self.update_track(self.pending)
        except ValueError as e:
            QMessageBox.warning(self, "Audio tags written", f"The file was written, but the project changed:\n{e}")
            self.status.setText(f"Audio tags written, but project metadata was not applied: {e}")
        else:
            self.status.setText(f"Audio tags written. Backup: {result.backup}")
        self.file_written.emit(result.path)

    def write_failed(self, message):
        self.status.setText(f"Tags were not written: {message}")
        QMessageBox.critical(self, "Write audio tags", message)

    def write_finished(self):
        job, self.job = self.job, None
        self.pending = None
        if job is not None:
            job.deleteLater()
        self.tabs.setEnabled(True)
        self.apply_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.refresh_write_button()

    def reject(self):
        if self.job is not None:
            return
        if self.values() != self.baseline:
            answer = QMessageBox.question(self, "Unapplied metadata", "Discard unapplied metadata changes?",
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        super().reject()

    def closeEvent(self, event):
        if self.job is not None:
            event.ignore()
            return
        super().closeEvent(event)
