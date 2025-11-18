"""
About Dialog Module for Traktor Bridge
Displays application information and credits
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent


class AboutDialog(QDialog):
    """Dialog for displaying application information."""
    
    def __init__(self, app_config, parent=None):
        super().__init__(parent)
        self.app_config = app_config
        
        self.setWindowTitle("About")
        self.resize(450, 300)
        self.setModal(True)
        
        # Apply styling
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {app_config.COLORS['bg_dark']};
                color: {app_config.COLORS['fg_light']};
            }}
            QLabel {{
                color: {app_config.COLORS['fg_light']};
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
        """Set up the about dialog interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 20, 30, 20)
        
        # Application name
        app_name = QLabel(self.app_config.APP_NAME)
        app_name.setStyleSheet("font-size: 20pt; font-weight: bold;")
        app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Version
        version = QLabel(f"Version {self.app_config.VERSION}")
        version.setStyleSheet("font-size: 12pt;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Description
        description = QLabel("Professional Traktor to Pioneer CDJ/XML Converter")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setStyleSheet(f"color: {self.app_config.COLORS['fg_muted']}; font-size: 11pt;")
        
        # Author information
        author = QLabel(f"Created by {self.app_config.AUTHOR}")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author.setStyleSheet("font-size: 11pt;")
        
        # Website link
        website = QLabel(f'<a href="https://{self.app_config.WEBSITE}" style="color: {self.app_config.COLORS["accent"]}; text-decoration: none;">{self.app_config.WEBSITE}</a>')
        website.setAlignment(Qt.AlignmentFlag.AlignCenter)
        website.setOpenExternalLinks(True)
        website.setStyleSheet("font-size: 11pt;")
        
        # License information
        license_text = QLabel("Open Source Project - Free for educational and personal use")
        license_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        license_text.setStyleSheet(f"color: {self.app_config.COLORS['fg_muted']}; font-size: 9pt;")
        license_text.setWordWrap(True)
        
        # Disclaimer
        disclaimer = QLabel("No affiliation with Pioneer DJ or Native Instruments")
        disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disclaimer.setStyleSheet(f"color: {self.app_config.COLORS['fg_muted']}; font-size: 9pt;")
        
        # Add widgets to layout
        layout.addWidget(app_name)
        layout.addWidget(version)
        layout.addSpacing(10)
        layout.addWidget(description)
        layout.addSpacing(15)
        layout.addWidget(author)
        layout.addWidget(website)
        layout.addSpacing(15)
        layout.addWidget(license_text)
        layout.addWidget(disclaimer)
        layout.addStretch()
        
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