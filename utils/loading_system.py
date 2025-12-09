"""
Loading System Module for Traktor Bridge
Handles automatic collection detection, loading, and configuration management
"""

import json
import logging
import queue
from pathlib import Path
from typing import Optional, Dict, Any
from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import QMessageBox


class LoadingThread(QThread):
    """Thread for loading NML files using bsm_parser_nml."""
    finished = Signal(dict)
    
    def __init__(self, nml_path: str, music_root_path: Optional[str], progress_queue: queue.Queue):
        super().__init__()
        self.nml_path = nml_path
        self.music_root_path = music_root_path
        self.progress_queue = progress_queue
        
    def run(self):
        try:
            self.progress_queue.put(("progress", (10, "Parsing NML file...")))
            
            # Import the new parser
            from parser.bsm_nml_parser import BSMNMLParser
            
            self.progress_queue.put(("progress", (30, "Initializing parser...")))
            
            # Create parser instance
            parser = BSMNMLParser(self.nml_path, self.music_root_path, self.progress_queue)
            
            self.progress_queue.put(("progress", (60, "Extracting playlist structure...")))
            
            # Get playlist structure
            playlist_structure = parser.get_playlists_with_structure()
            
            self.progress_queue.put(("progress", (90, "Finalizing...")))
            
            # Structured result
            result = {
                'success': True,
                'playlist_structure': playlist_structure,
                'parser_instance': parser  # Keep reference for collection map if needed
            }
            
            self.finished.emit(result)
            
        except Exception as e:
            logging.error(f"Error loading NML: {e}", exc_info=True)
            result = {
                'success': False,
                'error': str(e)
            }
            self.finished.emit(result)


class LoadingSystemMixin:
    """Mixin class to add loading system functionality to main GUI."""
    
    def _get_default_traktor_collection_path(self) -> Optional[str]:
        """Retrieves the default path of Traktor collection."""
        home = Path.home()
        documents = home / "Documents"
        
        # Look for 'Native Instruments' folder for Traktor folders
        ni_folder = documents / "Native Instruments"
        
        if not ni_folder.exists() or not ni_folder.is_dir():
            self._log_message(f"Native Instruments folder not found at: {ni_folder}")
            return None
        
        # Find all folders starting with "Traktor"
        traktor_folders = []
        try:
            for item in ni_folder.iterdir():
                if item.is_dir() and item.name.startswith("Traktor"):
                    traktor_folders.append(item)
        except Exception as e:
            self._log_message(f"Error listing Native Instruments directory: {e}")
            return None
        
        if not traktor_folders:
            self._log_message("No Traktor folders found")
            return None
        
        # Sort folders in descending order by version (assumed in name)
        # This prioritizes Traktor 3.5.3 over Traktor 3.5.2, etc.
        traktor_folders.sort(key=lambda x: x.name, reverse=True)
        
        # Check each folder for presence of collection.nml file
        for folder in traktor_folders:
            collection_path = folder / "collection.nml"
            if collection_path.exists() and collection_path.is_file():
                self._log_message(f"Found Traktor collection: {collection_path}")
                return str(collection_path)
        
        self._log_message("No collection.nml found in any Traktor folder")
        return None
    
    def _auto_load_collection(self):
        """Automatically loads Traktor collection at startup."""
        try:
            # Show loading status
            self.playlist_info.setText("Searching for Traktor collection...")
            
            # Check if we already have a valid NML path from config
            if self.nml_path and Path(self.nml_path).exists():
                self._log_message(f"Auto-loading saved collection: {self.nml_path}")
                self.playlist_info.setText("Loading saved collection...")
                # Small delay to show message
                QTimer.singleShot(200, self._load_playlists)
                return
            
            # Try to find default Traktor collection
            default_path = self._get_default_traktor_collection_path()
            if default_path:
                self.nml_path = default_path
                self.nml_input.setText(default_path)
                self._log_message(f"Auto-loading default Traktor collection: {default_path}")
                self.playlist_info.setText("Loading default Traktor collection...")
                # Small delay to show message
                QTimer.singleShot(200, self._load_playlists)
            else:
                self._log_message("No Traktor collection found for auto-loading")
                self.playlist_info.setText("No Traktor collection found. Please select an NML file.")
                # Show help message to user
                self._show_no_collection_found_message()
                
        except Exception as e:
            self._log_message(f"Error during auto-load: {e}", logging.ERROR)
            self.playlist_info.setText("Auto-load failed. Please select an NML file manually.")
    
    def _show_no_collection_found_message(self):
        """Show helpful message when no collection is found."""
        QTimer.singleShot(1000, lambda: QMessageBox.information(
            self,
            "No Collection Found",
            "No Traktor collection was found automatically.\n\n"
            "Please use the Browse button to select your collection.nml file.\n"
            "It's usually located in:\n"
            "Documents/Native Instruments/Traktor X.X.X/collection.nml"
        ))
    
    def _reload_current_collection(self):
        """Reloads the currently selected collection."""
        if self.nml_path and Path(self.nml_path).exists():
            self._log_message(f"Reloading collection: {self.nml_path}")
            self._load_playlists()
        else:
            QMessageBox.information(
                self,
                "No Collection",
                "No valid collection is currently loaded. Please select an NML file first."
            )
    
    def _load_playlists(self):
        """Loads playlists from NML file in background thread."""
        if not self.nml_path:
            return
        
        # Validate file exists before starting
        if not Path(self.nml_path).exists():
            self.playlist_info.setText("Selected NML file not found.")
            QMessageBox.warning(
                self,
                "File Not Found",
                f"The selected NML file could not be found:\n{self.nml_path}\n\n"
                "Please select a valid collection.nml file."
            )
            self._browse_nml()
            return
        
        # Update UI for loading state
        self.convert_button.setEnabled(False)
        self.convert_button.setText("LOADING...")
        self.progress_bar.setValue(0)
        self.playlist_tree.clear()
        self.selected_playlists = []
        self.structure = []
        
        # Start loading thread
        self.loading_thread = LoadingThread(self.nml_path, self.music_root_path, self.prog_q)
        self.loading_thread.finished.connect(self._finalize_nml_load)
        self.loading_thread.start()
    
    def _finalize_nml_load(self, result: Dict[str, Any]):
        """Processes NML loading results."""
        self.convert_button.setEnabled(True)
        self.convert_button.setText("CONVERT")
        
        # Free the thread
        if hasattr(self, 'loading_thread'):
            self.loading_thread = None
        
        # Check success
        if not result.get('success', False):
            error_msg = result.get('error', 'Unknown error')
            self._handle_loading_error(error_msg)
            self.playlist_info.setText("Error loading playlists.")
            return
        
        # Store data
        self.structure = result.get('playlist_structure', [])
        
        # Debug logging
        self._log_message(f"Loaded playlist structure: {len(self.structure)} root nodes")
        
        # Update interface
        self._populate_playlist_tree()
        self.progress_bar.setValue(100)
        self.playlist_info.setText("Playlists loaded successfully.")
        
        # Reset progress after delay
        QTimer.singleShot(2000, lambda: self.progress_bar.setValue(0))
    
    def _handle_loading_error(self, error_msg: str):
        """Handle loading errors with user-friendly messages."""
        self._log_message(f"Loading error: {error_msg}", logging.ERROR)
        
        # Show user-friendly error dialog
        if "encoding" in error_msg.lower() or "parse" in error_msg.lower():
            QMessageBox.critical(
                self, "File Format Error",
                f"The NML file appears to be corrupted or in an unsupported format.\n\n"
                f"Error: {error_msg}\n\n"
                "Please try selecting a different collection.nml file."
            )
        else:
            QMessageBox.critical(
                self, "Loading Error",
                f"Failed to load the NML file:\n\n{error_msg}\n\n"
                "Please check the file and try again."
            )
    
    def _load_configuration(self):
        """Loads application configuration from file."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                self.nml_path = config.get('nml_path', '')
                self.output_path = config.get('output_path', '')
                self.music_root_path = config.get('music_root_path', '')
                self.copy_music = config.get('copy_music', True)
                self.verify_copy = config.get('verify_copy', False)
                self.key_format = config.get('key_format', 'Open Key')
                self.export_format = config.get('export_format', 'Database')
                
                # Update interface
                self.nml_input.setText(self.nml_path)
                self.music_input.setText(self.music_root_path)
                self.copy_music_check.setChecked(self.copy_music)
                self.verify_copy_check.setChecked(self.verify_copy)
                self.export_format_button.setText(self.export_format)
                
                # Validate saved NML path
                if self.nml_path and not Path(self.nml_path).exists():
                    self._log_message(f"Saved NML path no longer exists: {self.nml_path}")
                    self.nml_path = ""  # Clear invalid path so auto-load works
                    
        except Exception as e:
            logging.warning(f"Error loading configuration: {e}")
    
    def _save_configuration(self):
        """Saves application configuration to file."""
        # Update state from interface
        self.nml_path = self.nml_input.text()
        self.music_root_path = self.music_input.text()
        self.copy_music = self.copy_music_check.isChecked()
        self.verify_copy = self.verify_copy_check.isChecked()
        
        config = {
            'nml_path': self.nml_path,
            'output_path': self.output_path,
            'music_root_path': self.music_root_path,
            'copy_music': self.copy_music,
            'verify_copy': self.verify_copy,
            'key_format': self.key_format,
            'export_format': self.export_format
        }
        
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logging.warning(f"Error saving configuration: {e}")
    
    def _create_nml_input_section(self, parent_layout):
        """Creates NML file input section with reload button."""
        from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
        
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel("1. Traktor NML File *")
        label.setStyleSheet("color: #00b4d8; font-weight: bold;")
        layout.addWidget(label)
        
        input_frame = QFrame()
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(0, 0, 0, 0)
        
        self.nml_input = QLineEdit()
        self.nml_input.setPlaceholderText("Traktor collection will be loaded automatically...")
        
        reload_button = QPushButton("Reload")
        reload_button.clicked.connect(self._reload_current_collection)
        reload_button.setToolTip("Reload the current collection")
        
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_nml)
        
        input_layout.addWidget(self.nml_input)
        input_layout.addWidget(reload_button)
        input_layout.addWidget(browse_button)
        
        layout.addWidget(input_frame)
        parent_layout.addWidget(frame)
        
        return self.nml_input
    
    def _check_progress_queue(self):
        """Checks progress queue for updates from loading thread."""
        try:
            while True:
                msg_type, data = self.prog_q.get_nowait()
                
                if msg_type == "progress":
                    percent, message = data
                    self.progress_bar.setValue(int(percent))
                    self.progress_label.setText(message)
                    self._log_message(message)
                elif msg_type == "error":
                    self._handle_loading_error(str(data))
                
        except queue.Empty:
            pass  # No updates in queue
    
    def _log_message(self, message: str, level: int = logging.INFO):
        """Log message with optional level."""
        logging.log(level, message)
        # Also send to log handler if available
        if hasattr(self, 'log_handler') and self.log_handler.log_text_widget:
            try:
                timestamp = __import__('datetime').datetime.now().strftime('%H:%M:%S')
                self.log_handler.log_text_widget.append(f"{timestamp} - {message}")
                self.log_handler.log_text_widget.verticalScrollBar().setValue(
                    self.log_handler.log_text_widget.verticalScrollBar().maximum()
                )
            except Exception:
                pass

    def start_loading(self, message: str = "Loading..."):
        """Start loading indicator with optional message."""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)

        if hasattr(self, 'progress_label'):
            self.progress_label.setText(message)

        if hasattr(self, 'convert_button'):
            self.convert_button.setEnabled(False)

        self._log_message(message)

    def stop_loading(self):
        """Stop loading indicator."""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(100)

        if hasattr(self, 'progress_label'):
            self.progress_label.setText("Ready")

        if hasattr(self, 'convert_button'):
            self.convert_button.setEnabled(True)