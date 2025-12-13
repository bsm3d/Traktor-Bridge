"""
Usage Dialog Module for Traktor Bridge
Displays comprehensive usage instructions and keyboard shortcuts
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent


class UsageDialog(QDialog):
    """Dialog for displaying usage instructions and help."""
    
    def __init__(self, app_config, parent=None):
        super().__init__(parent)
        self.app_config = app_config
        
        self.setWindowTitle("Usage Guide")
        self.resize(600, 500)
        self.setModal(True)
        
        # Apply styling
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {app_config.COLORS['bg_dark']};
                color: {app_config.COLORS['fg_light']};
            }}
            QTextEdit {{
                background-color: {app_config.COLORS['bg_med']};
                color: {app_config.COLORS['fg_light']};
                border: none;
                font-size: 10pt;
            }}
            QPushButton {{
                background-color: {app_config.COLORS['bg_med']};
                color: {app_config.COLORS['fg_light']};
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {app_config.COLORS['bg_light']};
            }}
        """)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the usage dialog interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("USAGE GUIDE")
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Content
        content = QTextEdit()
        content.setReadOnly(True)
        
        usage_html = f"""
        <style>
            h3 {{ color: {self.app_config.COLORS['accent']}; margin-top: 20px; }}
            table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
            th, td {{ border: 1px solid {self.app_config.COLORS['bg_light']}; padding: 8px; text-align: left; }}
            th {{ background-color: {self.app_config.COLORS['bg_light']}; font-weight: bold; }}
            kbd {{ 
                background-color: {self.app_config.COLORS['bg_light']}; 
                color: {self.app_config.COLORS['fg_light']};
                padding: 2px 6px; 
                border-radius: 3px; 
                font-family: monospace;
                font-size: 9pt;
            }}
            ul, ol {{ margin: 10px 0; padding-left: 20px; }}
            li {{ margin: 5px 0; }}
        </style>
        
        <h3>How to Use Traktor Bridge:</h3>
        <ol>
            <li><strong>Load Collection:</strong> Select your Traktor .nml file or let it auto-detect</li>
            <li><strong>Music Root (Optional):</strong> Select music folder to find relocated files</li>
            <li><strong>Select Playlists:</strong> Choose playlists/folders to convert</li>
            <li><strong>Choose Format:</strong> Database (CDJ), XML (Rekordbox), or M3U (Universal)</li>
            <li><strong>Convert:</strong> Click CONVERT and select destination</li>
        </ol>

        <h3>Keyboard Shortcuts:</h3>
        <table>
            <tr><th>Shortcut</th><th>Action</th></tr>
            <tr><td><kbd>Ctrl+O</kbd></td><td>Open NML File</td></tr>
            <tr><td><kbd>Ctrl+M</kbd></td><td>Select Music Root</td></tr>
            <tr><td><kbd>Ctrl+R</kbd></td><td>Reload Collection</td></tr>
            <tr><td><kbd>Ctrl+D</kbd></td><td>View Playlist Details</td></tr>
            <tr><td><kbd>Ctrl+L</kbd></td><td>View Conversion Log</td></tr>
            <tr><td><kbd>Ctrl+Return</kbd></td><td>Start Conversion</td></tr>
            <tr><td><kbd>Ctrl+Q</kbd></td><td>Exit Application</td></tr>
            <tr><td><kbd>F1</kbd></td><td>Show This Help</td></tr>
            <tr><td><kbd>Escape</kbd></td><td>Cancel/Close</td></tr>
        </table>

        <h3>Playlist Details Window:</h3>
        <table>
            <tr><th>Shortcut</th><th>Action</th></tr>
            <tr><td><kbd>P</kbd></td><td>Play/Pause Selected Track</td></tr>
            <tr><td><kbd>Ctrl+F</kbd></td><td>Focus Search Field</td></tr>
            <tr><td><kbd>Double-click Cues</kbd></td><td>Open Cue Timeline</td></tr>
            <tr><td><kbd>Click ▶</kbd></td><td>Play/Pause Track</td></tr>
        </table>

        <h3>Export Formats:</h3>
        <ul>
            <li><strong>CDJ/USB (Hardware):</strong> DeviceSQL binary format (.PDB) for Pioneer CDJ/XDJ hardware players with ANLZ waveforms</li>
            <li><strong>Rekordbox Database (Software):</strong> SQLite database format for Rekordbox desktop software</li>
            <li><strong>Rekordbox XML:</strong> XML file format for Rekordbox and compatible software</li>
            <li><strong>M3U (Universal):</strong> Simple playlist files for broad compatibility across DJ software and media players</li>
        </ul>

        <h3>Audio Features:</h3>
        <ul>
            <li>Full-length track preview playback</li>
            <li>Cue point visualization with timeline</li>
            <li>Musical key display with color coding</li>
            <li>BPM and beat grid information</li>
            <li>Hot cues, memory cues, and loop support</li>
        </ul>

        <h3>Tips & Best Practices:</h3>
        <ul>
            <li><strong>Music Root:</strong> Helps find tracks moved after collection creation</li>
            <li><strong>File Verification:</strong> Enable for USB drives to ensure perfect copies</li>
            <li><strong>Key Formats:</strong> Switch between Open Key and Classical notation</li>
            <li><strong>Search:</strong> Use search in details window to filter large playlists</li>
            <li><strong>Auto-Load:</strong> Application automatically finds your Traktor collection</li>
        </ul>

        <h3>Troubleshooting:</h3>
        <ul>
            <li><strong>Missing Files:</strong> Use music root folder to relocate tracks</li>
            <li><strong>No Playlists:</strong> Check NML file path and reload collection</li>
            <li><strong>Audio Issues:</strong> Ensure pygame is installed for playback</li>
            <li><strong>Export Errors:</strong> Check destination permissions and space</li>
        </ul>

        <h3>File Menu Options:</h3>
        <ul>
            <li><strong>New:</strong> Start fresh conversion project</li>
            <li><strong>Open:</strong> Load different NML collection</li>
            <li><strong>Recent:</strong> Quick access to recently used collections</li>
            <li><strong>Exit:</strong> Close application</li>
        </ul>
        """
        
        content.setHtml(usage_html)
        
        layout.addWidget(title)
        layout.addWidget(content)
        
        # Close button
        button_layout = QHBoxLayout()
        close_button = QPushButton("Close")
        close_button.setMinimumWidth(80)
        close_button.clicked.connect(self.accept)
        close_button.setDefault(True)
        
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard events."""
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)