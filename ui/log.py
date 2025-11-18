"""
Log Dialog Module for Traktor Bridge
Displays conversion logs and application messages
"""

from datetime import datetime
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QFrame, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent


class LogDialog(QDialog):
    """Dialog for displaying and managing log messages."""
    
    def __init__(self, app_config, parent=None):
        super().__init__(parent)
        self.app_config = app_config
        
        self.setWindowTitle("Conversion Log")
        self.resize(800, 500)
        self.setModal(False)
        
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
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 9pt;
                line-height: 1.2;
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
        """Setup the log dialog interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("Log messages will appear here...")
        
        layout.addWidget(self.log_text)
        
        # Button frame
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        # Clear button
        clear_button = QPushButton("Clear Log")
        clear_button.clicked.connect(self.clear_log)
        clear_button.setToolTip("Clear all log messages")
        
        # Copy button
        copy_button = QPushButton("Copy to Clipboard")
        copy_button.clicked.connect(self._copy_to_clipboard)
        copy_button.setToolTip("Copy log contents to clipboard")
        
        # Export button
        export_button = QPushButton("Export to File")
        export_button.clicked.connect(self._export_to_file)
        export_button.setToolTip("Save log to text file")
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_button.setDefault(True)
        
        button_layout.addWidget(clear_button)
        button_layout.addWidget(copy_button)
        button_layout.addWidget(export_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addWidget(button_frame)
    
    def append_log(self, message: str, level: str = "INFO"):
        """Append message to log with timestamp and level."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Format message with level coloring
        level_colors = {
            'DEBUG': '#adb5bd',
            'INFO': '#f8f9fa',
            'WARNING': '#ffc107',
            'ERROR': '#dc3545',
            'CRITICAL': '#dc3545'
        }
        
        color = level_colors.get(level.upper(), '#f8f9fa')
        formatted_message = f'<span style="color: {color};">[{timestamp}] {level}: {message}</span>'
        
        self.log_text.append(formatted_message)
        
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def clear_log(self):
        """Clear all log content."""
        self.log_text.clear()
        self.append_log("Log cleared", "INFO")
    
    def _copy_to_clipboard(self):
        """Copy log contents to clipboard."""
        text = self.log_text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.append_log("Log copied to clipboard", "INFO")
        else:
            self.append_log("No log content to copy", "WARNING")
    
    def _export_to_file(self):
        """Export log contents to file."""
        from PySide6.QtWidgets import QFileDialog
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_filename = f"traktor_bridge_log_{timestamp}.txt"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Log to File",
            default_filename,
            "Text Files (*.txt);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"Traktor Bridge Log Export\n")
                    f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(self.log_text.toPlainText())
                
                self.append_log(f"Log exported to: {file_path}", "INFO")
                
            except Exception as e:
                self.append_log(f"Failed to export log: {str(e)}", "ERROR")
    
    def get_log_content(self) -> str:
        """Get current log content as plain text."""
        return self.log_text.toPlainText()
    
    def set_log_content(self, content: str):
        """Set log content directly."""
        self.log_text.setPlainText(content)
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard events."""
        # Escape to close
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
        # Ctrl+C to copy
        elif event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._copy_to_clipboard()
        # Ctrl+S to export
        elif event.key() == Qt.Key.Key_S and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._export_to_file()
        # Delete to clear
        elif event.key() == Qt.Key.Key_Delete:
            self.clear_log()
        else:
            super().keyPressEvent(event)


class LogHandler:
    """Log handler that connects to LogDialog."""
    
    def __init__(self):
        self.log_dialog = None
    
    def set_log_dialog(self, dialog: LogDialog):
        """Set the log dialog to receive messages."""
        self.log_dialog = dialog
    
    def log_message(self, message: str, level: str = "INFO"):
        """Send message to log dialog if available."""
        if self.log_dialog:
            self.log_dialog.append_log(message, level)
    
    def show_log_window(self, parent=None, app_config=None):
        """Show or create log window."""
        if not self.log_dialog and app_config:
            self.log_dialog = LogDialog(app_config, parent)
        
        if self.log_dialog:
            self.log_dialog.show()
            self.log_dialog.raise_()
            self.log_dialog.activateWindow()
            return self.log_dialog
        
        return None