"""
================================================================================
TRAKTOR BRIDGE - Professional Traktor to Pioneer CDJ/XML/M3U Converter
================================================================================

Version: 2.1
Author: Benoit (BSM) Saint-Moulin
Website: www.benoitsaintmoulin.com
GitHub: https://github.com/bsm3d/Traktor-Bridge

================================================================================
LICENSE & USAGE
================================================================================

**Open Source Project** - Free for educational and personal use

**Authorized**: 
- Educational use within academic framework
- Personal modification and use
- Citation with appropriate author attribution

**Restricted**: 
- Commercial use requires prior authorization from the author
- Redistribution must maintain original copyright notice

**Contact**: GitHub repository for authorization requests

================================================================================
"""

import sys
import json
import queue
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut

# Import modular components
from threads.conversion import ConversionThread
from utils.audio_manager import AudioManager
from utils.db_manager import DatabaseManager, CipherManager
from utils.loading_system import LoadingSystemMixin
from utils.key_translator import KeyTranslator
from utils.playlist import PlaylistManager, Node, PlaylistDetailsWindow

# Import UI modules
from ui.about import AboutDialog
from ui.details import DetailWindow
from ui.log import LogDialog, LogHandler
from ui.timeline import TimelineDialog
from ui.usage import UsageDialog
from ui.options import OptionsDialog

# Import / Export 
from parser.bsm_nml_parser import TraktorNMLParser, Track, Node, create_traktor_parser

class AppConfig:
    """Application configuration and constants."""
    VERSION = "2.0"
    APP_NAME = "Traktor Bridge"
    AUTHOR = "Benoit (BSM) Saint-Moulin"
    WEBSITE = "www.benoitsaintmoulin.com"
    
    # UI Configuration
    WINDOW_SIZE = (700, 650)
    MIN_SIZE = (700, 650)
    
    # Colors for styling
    COLORS = {
        'bg_dark': '#212529',
        'bg_med': '#343a40', 
        'bg_light': '#495057',
        'fg_light': '#f8f9fa',
        'fg_muted': '#adb5bd',
        'accent': '#00b4d8',
        'hover': '#0096c7'
    }


class ConverterGUI(QMainWindow, LoadingSystemMixin):
    """Main application window with modular architecture."""
    
    def __init__(self):
        super().__init__()
        
        # Core configuration
        self.config_file = Path(sys.argv[0]).parent / "converter_config.json"
        self.app_config = AppConfig()
        
        # Application state
        self.nml_path = ""
        self.output_path = ""
        self.music_root_path = ""
        self.structure = []
        self.selected_playlists = []
        
        # Settings with defaults - CDJ-2000NXS2 target
        self.settings = {
            'export_format': 'CDJ/USB',  # CDJ hardware export
            'key_format': 'Open Key',
            'copy_music': True,
            'verify_copy': False,
            'generate_anlz': True,
            'anlz_processes': 2,  # Nombre de process pour génération ANLZ (1-8)
            'master_volume': 70,
            'auto_load_collection': True,
            'confirm_exit': False,
            'cache_size': 30000,
            'memory_limit_mb': 100,
            'worker_threads': 2,
            'log_level': 'INFO',
            'debug_mode': False,
            'default_output_path': '',
            'rekordbox_version': 'RB6'
        }
        
        # Threading and communication
        self.cancel_event = threading.Event()
        self.prog_q = queue.Queue()
        
        # Core managers
        self.audio_manager = AudioManager()
        self.key_translator = KeyTranslator()
        self.log_handler = LogHandler()
        
        # UI elements
        self.playlist_tree = None
        self.convert_button = None
        self.cancel_button = None
        self.progress_bar = None
        self.progress_label = None
        self.playlist_info = None
        
        # Setup application
        self.setWindowTitle(f"{self.app_config.APP_NAME} v{self.app_config.VERSION}")
        self.resize(*self.app_config.WINDOW_SIZE)
        self.setMinimumSize(*self.app_config.MIN_SIZE)
        
        self._setup_ui()
        self._setup_menu()
        self._load_configuration()
        self._center_window()
        
        # Initialize audio
        self.audio_manager.initialize(self)
        
        # Start progress timer
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self._check_progress_queue)
        self.progress_timer.start(100)
        
        # Auto-load collection if enabled
        if self.settings.get('auto_load_collection', True):
            QTimer.singleShot(500, self._auto_load_collection)
    
    def _setup_ui(self):
        """Setup the main user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Apply dark theme styling (ORIGINAL)
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {self.app_config.COLORS['bg_dark']};
                color: {self.app_config.COLORS['fg_light']};
            }}
            QLabel {{ 
                color: {self.app_config.COLORS['fg_light']}; 
            }}
            QPushButton {{
                background-color: {self.app_config.COLORS['bg_med']};
                color: {self.app_config.COLORS['fg_light']};
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QPushButton:hover {{ 
                background-color: {self.app_config.COLORS['bg_light']}; 
            }}
            QLineEdit {{
                background-color: {self.app_config.COLORS['bg_med']};
                color: {self.app_config.COLORS['fg_light']};
                border: none;
                padding: 6px;
                border-radius: 4px;
            }}
            QComboBox {{
                background-color: {self.app_config.COLORS['bg_med']};
                color: {self.app_config.COLORS['fg_light']};
                border: none;
                padding: 6px;
                border-radius: 4px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {self.app_config.COLORS['bg_med']};
                color: {self.app_config.COLORS['fg_light']};
                selection-background-color: {self.app_config.COLORS['accent']};
            }}
            QProgressBar {{
                border: none;
                background-color: {self.app_config.COLORS['bg_med']};
                text-align: center;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{ 
                background-color: {self.app_config.COLORS['accent']}; 
                border-radius: 4px;
            }}
            QTreeWidget {{
                background-color: {self.app_config.COLORS['bg_med']};
                color: {self.app_config.COLORS['fg_light']};
                border: none;
                alternate-background-color: {self.app_config.COLORS['bg_light']};
            }}
            QHeaderView::section {{
                background-color: {self.app_config.COLORS['bg_dark']};
                color: {self.app_config.COLORS['fg_light']};
                padding: 5px;
                border: none;
            }}
            QCheckBox {{ 
                color: {self.app_config.COLORS['fg_light']}; 
            }}
            QMenu {{
                background-color: {self.app_config.COLORS['bg_med']};
                color: {self.app_config.COLORS['fg_light']};
                border: 1px solid {self.app_config.COLORS['bg_light']};
            }}
            QMenu::item:selected {{
                background-color: {self.app_config.COLORS['accent']};
            }}
        """)
        
        # Title section (ORIGINAL)
        title_label = QLabel("Traktor Bridge")
        title_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        subtitle_label = QLabel("Professional Traktor to Pioneer CDJ/XML/M3U Converter")
        subtitle_label.setStyleSheet(f"color: {self.app_config.COLORS['fg_muted']};")
        
        main_layout.addWidget(title_label)
        main_layout.addWidget(subtitle_label)
        main_layout.addSpacing(15)
        
        # File input sections (ORIGINAL)
        self._create_nml_input_section(main_layout)
        main_layout.addSpacing(15)
        
        self._create_music_input_section(main_layout)
        main_layout.addSpacing(10)
        
        # Playlist section (ORIGINAL)
        self._create_playlist_section(main_layout)
        
        # Options section (ORIGINAL avec corrections CDJ)
        self._create_options_section(main_layout)
        
        # Progress section (ORIGINAL)
        self._create_progress_section(main_layout)
        main_layout.addSpacing(10)
        
        # Action buttons (ORIGINAL)
        self._create_action_section(main_layout)
        
        # Close section (ORIGINAL)
        self._create_close_section(main_layout)
    
    def _create_nml_input_section(self, parent_layout):
        """Create NML file input section."""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel("1. Traktor NML File")
        label.setStyleSheet("color: #00b4d8; font-weight: bold;")
        layout.addWidget(label)
        
        input_frame = QFrame()
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(0, 0, 0, 0)
        
        self.nml_input = QLineEdit()
        self.nml_input.setPlaceholderText("Select your collection.nml file...")
        if self.nml_path:
            self.nml_input.setText(self.nml_path)
        
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_nml)
        
        input_layout.addWidget(self.nml_input)
        input_layout.addWidget(browse_button)
        
        layout.addWidget(input_frame)
        parent_layout.addWidget(frame)
    
    def _browse_nml(self):
        """Browse for NML file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Traktor NML File", 
            self.nml_path, "Traktor NML Files (*.nml);;All Files (*)"
        )
        if file_path:
            self.nml_path = file_path
            self.nml_input.setText(file_path)
            self._save_configuration()
            self._load_playlists()
    
    def _auto_load_collection(self):
        """Try to auto-load common Traktor collection locations."""
        if self.nml_path and Path(self.nml_path).exists():
            self._load_playlists()
            return
        
        # Search common Traktor locations
        import os
        possible_paths = []
        
        if os.name == 'nt':  # Windows
            traktor_paths = [
                os.path.expanduser("~/Documents/Native Instruments/Traktor Pro 3/collection.nml"),
                os.path.expanduser("~/Documents/Native Instruments/Traktor/collection.nml"),
            ]
        else:  # macOS/Linux
            traktor_paths = [
                os.path.expanduser("~/Documents/Native Instruments/Traktor Pro 3/collection.nml"),
                os.path.expanduser("~/Documents/Native Instruments/Traktor/collection.nml"),
            ]
        
        for path in traktor_paths:
            if os.path.exists(path):
                self.nml_path = path
                self.nml_input.setText(path)
                self._save_configuration()
                self._load_playlists()
                break

    def _reload_current_collection(self):
        """Reload current collection."""
        if self.nml_path:
            self._load_playlists()
        else:
            QMessageBox.information(self, "No Collection", "Please select an NML file first.")
    
    def _create_music_input_section(self, parent_layout):
        """Create music root folder input section."""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel("2. Music Root Folder (Optional)")
        label.setStyleSheet("color: #00b4d8; font-weight: bold;")
        layout.addWidget(label)
        
        input_frame = QFrame()
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(0, 0, 0, 0)
        
        self.music_input = QLineEdit()
        self.music_input.setPlaceholderText("Select music root folder...")
        
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_music_root)
        
        input_layout.addWidget(self.music_input)
        input_layout.addWidget(browse_button)
        
        layout.addWidget(input_frame)
        parent_layout.addWidget(frame)
    
    def _create_playlist_section(self, parent_layout):
        """Create playlist selection section."""
        playlist_frame = QFrame()
        playlist_layout = QVBoxLayout(playlist_frame)
        
        # Header
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        playlist_title = QLabel("3. Select Playlists")
        playlist_title.setStyleSheet("color: #00b4d8; font-weight: bold;")
        
        self.playlist_info = QLabel("Load a collection first...")
        self.playlist_info.setStyleSheet(f"color: {self.app_config.COLORS['fg_muted']};")
        
        details_button = QPushButton("Details")
        details_button.clicked.connect(self._show_details)
        
        header_layout.addWidget(playlist_title)
        header_layout.addWidget(self.playlist_info)
        header_layout.addStretch()
        header_layout.addWidget(details_button)
        
        playlist_layout.addLayout(header_layout)
        
        # Tree widget
        self.playlist_tree = QTreeWidget()
        self.playlist_tree.setHeaderLabels(["Playlist", "Tracks", "Type"])
        self.playlist_tree.setAlternatingRowColors(True)
        self.playlist_tree.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.playlist_tree.itemSelectionChanged.connect(self._on_playlist_selection_changed)
        self.playlist_tree.itemDoubleClicked.connect(self._on_playlist_double_clicked)
        
        playlist_layout.addWidget(self.playlist_tree)
        parent_layout.addWidget(playlist_frame)
    
    def _create_options_section(self, parent_layout):
        """Create options section avec corrections CDJ."""
        options_frame = QFrame()
        options_layout = QHBoxLayout(options_frame)
        options_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left side - copy options
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.copy_music_check = QCheckBox("Copy Music Files")
        self.copy_music_check.setChecked(self.settings['copy_music'])
        self.copy_music_check.toggled.connect(self._on_copy_music_toggled)
        
        self.verify_copy_check = QCheckBox("Verify File Copy")
        self.verify_copy_check.setChecked(self.settings['verify_copy'])
        self.verify_copy_check.toggled.connect(self._on_verify_copy_toggled)
        
        left_layout.addWidget(self.copy_music_check)
        left_layout.addWidget(self.verify_copy_check)
        left_layout.addStretch()
        
        # Right side - export format with new options CORRIGÉ
        right_frame = QFrame()
        right_layout = QHBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        format_label = QLabel("Export:")
        self.export_format_button = QPushButton(self.settings['export_format'])
        
        export_menu = QMenu(self)
        
        # Updated export formats
        export_formats = [
            "CDJ/USB",           # New CDJ PDB + ANLZ format
            "Rekordbox Database", # New Rekordbox software format
            "Rekordbox XML",     # Updated XML format
            "M3U"               # Existing M3U format
        ]
        
        for fmt in export_formats:
            action = export_menu.addAction(fmt)
            action.triggered.connect(lambda checked, f=fmt: self._change_export_format(f))
        
        self.export_format_button.setMenu(export_menu)
        
        right_layout.addWidget(format_label)
        right_layout.addWidget(self.export_format_button)
        
        options_layout.addWidget(left_frame)
        options_layout.addStretch()
        options_layout.addWidget(right_frame)
        
        parent_layout.addWidget(options_frame)
    
    def _change_export_format(self, format_name: str):
        """Handle export format change CORRIGÉ."""
        self.settings['export_format'] = format_name
        self.export_format_button.setText(format_name)
        self._save_configuration()
        
        # Show CDJ info if selecting CDJ format
        if format_name == "CDJ/USB":
            self._show_cdj_info_dialog()
    
    def _show_cdj_info_dialog(self):
        """Show CDJ-2000NXS2 specific information"""
        msg = QMessageBox(self)
        msg.setWindowTitle("CDJ Hardware Export")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("CDJ Hardware Export Selected")
        msg.setInformativeText(
            "<b>CDJ-2000NXS2 Hardware Requirements:</b><br><br>"
            "• USB must be formatted <b>FAT32</b> (MBR partition)<br>"
            "• Maximum ~10,000 tracks supported<br>"
            "• ASCII-only filenames (no accents)<br>"
            "• Maximum path length: 256 characters<br><br>"
            "<b>Traktor Bridge will automatically:</b><br>"
            "• Generate binary PDB database<br>"
            "• Create ANLZ waveform files<br>"
            "• Sanitize file paths for compatibility<br>"
            "• Create DeviceSQL.edb for CDJ recognition"
        )
        msg.exec()
    
    def _on_copy_music_toggled(self, checked: bool):
        """Handle copy music checkbox"""
        self.settings['copy_music'] = checked
        self.verify_copy_check.setEnabled(checked)
        self._save_configuration()
    
    def _on_verify_copy_toggled(self, checked: bool):
        """Handle verify copy checkbox"""
        self.settings['verify_copy'] = checked
        self._save_configuration()
    
    def _create_progress_section(self, parent_layout):
        """Create progress section."""
        progress_frame = QFrame()
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        
        self.progress_label = QLabel("Ready to convert...")
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_label)
        
        parent_layout.addWidget(progress_frame)
    
    def _create_action_section(self, parent_layout):
        """Create action buttons section."""
        action_frame = QFrame()
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(0, 0, 0, 0)
        
        self.convert_button = QPushButton("CONVERT")
        self.convert_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.app_config.COLORS['accent']};
                color: {self.app_config.COLORS['fg_light']};
                font-weight: bold;
                font-size: 11pt;
                padding: 12px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {self.app_config.COLORS['hover']};
            }}
            QPushButton:disabled {{
                background-color: {self.app_config.COLORS['bg_light']};
                color: {self.app_config.COLORS['fg_muted']};
            }}
        """)
        self.convert_button.clicked.connect(self._start_conversion)
        
        self.cancel_button = QPushButton("CANCEL")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_conversion)
        
        action_layout.addWidget(self.convert_button)
        action_layout.addWidget(self.cancel_button)
        
        parent_layout.addWidget(action_frame)
    
    def _create_close_section(self, parent_layout):
        """Create close button section."""
        close_frame = QFrame()
        close_layout = QHBoxLayout(close_frame)
        close_layout.setContentsMargins(0, 0, 0, 0)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        
        close_layout.addStretch()
        close_layout.addWidget(close_button)
        
        parent_layout.addWidget(close_frame)
    
    def _setup_menu(self):
        """Setup application menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open NML...", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._browse_nml)
        file_menu.addAction(open_action)
        
        reload_action = QAction("Reload Collection", self)
        reload_action.setShortcut(QKeySequence("Ctrl+R"))
        reload_action.triggered.connect(self._reload_current_collection)
        file_menu.addAction(reload_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Options menu
        options_menu = menubar.addMenu("Options")
        
        preferences_action = QAction("Preferences...", self)
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.triggered.connect(self._show_options_dialog)
        options_menu.addAction(preferences_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        log_action = QAction("View Log", self)
        log_action.setShortcut(QKeySequence("Ctrl+L"))
        log_action.triggered.connect(self._show_log_window)
        help_menu.addAction(log_action)
        
        usage_action = QAction("Usage Guide", self)
        usage_action.setShortcut(QKeySequence("F1"))
        usage_action.triggered.connect(self._show_usage_dialog)
        help_menu.addAction(usage_action)
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)
    
    def _browse_music_root(self):
        """Browse for music root folder."""
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Music Root Folder", self.music_root_path
        )
        if folder_path:
            self.music_root_path = folder_path
            self.music_input.setText(folder_path)
            self._save_configuration()
    
    def _browse_output(self):
        """Browse for output directory."""
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self.output_path
        )
        if folder_path:
            self.output_path = folder_path
            self._save_configuration()
    
    def _load_configuration(self):
        """Load configuration from file."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Load paths
                self.nml_path = config.get('nml_path', '')
                self.output_path = config.get('output_path', '')
                self.music_root_path = config.get('music_root_path', '')
                
                # Load settings
                loaded_settings = config.get('settings', {})
                self.settings.update(loaded_settings)
                
                # Update UI
                self.nml_input.setText(self.nml_path)
                self.music_input.setText(self.music_root_path)
                
                self.export_format_button.setText(self.settings['export_format'])
                self.copy_music_check.setChecked(self.settings['copy_music'])
                self.verify_copy_check.setChecked(self.settings['verify_copy'])
                
                self._log_message("Configuration loaded successfully")
                
        except Exception as e:
            self._log_message(f"Failed to load configuration: {e}", logging.WARNING)
    
    def _save_configuration(self):
        """Save configuration to file."""
        try:
            config = {
                'nml_path': self.nml_path,
                'output_path': self.output_path,
                'music_root_path': self.music_root_path,
                'settings': self.settings
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self._log_message(f"Failed to save configuration: {e}", logging.WARNING)
    
    def _load_playlists(self):
        """Load playlists from NML file."""
        if not self.nml_path:
            self._log_message("No NML file selected", logging.WARNING)
            return
        
        if not Path(self.nml_path).exists():
            self._log_message("NML file not found", logging.ERROR)
            return
        
        try:
            self._log_message(f"Loading collection from: {self.nml_path}")
            
            # Use loading system mixin
            self.start_loading("Loading Traktor collection...")
            
            # Create parser
            parser = create_traktor_parser(self.nml_path, self.music_root_path)
            self.structure = parser.get_playlists_with_structure()
            
            # Update UI
            self._populate_playlist_tree()
            self._update_playlist_info()
            
            self.stop_loading()
            self._log_message("Collection loaded successfully")
            
        except Exception as e:
            self.stop_loading()
            self._log_message(f"Failed to load collection: {e}", logging.ERROR)
            QMessageBox.critical(self, "Error", f"Failed to load collection:\n{str(e)}")
    
    def _populate_playlist_tree(self):
        """Populate the playlist tree widget."""
        self.playlist_tree.clear()
        
        def add_node_to_tree(node, parent_item=None):
            if hasattr(node, 'type'):
                if node.type == 'folder':
                    folder_item = QTreeWidgetItem()
                    folder_item.setText(0, f"📁 {node.name}")
                    folder_item.setText(1, "")
                    folder_item.setText(2, "Folder")
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, node)
                    
                    if parent_item:
                        parent_item.addChild(folder_item)
                    else:
                        self.playlist_tree.addTopLevelItem(folder_item)
                    
                    if hasattr(node, 'children'):
                        for child in node.children:
                            add_node_to_tree(child, folder_item)
                    
                    folder_item.setExpanded(True)
                    
                elif node.type in ['playlist', 'smartlist']:
                    playlist_item = QTreeWidgetItem()
                    icon = "🎵" if node.type == 'playlist' else "🔍"
                    playlist_item.setText(0, f"{icon} {node.name}")
                    
                    track_count = len(getattr(node, 'tracks', []))
                    playlist_item.setText(1, str(track_count))
                    playlist_item.setText(2, node.type.title())
                    playlist_item.setData(0, Qt.ItemDataRole.UserRole, node)
                    
                    if parent_item:
                        parent_item.addChild(playlist_item)
                    else:
                        self.playlist_tree.addTopLevelItem(playlist_item)
        
        for node in self.structure:
            add_node_to_tree(node)
    
    def _update_playlist_info(self):
        """Update playlist information label."""
        total_playlists = self._count_playlists(self.structure)
        total_tracks = len(self._collect_all_tracks())
        
        self.playlist_info.setText(f"{total_playlists} playlists, {total_tracks} tracks")
    
    def _count_playlists(self, structure: List) -> int:
        """Count total playlists in structure."""
        count = 0
        for node in structure:
            if hasattr(node, 'type'):
                if node.type in ['playlist', 'smartlist']:
                    count += 1
                elif node.type == 'folder' and hasattr(node, 'children'):
                    count += self._count_playlists(node.children)
        return count
    
    def _collect_all_tracks(self) -> List:
        """Collect all unique tracks from structure."""
        all_tracks = []
        track_seen = set()
        
        def collect_recursive(nodes: List):
            for node in nodes:
                if hasattr(node, 'type'):
                    if node.type in ['playlist', 'smartlist'] and hasattr(node, 'tracks'):
                        for track in node.tracks:
                            track_key = getattr(track, 'audio_id', None) or getattr(track, 'file_path', None)
                            if track_key and track_key not in track_seen:
                                all_tracks.append(track)
                                track_seen.add(track_key)
                    elif node.type == 'folder' and hasattr(node, 'children'):
                        collect_recursive(node.children)
        
        collect_recursive(self.structure)
        return all_tracks
    
    def _on_playlist_selection_changed(self):
        """Handle playlist selection changes."""
        selected_items = self.playlist_tree.selectedItems()
        self.selected_playlists = []
        
        for item in selected_items:
            node = item.data(0, Qt.ItemDataRole.UserRole)
            if node and hasattr(node, 'type') and node.type in ['playlist', 'smartlist']:
                self.selected_playlists.append(node)
        
        # Update button state
        has_selection = len(self.selected_playlists) > 0
        has_collection = len(self.structure) > 0
        
        self.convert_button.setEnabled(has_collection)
    
    def _on_playlist_double_clicked(self, item, column):
        """Handle playlist double-click."""
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node and hasattr(node, 'type') and node.type in ['playlist', 'smartlist']:
            self._show_playlist_details(node)
    
    def _show_playlist_details(self, playlist):
        """Show playlist details dialog."""
        dialog = PlaylistDetailsWindow(playlist, self.key_translator, self.audio_manager, self)
        dialog.exec()
    
    def _show_details(self):
        """Show details for selected playlist."""
        selected_items = self.playlist_tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            node = item.data(0, Qt.ItemDataRole.UserRole)
            if node and hasattr(node, 'type') and node.type in ['playlist', 'smartlist']:
                self._show_playlist_details(node)
    
    def _check_progress_queue(self):
        """Check for progress updates from worker thread."""
        try:
            while not self.prog_q.empty():
                message_type, data = self.prog_q.get_nowait()
                
                if message_type == "progress":
                    percentage, message = data
                    self.progress_bar.setValue(percentage)
                    self.progress_label.setText(message)
        
        except queue.Empty:
            pass
    
    def _start_conversion(self):
        """Start the conversion process."""
        # Validate inputs
        if not self.structure:
            QMessageBox.warning(self, "Warning", "Please load a Traktor collection first.")
            return
        
        # Select output directory if not set
        if not self.output_path:
            folder_path = QFileDialog.getExistingDirectory(
                self, "Select Output Directory"
            )
            if folder_path:
                self.output_path = folder_path
                self._save_configuration()
            else:
                return
        
        # Show confirmation with format info
        format_name = self.settings['export_format']
        selected_count = len(self.selected_playlists)
        total_count = self._count_playlists(self.structure)
        
        if selected_count > 0:
            message = f"Export {selected_count} selected playlist(s) to {format_name}?"
        else:
            message = f"Export all {total_count} playlist(s) to {format_name}?"
        
        reply = QMessageBox.question(
            self, "Confirm Export", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Reset cancel event
        self.cancel_event.clear()
        
        # Update UI for conversion
        self.convert_button.setEnabled(False)
        self.convert_button.setText("Converting...")
        self.cancel_button.setEnabled(True)
        
        # Log conversion start
        self._log_message(f"Starting conversion: {format_name}")
        self._log_message(f"Output: {self.output_path}")
        self._log_message(f"Selected playlists: {selected_count}")
        
        # Start conversion thread
        self.conversion_thread = ConversionThread(
            output_path=self.output_path,
            selected_playlists=self.selected_playlists,
            structure=self.structure,
            export_format=format_name,
            copy_music=self.settings['copy_music'],
            verify_copy=self.settings['verify_copy'],
            key_format=self.settings['key_format'],
            progress_queue=self.prog_q,
            cancel_event=self.cancel_event,
            settings=self.settings
        )
        
        self.conversion_thread.finished.connect(self._on_conversion_finished)
        self.conversion_thread.start()
    
    def _cancel_conversion(self):
        """Cancel the current conversion."""
        self.cancel_event.set()
        self.cancel_button.setEnabled(False)
        self.progress_label.setText("Cancelling...")
        self._log_message("Conversion cancelled by user")
    
    def _on_conversion_finished(self, status, message):
        """Handle conversion completion."""
        self.convert_button.setEnabled(True)
        self.convert_button.setText("CONVERT")
        self.cancel_button.setEnabled(False)
        
        if status == "completed":
            self.progress_bar.setValue(100)
            self.progress_label.setText("Conversion completed successfully!")
            self._log_message(f"Conversion completed successfully: {message}")
            
            # Show format-specific success message
            format_info = self._get_format_success_info()
            success_msg = f"Conversion completed!\n\nOutput: {self.output_path}\n\n{format_info}"
            QMessageBox.information(self, "Success", success_msg)
            
        elif status == "cancelled":
            self.progress_bar.setValue(0)
            self.progress_label.setText("Conversion cancelled.")
            self._log_message("Conversion was cancelled")
            
        elif status == "error":
            self.progress_bar.setValue(0)
            self.progress_label.setText("Conversion failed.")
            self._log_message(f"Conversion failed: {message}", logging.ERROR)
            QMessageBox.critical(self, "Error", f"Conversion failed:\n{message}")
    
    def _get_format_success_info(self):
        """Get format-specific success information."""
        format_name = self.settings['export_format']
        
        if format_name == "CDJ/USB":
            return ("Created CDJ hardware export:\n"
                   "• Binary PDB database (export.pdb + DeviceSQL.edb)\n"
                   "• ANLZ waveform files (.DAT + .EXT)\n"
                   "• Ready for USB installation on CDJ-2000NXS2")
        
        elif format_name == "Rekordbox Database":
            return ("Created Rekordbox software database:\n"
                   "• SQLite/SQLCipher database\n"
                   "• Compatible with Rekordbox software\n"
                   "• Import via Rekordbox preferences")
        
        elif format_name == "Rekordbox XML":
            return ("Created Rekordbox XML file:\n"
                   "• Import into Rekordbox software\n"
                   "• Contains playlists and track metadata\n"
                   "• Standard XML format")
        
        elif format_name == "M3U":
            return ("Created M3U playlist files:\n"
                   "• Compatible with most DJ software\n"
                   "• Individual .m3u files per playlist\n"
                   "• Universal playlist format")
        
        return "Export completed successfully!"
    
    def _show_options_dialog(self):
        """Show options dialog."""
        dialog = OptionsDialog(self.app_config, self.settings, self)
        dialog.settings_changed.connect(self._on_settings_changed)
        if dialog.exec():
            self.settings = dialog.get_settings()
            self._save_configuration()
    
    def _on_settings_changed(self, new_settings):
        """Handle settings changes."""
        self.settings.update(new_settings)
        self._save_configuration()
        
        # Update UI elements
        self.copy_music_check.setChecked(self.settings['copy_music'])
        self.verify_copy_check.setChecked(self.settings['verify_copy'])
        self.export_format_button.setText(self.settings['export_format'])
        
    def _show_log_window(self):
        """Show the log window."""
        self.log_handler.show_log_window(self, self.app_config)
    
    def _show_usage_dialog(self):
        """Show usage guide dialog."""
        dialog = UsageDialog(self.app_config, self)
        dialog.exec()
    
    def _show_about_dialog(self):
        """Show about dialog."""
        dialog = AboutDialog(self.app_config, self)
        dialog.exec()
    
    def _center_window(self):
        """Center the window on screen."""
        screen = QApplication.primaryScreen().geometry()
        window = self.geometry()
        x = (screen.width() - window.width()) // 2
        y = (screen.height() - window.height()) // 2
        self.move(x, y)
    
    def _log_message(self, message: str, level: int = logging.INFO):
        """Log message to handler and console."""
        level_names = {
            logging.DEBUG: "DEBUG",
            logging.INFO: "INFO", 
            logging.WARNING: "WARNING",
            logging.ERROR: "ERROR",
            logging.CRITICAL: "CRITICAL"
        }
        level_name = level_names.get(level, "INFO")
        
        # Send to log handler
        self.log_handler.log_message(message, level_name)
        
        # Also log to console
        logging.log(level, message)
    
    def closeEvent(self, event):
        """Handle application close event."""
        # Check for confirmation if enabled
        if self.settings.get('confirm_exit', False):
            reply = QMessageBox.question(
                self, "Confirm Exit",
                "Are you sure you want to exit Traktor Bridge?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        
        # Cancel any running operations
        self.cancel_event.set()
        
        # Save configuration
        self._save_configuration()
        
        # Clean up audio
        if hasattr(self, 'audio_manager'):
            self.audio_manager.cleanup()
        
        # Wait for threads to finish
        if hasattr(self, 'loading_thread') and self.loading_thread.isRunning():
            self.loading_thread.wait(3000)
        
        if hasattr(self, 'conversion_thread') and self.conversion_thread.isRunning():
            self.conversion_thread.wait(5000)
        
        event.accept()


def setup_logging():
    """Configure application logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('traktor_bridge.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName(AppConfig.APP_NAME)
    app.setApplicationVersion(AppConfig.VERSION)
    app.setOrganizationName(AppConfig.AUTHOR)
    
    # Setup logging
    setup_logging()
    logging.info(f"Starting {AppConfig.APP_NAME} v{AppConfig.VERSION}")
    
    try:
        window = ConverterGUI()
        
        # Connect logs to GUI after window creation
        log_dialog = LogDialog(window.app_config, window)
        
        class GuiLogHandler(logging.Handler):
            def __init__(self, log_dialog):
                super().__init__()
                self.log_dialog = log_dialog
            
            def emit(self, record):
                if self.log_dialog:
                    msg = self.format(record)
                    self.log_dialog.append_log(msg, record.levelname)
        
        gui_handler = GuiLogHandler(log_dialog)
        gui_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(gui_handler)
        window.log_handler.set_log_dialog(log_dialog)
        
        window.show()
        
        logging.info("Application started successfully")
        return app.exec()
        
    except Exception as e:
        logging.error(f"Failed to start application: {e}")
        logging.error("", exc_info=True)
        
        try:
            QMessageBox.critical(
                None, "Startup Error", 
                f"Failed to start {AppConfig.APP_NAME}:\n\n{str(e)}\n\nCheck the log file for details."
            )
        except:
            pass
        
        return 1


if __name__ == "__main__":
    sys.exit(main())

    
    def _show_format_menu(self):
        """Show export format selection menu CORRIGÉ"""
        menu = QMenu(self)
        
        # Formats disponibles avec descriptions
        formats = [
            ("CDJ/USB", "🎛️ CDJ Hardware (PDB Binary + ANLZ)", "Export for CDJ-2000NXS2 hardware"),
            ("Rekordbox Database", "💾 Rekordbox Software (SQLite)", "Export for Rekordbox software"),
            ("Rekordbox XML", "📄 XML Format", "Standard XML for import into Rekordbox"),
            ("M3U Playlists", "📝 M3U Files", "Universal playlist format")
        ]
        
        for format_key, format_title, format_desc in formats:
            action = menu.addAction(format_title)
            action.setToolTip(format_desc)
            action.triggered.connect(lambda checked, fmt=format_key: self._on_format_selected(fmt))
            
            # Mark current format
            if format_key == self.settings['export_format']:
                action.setCheckable(True)
                action.setChecked(True)
        
        menu.exec(self.export_format_button.mapToGlobal(self.export_format_button.rect().bottomLeft()))
    
    def _on_format_selected(self, format_name: str):
        """Handle format selection CORRIGÉ"""
        self.settings['export_format'] = format_name
        self.export_format_button.setText(format_name)
        self._save_configuration()
        self._update_ui_for_format()
        
        # Show info dialog for CDJ format
        if format_name == "CDJ/USB":
            self._show_cdj_info_dialog()
    
    def _show_cdj_info_dialog(self):
        """Show CDJ-2000NXS2 specific information"""
        msg = QMessageBox(self)
        msg.setWindowTitle("CDJ Hardware Export")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("CDJ-2000NXS2 Hardware Export")
        msg.setInformativeText(
            "<b>Requirements for CDJ hardware:</b><br><br>"
            "• USB must be formatted <b>FAT32</b> (MBR partition)<br>"
            "• Maximum ~10,000 tracks supported<br>"
            "• ASCII-only filenames (no accents)<br>"
            "• Maximum path length: 256 characters<br><br>"
            "<b>Traktor Bridge will automatically:</b><br>"
            "• Generate binary PDB database<br>"
            "• Create ANLZ waveform files<br>"
            "• Sanitize file paths for compatibility<br>"
            "• Create DeviceSQL.edb for CDJ recognition"
        )
        msg.exec()
    
    def _update_ui_for_format(self):
        """Update UI elements based on selected format"""
        format_name = self.settings['export_format']
        
        # CDJ model selector visibility
        is_cdj_export = format_name in ["CDJ/USB", "Database"]
        self.cdj_model_combo.setEnabled(is_cdj_export)
        
        # Copy options for formats that support it
        supports_copy = format_name in ["CDJ/USB", "Database", "M3U Playlists"]
        self.copy_music_check.setEnabled(supports_copy)
        self.verify_copy_check.setEnabled(supports_copy and self.copy_music_check.isChecked())
        
        # Update progress label hint
        if format_name == "CDJ/USB":
            self.progress_label.setText("Ready to export for CDJ hardware...")
        elif format_name == "Rekordbox Database":
            self.progress_label.setText("Ready to export Rekordbox database...")
        elif format_name == "Rekordbox XML":
            self.progress_label.setText("Ready to export XML file...")
        elif format_name == "M3U Playlists":
            self.progress_label.setText("Ready to export M3U playlists...")
    
    def _on_cdj_model_changed(self, model_name: str):
        """Handle CDJ model selection change"""
        self.settings['cdj_target'] = model_name
        self._save_configuration()
        self._log_message(f"CDJ target changed to: {model_name}")
    
    def _on_copy_music_toggled(self, checked: bool):
        """Handle copy music checkbox"""
        self.settings['copy_music'] = checked
        self.verify_copy_check.setEnabled(checked)
        self._save_configuration()
    
    def _on_verify_copy_toggled(self, checked: bool):
        """Handle verify copy checkbox"""
        self.settings['verify_copy'] = checked
        self._save_configuration()
    
    def _setup_menu(self):
        """Setup application menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open NML...", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._browse_nml)
        file_menu.addAction(open_action)
        
        reload_action = QAction("Reload Collection", self)
        reload_action.setShortcut(QKeySequence("Ctrl+R"))
        reload_action.triggered.connect(self._reload_current_collection)
        file_menu.addAction(reload_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Options menu
        options_menu = menubar.addMenu("Options")
        
        preferences_action = QAction("Preferences...", self)
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.triggered.connect(self._show_options_dialog)
        options_menu.addAction(preferences_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        log_action = QAction("View Log", self)
        log_action.setShortcut(QKeySequence("Ctrl+L"))
        log_action.triggered.connect(self._show_log_window)
        help_menu.addAction(log_action)
        
        usage_action = QAction("Usage Guide", self)
        usage_action.setShortcut(QKeySequence("F1"))
        usage_action.triggered.connect(self._show_usage_dialog)
        help_menu.addAction(usage_action)
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)
    
    def _browse_nml(self):
        """Browse for NML file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Traktor NML File", 
            self.nml_path, "Traktor NML Files (*.nml);;All Files (*)"
        )
        if file_path:
            self.nml_path = file_path
            self.nml_input.setText(file_path)
            self._save_configuration()
            self._load_playlists()
    
    def _browse_music_root(self):
        """Browse for music root folder."""
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Music Root Folder", self.music_root_path
        )
        if folder_path:
            self.music_root_path = folder_path
            self.music_input.setText(folder_path)
            self._save_configuration()
    
    def _browse_output(self):
        """Browse for output directory."""
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self.output_path
        )
        if folder_path:
            self.output_path = folder_path
            self.output_input.setText(folder_path)
            self._save_configuration()
    
    def _load_configuration(self):
        """Load configuration from file."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Load paths
                self.nml_path = config.get('nml_path', '')
                self.output_path = config.get('output_path', '')
                self.music_root_path = config.get('music_root_path', '')
                
                # Load settings
                loaded_settings = config.get('settings', {})
                self.settings.update(loaded_settings)
                
                # Update UI
                self.nml_input.setText(self.nml_path)
                self.output_input.setText(self.output_path)
                self.music_input.setText(self.music_root_path)
                
                self.export_format_button.setText(self.settings['export_format'])
                self.cdj_model_combo.setCurrentText(self.settings['cdj_target'])
                self.copy_music_check.setChecked(self.settings['copy_music'])
                self.verify_copy_check.setChecked(self.settings['verify_copy'])
                
                self._log_message("Configuration loaded successfully")
                
        except Exception as e:
            self._log_message(f"Failed to load configuration: {e}", logging.WARNING)
    
    def _save_configuration(self):
        """Save configuration to file."""
        try:
            config = {
                'nml_path': self.nml_path,
                'output_path': self.output_path,
                'music_root_path': self.music_root_path,
                'settings': self.settings
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self._log_message(f"Failed to save configuration: {e}", logging.WARNING)
    
    def _auto_load_collection(self):
        """Auto-load collection if NML path is configured."""
        if self.nml_path and Path(self.nml_path).exists():
            self._log_message("Auto-loading Traktor collection...")
            self._load_playlists()
    
    def _load_playlists(self):
        """Load playlists from NML file."""
        if not self.nml_path:
            self._log_message("No NML file selected", logging.WARNING)
            return
        
        if not Path(self.nml_path).exists():
            self._log_message("NML file not found", logging.ERROR)
            return
        
        try:
            self._log_message(f"Loading collection from: {self.nml_path}")
            
            # Use loading system mixin
            self.start_loading("Loading Traktor collection...")
            
            # Create parser
            parser = create_traktor_parser(self.nml_path, self.music_root_path)
            self.structure = parser.get_playlists_with_structure()
            
            # Update UI
            self._populate_playlist_tree()
            self._update_playlist_info()
            
            self.stop_loading()
            self._log_message("Collection loaded successfully")
            
        except Exception as e:
            self.stop_loading()
            self._log_message(f"Failed to load collection: {e}", logging.ERROR)
            QMessageBox.critical(self, "Error", f"Failed to load collection:\n{str(e)}")
    
    def _populate_playlist_tree(self):
        """Populate the playlist tree widget."""
        self.playlist_tree.clear()
        
        def add_node_to_tree(node, parent_item=None):
            if hasattr(node, 'type'):
                if node.type == 'folder':
                    folder_item = QTreeWidgetItem()
                    folder_item.setText(0, f"📁 {node.name}")
                    folder_item.setText(1, "")
                    folder_item.setText(2, "Folder")
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, node)
                    
                    if parent_item:
                        parent_item.addChild(folder_item)
                    else:
                        self.playlist_tree.addTopLevelItem(folder_item)
                    
                    if hasattr(node, 'children'):
                        for child in node.children:
                            add_node_to_tree(child, folder_item)
                    
                    folder_item.setExpanded(True)
                    
                elif node.type in ['playlist', 'smartlist']:
                    playlist_item = QTreeWidgetItem()
                    icon = "🎵" if node.type == 'playlist' else "🔍"
                    playlist_item.setText(0, f"{icon} {node.name}")
                    
                    track_count = len(getattr(node, 'tracks', []))
                    playlist_item.setText(1, str(track_count))
                    playlist_item.setText(2, node.type.title())
                    playlist_item.setData(0, Qt.ItemDataRole.UserRole, node)
                    
                    if parent_item:
                        parent_item.addChild(playlist_item)
                    else:
                        self.playlist_tree.addTopLevelItem(playlist_item)
        
        for node in self.structure:
            add_node_to_tree(node)
    
    def _update_playlist_info(self):
        """Update playlist information label."""
        total_playlists = self._count_playlists(self.structure)
        total_tracks = len(self._collect_all_tracks())
        
        self.playlist_info.setText(f"{total_playlists} playlists, {total_tracks} tracks")
    
    def _count_playlists(self, structure: List) -> int:
        """Count total playlists in structure."""
        count = 0
        for node in structure:
            if hasattr(node, 'type'):
                if node.type in ['playlist', 'smartlist']:
                    count += 1
                elif node.type == 'folder' and hasattr(node, 'children'):
                    count += self._count_playlists(node.children)
        return count
    
    def _collect_all_tracks(self) -> List:
        """Collect all unique tracks from structure."""
        all_tracks = []
        track_seen = set()
        
        def collect_recursive(nodes: List):
            for node in nodes:
                if hasattr(node, 'type'):
                    if node.type in ['playlist', 'smartlist'] and hasattr(node, 'tracks'):
                        for track in node.tracks:
                            track_key = getattr(track, 'audio_id', None) or getattr(track, 'file_path', None)
                            if track_key and track_key not in track_seen:
                                all_tracks.append(track)
                                track_seen.add(track_key)
                    elif node.type == 'folder' and hasattr(node, 'children'):
                        collect_recursive(node.children)
        
        collect_recursive(self.structure)
        return all_tracks
    
    def _on_playlist_selection_changed(self):
        """Handle playlist selection changes."""
        selected_items = self.playlist_tree.selectedItems()
        self.selected_playlists = []
        
        for item in selected_items:
            node = item.data(0, Qt.ItemDataRole.UserRole)
            if node and hasattr(node, 'type') and node.type in ['playlist', 'smartlist']:
                self.selected_playlists.append(node)
        
        # Update button state
        has_selection = len(self.selected_playlists) > 0
        has_collection = len(self.structure) > 0
        has_output = bool(self.output_path)
        
        can_convert = (has_collection and has_output and 
                      (has_selection or not self.selected_playlists))
        
        self.convert_button.setEnabled(can_convert)
    
    def _on_playlist_double_clicked(self, item, column):
        """Handle playlist double-click."""
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node and hasattr(node, 'type') and node.type in ['playlist', 'smartlist']:
            self._show_playlist_details(node)
    
    def _show_playlist_details(self, playlist):
        """Show playlist details dialog."""
        dialog = PlaylistDetailsWindow(playlist, self.key_translator, self.audio_manager, self)
        dialog.exec()
    
    def _show_details(self):
        """Show details for selected playlist."""
        selected_items = self.playlist_tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            node = item.data(0, Qt.ItemDataRole.UserRole)
            if node and hasattr(node, 'type') and node.type in ['playlist', 'smartlist']:
                self._show_playlist_details(node)
    
    def _reload_current_collection(self):
        """Reload the current collection."""
        if self.nml_path:
            self._load_playlists()
        else:
            self._log_message("No collection to reload", logging.WARNING)
    
    def _check_progress_queue(self):
        """Check for progress updates from worker thread."""
        try:
            while not self.prog_q.empty():
                message_type, data = self.prog_q.get_nowait()
                
                if message_type == "progress":
                    percentage, message = data
                    self.progress_bar.setValue(percentage)
                    self.progress_label.setText(message)
        
        except queue.Empty:
            pass
    
    def _start_conversion(self):
        """Start the conversion process."""
        # Validate inputs
        if not self.structure:
            QMessageBox.warning(self, "Warning", "Please load a Traktor collection first.")
            return
        
        if not self.output_path:
            QMessageBox.warning(self, "Warning", "Please select an output directory.")
            return
        
        # Show confirmation with format info
        format_name = self.settings['export_format']
        selected_count = len(self.selected_playlists)
        total_count = self._count_playlists(self.structure)
        
        if selected_count > 0:
            message = f"Export {selected_count} selected playlist(s) to {format_name}?"
        else:
            message = f"Export all {total_count} playlist(s) to {format_name}?"
        
        reply = QMessageBox.question(
            self, "Confirm Export", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Reset cancel event
        self.cancel_event.clear()
        
        # Update UI for conversion
        self.convert_button.setEnabled(False)
        self.convert_button.setText("Converting...")
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Log conversion start
        self._log_message(f"Starting conversion: {format_name}")
        self._log_message(f"Output: {self.output_path}")
        self._log_message(f"Selected playlists: {selected_count}")
        
        # Start conversion thread
        self.conversion_thread = ConversionThread(
            output_path=self.output_path,
            selected_playlists=self.selected_playlists,
            structure=self.structure,
            export_format=format_name,
            copy_music=self.settings['copy_music'],
            verify_copy=self.settings['verify_copy'],
            key_format=self.settings['key_format'],
            progress_queue=self.prog_q,
            cancel_event=self.cancel_event,
            settings=self.settings
        )
        
        self.conversion_thread.finished.connect(self._on_conversion_finished)
        self.conversion_thread.start()
    
    def _cancel_conversion(self):
        """Cancel the current conversion."""
        self.cancel_event.set()
        self.cancel_button.setEnabled(False)
        self.progress_label.setText("Cancelling...")
        self._log_message("Conversion cancelled by user")
    
    def _on_conversion_finished(self, status, message):
        """Handle conversion completion."""
        self.convert_button.setEnabled(True)
        self.convert_button.setText("🚀 CONVERT")
        self.cancel_button.setEnabled(False)
        
        if status == "completed":
            self.progress_bar.setValue(100)
            self.progress_label.setText("Conversion completed successfully!")
            self._log_message(f"Conversion completed successfully: {message}")
            
            # Show format-specific success message
            format_info = self._get_format_success_info()
            success_msg = f"Conversion completed!\n\nOutput: {self.output_path}\n\n{format_info}"
            QMessageBox.information(self, "Success", success_msg)
            
        elif status == "cancelled":
            self.progress_bar.setValue(0)
            self.progress_label.setText("Conversion cancelled.")
            self._log_message("Conversion was cancelled")
            
        elif status == "error":
            self.progress_bar.setValue(0)
            self.progress_label.setText("Conversion failed.")
            self._log_message(f"Conversion failed: {message}", logging.ERROR)
            QMessageBox.critical(self, "Error", f"Conversion failed:\n{message}")
        
        # Hide progress bar after delay
        QTimer.singleShot(3000, lambda: self.progress_bar.setVisible(False))
    
    def _get_format_success_info(self):
        """Get format-specific success information CORRIGÉ."""
        format_name = self.settings['export_format']
        
        if format_name == "CDJ/USB":
            return ("Created CDJ hardware export:\n"
                   "• Binary PDB database (export.pdb + DeviceSQL.edb)\n"
                   "• ANLZ waveform files (.DAT + .EXT)\n"
                   "• Ready for USB installation on CDJ-2000NXS2")
        
        elif format_name == "Rekordbox Database":
            return ("Created Rekordbox software database:\n"
                   "• SQLite/SQLCipher database\n"
                   "• Compatible with Rekordbox software\n"
                   "• Import via Rekordbox preferences")
        
        elif format_name == "Rekordbox XML":
            return ("Created Rekordbox XML file:\n"
                   "• Import into Rekordbox software\n"
                   "• Contains playlists and track metadata\n"
                   "• Standard XML format")
        
        elif format_name == "M3U Playlists":
            return ("Created M3U playlist files:\n"
                   "• Compatible with most DJ software\n"
                   "• Individual .m3u files per playlist\n"
                   "• Universal playlist format")
        
        return "Export completed successfully!"
    
    def _show_options_dialog(self):
        """Show options dialog."""
        dialog = OptionsDialog(self.app_config, self.settings, self)
        dialog.settings_changed.connect(self._on_settings_changed)
        if dialog.exec():
            self.settings = dialog.get_settings()
            self._save_configuration()
    
    def _on_settings_changed(self, new_settings):
        """Handle settings changes."""
        self.settings.update(new_settings)
        self._save_configuration()
        
        # Update UI elements
        self.copy_music_check.setChecked(self.settings['copy_music'])
        self.verify_copy_check.setChecked(self.settings['verify_copy'])
        self.export_format_button.setText(self.settings['export_format'])
        self.cdj_model_combo.setCurrentText(self.settings['cdj_target'])
        
        self._update_ui_for_format()
        
    def _show_log_window(self):
        """Show the log window."""
        self.log_handler.show_log_window(self, self.app_config)
    
    def _show_usage_dialog(self):
        """Show usage guide dialog."""
        dialog = UsageDialog(self.app_config, self)
        dialog.exec()
    
    def _show_about_dialog(self):
        """Show about dialog."""
        dialog = AboutDialog(self.app_config, self)
        dialog.exec()
    
    def _center_window(self):
        """Center the window on screen."""
        screen = QApplication.primaryScreen().geometry()
        window = self.geometry()
        x = (screen.width() - window.width()) // 2
        y = (screen.height() - window.height()) // 2
        self.move(x, y)
    
    def _log_message(self, message: str, level: int = logging.INFO):
        """Log message to handler and console."""
        level_names = {
            logging.DEBUG: "DEBUG",
            logging.INFO: "INFO", 
            logging.WARNING: "WARNING",
            logging.ERROR: "ERROR",
            logging.CRITICAL: "CRITICAL"
        }
        level_name = level_names.get(level, "INFO")
        
        # Send to log handler
        self.log_handler.log_message(message, level_name)
        
        # Also log to console
        logging.log(level, message)
    
    def closeEvent(self, event):
        """Handle application close event."""
        # Check for confirmation if enabled
        if self.settings.get('confirm_exit', False):
            reply = QMessageBox.question(
                self, "Confirm Exit",
                "Are you sure you want to exit Traktor Bridge?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        
        # Cancel any running operations
        self.cancel_event.set()
        
        # Save configuration
        self._save_configuration()
        
        # Clean up audio
        if hasattr(self, 'audio_manager'):
            self.audio_manager.cleanup()
        
        # Wait for threads to finish
        if hasattr(self, 'loading_thread') and self.loading_thread.isRunning():
            self.loading_thread.wait(3000)
        
        if hasattr(self, 'conversion_thread') and self.conversion_thread.isRunning():
            self.conversion_thread.wait(5000)
        
        event.accept()


def setup_logging():
    """Configure application logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('traktor_bridge.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName(AppConfig.APP_NAME)
    app.setApplicationVersion(AppConfig.VERSION)
    app.setOrganizationName(AppConfig.AUTHOR)
    
    # Setup logging
    setup_logging()
    logging.info(f"Starting {AppConfig.APP_NAME} v{AppConfig.VERSION}")
    
    try:
        window = ConverterGUI()
        
        # Connect logs to GUI after window creation
        log_dialog = LogDialog(window.app_config, window)
        
        class GuiLogHandler(logging.Handler):
            def __init__(self, log_dialog):
                super().__init__()
                self.log_dialog = log_dialog
            
            def emit(self, record):
                if self.log_dialog:
                    msg = self.format(record)
                    self.log_dialog.append_log(msg, record.levelname)
        
        gui_handler = GuiLogHandler(log_dialog)
        gui_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(gui_handler)
        window.log_handler.set_log_dialog(log_dialog)
        
        window.show()
        
        logging.info("Application started successfully")
        return app.exec()
        
    except Exception as e:
        logging.error(f"Failed to start application: {e}")
        logging.error("", exc_info=True)
        
        try:
            QMessageBox.critical(
                None, "Startup Error", 
                f"Failed to start {AppConfig.APP_NAME}:\n\n{str(e)}\n\nCheck the log file for details."
            )
        except:
            pass
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
