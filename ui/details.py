"""
Detail Window Module for Traktor Bridge
Enhanced playlist view with track information and playback functionality
"""

import os
from typing import Dict, List, Optional
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QBrush, QFont


class DetailWindow(QDialog):
    """Enhanced playlist details window with playback and sorting."""
    
    def __init__(self, playlist, key_translator, audio_manager, parent=None):
        super().__init__(parent)
        self.playlist = playlist
        self.key_translator = key_translator
        self.audio_manager = audio_manager
        self.selected_track_id = None
        self.key_format = "Open Key"
        
        self.setWindowTitle(f"Details: {playlist.name}")
        self.resize(1200, 600)
        self.setModal(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Track lookup for performance
        self.tracks_by_id = {id(track): track for track in playlist.tracks}
        
        # Play/pause icons
        self.play_icon = "▶"
        self.pause_icon = "⏸"
        
        self._setup_ui()
        self._populate_table()
        self._setup_shortcuts()
    
    def _setup_ui(self):
        """Setup the detail window interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header with search and options
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        
        # Playlist info
        playlist_label = QLabel(f"{self.playlist.name}")
        playlist_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        
        tracks_label = QLabel(f"{len(self.playlist.tracks)} tracks")
        tracks_label.setStyleSheet("color: #adb5bd;")
        
        # Search
        search_label = QLabel("Search:")
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Filter tracks...")
        self.search_field.textChanged.connect(self._filter_tracks)
        
        # Key format selector
        key_label = QLabel("Key Format:")
        self.key_format_button = QPushButton(self.key_format)
        
        key_menu = QMenu(self)
        for fmt in self.key_translator.get_supported_formats():
            action = key_menu.addAction(fmt)
            action.triggered.connect(lambda checked, f=fmt: self._change_key_format(f))
        self.key_format_button.setMenu(key_menu)
        
        header_layout.addWidget(playlist_label)
        header_layout.addWidget(tracks_label)
        header_layout.addStretch()
        header_layout.addWidget(search_label)
        header_layout.addWidget(self.search_field)
        header_layout.addWidget(key_label)
        header_layout.addWidget(self.key_format_button)
        
        layout.addWidget(header_frame)
        
        # Instructions
        info_label = QLabel("Shortcuts: P = Play/Pause | Click ▶ to play | Double-click Cues to open timeline")
        layout.addWidget(info_label)
        
        # Tracks table
        self.tracks_table = QTreeWidget()
        self.tracks_table.setAlternatingRowColors(True)
        self.tracks_table.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tracks_table.setRootIsDecorated(False)
        
        columns = ['▶', '#', 'Artist', 'Title', 'Key', 'BPM', 'Gain', 'Grid', 'Duration', 'Cues', 'Album']
        self.tracks_table.setColumnCount(len(columns))
        self.tracks_table.setHeaderLabels(columns)
        
        # Column widths
        widths = {'▶': 30, '#': 40, 'Artist': 200, 'Title': 280, 'Key': 60, 
                 'BPM': 60, 'Gain': 60, 'Grid': 40, 'Duration': 70, 'Cues': 100, 'Album': 220}
        
        for i, col in enumerate(columns):
            self.tracks_table.setColumnWidth(i, widths.get(col, 100))
        
        # Connect signals
        self.tracks_table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tracks_table.itemClicked.connect(self._on_item_clicked)
        self.tracks_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.tracks_table.header().sectionClicked.connect(self._on_header_clicked)
        
        self.sort_column = -1
        self.sort_order = Qt.SortOrder.AscendingOrder
        
        layout.addWidget(self.tracks_table)
        
        # Bottom buttons
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        
        self.play_button = QPushButton("Play Selected")
        self.play_button.clicked.connect(self._play_selected_track)
        
        copy_button = QPushButton("Copy Track Info")
        copy_button.clicked.connect(self._copy_track_info)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self._close_dialog)
        
        button_layout.addWidget(self.play_button)
        button_layout.addWidget(copy_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addWidget(button_frame)
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        from PySide6.QtGui import QShortcut, QKeySequence
        
        # Play/Pause with P
        self.play_shortcut = QShortcut(QKeySequence("P"), self)
        self.play_shortcut.activated.connect(self._play_selected_track)
        
        # Search focus with Ctrl+F
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(lambda: self.search_field.setFocus())
    
    def _close_dialog(self):
        """Handle close button click with audio cleanup."""
        if self.audio_manager:
            self.audio_manager.stop()
        self.accept()    
    
    def _change_key_format(self, format_name: str):
        """Change key display format."""
        self.key_format = format_name
        self.key_format_button.setText(format_name)
        self._populate_table()
    
    def _populate_table(self):
        """Populate table with track data."""
        if self.sort_column == -1:
            self._populate_table_with_tracks(self.playlist.tracks)
        else:
            tracks_to_sort = list(self.playlist.tracks)
            
            sort_keys = {
                2: lambda t: t.artist.lower(),
                3: lambda t: t.title.lower(),
                4: lambda t: self.key_translator.translate(t.musical_key, self.key_format),
                5: lambda t: t.bpm,
                6: lambda t: t.gain,
                7: lambda t: 1 if t.grid_anchor_ms is not None else 0,
                8: lambda t: t.playtime,
                9: lambda t: len(t.cue_points),
                10: lambda t: t.album.lower()
            }
            
            if self.sort_column == 1:  # Number column
                if self.sort_order == Qt.SortOrder.DescendingOrder:
                    tracks_to_sort.reverse()
            elif self.sort_column in sort_keys:
                tracks_to_sort.sort(key=sort_keys[self.sort_column],
                                  reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
            
            self._populate_table_with_tracks(tracks_to_sort)
    
    def _populate_table_with_tracks(self, tracks: List):
        """Populate table with provided track list."""
        current_state = self.audio_manager.get_current_state() if self.audio_manager else {}
        currently_playing_id = current_state.get('item_id')
        is_playing = current_state.get('is_playing', False)
        
        selected_track_id = self.selected_track_id
        
        self.tracks_table.blockSignals(True)
        self.tracks_table.clear()
        
        item_to_reselect = None
        
        for i, track in enumerate(tracks, 1):
            item = QTreeWidgetItem()
            track_id = id(track)
            
            # Calculate display values
            duration = f"{int(track.playtime // 60):02d}:{int(track.playtime % 60):02d}"
            key = self.key_translator.translate(track.musical_key, self.key_format)
            gain = f"{track.gain:+.2f}" if track.gain else ""
            grid_marker = "✓" if track.grid_anchor_ms is not None else ""
            cue_summary = self._get_cue_summary(track.cue_points)
            
            play_icon = self.pause_icon if is_playing and track_id == currently_playing_id else self.play_icon
            
            # Set item data
            item.setText(0, play_icon)
            item.setText(1, str(i))
            item.setText(2, track.artist)
            item.setText(3, track.title)
            item.setText(4, key)
            item.setText(5, f"{track.bpm:.2f}" if track.bpm else "")
            item.setText(6, gain)
            item.setText(7, grid_marker)
            item.setText(8, duration)
            item.setText(9, cue_summary)
            item.setText(10, track.album)
            
            # Set key color
            key_color = self.key_translator.get_key_color(track.musical_key, self.key_format)
            if key_color:
                item.setForeground(4, QColor(key_color))
            
            item.setData(0, Qt.ItemDataRole.UserRole, track_id)
            
            if selected_track_id and track_id == selected_track_id:
                item_to_reselect = item
                
            self.tracks_table.addTopLevelItem(item)
        
        # Update play button state
        if is_playing and currently_playing_id:
            self.play_button.setText("Stop Playback")
        else:
            self.play_button.setText("Play Selected")
        
        self.tracks_table.blockSignals(False)
        
        if item_to_reselect:
            self.tracks_table.clearSelection()
            item_to_reselect.setSelected(True)
            self.tracks_table.setCurrentItem(item_to_reselect)
    
    def _filter_tracks(self):
        """Filter tracks based on search text."""
        search_text = self.search_field.text().lower()
        
        if not search_text:
            self._populate_table()
            return
        
        filtered_tracks = [
            t for t in self.playlist.tracks
            if (search_text in t.artist.lower() or
                search_text in t.title.lower() or
                search_text in t.album.lower())
        ]
        
        self._populate_table_with_tracks(filtered_tracks)
    
    def _get_cue_summary(self, cue_points: List[Dict]) -> str:
        """Generate cue point summary."""
        from utils.playlist import CueType
        
        summary = {'hotcues': 0, 'memory': 0, 'loops': 0}
        
        for cue in cue_points:
            if cue.get('type') == CueType.HOT_CUE.value and cue.get('hotcue', -1) > 0:
                summary['hotcues'] += 1
            elif cue.get('type') == CueType.LOAD.value:
                summary['memory'] += 1
            elif cue.get('type') == CueType.LOOP.value and cue.get('len', 0) > 0:
                summary['loops'] += 1
        
        parts = []
        if summary['hotcues'] > 0: parts.append(f"H{summary['hotcues']}")
        if summary['memory'] > 0: parts.append(f"M{summary['memory']}")
        if summary['loops'] > 0: parts.append(f"L{summary['loops']}")
        return " ".join(parts) if parts else "-"
    
    def _on_header_clicked(self, column_index: int):
        """Handle column header click for sorting."""
        if column_index == 0:
            return
            
        if column_index == self.sort_column:
            self.sort_order = Qt.SortOrder.DescendingOrder if self.sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.sort_column = column_index
            self.sort_order = Qt.SortOrder.AscendingOrder
        
        self.tracks_table.header().setSortIndicator(column_index, self.sort_order)
        self._populate_table()
    
    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle item clicks."""
        if column == 0:  # Play button
            track_id = item.data(0, Qt.ItemDataRole.UserRole)
            self._toggle_playback(item, track_id)
    
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-clicks."""
        if column == 9:  # Cues column
            self._show_cue_timeline(item)
    
    def _on_selection_changed(self):
        """Handle selection changes."""
        selected_items = self.tracks_table.selectedItems()
        if selected_items:
            self.selected_track_id = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
            self.setFocus()
    
    def _show_cue_timeline(self, item: QTreeWidgetItem):
        """Show cue timeline for track."""
        track_id = item.data(0, Qt.ItemDataRole.UserRole)
        if track_id:
            for track in self.playlist.tracks:
                if id(track) == track_id:
                    from ui.timeline import TimelineDialog
                    dialog = TimelineDialog(track, self.key_translator, self)
                    dialog.exec()
                    break
    
    def _toggle_playback(self, item: QTreeWidgetItem, track_id):
        """Toggle audio playback for track."""
        if not self.audio_manager or not track_id:
            return
            
        current_state = self.audio_manager.get_current_state()
        
        if current_state['is_playing']:
            self.audio_manager.stop()
            self.play_button.setText("Play Selected")
            
            # Update all play buttons
            for i in range(self.tracks_table.topLevelItemCount()):
                curr_item = self.tracks_table.topLevelItem(i)
                if curr_item.data(0, Qt.ItemDataRole.UserRole) == current_state['item_id']:
                    curr_item.setText(0, self.play_icon)
                    break
            
            if current_state['item_id'] == track_id:
                return
        
        for track in self.playlist.tracks:
            if id(track) == track_id:
                if track.file_path and os.path.exists(track.file_path):
                    if self.audio_manager.play_file(track.file_path, track_id):
                        item.setText(0, self.pause_icon)
                        self.play_button.setText("Stop Playback")
                    else:
                        QMessageBox.warning(self, "File Not Found",
                                          "The audio file for this track could not be found.")
                break
    
    def _play_selected_track(self):
        """Play currently selected track."""
        selected_items = self.tracks_table.selectedItems()
        if selected_items:
            item = selected_items[0]
            track_id = item.data(0, Qt.ItemDataRole.UserRole)
            if track_id:
                self._toggle_playback(item, track_id)
    
    def _copy_track_info(self):
        """Copy selected track info to clipboard."""
        selected_items = self.tracks_table.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select a track first.")
            return
            
        item = selected_items[0]
        track_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        for track in self.playlist.tracks:
            if id(track) == track_id:
                info = f"""Track Information:
Artist: {track.artist}
Title: {track.title}
Album: {track.album}
BPM: {track.bpm:.2f}
Key: {self.key_translator.translate(track.musical_key, self.key_format)}
Duration: {int(track.playtime // 60):02d}:{int(track.playtime % 60):02d}
File: {track.file_path}
Cue Points: {len(track.cue_points)}"""
                
                QApplication.clipboard().setText(info)
                QMessageBox.information(self, "Copied", "Track information copied to clipboard.")
                break
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key.Key_P:
            self._play_selected_track()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """Handle window close."""
        if self.audio_manager:
            self.audio_manager.stop()
        event.accept()