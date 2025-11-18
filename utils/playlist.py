"""
Playlist Management Module for Traktor Bridge
Handles playlist data structures and DetailsWindow functionality
"""

import os
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent


class CueType(Enum):
    """Cue point types for Traktor/Rekordbox mapping."""
    GRID, HOT_CUE, FADE_IN, FADE_OUT, LOAD, LOOP = range(6)


@dataclass
class Track:
    """Enhanced track data container compatible with BSM parser."""
    title: str = "Unknown"
    artist: str = "Unknown"
    album: str = ""
    genre: str = ""
    label: str = ""
    comment: str = ""
    file_path: str = ""
    bpm: float = 0.0
    musical_key: str = ""
    gain: float = 0.0
    playtime: float = 0.0
    bitrate: int = 0
    cue_points: List[Dict] = field(default_factory=list)
    grid_anchor_ms: Optional[float] = None
    artwork_data: Optional[bytes] = None


@dataclass 
class Node:
    """Playlist/folder structure container."""
    type: str  # 'playlist' or 'folder'
    name: str
    tracks: List[Track] = field(default_factory=list)
    children: List['Node'] = field(default_factory=list)


class PlaylistDetailsWindow(QDialog):
    """Enhanced details window for playlist view with audio playback."""
    
    def __init__(self, playlist: Node, key_translator, audio_manager, parent=None):
        super().__init__(parent)
        self.playlist = playlist
        self.key_translator = key_translator
        self.audio_manager = audio_manager
        self.selected_track_id = None
        self.key_format = "Open Key"
        
        self.setWindowTitle(f"Details: {playlist.name}")
        self.resize(1200, 500)
        self.setModal(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self._setup_ui()
        self._populate_table()
        
    def _setup_ui(self):
        """Setup the details window interface."""
        layout = QVBoxLayout(self)
        
        # Header with search and options
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        
        # Search functionality
        search_label = QLabel("Search:")
        self.search_field = QLineEdit()
        self.search_field.textChanged.connect(self._filter_tracks)
        self.search_field.setPlaceholderText("Filter tracks...")
        
        # Key format selector
        key_label = QLabel("Key Format:")
        self.key_format_button = QPushButton(self.key_format)
        
        key_menu = QMenu(self)
        for fmt in self.key_translator.get_supported_formats():
            action = key_menu.addAction(fmt)
            action.triggered.connect(lambda checked, f=fmt: self._change_key_format(f))
        self.key_format_button.setMenu(key_menu)
        
        header_layout.addWidget(search_label)
        header_layout.addWidget(self.search_field, 1)
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
        
        play_button = QPushButton("Play Selected")
        play_button.clicked.connect(self._play_selected_track)
        
        copy_button = QPushButton("Copy Track Info") 
        copy_button.clicked.connect(self._copy_track_info)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        
        button_layout.addWidget(play_button)
        button_layout.addWidget(copy_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addWidget(button_frame)
    
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
    
    def _populate_table_with_tracks(self, tracks: List[Track]):
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
            
            play_icon = "⏸" if is_playing and track_id == currently_playing_id else "▶"
            
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
        elif column == 9:  # Cues column
            self._show_cue_timeline(item)
    
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
            
            if current_state['item_id']:
                for i in range(self.tracks_table.topLevelItemCount()):
                    curr_item = self.tracks_table.topLevelItem(i)
                    if curr_item.data(0, Qt.ItemDataRole.UserRole) == current_state['item_id']:
                        curr_item.setText(0, "▶")
                        break
            
            if current_state['item_id'] == track_id:
                return
        
        for track in self.playlist.tracks:
            if id(track) == track_id:
                if track.file_path and os.path.exists(track.file_path):
                    if self.audio_manager.play_file(track.file_path, track_id):
                        item.setText(0, "⏸")
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


class PlaylistManager:
    """Manages playlist operations and data structures."""
    
    @staticmethod
    def count_tracks_in_structure(structure: List[Node]) -> int:
        """Count total tracks in playlist structure."""
        count = 0
        for node in structure:
            if node.type == 'playlist':
                count += len(node.tracks)
            elif node.type == 'folder':
                count += PlaylistManager.count_tracks_in_structure(node.children)
        return count
    
    @staticmethod
    def collect_all_tracks(structure: List[Node]) -> List[Track]:
        """Collect all unique tracks from playlist structure."""
        all_tracks = []
        track_paths = set()
        
        def collect_recursive(nodes):
            for node in nodes:
                if node.type == 'playlist':
                    for track in node.tracks:
                        if track.file_path and track.file_path not in track_paths:
                            all_tracks.append(track)
                            track_paths.add(track.file_path)
                elif node.type == 'folder':
                    collect_recursive(node.children)
        
        collect_recursive(structure)
        return all_tracks
    
    @staticmethod
    def find_playlist_by_name(structure: List[Node], name: str) -> Optional[Node]:
        """Find playlist by name in structure."""
        for node in structure:
            if node.type == 'playlist' and node.name == name:
                return node
            elif node.type == 'folder':
                result = PlaylistManager.find_playlist_by_name(node.children, name)
                if result:
                    return result
        return None
    
    @staticmethod
    def get_playlist_statistics(playlist: Node) -> Dict[str, Any]:
        """Get comprehensive playlist statistics."""
        if playlist.type != 'playlist':
            return {}
        
        stats = {
            'track_count': len(playlist.tracks),
            'total_duration': sum(track.playtime for track in playlist.tracks),
            'avg_bpm': 0,
            'key_distribution': {},
            'cue_points_total': 0,
            'file_formats': {},
            'missing_files': 0
        }
        
        if playlist.tracks:
            bpms = [track.bpm for track in playlist.tracks if track.bpm > 0]
            stats['avg_bpm'] = sum(bpms) / len(bpms) if bpms else 0
            
            # Key distribution
            for track in playlist.tracks:
                if track.musical_key:
                    key = track.musical_key
                    stats['key_distribution'][key] = stats['key_distribution'].get(key, 0) + 1
            
            # Cue points
            stats['cue_points_total'] = sum(len(track.cue_points) for track in playlist.tracks)
            
            # File formats
            for track in playlist.tracks:
                if track.file_path:
                    ext = os.path.splitext(track.file_path)[1].lower()
                    stats['file_formats'][ext] = stats['file_formats'].get(ext, 0) + 1
                    
                    if not os.path.exists(track.file_path):
                        stats['missing_files'] += 1
        
        return stats