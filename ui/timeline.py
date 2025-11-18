"""
Timeline Dialog Module for Traktor Bridge
Visual timeline view of track cue points with enhanced visualization
"""

import math
from typing import List, Dict
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QRectF, QRect, QPoint
from PySide6.QtGui import QPen, QColor, QBrush, QFont, QPainter


class TimelineDialog(QDialog):
    """Dialog for displaying cue point timeline with enhanced visualization."""
    
    def __init__(self, track, key_translator, parent=None):
        super().__init__(parent)
        self.track = track
        self.key_translator = key_translator
        
        self.setWindowTitle(f"Cue Points: {track.artist} - {track.title}")
        self.resize(700, 500)
        self.setModal(True)
        
        # Filter relevant cue points
        from utils.playlist import CueType
        self.cue_points = sorted(
            [cue for cue in track.cue_points if self._is_relevant_cue(cue)],
            key=lambda c: c.get('start', 0)
        )
        
        # Filter states
        self.show_hotcues = True
        self.show_memory_cues = True
        self.show_loops = True
        self.show_grid = True
        
        self._setup_ui()
    
    def _is_relevant_cue(self, cue):
        """Determine if cue point is relevant for display."""
        from utils.playlist import CueType
        cue_type = cue.get('type', -1)
        hotcue_num = cue.get('hotcue', -1)
        return ((cue_type == CueType.HOT_CUE.value and hotcue_num > 0) or 
                cue_type in [CueType.LOAD.value, CueType.LOOP.value])
    
    def _setup_ui(self):
        """Setup the timeline dialog interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header info
        header_frame = QFrame()
        header_layout = QVBoxLayout(header_frame)
        
        title_label = QLabel(f"🎵 {self.track.artist} - {self.track.title}")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        
        # Track info
        info_text = f"BPM: {self.track.bpm:.1f} | Duration: {int(self.track.playtime // 60)}:{int(self.track.playtime % 60):02d}"
        if self.track.musical_key:
            key = self.key_translator.translate(self.track.musical_key)
            info_text += f" | Key: {key}"
            
        if self.track.grid_anchor_ms is not None:
            ms = self.track.grid_anchor_ms
            minutes = int(ms // 60000)
            seconds = (ms % 60000) / 1000
            grid_time = f"{minutes:02d}:{seconds:06.3f}"
            info_text += f" | Grid Anchor: {grid_time}"
            
        info_label = QLabel(info_text)
        info_label.setStyleSheet("color: #adb5bd;")
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(info_label)
        layout.addWidget(header_frame)
        
        # Filter controls
        filter_frame = QFrame()
        filter_layout = QHBoxLayout(filter_frame)
        
        stats_label = QLabel(self._get_cue_stats())
        stats_label.setStyleSheet("font-weight: bold;")
        
        filter_label = QLabel("Filter:")
        self.hotcue_check = QCheckBox("Hot Cues")
        self.hotcue_check.setChecked(True)
        self.hotcue_check.toggled.connect(self._update_filters)
        
        self.memory_check = QCheckBox("Memory Cues")
        self.memory_check.setChecked(True)
        self.memory_check.toggled.connect(self._update_filters)
        
        self.loop_check = QCheckBox("Loops")
        self.loop_check.setChecked(True)
        self.loop_check.toggled.connect(self._update_filters)
        
        self.grid_check = QCheckBox("Grid Anchor")
        self.grid_check.setChecked(True)
        self.grid_check.toggled.connect(self._update_filters)
        self.grid_check.setEnabled(self.track.grid_anchor_ms is not None)
        
        filter_layout.addWidget(stats_label)
        filter_layout.addStretch()
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.hotcue_check)
        filter_layout.addWidget(self.memory_check)
        filter_layout.addWidget(self.loop_check)
        filter_layout.addWidget(self.grid_check)
        
        layout.addWidget(filter_frame)
        
        # Timeline visualization
        self.timeline_view = self._create_timeline_widget()
        layout.addWidget(self.timeline_view)
        
        # Cue points table
        self.cue_table = self._create_cue_table()
        layout.addWidget(self.cue_table, 1)
        
        # Buttons
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        
        export_button = QPushButton("Export to Clipboard")
        export_button.clicked.connect(self._export_to_clipboard)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        
        button_layout.addWidget(export_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addWidget(button_frame)
    
    def _get_cue_stats(self):
        """Generate cue point statistics."""
        from utils.playlist import CueType
        hot_cues = sum(1 for cue in self.cue_points if cue.get('type') == CueType.HOT_CUE.value)
        memory_cues = sum(1 for cue in self.cue_points if cue.get('type') == CueType.LOAD.value)
        loops = sum(1 for cue in self.cue_points if cue.get('type') == CueType.LOOP.value)
        
        stats = f"Total: {len(self.cue_points)} points ({hot_cues} Hot Cues, {memory_cues} Memory Cues, {loops} Loops"
        if self.track.grid_anchor_ms is not None:
            stats += ", 1 Grid Anchor"
        stats += ")"
        
        return stats
    
    def _create_timeline_widget(self):
        """Create enhanced timeline visualization widget."""
        
        class TimelineView(QWidget):
            def __init__(self, track, cue_points, parent=None):
                super().__init__(parent)
                self.track = track
                self.cue_points = cue_points
                self.setMinimumHeight(100)
                self.setStyleSheet("background-color: #343a40;")
                
                self.show_hotcues = True
                self.show_memory_cues = True
                self.show_loops = True
                self.show_grid = True
            
            def update_filters(self, show_hotcues, show_memory_cues, show_loops, show_grid):
                self.show_hotcues = show_hotcues
                self.show_memory_cues = show_memory_cues
                self.show_loops = show_loops
                self.show_grid = show_grid
                self.update()
            
            def paintEvent(self, event):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                
                width = self.width()
                height = self.height()
                
                # Background gradient
                gradient = QColor('#343a40')
                gradient_dark = QColor('#212529')
                for y in range(height):
                    blend_factor = y / height
                    color = QColor(
                        int(gradient.red() * (1 - blend_factor) + gradient_dark.red() * blend_factor),
                        int(gradient.green() * (1 - blend_factor) + gradient_dark.green() * blend_factor),
                        int(gradient.blue() * (1 - blend_factor) + gradient_dark.blue() * blend_factor)
                    )
                    painter.setPen(color)
                    painter.drawLine(0, y, width, y)
                
                # Main timeline
                painter.setPen(QPen(QColor('#888888'), 2))
                mid_y = height // 2
                painter.drawLine(10, mid_y, width - 10, mid_y)
                
                # Simulated waveform
                wave_color = QColor('#555555')
                painter.setPen(QPen(wave_color, 1))
                
                for x in range(10, width - 10, 2):
                    pos_ratio = (x - 10) / (width - 20)
                    amp_factor = math.sin(pos_ratio * 3.14) * 0.8 + 0.2
                    freq = 0.2 + pos_ratio * 0.1
                    y_offset = math.sin(pos_ratio * 100 * freq) * 10 * amp_factor
                    painter.drawLine(x, mid_y + y_offset, x, mid_y - y_offset)
                
                # Time markers
                total_duration = self.track.playtime * 1000 if self.track.playtime > 0 else 1
                
                def format_time(ms):
                    seconds = ms / 1000
                    minutes = int(seconds // 60)
                    seconds = seconds % 60
                    return f"{minutes:02d}:{seconds:05.2f}"
                
                painter.setPen(QPen(QColor('#AAAAAA'), 1))
                for i in range(6):
                    x_pos = 10 + (i * ((width - 20) / 5))
                    time_pos = (i / 5) * total_duration
                    
                    painter.drawLine(x_pos, mid_y - 5, x_pos, mid_y + 5)
                    painter.drawText(QRectF(x_pos - 40, mid_y + 10, 80, 20), 
                                  Qt.AlignmentFlag.AlignCenter, format_time(time_pos))
                
                # Grid anchor
                if self.show_grid and self.track.grid_anchor_ms is not None:
                    grid_pos = 10 + ((self.track.grid_anchor_ms / total_duration) * (width - 20))
                    grid_color = QColor('#00FFFF')
                    painter.setPen(QPen(grid_color, 1, Qt.PenStyle.DashLine))
                    painter.drawLine(int(grid_pos), 10, int(grid_pos), height - 10)
                    
                    painter.setBrush(QBrush(grid_color))
                    painter.setPen(QPen(grid_color.darker(120), 1))
                    
                    size = 6
                    points = [
                        QPoint(int(grid_pos), mid_y - size),
                        QPoint(int(grid_pos + size), mid_y),
                        QPoint(int(grid_pos), mid_y + size),
                        QPoint(int(grid_pos - size), mid_y)
                    ]
                    painter.drawPolygon(points)
                
                # Cue points with colors
                from utils.playlist import CueType
                cue_colors = {
                    CueType.HOT_CUE.value: QColor('#ff4d4d'),
                    CueType.LOAD.value: QColor('#4da6ff'),
                    CueType.LOOP.value: QColor('#4dff88')
                }
                
                filtered_cues = [c for c in self.cue_points if self._is_visible(c)]
                
                for cue in filtered_cues:
                    position = 10 + ((cue.get('start', 0) / total_duration) * (width - 20))
                    cue_type = cue.get('type', -1)
                    
                    if cue_type in cue_colors:
                        color = cue_colors[cue_type]
                        painter.setBrush(QBrush(color))
                        painter.setPen(QPen(color.darker(120), 1))
                        
                        if cue_type == CueType.HOT_CUE.value:
                            # Hot Cue - Square with number
                            size = 12
                            painter.drawRect(int(position) - size//2, mid_y - size//2, size, size)
                            painter.setPen(QPen(QColor('#FFFFFF'), 1))
                            hotcue_num = str(cue.get('hotcue', '-'))
                            painter.drawText(QRect(int(position) - 6, mid_y - 7, 12, 14), 
                                          Qt.AlignmentFlag.AlignCenter, hotcue_num)
                        
                        elif cue_type == CueType.LOAD.value:
                            # Memory Cue - Circle
                            painter.drawEllipse(QPoint(int(position), mid_y), 6, 6)
                            
                        elif cue_type == CueType.LOOP.value and cue.get('len', 0) > 0:
                            # Loop - Circle with rectangle
                            painter.drawEllipse(QPoint(int(position), mid_y), 6, 6)
                            
                            end_position = 10 + (((cue.get('start', 0) + cue.get('len', 0)) / total_duration) * (width - 20))
                            
                            loop_color = QColor(color)
                            loop_color.setAlpha(80)
                            painter.setBrush(QBrush(loop_color))
                            painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
                            painter.drawRect(QRect(int(position), mid_y - 10, int(end_position - position), 20))
            
            def _is_visible(self, cue):
                from utils.playlist import CueType
                cue_type = cue.get('type', -1)
                if cue_type == CueType.HOT_CUE.value:
                    return self.show_hotcues
                elif cue_type == CueType.LOAD.value:
                    return self.show_memory_cues
                elif cue_type == CueType.LOOP.value:
                    return self.show_loops
                return False
        
        return TimelineView(self.track, self.cue_points)
    
    def _create_cue_table(self):
        """Create detailed cue points table."""
        table = QTreeWidget()
        table.setAlternatingRowColors(True)
        table.setRootIsDecorated(False)
        table.setSortingEnabled(False)
        
        columns = ["#", "Time", "Type", "Length", "Name", "Details"]
        table.setColumnCount(len(columns))
        table.setHeaderLabels(columns)
        
        column_widths = {'#': 40, 'Time': 100, 'Type': 120, 'Length': 100, 'Name': 150, 'Details': 150}
        for i, col in enumerate(columns):
            table.setColumnWidth(i, column_widths.get(col, 100))
        
        self._populate_cue_table(table)
        return table
    
    def _populate_cue_table(self, table):
        """Populate cue table with data."""
        table.clear()
        
        def format_time(ms):
            seconds = ms / 1000
            minutes = int(seconds // 60)
            seconds = seconds % 60
            return f"{minutes:02d}:{seconds:05.2f}"
        
        # Add Grid Anchor if present and visible
        if self.track.grid_anchor_ms is not None and self.show_grid:
            grid_item = QTreeWidgetItem()
            grid_item.setText(0, "G")
            grid_item.setText(1, format_time(self.track.grid_anchor_ms))
            grid_item.setText(2, "Grid Anchor")
            grid_item.setText(3, "-")
            grid_item.setText(4, "BPM Beat 1")
            grid_item.setText(5, f"BPM: {self.track.bpm:.2f}")
            
            for col in range(6):
                grid_item.setForeground(col, QColor('#00FFFF'))
                
            table.addTopLevelItem(grid_item)
        
        # Add cue points
        row_index = 1
        
        from utils.playlist import CueType
        for cue in self.cue_points:
            if (cue.get('type') == CueType.HOT_CUE.value and not self.show_hotcues or
                cue.get('type') == CueType.LOAD.value and not self.show_memory_cues or
                cue.get('type') == CueType.LOOP.value and not self.show_loops):
                continue
                
            item = QTreeWidgetItem()
            
            cue_type = cue.get('type')
            type_str = "Unknown"
            details_str = ""
            name_str = cue.get('name', '')
            
            if cue_type == CueType.HOT_CUE.value:
                type_str = f"Hot Cue {cue.get('hotcue')}"
                details_str = "One-shot trigger point"
            elif cue_type == CueType.LOAD.value:
                type_str = "Memory Cue"
                details_str = "Navigation marker"
            elif cue_type == CueType.LOOP.value:
                type_str = "Loop"
                details_str = "Auto-repeating section"
            
            length_str = "-"
            if cue_type == CueType.LOOP.value and cue.get('len', 0) > 0:
                length_str = format_time(cue.get('len', 0))
            
            item.setText(0, str(row_index))
            item.setText(1, format_time(cue.get('start', 0)))
            item.setText(2, type_str)
            item.setText(3, length_str)
            item.setText(4, name_str)
            item.setText(5, details_str)
            
            # Color coding
            if cue_type == CueType.HOT_CUE.value:
                item.setForeground(2, QColor('#ff4d4d'))
            elif cue_type == CueType.LOAD.value:
                item.setForeground(2, QColor('#4da6ff'))
            elif cue_type == CueType.LOOP.value:
                item.setForeground(2, QColor('#4dff88'))
            
            table.addTopLevelItem(item)
            row_index += 1
    
    def _update_filters(self):
        """Update filters and refresh display."""
        self.show_hotcues = self.hotcue_check.isChecked()
        self.show_memory_cues = self.memory_check.isChecked()
        self.show_loops = self.loop_check.isChecked()
        self.show_grid = self.grid_check.isChecked()
        
        self.timeline_view.update_filters(
            self.show_hotcues, 
            self.show_memory_cues, 
            self.show_loops,
            self.show_grid
        )
        
        self._populate_cue_table(self.cue_table)
    
    def _export_to_clipboard(self):
        """Export cue point data to clipboard."""
        clipboard_text = f"Cue Points: {self.track.artist} - {self.track.title}\n"
        clipboard_text += f"BPM: {self.track.bpm:.1f}\n"
        if self.track.musical_key:
            key = self.key_translator.translate(self.track.musical_key)
            clipboard_text += f"Key: {key}\n"
        clipboard_text += f"Duration: {int(self.track.playtime // 60)}:{int(self.track.playtime % 60):02d}\n"
        
        if self.track.grid_anchor_ms is not None:
            ms = self.track.grid_anchor_ms
            minutes = int(ms // 60000)
            seconds = (ms % 60000) / 1000
            grid_time = f"{minutes:02d}:{seconds:06.3f}"
            clipboard_text += f"Grid Anchor: {grid_time}\n"
            
        clipboard_text += "-" * 50 + "\n"
        
        def format_time(ms):
            seconds = ms / 1000
            minutes = int(seconds // 60)
            seconds = seconds % 60
            return f"{minutes:02d}:{seconds:05.2f}"
        
        if self.track.grid_anchor_ms is not None and self.show_grid:
            clipboard_text += f"G. Grid Anchor @ {format_time(self.track.grid_anchor_ms)} - Beat 1\n"
        
        idx = 1
        from utils.playlist import CueType
        for cue in self.cue_points:
            if (cue.get('type') == CueType.HOT_CUE.value and not self.show_hotcues or
                cue.get('type') == CueType.LOAD.value and not self.show_memory_cues or
                cue.get('type') == CueType.LOOP.value and not self.show_loops):
                continue
                
            cue_type = cue.get('type')
            
            if cue_type == CueType.HOT_CUE.value:
                type_str = f"Hot Cue {cue.get('hotcue')}"
            elif cue_type == CueType.LOAD.value:
                type_str = "Memory Cue"
            elif cue_type == CueType.LOOP.value:
                type_str = "Loop"
                
            line = f"{idx}. {type_str} @ {format_time(cue.get('start', 0))}"
            
            if cue_type == CueType.LOOP.value and cue.get('len', 0) > 0:
                line += f" - Length: {format_time(cue.get('len', 0))}"
                
            name = cue.get('name', '')
            if name:
                line += f" - '{name}'"
                
            clipboard_text += line + "\n"
            idx += 1
        
        QApplication.clipboard().setText(clipboard_text)
        
        points_count = sum(1 for cue in self.cue_points if (
            (cue.get('type') == CueType.HOT_CUE.value and self.show_hotcues) or
            (cue.get('type') == CueType.LOAD.value and self.show_memory_cues) or
            (cue.get('type') == CueType.LOOP.value and self.show_loops)
        ))
        
        if self.track.grid_anchor_ms is not None and self.show_grid:
            points_count += 1
            
        QMessageBox.information(self, "Export Successful", 
                               f"Cue points data copied to clipboard.\n{points_count} points exported.")