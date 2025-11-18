# -*- coding: utf-8 -*-
"""
Options Dialog Module for Traktor Bridge
Dialog d'options harmonisé avec l'interface principale
"""

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence


class OptionsDialog(QDialog):
    """Dialog d'options avec design harmonisé à l'interface principale."""
    
    settings_changed = Signal(dict)
    
    def __init__(self, app_config, settings, parent=None):
        super().__init__(parent)
        self.app_config = app_config
        self.settings = settings.copy()
        
        self.setWindowTitle("Traktor Bridge - Options")
        self.setModal(True)
        self.resize(500, 400)
        
        # Appliquer le même style que l'interface principale
        self.setStyleSheet(f"""
            QDialog {{
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
            QCheckBox {{ 
                color: {self.app_config.COLORS['fg_light']}; 
            }}
            QSpinBox {{
                background-color: {self.app_config.COLORS['bg_med']};
                color: {self.app_config.COLORS['fg_light']};
                border: none;
                padding: 6px;
                border-radius: 4px;
            }}
            QTabWidget::pane {{
                border: none;
                background-color: {self.app_config.COLORS['bg_dark']};
            }}
            QTabBar::tab {{
                background-color: {self.app_config.COLORS['bg_med']};
                color: {self.app_config.COLORS['fg_light']};
                border: none;
                padding: 8px 16px;
                margin-right: 2px;
                border-radius: 4px 4px 0px 0px;
            }}
            QTabBar::tab:selected {{
                background-color: {self.app_config.COLORS['accent']};
            }}
            QTabBar::tab:hover {{
                background-color: {self.app_config.COLORS['bg_light']};
            }}
            QGroupBox {{
                font-weight: bold;
                color: {self.app_config.COLORS['accent']};
                border: 1px solid {self.app_config.COLORS['bg_light']};
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }}
        """)
        
        self._setup_ui()
        self._load_current_settings()
    
    def _setup_ui(self):
        """Setup the options dialog UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title section
        title_label = QLabel("Options & Preferences")
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        layout.addWidget(title_label)
        
        subtitle_label = QLabel("Configure export settings and application preferences")
        subtitle_label.setStyleSheet(f"color: {self.app_config.COLORS['fg_muted']};")
        layout.addWidget(subtitle_label)
        layout.addSpacing(15)
        
        # Tab widget pour organiser les options
        self.tab_widget = QTabWidget()
        
        # Onglet Export
        self._create_export_tab()
        
        # Onglet CDJ Settings
        self._create_cdj_tab()
        
        # Onglet Application
        self._create_application_tab()
        
        layout.addWidget(self.tab_widget)
        
        # Buttons
        self._create_button_section(layout)
    
    def _create_export_tab(self):
        """Create export settings tab."""
        export_widget = QWidget()
        layout = QVBoxLayout(export_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Export Format Group
        format_group = QGroupBox("Export Format")
        format_layout = QVBoxLayout(format_group)
        
        self.export_format_combo = QComboBox()
        self.export_format_combo.addItems([
            "CDJ/USB",
            "Rekordbox Database", 
            "Rekordbox XML",
            "M3U"
        ])
        format_layout.addWidget(self.export_format_combo)
        
        format_help = QLabel("Select the target format for your export")
        format_help.setStyleSheet(f"color: {self.app_config.COLORS['fg_muted']}; font-size: 9pt;")
        format_layout.addWidget(format_help)
        
        layout.addWidget(format_group)
        
        # Key Format Group
        key_group = QGroupBox("Musical Key Format")
        key_layout = QVBoxLayout(key_group)
        
        self.key_format_combo = QComboBox()
        self.key_format_combo.addItems([
            "Open Key",
            "Camelot",
            "Traditional",
            "Mixed In Key"
        ])
        key_layout.addWidget(self.key_format_combo)
        
        key_help = QLabel("Choose musical key notation system")
        key_help.setStyleSheet(f"color: {self.app_config.COLORS['fg_muted']}; font-size: 9pt;")
        key_layout.addWidget(key_help)
        
        layout.addWidget(key_group)
        
        # File Operations Group
        file_group = QGroupBox("File Operations")
        file_layout = QVBoxLayout(file_group)
        
        self.copy_music_check = QCheckBox("Copy music files to export directory")
        self.verify_copy_check = QCheckBox("Verify file integrity after copying")
        
        file_layout.addWidget(self.copy_music_check)
        file_layout.addWidget(self.verify_copy_check)
        
        layout.addWidget(file_group)
        
        layout.addStretch()
        
        self.tab_widget.addTab(export_widget, "Export Settings")
    
    def _create_cdj_tab(self):
        """Create CDJ-specific settings tab."""
        cdj_widget = QWidget()
        layout = QVBoxLayout(cdj_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # CDJ Model Group
        model_group = QGroupBox("CDJ Hardware Target")
        model_layout = QVBoxLayout(model_group)
        
        self.cdj_target_combo = QComboBox()
        self.cdj_target_combo.addItems([
            "CDJ-2000NXS2",
            "CDJ-2000",
            "CDJ-3000",
            "XDJ-1000MK2"
        ])
        model_layout.addWidget(self.cdj_target_combo)
        
        model_help = QLabel("Select your CDJ model for optimized compatibility")
        model_help.setStyleSheet(f"color: {self.app_config.COLORS['fg_muted']}; font-size: 9pt;")
        model_layout.addWidget(model_help)
        
        layout.addWidget(model_group)
        
        # CDJ Features Group
        features_group = QGroupBox("CDJ Features")
        features_layout = QVBoxLayout(features_group)
        
        self.generate_anlz_check = QCheckBox("Generate ANLZ waveform files")
        self.generate_anlz_check.setChecked(True)  # Toujours activé pour CDJ
        self.generate_anlz_check.setEnabled(False)  # Non modifiable
        
        features_layout.addWidget(self.generate_anlz_check)
        
        anlz_help = QLabel("ANLZ files are required for CDJ waveform display")
        anlz_help.setStyleSheet(f"color: {self.app_config.COLORS['fg_muted']}; font-size: 9pt;")
        features_layout.addWidget(anlz_help)
        
        layout.addWidget(features_group)
        
        # Rekordbox Version Group (pour Rekordbox Database)
        rb_group = QGroupBox("Rekordbox Software Version")
        rb_layout = QVBoxLayout(rb_group)
        
        self.rekordbox_version_combo = QComboBox()
        self.rekordbox_version_combo.addItems([
            "RB6",
            "RB7"
        ])
        rb_layout.addWidget(self.rekordbox_version_combo)
        
        rb_help = QLabel("Target Rekordbox software version (for Database format)")
        rb_help.setStyleSheet(f"color: {self.app_config.COLORS['fg_muted']}; font-size: 9pt;")
        rb_layout.addWidget(rb_help)
        
        layout.addWidget(rb_group)
        
        layout.addStretch()
        
        self.tab_widget.addTab(cdj_widget, "CDJ Settings")
    
    def _create_application_tab(self):
        """Create application settings tab."""
        app_widget = QWidget()
        layout = QVBoxLayout(app_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Startup Group
        startup_group = QGroupBox("Startup Behavior")
        startup_layout = QVBoxLayout(startup_group)
        
        self.auto_load_check = QCheckBox("Auto-load collection on startup")
        self.confirm_exit_check = QCheckBox("Confirm before exit")
        
        startup_layout.addWidget(self.auto_load_check)
        startup_layout.addWidget(self.confirm_exit_check)
        
        layout.addWidget(startup_group)
        
        # Performance Group
        perf_group = QGroupBox("Performance Settings")
        perf_layout = QFormLayout(perf_group)
        
        self.cache_size_spin = QSpinBox()
        self.cache_size_spin.setRange(1000, 100000)
        self.cache_size_spin.setSuffix(" entries")
        perf_layout.addRow("Cache size:", self.cache_size_spin)
        
        self.memory_limit_spin = QSpinBox()
        self.memory_limit_spin.setRange(50, 1000)
        self.memory_limit_spin.setSuffix(" MB")
        perf_layout.addRow("Memory limit:", self.memory_limit_spin)
        
        self.worker_threads_spin = QSpinBox()
        self.worker_threads_spin.setRange(1, 8)
        perf_layout.addRow("Worker threads:", self.worker_threads_spin)
        
        layout.addWidget(perf_group)
        
        # Logging Group
        log_group = QGroupBox("Logging & Debug")
        log_layout = QVBoxLayout(log_group)
        
        log_level_layout = QHBoxLayout()
        log_level_label = QLabel("Log level:")
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems([
            "DEBUG",
            "INFO", 
            "WARNING",
            "ERROR"
        ])
        log_level_layout.addWidget(log_level_label)
        log_level_layout.addWidget(self.log_level_combo)
        log_level_layout.addStretch()
        
        log_layout.addLayout(log_level_layout)
        
        self.debug_mode_check = QCheckBox("Enable debug mode")
        log_layout.addWidget(self.debug_mode_check)
        
        layout.addWidget(log_group)
        
        layout.addStretch()
        
        self.tab_widget.addTab(app_widget, "Application")
    
    def _create_button_section(self, parent_layout):
        """Create button section."""
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 15, 0, 0)
        
        # Reset button
        reset_button = QPushButton("Reset to Defaults")
        reset_button.clicked.connect(self._reset_to_defaults)
        
        # Standard buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel | 
            QDialogButtonBox.StandardButton.Apply
        )
        
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_settings)
        
        button_layout.addWidget(reset_button)
        button_layout.addStretch()
        button_layout.addWidget(button_box)
        
        parent_layout.addLayout(button_layout)
    
    def _load_current_settings(self):
        """Load current settings into UI controls."""
        # Export tab
        self.export_format_combo.setCurrentText(self.settings.get('export_format', 'CDJ/USB'))
        self.key_format_combo.setCurrentText(self.settings.get('key_format', 'Open Key'))
        self.copy_music_check.setChecked(self.settings.get('copy_music', True))
        self.verify_copy_check.setChecked(self.settings.get('verify_copy', False))
        
        # CDJ tab
        self.cdj_target_combo.setCurrentText(self.settings.get('cdj_target', 'CDJ-2000NXS2'))
        self.rekordbox_version_combo.setCurrentText(self.settings.get('rekordbox_version', 'RB6'))
        
        # Application tab
        self.auto_load_check.setChecked(self.settings.get('auto_load_collection', True))
        self.confirm_exit_check.setChecked(self.settings.get('confirm_exit', False))
        self.cache_size_spin.setValue(self.settings.get('cache_size', 30000))
        self.memory_limit_spin.setValue(self.settings.get('memory_limit_mb', 100))
        self.worker_threads_spin.setValue(self.settings.get('worker_threads', 2))
        self.log_level_combo.setCurrentText(self.settings.get('log_level', 'INFO'))
        self.debug_mode_check.setChecked(self.settings.get('debug_mode', False))
        
        # Connect signals for real-time updates
        self._connect_signals()
    
    def _connect_signals(self):
        """Connect signals for real-time setting updates."""
        # Export tab
        self.export_format_combo.currentTextChanged.connect(self._on_export_format_changed)
        self.copy_music_check.toggled.connect(self._update_verify_copy_state)
        
        # Update verify copy state initially
        self._update_verify_copy_state()
    
    def _on_export_format_changed(self, format_name: str):
        """Handle export format change."""
        # Show CDJ info if selecting CDJ format
        if format_name == "CDJ/USB":
            self._show_cdj_info()
    
    def _show_cdj_info(self):
        """Show CDJ format information."""
        QMessageBox.information(
            self, 
            "CDJ Hardware Format Selected",
            "<b>CDJ Hardware Export Requirements:</b><br><br>"
            "• USB must be formatted <b>FAT32</b> (MBR partition)<br>"
            "• ASCII-only filenames (no accents)<br>"
            "• Maximum path length: 256 characters<br>"
            "• Binary PDB database format<br>"
            "• ANLZ waveform files (.DAT + .EXT)<br><br>"
            "<i>Traktor Bridge will automatically handle these requirements.</i>"
        )
    
    def _update_verify_copy_state(self):
        """Update verify copy checkbox state."""
        self.verify_copy_check.setEnabled(self.copy_music_check.isChecked())
    
    def _apply_settings(self):
        """Apply current settings without closing dialog."""
        self._save_settings()
        self.settings_changed.emit(self.settings)
    
    def _save_settings(self):
        """Save all settings from UI controls."""
        # Export tab
        self.settings['export_format'] = self.export_format_combo.currentText()
        self.settings['key_format'] = self.key_format_combo.currentText()
        self.settings['copy_music'] = self.copy_music_check.isChecked()
        self.settings['verify_copy'] = self.verify_copy_check.isChecked()
        
        # CDJ tab
        self.settings['cdj_target'] = self.cdj_target_combo.currentText()
        self.settings['generate_anlz'] = self.generate_anlz_check.isChecked()
        self.settings['rekordbox_version'] = self.rekordbox_version_combo.currentText()
        
        # Application tab
        self.settings['auto_load_collection'] = self.auto_load_check.isChecked()
        self.settings['confirm_exit'] = self.confirm_exit_check.isChecked()
        self.settings['cache_size'] = self.cache_size_spin.value()
        self.settings['memory_limit_mb'] = self.memory_limit_spin.value()
        self.settings['worker_threads'] = self.worker_threads_spin.value()
        self.settings['log_level'] = self.log_level_combo.currentText()
        self.settings['debug_mode'] = self.debug_mode_check.isChecked()
    
    def _reset_to_defaults(self):
        """Reset all settings to default values."""
        reply = QMessageBox.question(
            self, 
            "Reset to Defaults",
            "Are you sure you want to reset all settings to their default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Default settings
            default_settings = {
                'export_format': 'CDJ/USB',
                'key_format': 'Open Key',
                'copy_music': True,
                'verify_copy': False,
                'cdj_target': 'CDJ-2000NXS2',
                'use_encryption': False,
                'generate_anlz': True,
                'rekordbox_version': 'RB6',
                'auto_load_collection': True,
                'confirm_exit': False,
                'cache_size': 30000,
                'memory_limit_mb': 100,
                'worker_threads': 2,
                'log_level': 'INFO',
                'debug_mode': False
            }
            
            self.settings.update(default_settings)
            self._load_current_settings()
    
    def get_settings(self):
        """Get current settings dictionary."""
        return self.settings.copy()
    
    def accept(self):
        """Handle dialog accept (OK button)."""
        self._save_settings()
        self.settings_changed.emit(self.settings)
        super().accept()
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        elif event.matches(QKeySequence.StandardKey.Save):
            self._apply_settings()
        else:
            super().keyPressEvent(event)
