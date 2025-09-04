"""
Traktor Bridge - Professional Traktor to Pioneer CDJ Database, M3U, XML Converter and USB Transfert
Original Author: Benoit (BSM) Saint-Moulin
Website: www.benoitsaintmoulin.com
Version: 1.1
"""

# =============================================================================
# IMPORTS AND DEPENDENCIES
# =============================================================================

import xml.etree.ElementTree as ET
import os
import sqlite3
import shutil
import urllib.parse
import traceback
import sys
import threading
import queue
import json
import logging
import uuid
import io
import time
import re
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

# GUI Libraries - PySide6 instead of tkinter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QProgressBar, 
    QCheckBox, QComboBox, QFrame, QSplitter, QScrollArea,
    QDialog, QTextEdit, QMenu, QStyleFactory
)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QThread, QTimer, QEvent
from PySide6.QtGui import QColor, QFont, QPalette, QIcon, QAction, QKeyEvent

# Audio and image processing dependencies
try:
    import pygame
    from tinytag import TinyTag, TinyTagException
    from PIL import Image
    AUDIO_PREVIEW_AVAILABLE = True
    pygame.init()
    pygame.mixer.init()
except ImportError:
    AUDIO_PREVIEW_AVAILABLE = False

try:
    import mutagen
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

ARTWORK_AVAILABLE = AUDIO_PREVIEW_AVAILABLE or MUTAGEN_AVAILABLE

# =============================================================================
# CONFIGURATION AND CONSTANTS
# =============================================================================

class AppConfig:
    """Application configuration constants and settings."""
    VERSION = "1.1"
    APP_NAME = "Traktor Bridge"
    AUTHOR = "Benoit (BSM) Saint-Moulin"
    WEBSITE = "www.benoitsaintmoulin.com"

    # UI Configuration
    WINDOW_WIDTH = 700
    WINDOW_HEIGHT = 650
    MIN_WIDTH = 700
    MIN_HEIGHT = 650

    # File Processing
    MAX_CACHE_SIZE = 30000  # Reduced for better memory management
    MAX_CACHE_MEMORY_MB = 100
    SUPPORTED_AUDIO_FORMATS = {'.mp3', '.wav', '.flac', '.aiff', '.m4a', '.ogg'}

    # Database
    BATCH_SIZE = 100
    DB_TIMEOUT_SECONDS = 30

    # Preview
    PREVIEW_DURATION_MS = None

    # Artwork
    MAX_ARTWORK_SIZE_MB = 10
    
    # Colors (Add these for consistent styling in PySide6)
    COLORS = {
        'bg_dark': '#212529',
        'bg_medium': '#343a40',
        'bg_light': '#495057',
        'fg_light': '#f8f9fa',
        'fg_muted': '#adb5bd',
        'accent_primary': '#00b4d8',
        'accent_hover': '#0096c7'
    }


class CueType(Enum):
    """Cue point types for Traktor/Rekordbox mapping."""
    GRID = 0
    HOT_CUE = 1
    FADE_IN = 2
    FADE_OUT = 3
    LOAD = 4
    LOOP = 5


# =============================================================================
# UTILITY CLASSES AND FUNCTIONS
# =============================================================================

@dataclass
class TrackInfo:
    """Container for all track-related information and metadata."""
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
class PlaylistNode:
    """Container for playlist/folder structure, allowing nested hierarchies."""
    type: str  # 'playlist' or 'folder'
    name: str
    tracks: List[TrackInfo] = field(default_factory=list)
    children: List['PlaylistNode'] = field(default_factory=list)


class PathValidator:
    """Validates and sanitizes file paths to prevent errors and security issues."""
    
    @staticmethod
    def validate_path(path_str: str, must_exist: bool = True) -> Optional[Path]:
        """Validates and resolves a path string with security checks."""
        if not path_str:
            return None
        try:
            path = Path(path_str).resolve()
            # Basic security check against path traversal
            if '..' in str(path) or str(path).startswith('..'):
                raise ValueError("Invalid path format (path traversal detected).")
            if must_exist and not path.exists():
                raise FileNotFoundError(f"Path does not exist: {path}")
            return path
        except Exception as e:
            logging.warning(f"Path validation failed for '{path_str}': {e}")
            return None


class AudioKeyTranslator:
    """Translates Traktor's numerical key values into musical notation formats."""
    
    def __init__(self):
        # Mapping from Traktor's internal key index to musical notations
        self.open_key_map = [
            "8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B",
            "5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"
        ]
        self.classical_map = [
            "F#", "A#", "D#", "G#", "C#", "F", "A", "D", "G", "C", "E", "B",
            "D#m", "Bbm", "Fm", "Cm", "Gm", "Dm", "Am", "Em", "Bm", "F#m", "C#m", "G#m"
        ]

    def translate(self, traktor_key: str, target_format: str = "Open Key") -> str:
        """Translates a Traktor key index to the specified format."""
        if not traktor_key or not traktor_key.isdigit():
            return ""
        try:
            key_index = int(traktor_key)
            if not 0 <= key_index < len(self.open_key_map):
                return ""
            return self.classical_map[key_index] if target_format == "Classical" else self.open_key_map[key_index]
        except (IndexError, ValueError):
            return ""


def handle_exceptions(operation_name: str):
    """Decorator to catch and log exceptions during critical operations."""
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                error_msg = f"Operation '{operation_name}' failed: {str(e)}"
                logging.error(traceback.format_exc())
                if hasattr(self, 'log_message'):
                    self.log_message(error_msg, logging.ERROR)
                if hasattr(self, 'progress_queue'):
                    self.progress_queue.put(("error", error_msg))
                raise
        return wrapper
    return decorator


# =============================================================================
# AUDIO MANAGER - Thread-Safe Audio Playback System
# =============================================================================

class AudioManager:
    """Thread-safe audio playback manager using pygame."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._initialized = False
        self._current_file = None
        self._playing_item_id = None
        self._auto_stop_timer = None
        self._root_ref = None
        
    def initialize(self, root_widget):
        """Initialize pygame mixer in a thread-safe manner."""
        with self._lock:
            if not self._initialized:
                try:
                    if not pygame.mixer.get_init():
                        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
                    self._initialized = True
                    self._root_ref = root_widget
                    return True
                except pygame.error as e:
                    logging.error(f"Failed to initialize pygame mixer: {e}")
                    return False
            return True
    
    @contextmanager
    def _safe_operation(self):
        """Context manager for thread-safe audio operations."""
        self._lock.acquire()
        try:
            yield
        finally:
            self._lock.release()
    
    def play_file(self, file_path: str, item_id: str, duration_callback=None) -> bool:
        """Play an audio file in a thread-safe manner."""
        with self._safe_operation():
            if not self._initialized:
                return False
                
            # Clean stop of previous file
            self._stop_internal()
            
            try:
                # File validation
                if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                    return False
                
                # Load and play
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.play()
                
                self._current_file = file_path
                self._playing_item_id = item_id
                
                return True
                
            except (pygame.error, OSError) as e:
                logging.error(f"Failed to play {file_path}: {e}")
                return False
    
    def stop(self):
        """Stop playback in a thread-safe manner."""
        with self._safe_operation():
            self._stop_internal()
    
    def _stop_internal(self):
        """Internal stop method (already in thread-safe context)."""
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except:
            pass
        
        self._current_file = None
        self._playing_item_id = None
    
    def get_current_state(self):
        """Return current state in a thread-safe manner."""
        with self._safe_operation():
            return {
                'file': self._current_file,
                'item_id': self._playing_item_id,
                'is_playing': pygame.mixer.music.get_busy() if self._initialized else False
            }
    
    def cleanup(self):
        """Clean up audio resources."""
        with self._safe_operation():
            self._stop_internal()
            if self._initialized:
                try:
                    pygame.mixer.quit()
                except:
                    pass
                self._initialized = False


# =============================================================================
# SMART FILE CACHE - Memory-Aware Caching System
# =============================================================================

class SmartFileCache:
    """Intelligent file cache with memory management and access tracking."""
    
    def __init__(self, max_size=30000, max_memory_mb=100):
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self._cache = {}
        self._access_times = {}
        self._lock = threading.RLock()
        
    def build_cache(self, root_path: str, progress_callback=None):
        """Build file cache with memory monitoring."""
        if not root_path:
            return {}
            
        music_path = PathValidator.validate_path(root_path, must_exist=True)
        if not music_path or not music_path.is_dir():
            return {}
        
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
            
            try:
                all_files = list(music_path.rglob('*'))
                total_files = len(all_files)
                current_memory = 0
                processed = 0
                
                for i, file_path in enumerate(all_files):
                    if i % 1000 == 0 and progress_callback:
                        progress_callback(
                            int((i / total_files) * 4),
                            f"Scanning: {i}/{total_files} files ({len(self._cache)} cached)"
                        )
                    
                    if not file_path.is_file():
                        continue
                        
                    if file_path.suffix.lower() not in AppConfig.SUPPORTED_AUDIO_FORMATS:
                        continue
                    
                    # Memory estimation (filename + path)
                    estimated_size = len(file_path.name) * 2 + len(str(file_path)) * 2
                    
                    # Limit checks
                    if (len(self._cache) >= self.max_size or 
                        current_memory + estimated_size > self.max_memory_bytes):
                        if progress_callback:
                            progress_callback(4, f"Cache limit reached: {len(self._cache)} files")
                        break
                    
                    self._cache[file_path.name] = str(file_path)
                    self._access_times[file_path.name] = 0  # Not accessed yet
                    current_memory += estimated_size
                    processed += 1
                
                if progress_callback:
                    progress_callback(5, f"Cache built: {len(self._cache)} files ({current_memory // 1024}KB)")
                    
            except Exception as e:
                logging.error(f"Cache building failed: {e}")
                
            return dict(self._cache)  # Copy for thread-safety
    
    def get(self, filename: str) -> Optional[str]:
        """Retrieve file from cache with access statistics update."""
        with self._lock:
            if filename in self._cache:
                self._access_times[filename] = time.time()
                return self._cache[filename]
            return None
    
    def cleanup_least_used(self, target_size: int = None):
        """Clean up least recently used entries."""
        if target_size is None:
            target_size = self.max_size // 2
            
        with self._lock:
            if len(self._cache) <= target_size:
                return
            
            # Sort by access time (oldest first)
            sorted_items = sorted(
                self._access_times.items(), 
                key=lambda x: x[1]
            )
            
            to_remove = len(self._cache) - target_size
            for filename, _ in sorted_items[:to_remove]:
                self._cache.pop(filename, None)
                self._access_times.pop(filename, None)


# =============================================================================
# DATABASE MANAGER - Robust Database Operations
# =============================================================================

class DatabaseManager:
    """Database manager with retry logic and transaction safety."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        
    @contextmanager
    def get_connection(self, max_retries=3):
        """Context manager with automatic retry functionality."""
        conn = None
        last_error = None
        
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(
                    str(self.db_path),
                    timeout=AppConfig.DB_TIMEOUT_SECONDS,
                    isolation_level=None  # Auto-commit
                )
                conn.execute("PRAGMA journal_mode=WAL")  # WAL mode for better performance
                conn.execute("PRAGMA synchronous=NORMAL")
                break
                
            except sqlite3.Error as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    raise sqlite3.Error(f"Failed to connect after {max_retries} attempts: {e}")
        
        try:
            yield conn
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def execute_batch(self, query: str, data_batch: List[tuple], batch_size: int = 100):
        """Execute batch operations with validation."""
        if not data_batch:
            return
            
        with self._lock:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Process in batches to avoid timeouts
                for i in range(0, len(data_batch), batch_size):
                    batch = data_batch[i:i + batch_size]
                    try:
                        cursor.executemany(query, batch)
                    except sqlite3.Error as e:
                        logging.error(f"Batch execution failed at batch {i//batch_size}: {e}")
                        # Continue with other batches
                        continue


# =============================================================================
# ARTWORK MANAGER - Secure Artwork Processing
# =============================================================================

class ArtworkManager:
    """Secure artwork manager with validation and cleanup."""
    
    def __init__(self, artwork_path: Path):
        self.artwork_path = artwork_path
        self._lock = threading.RLock()
        self.supported_formats = {
            b'\xff\xd8\xff': ('JPG', 'image/jpeg'),
            b'\x89PNG\r\n\x1a\n': ('PNG', 'image/png'),
            b'GIF87a': ('GIF', 'image/gif'),
            b'GIF89a': ('GIF', 'image/gif'),
        }
    
    def save_artwork(self, artwork_data: bytes, cursor: sqlite3.Cursor, track_title: str = "Unknown") -> Optional[int]:
        """Securely save artwork with validation."""
        if not artwork_data or len(artwork_data) < 10:
            return None
        
        with self._lock:
            try:
                # Format detection
                format_ext, mime_type = self._detect_format(artwork_data)
                if not format_ext:
                    logging.warning(f"Unsupported image format for track: {track_title}")
                    return None
                
                # Size validation
                if len(artwork_data) > AppConfig.MAX_ARTWORK_SIZE_MB * 1024 * 1024:
                    logging.warning(f"Artwork too large ({len(artwork_data)} bytes) for track: {track_title}")
                    return None
                
                # Generate unique filename
                artwork_filename = f"{uuid.uuid4().hex.upper()}.{format_ext}"
                artwork_file_path = self.artwork_path / artwork_filename
                
                # Temporary save for validation
                temp_path = artwork_file_path.with_suffix('.tmp')
                try:
                    with open(temp_path, 'wb') as f:
                        f.write(artwork_data)
                    
                    # Integrity validation
                    if not self._validate_image_file(temp_path):
                        temp_path.unlink()
                        return None
                    
                    # Move to final name
                    temp_path.rename(artwork_file_path)
                    
                except IOError as e:
                    if temp_path.exists():
                        temp_path.unlink()
                    logging.error(f"Failed to save artwork for '{track_title}': {e}")
                    return None
                
                # Create database entry
                try:
                    cursor.execute("SELECT MAX(ID) FROM djmdArtwork")
                    max_id = cursor.fetchone()[0] or 0
                    artwork_id = max_id + 1
                    
                    db_path = f"/ARTWORK/{artwork_filename}"
                    cursor.execute("INSERT INTO djmdArtwork (ID, Path) VALUES (?, ?)",
                                   (artwork_id, db_path))
                    
                    logging.debug(f"Artwork saved: {artwork_filename} for '{track_title}'")
                    return artwork_id
                    
                except sqlite3.Error as e:
                    # Cleanup on database error
                    if artwork_file_path.exists():
                        artwork_file_path.unlink()
                    logging.error(f"Database error saving artwork for '{track_title}': {e}")
                    return None
                
            except Exception as e:
                logging.error(f"Unexpected error saving artwork for '{track_title}': {e}")
                return None
    
    def _detect_format(self, data: bytes) -> Tuple[Optional[str], Optional[str]]:
        """Detect image format from magic bytes."""
        for magic_bytes, (ext, mime) in self.supported_formats.items():
            if data.startswith(magic_bytes):
                return ext, mime
        
        # WebP check
        if data.startswith(b'RIFF') and b'WEBP' in data[:12]:
            return 'WEBP', 'image/webp'
        
        return None, None
    
    def _validate_image_file(self, file_path: Path) -> bool:
        """Validate that a file is a readable image."""
        try:
            with Image.open(file_path) as img:
                img.verify()  # Verify integrity
                return True
        except Exception:
            return False
    
    def cleanup_orphaned_files(self, cursor: sqlite3.Cursor):
        """Clean up orphaned artwork files."""
        try:
            # Get files referenced in database
            cursor.execute("SELECT Path FROM djmdArtwork")
            db_files = {row[0].split('/')[-1] for row in cursor.fetchall()}
            
            # Clean up unreferenced files
            if self.artwork_path.exists():
                for file_path in self.artwork_path.iterdir():
                    if file_path.is_file() and file_path.name not in db_files:
                        try:
                            file_path.unlink()
                            logging.debug(f"Cleaned orphaned artwork: {file_path.name}")
                        except OSError:
                            pass
                            
        except Exception as e:
            logging.warning(f"Artwork cleanup failed: {e}")


# =============================================================================
# REKORDBOX XML EXPORTER
# =============================================================================

class RekordboxXMLExporter:
    """
    Exports tracks and playlists to Rekordbox XML format.
    Can be used as an alternative to the SQLite database export for some DJ software.
    """
    
    def __init__(self, key_translator):
        self.key_translator = key_translator
        
    def export_to_xml(self, playlist_structure, file_path, key_format="Open Key"):
        """
        Export playlist structure to a Rekordbox XML file.
        
        Args:
            playlist_structure: List of PlaylistNode objects containing tracks and folder structure
            file_path: Path where to save the XML file
            key_format: Format for musical keys (Open Key or Classical)
        """
        import xml.etree.ElementTree as ET
        import os
        import time
        from xml.dom import minidom
        from pathlib import Path
        from datetime import datetime
        
        # Create the root structure
        root = ET.Element('DJ_PLAYLISTS', Version="1.0.0")
        
        # Create PRODUCT element
        ET.SubElement(root, 'PRODUCT', 
                      Name="rekordbox", 
                      Version="6.0.0", 
                      Company="Pioneer DJ")
        
        # Create COLLECTION element - first collect all unique tracks
        all_tracks = self._collect_all_tracks(playlist_structure)
        collection = ET.SubElement(root, 'COLLECTION', Entries=str(len(all_tracks)))
        
        # Track ID mapping for playlists
        track_id_map = {}
        
        # Add tracks to collection
        for track in all_tracks:
            track_id = self._get_track_key(track.file_path)
            track_id_map[track.file_path] = track_id
            self._add_track_to_collection(collection, track, track_id, key_format)
        
        # Create playlists section
        playlists = ET.SubElement(root, 'PLAYLISTS')
        
        # Create root node
        root_node = ET.SubElement(playlists, 'NODE', Name="ROOT", Type="0")
        
        # Process playlist structure recursively
        self._process_playlist_structure(root_node, playlist_structure, track_id_map)
        
        # Write to file
        xml_str = ET.tostring(root, 'utf-8')
        pretty_xml_str = minidom.parseString(xml_str).toprettyxml(indent="  ")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml_str)
            
        return file_path
    
    def _collect_all_tracks(self, playlist_structure):
        """Recursively collect all unique tracks from the playlist structure."""
        all_tracks = []
        track_paths = set()
        
        def collect_tracks(nodes):
            for node in nodes:
                if node.type == 'playlist':
                    for track in node.tracks:
                        # Only add each track once based on file path
                        if track.file_path and track.file_path not in track_paths:
                            all_tracks.append(track)
                            track_paths.add(track.file_path)
                elif node.type == 'folder':
                    collect_tracks(node.children)
        
        collect_tracks(playlist_structure)
        return all_tracks
    
    def _get_track_key(self, file_path):
        """Generate a unique key for a track."""
        # Use a consistent hash of the path as the key
        if not file_path:
            return str(abs(hash("unknown")) % 10000000)
        return str(abs(hash(str(file_path))) % 10000000)
    
    def _add_track_to_collection(self, collection, track, track_id, key_format):
        """Add a track to the Rekordbox collection."""
        import xml.etree.ElementTree as ET
        from pathlib import Path
        import os
        import time
        
        # Parse time fields
        duration_sec = int(track.playtime) if track.playtime > 0 else 0
        creation_time = time.strftime("%Y-%m-%d")
        
        # Format location for Rekordbox
        location = self._format_location(track.file_path)
        
        # Create track element with required attributes
        track_elem = ET.SubElement(collection, 'TRACK', 
                                  TrackID=track_id,
                                  Name=track.title,
                                  Artist=track.artist,
                                  Album=track.album or "",
                                  Genre=track.genre or "",
                                  TotalTime=str(duration_sec),
                                  Location=location,
                                  Year=track.label or "",  # Using Label field as Year if available
                                  DateAdded=creation_time,
                                  BitRate=str(track.bitrate) if track.bitrate else "0",
                                  Comments=track.comment or "")
        
        # Add tempo (BPM)
        if track.bpm and track.bpm > 0:
            track_elem.set('AverageBpm', f"{track.bpm:.2f}")
        
        # Add musical key
        if track.musical_key:
            # Convert to Classical notation for Rekordbox
            key_value = self.key_translator.translate(track.musical_key, key_format)
            track_elem.set('Tonality', key_value)
        
        # Add gain info if available
        if track.gain:
            track_elem.set('ReplayGain', f"{track.gain:.2f}")
        
        # Add file type
        if track.file_path:
            file_ext = os.path.splitext(track.file_path)[-1].upper().replace('.', '')
            track_elem.set('Kind', file_ext)
        
        return track_elem
    
    def _format_location(self, file_path):
        """Format file location for Rekordbox."""
        if not file_path:
            return "file://localhost/unknown.mp3"
            
        # Rekordbox uses a specific URI format for file locations
        from pathlib import Path
        import os
        import urllib.parse
        
        try:
            abs_path = Path(file_path).resolve()
            
            if os.name == 'nt':  # Windows
                # Convert Windows path to file:// URI format
                path_str = str(abs_path).replace('\\', '/')
                if not path_str.startswith('/'):
                    path_str = '/' + path_str
                return f"file://localhost{path_str}"
            else:  # macOS/Linux
                # For macOS/Linux, use standard file:// URI
                return f"file://{abs_path}"
        except Exception:
            # Fallback for invalid paths
            return f"file://localhost/{os.path.basename(file_path)}"
    
    def _process_playlist_structure(self, parent_node, nodes, track_id_map):
        """
        Recursively process playlist structure to create folders and playlists.
        
        Args:
            parent_node: XML node to attach children to
            nodes: List of PlaylistNode objects to process
            track_id_map: Dictionary mapping file paths to track IDs
        """
        import xml.etree.ElementTree as ET
        
        for node in nodes:
            if node.type == 'folder':
                # Create folder node
                folder_node = ET.SubElement(parent_node, 'NODE', 
                                           Name=node.name, 
                                           Type="1")  # Type 1 = Folder
                
                # Process children recursively
                self._process_playlist_structure(folder_node, node.children, track_id_map)
                
            elif node.type == 'playlist':
                # Create playlist node
                playlist_node = ET.SubElement(parent_node, 'NODE',
                                             Name=node.name,
                                             Type="1")  # Type 1 = Playlist
                                             
                # Create actual playlist with tracks
                playlist = ET.SubElement(playlist_node, 'PLAYLIST',
                                        Name=node.name,
                                        Type="1",  # Type 1 = Playlist
                                        Count=str(len(node.tracks)))
                
                # Add tracks to playlist
                for track in node.tracks:
                    if track.file_path in track_id_map:
                        track_id = track_id_map[track.file_path]
                        ET.SubElement(playlist, 'TRACK', Key=track_id)


# =============================================================================
# NML PARSER MODULE
# =============================================================================

class TraktorNMLParser:
    """Parses Traktor NML files to extract track collections and playlist structures."""
    
    def __init__(self, nml_path: str, music_root: Optional[str] = None,
                 progress_queue: Optional[queue.Queue] = None):
        self.nml_path = Path(nml_path)
        self.music_root = music_root
        self.progress_queue = progress_queue
        self.key_translator = AudioKeyTranslator()
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        self._parse_xml()
        self._report_progress(0, "Building file cache from music root...")
        self.file_cache = self._build_file_cache()
        self._report_progress(5, "Indexing Traktor collection entries...")
        self.collection_map = self._build_collection_map()

    def _parse_xml(self):
        """Parse NML file with multiple encoding attempts."""
        encodings = ['utf-8', 'iso-8859-1', 'cp1252', 'utf-16']
        for encoding in encodings:
            try:
                parser = ET.XMLParser(encoding=encoding)
                self.tree = ET.parse(self.nml_path, parser)
                self.root = self.tree.getroot()
                self.logger.info(f"Successfully parsed NML with '{encoding}' encoding.")
                return
            except (ET.ParseError, UnicodeDecodeError) as e:
                self.logger.warning(f"Failed to parse with '{encoding}': {e}")
        raise ValueError("Unable to parse NML file. The file may be corrupt or use an unsupported encoding.")

    def _report_progress(self, percent: int, message: str):
        """Report progress to the queue if available."""
        if self.progress_queue:
            self.progress_queue.put(("progress", (percent, message)))

    @handle_exceptions("File cache building")
    def _build_file_cache(self) -> Dict[str, str]:
        """Build file cache using SmartFileCache."""
        if not self.music_root:
            return {}
        
        smart_cache = SmartFileCache(
            max_size=AppConfig.MAX_CACHE_SIZE,
            max_memory_mb=AppConfig.MAX_CACHE_MEMORY_MB
        )
        
        return smart_cache.build_cache(self.music_root, self._report_progress)

    @handle_exceptions("Collection mapping")
    def _build_collection_map(self) -> Dict[str, ET.Element]:
        """Build collection mapping from track keys to XML elements."""
        collection_map = {}
        all_entries = self.root.findall(".//COLLECTION/ENTRY")
        total_entries = len(all_entries)
        for i, entry in enumerate(all_entries):
            if i % 500 == 0:
                progress = 5 + int((i / total_entries) * 45)
                self._report_progress(progress, f"Indexing collection: {i}/{total_entries}")

            location = entry.find("LOCATION")
            if location is not None:
                volume = location.get('VOLUME', '')
                dir_path = location.get('DIR', '')
                file_name = location.get('FILE', '')
                if volume and dir_path and file_name:
                    # Unique identifier from file location parts
                    traktor_key = f"{volume}{dir_path}{file_name}"
                    collection_map[traktor_key] = entry
        self._report_progress(50, "Collection indexed successfully.")
        return collection_map

    def get_playlists_with_structure(self) -> List[PlaylistNode]:
        """Parse and return complete playlist and folder structure."""
        self._report_progress(50, "Searching for playlists and folders...")
        # Support both Traktor versions with different XML structures
        strategies = [
            (".//PLAYLISTS/NODE[@NAME='$ROOT']", "Traktor Pro 3.5+ format"),
            (".//PLAYLISTS", "Legacy Traktor format")
        ]
        root_node, used_strategy = None, None
        for xpath, description in strategies:
            found_node = self.root.find(xpath)
            if found_node is not None:
                root_node = found_node
                used_strategy = description
                break
        if root_node is None:
            self.logger.warning("No playlist structure found in NML file.")
            return []

        playlist_structure = self._parse_node_recursively(root_node)
        self._report_progress(100, f"Playlists loaded successfully using {used_strategy}.")
        return playlist_structure

    def _parse_node_recursively(self, node: ET.Element) -> List[PlaylistNode]:
        """Recursively parse playlist folders and playlists."""
        results = []
        # Handle both direct nodes and SUBNODES containers
        subnodes_container = node.find("SUBNODES") or node
        for child_node in subnodes_container.findall("NODE"):
            node_type = child_node.get('TYPE')
            node_name = child_node.get('NAME', 'Unnamed')

            if node_type == 'PLAYLIST':
                playlist = PlaylistNode(type='playlist', name=node_name)
                playlist_container = child_node.find('PLAYLIST')
                if playlist_container is not None:
                    for entry in playlist_container.findall('ENTRY'):
                        track_info = self._parse_playlist_entry(entry)
                        if track_info:
                            playlist.tracks.append(track_info)
                if playlist.tracks:  # Only add non-empty playlists
                    results.append(playlist)

            elif node_type == 'FOLDER':
                folder = PlaylistNode(type='folder', name=node_name)
                children = self._parse_node_recursively(child_node)
                if children:  # Only add folders that contain playlists
                    folder.children = children
                    results.append(folder)
        return results

    def _parse_playlist_entry(self, entry: ET.Element) -> Optional[TrackInfo]:
        """Find track in collection map using primary key."""
        primary_key_elem = entry.find("PRIMARYKEY")
        if primary_key_elem is None:
            return None
        track_key = primary_key_elem.get('KEY', '')
        collection_entry = self.collection_map.get(track_key)
        if collection_entry is not None:
            return self._parse_collection_entry(collection_entry)

        self.logger.warning(f"Track key not found in collection map: {track_key}")
        return None

    def _parse_collection_entry(self, entry: ET.Element) -> TrackInfo:
        """Extract all metadata from a single track XML element."""
        track = TrackInfo(
            title=entry.get('TITLE', 'Unknown'),
            artist=entry.get('ARTIST', 'Unknown')
        )
        track.file_path = self._parse_file_location(entry)

        info = entry.find("INFO")
        if info is not None:
            track.genre = info.get('GENRE', '')
            track.comment = info.get('COMMENT', '')
            track.label = info.get('LABEL', '')
            track.bitrate = int(info.get('BITRATE', '0'))
            track.playtime = float(info.get('PLAYTIME', '0'))

        album = entry.find("ALBUM")
        if album is not None:
            track.album = album.get('TITLE', '')

        tempo = entry.find("TEMPO")
        if tempo is not None:
            try:
                track.bpm = float(tempo.get('BPM', '0'))
            except (ValueError, TypeError):
                track.bpm = 0.0

        key = entry.find("MUSICAL_KEY")
        if key is not None:
            track.musical_key = key.get('VALUE', '')

        loudness = entry.find("LOUDNESS")
        if loudness is not None:
            try:
                track.gain = float(loudness.get('ANALYZED_DB', '0.0'))
            except (ValueError, TypeError):
                track.gain = 0.0

        self._parse_cue_points(entry, track)
        self._extract_artwork(track)
        return track

    def _parse_file_location(self, entry: ET.Element) -> str:
        """Reconstruct full file path from NML location data."""
        location = entry.find("LOCATION")
        if location is None:
            return ''

        file_from_nml = location.get('FILE', '')

        # Strategy 1: Use music root folder cache for relocated files
        if self.music_root and self.file_cache and file_from_nml:
            file_name = urllib.parse.unquote(os.path.basename(file_from_nml))
            cached_path = self.file_cache.get(file_name)
            if cached_path:
                return cached_path

        # Strategy 2: Reconstruct path from NML data
        volume = location.get('VOLUME', '')
        dir_path = location.get('DIR', '').replace('/:', '/')
        reconstructed = urllib.parse.unquote(f"{volume}{dir_path}{file_from_nml}")

        # Clean up common URI prefixes
        for prefix in ['file://localhost/', 'file:///', 'file://']:
            if reconstructed.startswith(prefix):
                reconstructed = reconstructed[len(prefix):]
                break

        # Handle Windows-style paths that start with slash (e.g., /C:/Users/...)
        if len(reconstructed) > 2 and reconstructed.startswith('/') and reconstructed[2] == ':':
            reconstructed = reconstructed[1:]

        return reconstructed

    def _parse_cue_points(self, entry: ET.Element, track: TrackInfo):
        """Parse CUE_V2 elements to extract cue points, loops, and grid marker."""
        for cue in entry.findall(".//CUE_V2"):
            try:
                cue_type = int(cue.get('TYPE', '-1'))
                start_ms = float(cue.get('START', '0.0'))

                # First cue of type 0 is the grid anchor
                if cue_type == CueType.GRID.value and track.grid_anchor_ms is None:
                    track.grid_anchor_ms = start_ms

                track.cue_points.append({
                    'name': cue.get('NAME', ''),
                    'type': cue_type,
                    'start': int(start_ms),
                    'len': int(float(cue.get('LEN', '0'))),
                    'hotcue': int(cue.get('HOTCUE', '-1'))
                })
            except (ValueError, TypeError):
                continue

    def _extract_artwork(self, track: TrackInfo):
        """Robust artwork extraction using TinyTag with mutagen fallback."""
        if not (ARTWORK_AVAILABLE and track.file_path and os.path.exists(track.file_path)):
            return

        # Primary method: TinyTag for reliable artwork extraction
        if AUDIO_PREVIEW_AVAILABLE:
            try:
                tag = TinyTag.get(track.file_path, image=True)
                
                if tag and tag.images and tag.images.any and tag.images.any.data:
                    track.artwork_data = tag.images.any.data
                    self.logger.debug(f"Artwork extracted using TinyTag for: {os.path.basename(track.file_path)}")
                    return
                    
            except TinyTagException as e:
                self.logger.warning(f"TinyTag artwork extraction failed for {track.file_path}: {e}")
            except Exception as e:
                self.logger.warning(f"Unexpected error during TinyTag extraction for {track.file_path}: {e}")

        # Fallback method: Mutagen backup
        if MUTAGEN_AVAILABLE:
            try:
                # Use easy=False for artwork access
                audio_file = mutagen.File(track.file_path, easy=False)
                if audio_file is None:
                    self.logger.warning(f"Mutagen fallback could not open file: {track.file_path}")
                    return

                artwork_data = None
                
                # Method 1: FLAC, OGG, and other formats with pictures attribute
                if hasattr(audio_file, 'pictures') and audio_file.pictures:
                    artwork_data = audio_file.pictures[0].data
                    
                # Method 2: MP3 files with ID3 tags
                elif hasattr(audio_file, 'tags') and audio_file.tags:
                    # Try standard APIC frame
                    for key in audio_file.tags.keys():
                        if key.startswith('APIC'):
                            frame = audio_file.tags[key]
                            if hasattr(frame, 'data'):
                                artwork_data = frame.data
                                break
                            
                # Method 3: MP4/M4A files
                elif 'covr' in audio_file and audio_file.get('covr'):
                    cover_art = audio_file.get('covr')[0]
                    if isinstance(cover_art, bytes):
                        artwork_data = cover_art
                    elif hasattr(cover_art, 'data'):
                        artwork_data = cover_art.data

                if artwork_data:
                    track.artwork_data = artwork_data
                    self.logger.debug(f"Artwork extracted using mutagen fallback for: {os.path.basename(track.file_path)}")
                else:
                    self.logger.debug(f"No artwork found for: {os.path.basename(track.file_path)}")

            except Exception as e:
                self.logger.warning(f"Mutagen fallback artwork extraction failed for {track.file_path}: {e}")


# =============================================================================
# DATABASE EXPORT MODULE
# =============================================================================

class CDJDatabaseExporter:
    """Handles creation of Pioneer Rekordbox database and file structure."""
    
    def __init__(self, output_path: str, progress_callback: Optional[callable] = None):
        self.output_path = Path(output_path)
        self.progress_callback = progress_callback
        self.key_translator = AudioKeyTranslator()
        self.cancel_event = None

        # Standard Pioneer USB folder structure
        self.contents_path = self.output_path / "CONTENTS"
        self.pioneer_path = self.output_path / "PIONEER"
        self.artwork_path = self.pioneer_path / "ARTWORK"
        self.db_path = self.pioneer_path / "rekordbox.pdb"
        self.logger = logging.getLogger(__name__)
        
        # Initialize managers
        self.db_manager = DatabaseManager(str(self.db_path))
        self.artwork_manager = ArtworkManager(self.artwork_path)

    def _update_progress(self, percent: int, message: str):
        """Update progress if callback is available."""
        if self.progress_callback:
            self.progress_callback(percent, message)

    @handle_exceptions("Database export")
    def export_playlists(self, playlist_structure: List[PlaylistNode],
                         copy_music: bool = True, verify_copy: bool = False,
                         key_format: str = "Open Key"):
        """Main export function with enhanced error handling."""
        try:
            self._create_folder_structure()
            self._create_database_structure()
            self._process_playlist_structure(playlist_structure, key_format, parent_id=0)
            if copy_music:
                all_tracks = self._collect_all_tracks(playlist_structure)
                self._copy_music_files(all_tracks, verify_copy)
            self._create_export_info()
        except Exception as e:
            self.logger.error(f"Export failed critically: {e}")
            raise

    def _create_folder_structure(self):
        """Create necessary PIONEER directory structure."""
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.contents_path.mkdir(exist_ok=True)
        self.pioneer_path.mkdir(exist_ok=True)
        self.artwork_path.mkdir(exist_ok=True)
        (self.pioneer_path / "USBANLZ").mkdir(exist_ok=True)

    def _create_database_structure(self):
        """Initialize SQLite database with all required tables."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            # Table definitions based on Rekordbox database schema
            table_definitions = {
                'djmdContent': '''CREATE TABLE IF NOT EXISTS djmdContent (
                    ID INTEGER PRIMARY KEY, KeyID INTEGER, AutoGain REAL, 
                    FolderPath TEXT, FileNameL TEXT, Title TEXT, ArtistID INTEGER, 
                    AlbumID INTEGER, GenreID INTEGER, LabelID INTEGER, BPM REAL, 
                    Length INTEGER, BitRate INTEGER, CommentsL TEXT, 
                    ContentTypeID INTEGER, FileType TEXT, ArtworkID INTEGER, 
                    created_at TEXT, updated_at TEXT
                )''',
                'djmdPlaylist': '''CREATE TABLE IF NOT EXISTS djmdPlaylist (
                    ID INTEGER PRIMARY KEY, Seq INTEGER, Name TEXT, ParentID INTEGER
                )''',
                'djmdSongPlaylist': '''CREATE TABLE IF NOT EXISTS djmdSongPlaylist (
                    ID INTEGER PRIMARY KEY, PlaylistID INTEGER, ContentID INTEGER, TrackNo INTEGER
                )''',
                'djmdArtist': '''CREATE TABLE IF NOT EXISTS djmdArtist (
                    ID INTEGER PRIMARY KEY, Name TEXT
                )''',
                'djmdAlbum': '''CREATE TABLE IF NOT EXISTS djmdAlbum (
                    ID INTEGER PRIMARY KEY, Name TEXT
                )''',
                'djmdGenre': '''CREATE TABLE IF NOT EXISTS djmdGenre (
                    ID INTEGER PRIMARY KEY, Name TEXT
                )''',
                'djmdLabel': '''CREATE TABLE IF NOT EXISTS djmdLabel (
                    ID INTEGER PRIMARY KEY, Name TEXT
                )''',
                'djmdKey': '''CREATE TABLE IF NOT EXISTS djmdKey (
                    ID INTEGER PRIMARY KEY, Name TEXT
                )''',
                'djmdCue': '''CREATE TABLE IF NOT EXISTS djmdCue (
                    ID INTEGER PRIMARY KEY, ContentID INTEGER, Type INTEGER, 
                    Time INTEGER, TimeEnd INTEGER DEFAULT 0, Number INTEGER DEFAULT 0, Name TEXT
                )''',
                'djmdBeatGrid': '''CREATE TABLE IF NOT EXISTS djmdBeatGrid (
                    ID INTEGER PRIMARY KEY, ContentID INTEGER, MeasureNo INTEGER, 
                    BeatNo INTEGER, Time REAL
                )''',
                'djmdArtwork': '''CREATE TABLE IF NOT EXISTS djmdArtwork (
                    ID INTEGER PRIMARY KEY, Path TEXT
                )'''
            }
            for table_name, sql in table_definitions.items():
                cursor.execute(sql)

            self._add_missing_columns(cursor)

    def _add_missing_columns(self, cursor: sqlite3.Cursor):
        """Ensure older database schemas are updated with necessary columns."""
        cursor.execute("PRAGMA table_info(djmdContent)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'KeyID' not in columns: 
            cursor.execute("ALTER TABLE djmdContent ADD COLUMN KeyID INTEGER")
        if 'AutoGain' not in columns: 
            cursor.execute("ALTER TABLE djmdContent ADD COLUMN AutoGain REAL")
        if 'ArtworkID' not in columns: 
            cursor.execute("ALTER TABLE djmdContent ADD COLUMN ArtworkID INTEGER")

    def _process_playlist_structure(self, nodes: List[PlaylistNode], key_format: str, parent_id: int):
        """Recursively process playlist structure to create folders and playlists."""
        for node in nodes:
            if self.cancel_event and self.cancel_event.is_set():
                return
            if node.type == 'folder':
                new_parent_id = self._create_playlist_folder(node.name, parent_id)
                self._process_playlist_structure(node.children, key_format, new_parent_id)
            elif node.type == 'playlist':
                self._process_single_playlist(node, key_format, parent_id)

    def _create_playlist_folder(self, name: str, parent_id: int) -> int:
        """Create playlist folder entry in database."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ID FROM djmdPlaylist WHERE Name = ? AND ParentID = ?", (name, parent_id))
            result = cursor.fetchone()
            if result:
                return result[0]

            cursor.execute("SELECT MAX(ID) FROM djmdPlaylist")
            max_id = cursor.fetchone()[0] or 0
            new_id = max_id + 1
            cursor.execute("INSERT INTO djmdPlaylist (ID, Seq, Name, ParentID) VALUES (?, ?, ?, ?)",
                           (new_id, new_id, name, parent_id))
            return new_id

    @handle_exceptions("Playlist processing")
    def _process_single_playlist(self, playlist: PlaylistNode, key_format: str, parent_id: int):
        """Process all tracks within a single playlist."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            # Cache lookups for performance
            caches = self._build_lookup_caches(cursor)
            playlist_id = self._create_or_update_playlist(cursor, playlist.name, parent_id)
            self._process_tracks_in_playlist(cursor, playlist.tracks, playlist_id, key_format, caches)

    def _build_lookup_caches(self, cursor: sqlite3.Cursor) -> Dict[str, Dict]:
        """Pre-load existing database entries for performance."""
        return {
            'artists': {row[1]: row[0] for row in cursor.execute("SELECT ID, Name FROM djmdArtist")},
            'albums': {row[1]: row[0] for row in cursor.execute("SELECT ID, Name FROM djmdAlbum")},
            'genres': {row[1]: row[0] for row in cursor.execute("SELECT ID, Name FROM djmdGenre")},
            'labels': {row[1]: row[0] for row in cursor.execute("SELECT ID, Name FROM djmdLabel")},
            'keys': {row[1]: row[0] for row in cursor.execute("SELECT ID, Name FROM djmdKey")},
            'content': {row[1]: row[0] for row in cursor.execute("SELECT ID, FileNameL FROM djmdContent")}
        }

    def _create_or_update_playlist(self, cursor: sqlite3.Cursor, name: str, parent_id: int) -> int:
        """Create new playlist or clear existing one."""
        cursor.execute("SELECT ID FROM djmdPlaylist WHERE Name = ? AND ParentID = ?", (name, parent_id))
        existing = cursor.fetchone()
        if existing:
            playlist_id = existing[0]
            # Clear existing tracks for fresh import
            cursor.execute("DELETE FROM djmdSongPlaylist WHERE PlaylistID = ?", (playlist_id,))
            return playlist_id

        cursor.execute("SELECT MAX(ID) FROM djmdPlaylist")
        max_id = cursor.fetchone()[0] or 0
        playlist_id = max_id + 1
        cursor.execute("INSERT INTO djmdPlaylist (ID, Seq, Name, ParentID) VALUES (?, ?, ?, ?)",
                       (playlist_id, playlist_id, name, parent_id))
        return playlist_id

    def _process_tracks_in_playlist(self, cursor: sqlite3.Cursor, tracks: List[TrackInfo], 
                                   playlist_id: int, key_format: str, caches: Dict):
        """Process tracks and link them to playlist."""
        for idx, track in enumerate(tracks, 1):
            if self.cancel_event and self.cancel_event.is_set():
                return

            file_name = os.path.basename(track.file_path) if track.file_path else f"track_{idx}.mp3"
            content_id = caches['content'].get(file_name)

            if not content_id:
                content_id = self._create_track_content(cursor, track, key_format, caches)
                caches['content'][file_name] = content_id

            cursor.execute("INSERT INTO djmdSongPlaylist (PlaylistID, ContentID, TrackNo) VALUES (?, ?, ?)",
                           (playlist_id, content_id, idx))

    def _create_track_content(self, cursor: sqlite3.Cursor, track: TrackInfo, key_format: str, caches: Dict) -> int:
        """Create new track entry with all metadata."""
        # Save artwork using new manager
        artwork_id = None
        if track.artwork_data:
            artwork_id = self.artwork_manager.save_artwork(track.artwork_data, cursor, track.title)

        artist_id = self._get_or_create_id(cursor, 'djmdArtist', track.artist, caches['artists'])
        album_id = self._get_or_create_id(cursor, 'djmdAlbum', track.album, caches['albums'])
        genre_id = self._get_or_create_id(cursor, 'djmdGenre', track.genre, caches['genres'])
        label_id = self._get_or_create_id(cursor, 'djmdLabel', track.label, caches['labels'])
        key_name = self.key_translator.translate(track.musical_key, key_format)
        key_id = self._get_or_create_id(cursor, 'djmdKey', key_name, caches['keys'])

        cursor.execute("SELECT MAX(ID) FROM djmdContent")
        max_id = cursor.fetchone()[0] or 0
        content_id = max_id + 1
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute("""
            INSERT INTO djmdContent (
                ID, Title, ArtistID, AlbumID, GenreID, LabelID, KeyID, AutoGain,
                BPM, Length, FileNameL, FolderPath, ContentTypeID, FileType,
                ArtworkID, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            content_id, track.title, artist_id, album_id, genre_id, label_id,
            key_id, track.gain, track.bpm, int(track.playtime), os.path.basename(track.file_path),
            '/CONTENTS/', 0, os.path.splitext(track.file_path)[-1].upper(), artwork_id,
            current_time, current_time
        ))

        if track.grid_anchor_ms is not None and track.bpm > 0:
            self._create_beat_grid(cursor, content_id, track)
        self._create_cue_points(cursor, content_id, track.cue_points)
        return content_id

    def _get_or_create_id(self, cursor: sqlite3.Cursor, table: str, name: str, cache: Dict) -> Optional[int]:
        """Get ID for metadata item from cache or create new entry."""
        if not name:
            return None
        if name in cache:
            return cache[name]

        cursor.execute(f"SELECT ID FROM {table} WHERE Name = ?", (name,))
        result = cursor.fetchone()
        if result:
            cache[name] = result[0]
            return result[0]

        cursor.execute(f"SELECT MAX(ID) FROM {table}")
        max_id = cursor.fetchone()[0] or 0
        new_id = max_id + 1
        cursor.execute(f"INSERT INTO {table} (ID, Name) VALUES (?, ?)", (new_id, name))
        cache[name] = new_id
        return new_id

    def _create_beat_grid(self, cursor: sqlite3.Cursor, content_id: int, track: TrackInfo):
        """Calculate and insert beat grid information."""
        cursor.execute("DELETE FROM djmdBeatGrid WHERE ContentID = ?", (content_id,))

        beat_interval_ms = 60000.0 / track.bpm
        beats_to_insert = []

        # Add anchor beat
        beats_to_insert.append((content_id, 1, 1, track.grid_anchor_ms / 1000.0))

        # Generate forward beats
        current_time_ms = track.grid_anchor_ms + beat_interval_ms
        beat_index = 1
        while current_time_ms < (track.playtime * 1000):
            measure_no = (beat_index // 4) + 1
            beat_no_in_measure = (beat_index % 4) + 1
            beats_to_insert.append((content_id, measure_no, beat_no_in_measure, current_time_ms / 1000.0))
            current_time_ms += beat_interval_ms
            beat_index += 1

        cursor.executemany("INSERT INTO djmdBeatGrid (ContentID, MeasureNo, BeatNo, Time) VALUES (?, ?, ?, ?)", beats_to_insert)

    def _create_cue_points(self, cursor: sqlite3.Cursor, content_id: int, cue_points: List[Dict]):
        """Translate Traktor cue points to Rekordbox format."""
        cursor.execute("DELETE FROM djmdCue WHERE ContentID = ?", (content_id,))
        cues_to_insert = []
        for cue in cue_points:
            traktor_type = cue.get('type', -1)
            hotcue_num_t = cue.get('hotcue', -1)
            start_time = cue.get('start', 0)
            length = cue.get('len', 0)
            name = cue.get('name', '') if cue.get('name', 'n.n.') != 'n.n.' else ''

            rekordbox_type = -1
            rekordbox_number = 0
            time_end = 0

            # Translate cue types
            if traktor_type == CueType.HOT_CUE.value and hotcue_num_t > 0:  # Hot Cue
                rekordbox_type, rekordbox_number = 1, hotcue_num_t
            elif traktor_type == CueType.LOAD.value:  # Memory Cue
                rekordbox_type = 0
            elif traktor_type == CueType.LOOP.value and length > 0:  # Loop
                rekordbox_type, time_end = 0, start_time + length

            if rekordbox_type != -1:
                cues_to_insert.append((content_id, rekordbox_type, start_time, time_end, rekordbox_number, name))

        if cues_to_insert:
            cursor.executemany("INSERT INTO djmdCue (ContentID, Type, Time, TimeEnd, Number, Name) VALUES (?, ?, ?, ?, ?, ?)", cues_to_insert)

    def _collect_all_tracks(self, structure: List[PlaylistNode]) -> List[TrackInfo]:
        """Gather unique list of all tracks from selected structure."""
        all_tracks = []
        def collect_recursive(nodes):
            for node in nodes:
                if node.type == 'playlist':
                    all_tracks.extend(node.tracks)
                elif node.type == 'folder':
                    collect_recursive(node.children)
        collect_recursive(structure)
        # Return unique list based on file path
        return list({t.file_path: t for t in all_tracks if t.file_path}.values())

    @handle_exceptions("Music file copying")
    def _copy_music_files(self, tracks: List[TrackInfo], verify: bool):
        """Copy music files to CONTENTS folder."""
        total = len(tracks) if tracks else 1
        success, failed, skipped = 0, 0, 0
        for i, track in enumerate(tracks, 1):
            if self.cancel_event and self.cancel_event.is_set():
                return

            progress = 30 + int((i / total) * 65)
            if not track.file_path:
                failed += 1
                self._update_progress(progress, f"Missing file path for track: {track.title}")
                continue

            source_path = PathValidator.validate_path(track.file_path, must_exist=True)
            if not source_path:
                failed += 1
                self._update_progress(progress, f"File not found: {track.title}")
                continue

            dest_path = self.contents_path / source_path.name
            try:
                if dest_path.exists() and not verify:
                    skipped += 1
                    self._update_progress(progress, f"Skipping (exists): {source_path.name}")
                    continue

                shutil.copy2(source_path, dest_path)

                if verify and source_path.stat().st_size != dest_path.stat().st_size:
                    failed += 1
                    dest_path.unlink()
                    self._update_progress(progress, f"Verification failed: {source_path.name}")
                    continue

                success += 1
                self._update_progress(progress, f"Copied: {source_path.name}")
            except Exception as e:
                failed += 1
                self._update_progress(progress, f"Error copying {source_path.name}: {e}")

        self._update_progress(95, f"Copy completed: {success} copied, {skipped} skipped, {failed} failed.")

    def _create_export_info(self):
        """Create EXPORT.INFO file required by some CDJ models."""
        info_content = (
            f"PIONEER DJ EXPORT\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Converter: {AppConfig.APP_NAME} v{AppConfig.VERSION}\n"
            f"Author: {AppConfig.AUTHOR}\n"
        )
        with open(self.pioneer_path / "EXPORT.INFO", 'w', encoding='utf-8') as f:
            f.write(info_content)


# =============================================================================
# GUI MODULE WITH PySide6
# =============================================================================

class LogHandler:
    """Handles log messages for GUI display."""
    
    def __init__(self):
        self.log_window = None
        self.log_text_widget = None
        
    def log_message(self, message: str, level: int = logging.INFO):
        """Log message to both file and GUI log window."""
        log_entry = f"{datetime.now().strftime('%H:%M:%S')} - {message}"
        logging.log(level, message)
        if self.log_text_widget is not None:
            try:
                self.log_text_widget.append(f"{log_entry}")
                # Scroll to bottom
                self.log_text_widget.verticalScrollBar().setValue(
                    self.log_text_widget.verticalScrollBar().maximum()
                )
            except Exception:
                self.log_text_widget = None


class LoadingThread(QThread):
    """Thread for loading NML files."""
    finished = Signal(object)
    
    def __init__(self, nml_path, music_root_path, progress_queue):
        super().__init__()
        self.nml_path = nml_path
        self.music_root_path = music_root_path
        self.progress_queue = progress_queue
        
    def run(self):
        try:
            parser = TraktorNMLParser(self.nml_path, self.music_root_path, self.progress_queue)
            self.finished.emit(parser.get_playlists_with_structure())
        except Exception as e:
            self.finished.emit(e)


class ConversionThread(QThread):
    """Thread for playlist conversion."""
    finished = Signal(str, str)  # type, message
    
    def __init__(self, output_path, selected_playlists, playlist_structure, 
                 export_format, copy_music, verify_copy, key_format, progress_queue, cancel_event):
        super().__init__()
        self.output_path = output_path
        self.selected_playlists = selected_playlists
        self.playlist_structure = playlist_structure
        self.export_format = export_format
        self.copy_music = copy_music
        self.verify_copy = verify_copy
        self.key_format = key_format
        self.progress_queue = progress_queue
        self.cancel_event = cancel_event
        
    def run(self):
        try:
            if self.export_format == "XML":
                self._run_xml_export()
            else:
                self._run_database_export()
            
            if self.cancel_event.is_set():
                self.finished.emit("cancelled", "Conversion cancelled by user")
            else:
                self.finished.emit("completed", f"Successfully exported playlists")
                
        except Exception as e:
            self.finished.emit("error", str(e))
            logging.error(f"Conversion error: {traceback.format_exc()}")
            
    def _run_database_export(self):
        """Run the standard database export."""
        exporter = CDJDatabaseExporter(self.output_path, 
                                      lambda p, m: self.progress_queue.put(("progress", (p, m))))
        exporter.cancel_event = self.cancel_event
        
        # Build structure containing only selected items and necessary parent folders
        structure_to_export = self._get_full_structure_for_selection()
        
        playlist_count = self._count_playlists(structure_to_export)
        self.progress_queue.put(("progress", (0, f"Exporting {playlist_count} playlist(s) to database format.")))

        exporter.export_playlists(structure_to_export, self.copy_music, 
                                 self.verify_copy, self.key_format)
    
    def _run_xml_export(self):
        """Run the Rekordbox XML export."""
        from pathlib import Path
        
        # Get destination path for XML file
        output_path = Path(self.output_path)
        xml_file_path = output_path / "rekordbox.xml"
        
        # Build structure containing only selected items and necessary parent folders
        structure_to_export = self._get_full_structure_for_selection()
        
        playlist_count = self._count_playlists(structure_to_export)
        self.progress_queue.put(("progress", (0, f"Exporting {playlist_count} playlist(s) to Rekordbox XML format.")))
        
        # Create XML exporter
        xml_exporter = RekordboxXMLExporter(AudioKeyTranslator())
        
        # Create necessary folders
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Handle copying music files if requested
        if self.copy_music:
            # Collect all tracks
            all_tracks = []
            def collect_tracks_from_structure(nodes):
                for node in nodes:
                    if node.type == 'playlist':
                        all_tracks.extend(node.tracks)
                    elif node.type == 'folder':
                        collect_tracks_from_structure(node.children)
            
            collect_tracks_from_structure(structure_to_export)
            
            # Create CONTENTS folder
            contents_path = output_path / "CONTENTS"
            contents_path.mkdir(exist_ok=True)
            
            # Copy files
            unique_tracks = {}
            for track in all_tracks:
                if track.file_path and track.file_path not in unique_tracks:
                    unique_tracks[track.file_path] = track
            
            total_tracks = len(unique_tracks)
            for i, (file_path, track) in enumerate(unique_tracks.items(), 1):
                if self.cancel_event.is_set():
                    return
                    
                progress = 10 + int((i / total_tracks) * 70)
                self.progress_queue.put(("progress", (progress, f"Copying file {i}/{total_tracks}: {os.path.basename(file_path)}")))
                
                try:
                    source_path = Path(file_path)
                    if source_path.exists():
                        dest_path = contents_path / source_path.name
                        
                        if not dest_path.exists() or self.verify_copy:
                            import shutil
                            shutil.copy2(source_path, dest_path)
                            
                            if self.verify_copy and source_path.stat().st_size != dest_path.stat().st_size:
                                logging.warning(f"Verification failed for {source_path.name}")
                except Exception as e:
                    logging.error(f"Failed to copy {file_path}: {e}")
        
        # Update progress
        self.progress_queue.put(("progress", (80, "Generating XML file...")))
        
        # Export XML
        try:
            xml_exporter.export_to_xml(structure_to_export, xml_file_path, self.key_format)
            
            # Create PIONEER folder structure for compatibility
            pioneer_folder = output_path / "PIONEER"
            pioneer_folder.mkdir(exist_ok=True)
            
            # Create EXPORT.INFO file required by some CDJ models
            from datetime import datetime
            info_content = (
                f"PIONEER DJ EXPORT\n"
                f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Format: XML\n"
                f"Converter: {AppConfig.APP_NAME} v{AppConfig.VERSION}\n"
                f"Author: {AppConfig.AUTHOR}\n"
            )
            with open(pioneer_folder / "EXPORT.INFO", 'w', encoding='utf-8') as f:
                f.write(info_content)
                
        except Exception as e:
            self.progress_queue.put(("error", f"XML export failed: {str(e)}"))
            logging.error(f"XML export error: {e}")
            
    def _get_full_structure_for_selection(self) -> List[PlaylistNode]:
        """Rebuild structure containing only selected items and required parent folders."""
        new_structure = []
        selected_ids = {id(n) for n in self.selected_playlists}

        def clone_and_filter(nodes: List[PlaylistNode]) -> List[PlaylistNode]:
            filtered_list = []
            for node in nodes:
                if id(node) in selected_ids:
                    # Node is selected, add it with all children if folder
                    filtered_list.append(node)
                elif node.type == 'folder':
                    # Check if folder contains selected descendants
                    filtered_children = clone_and_filter(node.children)
                    if filtered_children:
                        # Create clone with only selected children
                        new_folder = PlaylistNode(type='folder', name=node.name, children=filtered_children)
                        filtered_list.append(new_folder)
            return filtered_list

        return clone_and_filter(self.playlist_structure)
    
    def _count_playlists(self, structure: List[PlaylistNode]) -> int:
        """Count total number of playlists in structure."""
        count = 0
        for node in structure:
            if node.type == 'playlist':
                count += 1
            elif node.type == 'folder':
                count += self._count_playlists(node.children)
        return count

class TimelineDialog(QDialog):
    """Dialog for displaying cue point timeline with enhanced visualization."""
    
    def __init__(self, track: TrackInfo, parent=None):
        super().__init__(parent)
        self.track = track
        self.setWindowTitle(f"Cue Points: {track.artist} - {track.title}")
        self.resize(700, 500)  # Taille légèrement plus grande
        self.setStyleSheet(f"background-color: {AppConfig.COLORS['bg_dark']}; color: {AppConfig.COLORS['fg_light']};")
        
        # Filtrer et trier les points de repère par temps
        self.cue_points = sorted(
            [cue for cue in track.cue_points if self._is_relevant_cue(cue)],
            key=lambda c: c.get('start', 0)
        )
        
        # Configuration de filtres actifs
        self.show_hotcues = True
        self.show_memory_cues = True
        self.show_loops = True
        self.show_grid = True  # Nouveau filtre pour Grid Anchor
        
        # Setup UI
        self._setup_ui()
    
    def _is_relevant_cue(self, cue):
        """Détermine si un point de repère est pertinent pour l'affichage."""
        cue_type = cue.get('type', -1)
        hotcue_num = cue.get('hotcue', -1)
        # Inclure uniquement les Hot Cues (numérotés), Loops, et Memory Cues. Exclure Grid Markers.
        return ((cue_type == CueType.HOT_CUE.value and hotcue_num > 0) or 
                cue_type in [CueType.LOAD.value, CueType.LOOP.value])
        
    def _setup_ui(self):
        """Set up the timeline dialog UI."""
        layout = QVBoxLayout(self)
        
        # Header section avec titre et infos
        header_frame = QFrame()
        header_layout = QVBoxLayout(header_frame)
        
        # Title section avec icône musicale
        title_label = QLabel(f"🎵 {self.track.artist} - {self.track.title}")
        title_label.setStyleSheet(f"font-size: 14pt; font-weight: bold; color: {AppConfig.COLORS['fg_light']};")
        
        # Infos supplémentaires
        info_text = f"BPM: {self.track.bpm:.1f} | Duration: {int(self.track.playtime // 60)}:{int(self.track.playtime % 60):02d}"
        if self.track.musical_key:
            key = AudioKeyTranslator().translate(self.track.musical_key)
            info_text += f" | Key: {key}"
            
        # Ajouter info Grid Anchor
        if self.track.grid_anchor_ms is not None:
            ms = self.track.grid_anchor_ms
            minutes = int(ms // 60000)
            seconds = (ms % 60000) / 1000
            grid_time = f"{minutes:02d}:{seconds:06.3f}"
            info_text += f" | Grid Anchor: {grid_time}"
            
        info_label = QLabel(info_text)
        info_label.setStyleSheet(f"color: {AppConfig.COLORS['fg_muted']};")
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(info_label)
        layout.addWidget(header_frame)
        
        # Filtres et statistiques
        filter_frame = QFrame()
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(0, 10, 0, 10)
        
        # Statistiques des points
        stats_label = QLabel(self._get_cue_stats())
        stats_label.setStyleSheet(f"color: {AppConfig.COLORS['fg_light']}; font-weight: bold;")
        
        # Boutons de filtre
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
        
        # Ajouter checkbox pour Grid Anchor
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
        
        # Timeline visualization (custom widget) - avec amélioration pour la visualisation
        self.timeline_view = self._create_timeline_widget()
        layout.addWidget(self.timeline_view)
        
        # Table des points de repère
        self.cue_table = self._create_cue_table()
        layout.addWidget(self.cue_table, 1)  # Donner plus d'espace à la table
        
        # Bottom button bar
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        
        export_button = QPushButton("Export to Clipboard")
        export_button.setStyleSheet(self._get_button_style())
        export_button.clicked.connect(self._export_to_clipboard)
        
        close_button = QPushButton("Close")
        close_button.setStyleSheet(self._get_button_style())
        close_button.clicked.connect(self.accept)
        
        button_layout.addWidget(export_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addWidget(button_frame)
    
    def _get_button_style(self):
        """Retourne le style CSS pour les boutons."""
        return f"""
            QPushButton {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {AppConfig.COLORS['bg_light']};
            }}
        """
    
    def _get_cue_stats(self):
        """Génère des statistiques sur les points de repère."""
        hot_cues = sum(1 for cue in self.cue_points if cue.get('type') == CueType.HOT_CUE.value)
        memory_cues = sum(1 for cue in self.cue_points if cue.get('type') == CueType.LOAD.value)
        loops = sum(1 for cue in self.cue_points if cue.get('type') == CueType.LOOP.value)
        
        stats = f"Total: {len(self.cue_points)} points ({hot_cues} Hot Cues, {memory_cues} Memory Cues, {loops} Loops"
        if self.track.grid_anchor_ms is not None:
            stats += ", 1 Grid Anchor"
        stats += ")"
        
        return stats
    
    def _create_timeline_widget(self):
        """Crée le widget de timeline amélioré."""
        from PySide6.QtGui import QPainter, QPen, QBrush, QColor
        from PySide6.QtCore import QRect, QRectF, QPoint
        
        class EnhancedTimelineView(QWidget):
            def __init__(self, track, cue_points, parent=None):
                super().__init__(parent)
                self.track = track
                self.cue_points = cue_points
                self.setMinimumHeight(100)  # Plus grand pour une meilleure visualisation
                self.setStyleSheet(f"background-color: {AppConfig.COLORS['bg_medium']};")
                
                # Filtres
                self.show_hotcues = True
                self.show_memory_cues = True
                self.show_loops = True
                self.show_grid = True
            
            def update_filters(self, show_hotcues, show_memory_cues, show_loops, show_grid):
                """Met à jour les filtres d'affichage."""
                self.show_hotcues = show_hotcues
                self.show_memory_cues = show_memory_cues
                self.show_loops = show_loops
                self.show_grid = show_grid
                self.update()
            
            def paintEvent(self, event):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                
                width = self.width()
                height = self.height()
                
                # Arrière-plan avec dégradé subtil
                gradient = QColor(AppConfig.COLORS['bg_medium'])
                gradient_dark = QColor(AppConfig.COLORS['bg_dark'])
                for y in range(height):
                    blend_factor = y / height
                    color = QColor(
                        int(gradient.red() * (1 - blend_factor) + gradient_dark.red() * blend_factor),
                        int(gradient.green() * (1 - blend_factor) + gradient_dark.green() * blend_factor),
                        int(gradient.blue() * (1 - blend_factor) + gradient_dark.blue() * blend_factor)
                    )
                    painter.setPen(color)
                    painter.drawLine(0, y, width, y)
                
                # Draw main timeline
                painter.setPen(QPen(QColor('#888888'), 2))
                mid_y = height // 2
                painter.drawLine(10, mid_y, width - 10, mid_y)
                
                # Draw wave pattern (simulated waveform)
                wave_color = QColor('#555555')
                painter.setPen(QPen(wave_color, 1))
                
                # Simuler une forme d'onde pour un effet visuel
                import math
                for x in range(10, width - 10, 2):
                    pos_ratio = (x - 10) / (width - 20)  # 0 to 1 position
                    # Amplitude variable basée sur la position (simule un morceau avec intro/outro)
                    amp_factor = math.sin(pos_ratio * 3.14) * 0.8 + 0.2
                    # Fréquence variable
                    freq = 0.2 + pos_ratio * 0.1
                    y_offset = math.sin(pos_ratio * 100 * freq) * 10 * amp_factor
                    painter.drawLine(x, mid_y + y_offset, x, mid_y - y_offset)
                
                # Draw time markers
                total_duration = self.track.playtime * 1000 if self.track.playtime > 0 else 1
                
                # Format time function
                def format_time(ms):
                    seconds = ms / 1000
                    minutes = int(seconds // 60)
                    seconds = seconds % 60
                    return f"{minutes:02d}:{seconds:05.2f}"
                
                # Draw time markers
                painter.setPen(QPen(QColor('#AAAAAA'), 1))
                for i in range(6):
                    x_pos = 10 + (i * ((width - 20) / 5))
                    time_pos = (i / 5) * total_duration
                    
                    painter.drawLine(x_pos, mid_y - 5, x_pos, mid_y + 5)
                    painter.drawText(QRectF(x_pos - 40, mid_y + 10, 80, 20), 
                                  Qt.AlignmentFlag.AlignCenter, format_time(time_pos))
                
                # Draw grid anchor if enabled and present
                if self.show_grid and self.track.grid_anchor_ms is not None:
                    grid_pos = 10 + ((self.track.grid_anchor_ms / total_duration) * (width - 20))
                    grid_color = QColor('#00FFFF')  # Cyan
                    painter.setPen(QPen(grid_color, 1, Qt.PenStyle.DashLine))
                    painter.drawLine(int(grid_pos), 10, int(grid_pos), height - 10)
                    
                    # Draw grid marker symbol
                    painter.setBrush(QBrush(grid_color))
                    painter.setPen(QPen(grid_color.darker(120), 1))
                    
                    # Réduire la taille du diamant
                    size = 6  # Réduit de 10 à 6
                    points = [
                        QPoint(int(grid_pos), mid_y - size),
                        QPoint(int(grid_pos + size), mid_y),
                        QPoint(int(grid_pos), mid_y + size),
                        QPoint(int(grid_pos - size), mid_y)
                    ]
                    painter.drawPolygon(points)
                                
                # Draw cue points with colors
                cue_colors = {
                    CueType.HOT_CUE.value: QColor('#ff4d4d'),  # Rouge pour Hot Cues
                    CueType.LOAD.value: QColor('#4da6ff'),     # Bleu pour Memory Cues
                    CueType.LOOP.value: QColor('#4dff88')      # Vert pour Loops
                }
                
                filtered_cues = [c for c in self.cue_points if self._is_visible(c)]
                
                for cue in filtered_cues:
                    position = 10 + ((cue.get('start', 0) / total_duration) * (width - 20))
                    cue_type = cue.get('type', -1)
                    
                    if cue_type in cue_colors:
                        color = cue_colors[cue_type]
                        painter.setBrush(QBrush(color))
                        painter.setPen(QPen(color.darker(120), 1))
                        
                        # Personnaliser l'apparence selon le type
                        if cue_type == CueType.HOT_CUE.value:
                            # Hot Cue - Carré avec numéro
                            size = 12
                            painter.drawRect(int(position) - size//2, mid_y - size//2, size, size)
                            painter.setPen(QPen(QColor('#FFFFFF'), 1))
                            hotcue_num = str(cue.get('hotcue', '-'))
                            painter.drawText(QRect(int(position) - 6, mid_y - 7, 12, 14), 
                                          Qt.AlignmentFlag.AlignCenter, hotcue_num)
                        
                        elif cue_type == CueType.LOAD.value:
                            # Memory Cue - Triangle
                            painter.drawEllipse(QPoint(int(position), mid_y), 6, 6)
                            
                        elif cue_type == CueType.LOOP.value and cue.get('len', 0) > 0:
                            # Loop - Cercle avec rectangle
                            painter.drawEllipse(QPoint(int(position), mid_y), 6, 6)
                            
                            # Dessiner une ligne pour représenter la longueur
                            end_position = 10 + (((cue.get('start', 0) + cue.get('len', 0)) / total_duration) * (width - 20))
                            
                            # Rectangle semi-transparent pour montrer la boucle
                            loop_color = QColor(color)
                            loop_color.setAlpha(80)
                            painter.setBrush(QBrush(loop_color))
                            painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
                            painter.drawRect(QRect(int(position), mid_y - 10, int(end_position - position), 20))
            
            def _is_visible(self, cue):
                """Détermine si un point doit être affiché selon les filtres."""
                cue_type = cue.get('type', -1)
                if cue_type == CueType.HOT_CUE.value:
                    return self.show_hotcues
                elif cue_type == CueType.LOAD.value:
                    return self.show_memory_cues
                elif cue_type == CueType.LOOP.value:
                    return self.show_loops
                return False
        
        # Créer et retourner le widget
        return EnhancedTimelineView(self.track, self.cue_points)
    
    def _create_cue_table(self):
        """Crée une table de points de repère plus détaillée."""
        # Créer une QTreeWidget pour l'affichage tabulaire
        table = QTreeWidget()
        table.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                alternate-background-color: {AppConfig.COLORS['bg_light']};
            }}
            QHeaderView::section {{
                background-color: {AppConfig.COLORS['bg_dark']};
                color: {AppConfig.COLORS['fg_light']};
                padding: 5px;
                border: none;
            }}
            QTreeWidget::item {{
                padding: 4px;
            }}
        """)
        
        table.setAlternatingRowColors(True)
        table.setRootIsDecorated(False)
        table.setSortingEnabled(False)  # Désactivé par défaut, peut être activé via UI
        
        # Définir les colonnes
        columns = ["#", "Time", "Type", "Length", "Name", "Details"]
        table.setColumnCount(len(columns))
        table.setHeaderLabels(columns)
        
        # Configurer les largeurs de colonnes
        column_widths = {'#': 40, 'Time': 100, 'Type': 120, 'Length': 100, 'Name': 150, 'Details': 150}
        for i, col in enumerate(columns):
            table.setColumnWidth(i, column_widths.get(col, 100))
        
        # Remplir avec les points de repère
        self._populate_cue_table(table)
        
        return table
    
    def _populate_cue_table(self, table):
        """Remplit la table avec les points de repère."""
        table.clear()
        
        # Fonction pour formater le temps
        def format_time(ms):
            seconds = ms / 1000
            minutes = int(seconds // 60)
            seconds = seconds % 60
            return f"{minutes:02d}:{seconds:05.2f}"
        
        # Ajouter Grid Anchor en premier s'il existe et est visible
        if self.track.grid_anchor_ms is not None and self.show_grid:
            grid_item = QTreeWidgetItem()
            
            grid_item.setText(0, "G")
            grid_item.setText(1, format_time(self.track.grid_anchor_ms))
            grid_item.setText(2, "Grid Anchor")
            grid_item.setText(3, "-")  # Pas de longueur
            grid_item.setText(4, "BPM Beat 1")
            grid_item.setText(5, f"BPM: {self.track.bpm:.2f}")
            
            # Couleur cyan pour Grid Anchor
            for col in range(6):
                grid_item.setForeground(col, QColor('#00FFFF'))
                
            table.addTopLevelItem(grid_item)
        
        # Ajouter les points de repère
        row_index = 1  # Commencer l'indexation après le Grid Anchor
        
        for cue in self.cue_points:
            # Ne pas afficher si filtré
            if (cue.get('type') == CueType.HOT_CUE.value and not self.show_hotcues or
                cue.get('type') == CueType.LOAD.value and not self.show_memory_cues or
                cue.get('type') == CueType.LOOP.value and not self.show_loops):
                continue
                
            item = QTreeWidgetItem()
            
            # Determiner type et détails
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
            
            # Ajouter durée pour les loops
            length_str = "-"
            if cue_type == CueType.LOOP.value and cue.get('len', 0) > 0:
                length_str = format_time(cue.get('len', 0))
            
            # Définir les données de colonnes
            item.setText(0, str(row_index))
            item.setText(1, format_time(cue.get('start', 0)))
            item.setText(2, type_str)
            item.setText(3, length_str)
            item.setText(4, name_str)
            item.setText(5, details_str)
            
            # Coloration selon le type
            if cue_type == CueType.HOT_CUE.value:
                item.setForeground(2, QColor('#ff4d4d'))
            elif cue_type == CueType.LOAD.value:
                item.setForeground(2, QColor('#4da6ff'))
            elif cue_type == CueType.LOOP.value:
                item.setForeground(2, QColor('#4dff88'))
            
            table.addTopLevelItem(item)
            row_index += 1
    
    def _update_filters(self):
        """Met à jour les filtres et rafraîchit l'affichage."""
        self.show_hotcues = self.hotcue_check.isChecked()
        self.show_memory_cues = self.memory_check.isChecked()
        self.show_loops = self.loop_check.isChecked()
        self.show_grid = self.grid_check.isChecked()
        
        # Mettre à jour la timeline
        self.timeline_view.update_filters(
            self.show_hotcues, 
            self.show_memory_cues, 
            self.show_loops,
            self.show_grid
        )
        
        # Mettre à jour la table
        self._populate_cue_table(self.cue_table)
    
    def _export_to_clipboard(self):
        """Exporte les données des points de repère dans le presse-papier."""
        from PySide6.QtGui import QClipboard
        
        clipboard_text = f"Cue Points: {self.track.artist} - {self.track.title}\n"
        clipboard_text += f"BPM: {self.track.bpm:.1f}\n"
        if self.track.musical_key:
            key = AudioKeyTranslator().translate(self.track.musical_key)
            clipboard_text += f"Key: {key}\n"
        clipboard_text += f"Duration: {int(self.track.playtime // 60)}:{int(self.track.playtime % 60):02d}\n"
        
        # Ajouter Grid Anchor
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
        
        # D'abord Grid Anchor si présent et activé
        if self.track.grid_anchor_ms is not None and self.show_grid:
            clipboard_text += f"G. Grid Anchor @ {format_time(self.track.grid_anchor_ms)} - Beat 1\n"
        
        # Ensuite les autres points de repère
        idx = 1
        for cue in self.cue_points:
            # Ne pas inclure les points filtrés
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
                
            # Format de ligne
            line = f"{idx}. {type_str} @ {format_time(cue.get('start', 0))}"
            
            # Ajouter longueur pour les loops
            if cue_type == CueType.LOOP.value and cue.get('len', 0) > 0:
                line += f" - Length: {format_time(cue.get('len', 0))}"
                
            # Ajouter nom s'il existe
            name = cue.get('name', '')
            if name:
                line += f" - '{name}'"
                
            clipboard_text += line + "\n"
            idx += 1
        
        # Copier dans le presse-papier
        QApplication.clipboard().setText(clipboard_text)
        
        # Message de confirmation
        points_count = sum(1 for cue in self.cue_points if (
            (cue.get('type') == CueType.HOT_CUE.value and self.show_hotcues) or
            (cue.get('type') == CueType.LOAD.value and self.show_memory_cues) or
            (cue.get('type') == CueType.LOOP.value and self.show_loops)
        ))
        
        if self.track.grid_anchor_ms is not None and self.show_grid:
            points_count += 1
            
        QMessageBox.information(self, "Export Successful", 
                               f"Cue points data copied to clipboard.\n{points_count} points exported.")

class DetailsWindow(QDialog):
    """Window for displaying detailed track information."""
    
    def __init__(self, playlist: PlaylistNode, parent=None):
        super().__init__(parent)
        self.playlist = playlist
        self.key_translator = AudioKeyTranslator()
        self.audio_manager = AudioManager()
        self.audio_manager.initialize(self)
        self.playing_track_id = None
        
        self.setWindowTitle(f"Details for: {playlist.name}")
        self.resize(1200, 500)
        self.setStyleSheet(f"background-color: {AppConfig.COLORS['bg_dark']}; color: {AppConfig.COLORS['fg_light']};")
        
        # Track selection
        self.selected_track_id = None
        self.click_start_x = None
        self.click_start_y = None
        
        # Key format
        self.key_format = "Open Key"
        
        # IMPORTANT : Configurer le focus pour capturer les événements clavier
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_KeyCompression, False)
        
        # Setup UI
        self._setup_ui()
        self._populate_table()
    
    def _setup_ui(self):
        """Set up the details window UI."""
        layout = QVBoxLayout(self)
        
        # Search and options bar
        options_frame = QFrame()
        options_layout = QHBoxLayout(options_frame)
        options_layout.setContentsMargins(0, 0, 0, 0)
        
        # Search
        search_label = QLabel("Search:")
        self.search_field = QLineEdit()
        self.search_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                padding: 5px;
            }}
        """)
        self.search_field.textChanged.connect(self._filter_tracks)
        
        # Key format selector
        key_label = QLabel("Key Format:")
        self.key_format_button = QPushButton(self.key_format)
        self.key_format_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                padding: 6px 12px;
                text-align: left;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {AppConfig.COLORS['bg_light']};
            }}
            QPushButton::menu-indicator {{
                image: none;
                width: 0px;
            }}
        """)
        
        # Créer le menu pour key format
        key_menu = QMenu(self)
        key_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: 1px solid {AppConfig.COLORS['bg_light']};
                padding: 2px;
            }}
            QMenu::item {{
                padding: 6px 12px;
                margin: 1px;
            }}
            QMenu::item:selected {{
                background-color: {AppConfig.COLORS['accent_primary']};
            }}
        """)
        
        open_key_action = key_menu.addAction("Open Key")
        classical_action = key_menu.addAction("Classical")
        
        open_key_action.triggered.connect(lambda: self._change_key_format("Open Key"))
        classical_action.triggered.connect(lambda: self._change_key_format("Classical"))
        
        self.key_format_button.setMenu(key_menu)
        
        options_layout.addWidget(search_label)
        options_layout.addWidget(self.search_field, 1)
        options_layout.addWidget(key_label)
        options_layout.addWidget(self.key_format_button)
        
        layout.addWidget(options_frame)
        
        # Info label
        info_label = QLabel("Shortcuts: P = Play/Pause selected track | Click ▶ to play | Double-click on Cue column to open Cue List")
        layout.addWidget(info_label)
        
        # Tracks table
        self.tracks_table = QTreeWidget()
        self.tracks_table.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                alternate-background-color: {AppConfig.COLORS['bg_light']};
                font-size: 9pt;
            }}
            QHeaderView::section {{
                background-color: {AppConfig.COLORS['bg_dark']};
                color: {AppConfig.COLORS['fg_light']};
                padding: 5px;
                border: none;
                font-size: 9pt;
            }}
            QTreeWidget::item {{
                padding-top: 4px;
                padding-bottom: 4px;
            }}
        """)

        self.tracks_table.setAlternatingRowColors(True)
        self.tracks_table.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tracks_table.setRootIsDecorated(False)

        # Define columns - séparer play/pause du reste
        columns = ['▶', '#', 'Artist', 'Title', 'Key', 'BPM', 'Gain', 'Grid', 'Duration', 'Cues Detail', 'Album']
        self.tracks_table.setColumnCount(len(columns))
        self.tracks_table.setHeaderLabels(columns)

        # Set column widths
        column_widths = {'▶': 30, '#': 40, 'Artist': 200, 'Title': 280, 'Key': 60, 
                         'BPM': 60, 'Gain': 60, 'Grid': 40, 'Duration': 70, 
                         'Cues Detail': 100, 'Album': 220}

        for i, col in enumerate(columns):
            self.tracks_table.setColumnWidth(i, column_widths.get(col, 100))

        # Important: Ne PAS activer le tri automatique
        self.tracks_table.setSortingEnabled(False)
        
        # Configurer manuellement le comportement de tri
        self.tracks_table.header().setSortIndicatorShown(True)
        self.tracks_table.header().setSectionsClickable(True)

        # Connect custom sort handler qui gèrera les clics d'en-tête
        self.tracks_table.header().sectionClicked.connect(self._on_header_clicked)

        # Connect signals
        self.tracks_table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tracks_table.itemPressed.connect(self._on_item_pressed)
        self.tracks_table.itemClicked.connect(self._on_item_clicked)
        self.tracks_table.itemSelectionChanged.connect(self._on_selection_changed)

        # Store sort state
        self.sort_column = -1
        self.sort_order = Qt.SortOrder.AscendingOrder
        
        layout.addWidget(self.tracks_table)
    
    def _on_key_format_changed(self, new_format):
        """Handle key format change."""
        self.key_format = new_format
        self._populate_table()  # Refresh the table with new key format
        
    def _change_key_format(self, format_name):
        """Change key format and update display."""
        self.key_format = format_name
        self.key_format_button.setText(format_name)
        self._populate_table()
    
    def _populate_table(self):
        """Populate the table with track information."""
        # Si aucun tri n'est défini, utiliser l'ordre d'origine
        if self.sort_column == -1:
            self._populate_table_with_tracks(self.playlist.tracks)
        else:
            # Si un tri a été spécifié, l'appliquer
            tracks_to_sort = list(self.playlist.tracks)
            
            if self.sort_column == 1:  # Number column
                if self.sort_order == Qt.SortOrder.DescendingOrder:
                    tracks_to_sort.reverse()
            elif self.sort_column == 2:  # Artist
                tracks_to_sort.sort(key=lambda t: t.artist.lower(), 
                                   reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
            elif self.sort_column == 3:  # Title
                tracks_to_sort.sort(key=lambda t: t.title.lower(), 
                                   reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
            elif self.sort_column == 4:  # Key
                tracks_to_sort.sort(
                    key=lambda t: self.key_translator.translate(t.musical_key, self.key_format), 
                    reverse=(self.sort_order == Qt.SortOrder.DescendingOrder)
                )
            elif self.sort_column == 5:  # BPM
                tracks_to_sort.sort(key=lambda t: t.bpm, 
                                   reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
            elif self.sort_column == 6:  # Gain
                tracks_to_sort.sort(key=lambda t: t.gain, 
                                   reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
            elif self.sort_column == 7:  # Grid
                tracks_to_sort.sort(key=lambda t: 1 if t.grid_anchor_ms is not None else 0, 
                                   reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
            elif self.sort_column == 8:  # Duration
                tracks_to_sort.sort(key=lambda t: t.playtime, 
                                   reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
            elif self.sort_column == 9:  # Cues Detail
                tracks_to_sort.sort(key=lambda t: len(t.cue_points), 
                                   reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
            elif self.sort_column == 10:  # Album
                tracks_to_sort.sort(key=lambda t: t.album.lower(), 
                                   reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
            
            self._populate_table_with_tracks(tracks_to_sort)
    
    def _populate_table_with_tracks(self, tracks):
        """Populate the table with the provided tracks."""
        # Sauvegarder l'état actuel de lecture ET la sélection
        current_state = self.audio_manager.get_current_state()
        currently_playing_id = current_state['item_id']
        is_playing = current_state['is_playing']
        
        # Sauvegarder la sélection actuelle
        selected_items = self.tracks_table.selectedItems()
        selected_track_id = None
        if selected_items:
            selected_track_id = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        
        # Désactiver temporairement les signaux pour éviter les interactions pendant la mise à jour
        self.tracks_table.blockSignals(True)
        self.tracks_table.clear()
        
        # Define key colors
        open_key_colors = {
            '1A': '#FF80C0', '2A': '#FF80FF', '3A': '#C080FF', '4A': '#8080FF', 
            '5A': '#80C0FF', '6A': '#80FFFF', '7A': '#80FFC0', '8A': '#80FF80', 
            '9A': '#C0FF80', '10A': '#FFFF80', '11A': '#FFC080', '12A': '#FF8080',
            '1B': '#FF80C0', '2B': '#FF80FF', '3B': '#C080FF', '4B': '#8080FF', 
            '5B': '#80C0FF', '6B': '#80FFFF', '7B': '#80FFC0', '8B': '#80FF80', 
            '9B': '#C0FF80', '10B': '#FFFF80', '11B': '#FFC080', '12B': '#FF8080',
        }
        
        classical_key_colors = {
            'C': '#FF8080', 'G': '#FFFF80', 'D': '#80FF80', 'A': '#80FFC0', 
            'E': '#80FFFF', 'B': '#80C0FF', 'F#': '#8080FF', 'C#': '#C080FF', 
            'G#': '#FF80FF', 'D#': '#FF80C0', 'A#': '#FFC080', 'F': '#FFC080',
            'Am': '#FF80C0', 'Em': '#FF80FF', 'Bm': '#C080FF', 'F#m': '#8080FF', 
            'C#m': '#80C0FF', 'G#m': '#80FFFF', 'D#m': '#80FFC0', 'Bbm': '#80FF80', 
            'Fm': '#C0FF80', 'Cm': '#FFFF80', 'Gm': '#FFC080', 'Dm': '#FF8080',
        }
        
        item_to_reselect = None
        
        for i, track in enumerate(tracks, 1):
            item = QTreeWidgetItem()
            track_id = id(track)
            
            # Calculate values
            play_sec = float(track.playtime)
            duration = f"{int(play_sec // 60):02d}:{int(play_sec % 60):02d}"
            key = self.key_translator.translate(track.musical_key, self.key_format)
            gain = f"{track.gain:+.2f}" if track.gain else ""
            grid_marker = "✓" if track.grid_anchor_ms is not None else ""
            cue_summary = self._get_cue_summary(track.cue_points)
            
            # Déterminer l'icône de lecture en fonction de l'état actuel
            play_icon = "⏸" if is_playing and track_id == currently_playing_id else "▶"
            
            # Remplir les colonnes
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
            
            # Set key color based on format
            if self.key_format == "Open Key" and key in open_key_colors:
                item.setForeground(4, QColor(open_key_colors[key]))
            elif self.key_format == "Classical" and key in classical_key_colors:
                item.setForeground(4, QColor(classical_key_colors[key]))
            
            # Stocker l'ID de la piste dans les données utilisateur
            item.setData(0, Qt.ItemDataRole.UserRole, track_id)
            
            # Marquer l'item à resélectionner si nécessaire
            if selected_track_id and track_id == selected_track_id:
                item_to_reselect = item
            
            # Ajouter à la table
            self.tracks_table.addTopLevelItem(item)
        
        # Réactiver les signaux
        self.tracks_table.blockSignals(False)
        
        # Restaurer la sélection
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
    
    def _on_header_clicked(self, column_index):
        """Handle header column click for sorting."""
        # Ignorer complètement la colonne play/pause (colonne 0)
        if column_index == 0:
            return
        
        # Toggle sort order if clicking the same column
        if column_index == self.sort_column:
            self.sort_order = Qt.SortOrder.DescendingOrder if self.sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.sort_column = column_index
            self.sort_order = Qt.SortOrder.AscendingOrder
        
        # Update sort indicator
        self.tracks_table.header().setSortIndicator(column_index, self.sort_order)
        
        # Get copy of tracks to sort
        tracks_to_sort = list(self.playlist.tracks)
        
        # Sort based on column
        if column_index == 1:  # Number column
            if self.sort_order == Qt.SortOrder.DescendingOrder:
                tracks_to_sort.reverse()
        elif column_index == 2:  # Artist
            tracks_to_sort.sort(key=lambda t: t.artist.lower(), 
                               reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
        elif column_index == 3:  # Title
            tracks_to_sort.sort(key=lambda t: t.title.lower(), 
                               reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
        elif column_index == 4:  # Key
            tracks_to_sort.sort(
                key=lambda t: self.key_translator.translate(t.musical_key, self.key_format), 
                reverse=(self.sort_order == Qt.SortOrder.DescendingOrder)
            )
        elif column_index == 5:  # BPM
            tracks_to_sort.sort(key=lambda t: t.bpm, 
                               reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
        elif column_index == 6:  # Gain
            tracks_to_sort.sort(key=lambda t: t.gain, 
                               reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
        elif column_index == 7:  # Grid
            tracks_to_sort.sort(key=lambda t: 1 if t.grid_anchor_ms is not None else 0, 
                               reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
        elif column_index == 8:  # Duration
            tracks_to_sort.sort(key=lambda t: t.playtime, 
                               reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
        elif column_index == 9:  # Cues Detail
            tracks_to_sort.sort(key=lambda t: len(t.cue_points), 
                               reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
        elif column_index == 10:  # Album
            tracks_to_sort.sort(key=lambda t: t.album.lower(), 
                               reverse=(self.sort_order == Qt.SortOrder.DescendingOrder))
        
        # Clear and repopulate table with sorted tracks
        self._populate_table_with_tracks(tracks_to_sort)
    
    def _get_cue_summary(self, cue_points: List[Dict]) -> str:
        """Generate cue point summary for display."""
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
    
    def _on_item_double_clicked(self, item, column):
        """Handle double-click on an item."""
        if column == 9:  # Cues Detail column
            track_id = item.data(0, Qt.ItemDataRole.UserRole)
            if track_id:
                # Find the track
                for track in self.playlist.tracks:
                    if id(track) == track_id:
                        # Show timeline dialog
                        dialog = TimelineDialog(track, self)
                        dialog.exec()
                        break
    
    def _on_item_pressed(self, item, column):
        """Store item and position when mouse is pressed."""
        self.selected_track_id = item.data(0, Qt.ItemDataRole.UserRole)
        self.click_start_x = self.tracks_table.visualItemRect(item).x()
    
    def _on_item_clicked(self, item, column):
        """Handle clicks on items."""
        if column == 0:  # Play button column
            track_id = item.data(0, Qt.ItemDataRole.UserRole)
            self._toggle_playback(item, track_id)
    
    def _on_selection_changed(self):
        """Handle selection changes."""
        selected_items = self.tracks_table.selectedItems()
        if selected_items:
            self.selected_track_id = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
            # S'assurer que la fenêtre garde le focus
            self.setFocus()

    
    def keyPressEvent(self, event):
        """Override the key press event handler."""
        print(f"Touche détectée: {event.key()}, Qt.Key.Key_P = {Qt.Key.Key_P}")  # Debug
        
        if event.key() == Qt.Key.Key_P:
            print("Touche P détectée dans keyPressEvent")  # Debug
            selected_items = self.tracks_table.selectedItems()
            if selected_items:
                print(f"Item sélectionné trouvé: {len(selected_items)}")  # Debug
                item = selected_items[0]
                track_id = item.data(0, Qt.ItemDataRole.UserRole)
                if track_id:
                    print(f"Track ID: {track_id}")  # Debug
                    self._toggle_playback(item, track_id)
                    event.accept()
                    return
            else:
                print("Aucun item sélectionné")  # Debug
        
        super().keyPressEvent(event)
        
    def showEvent(self, event):
        """S'assurer que la fenêtre a le focus quand elle s'ouvre."""
        super().showEvent(event)
        self.setFocus()
        self.activateWindow()
        self.raise_()
    
    def _toggle_playback(self, item, track_id):
        """Toggle playback for a track."""
        if not track_id:
            return
            
        # Get current state
        current_state = self.audio_manager.get_current_state()
        
        # If something is playing, stop it
        if current_state['is_playing']:
            self.audio_manager.stop()
            
            # Update icon for previously playing item
            if current_state['item_id']:
                for i in range(self.tracks_table.topLevelItemCount()):
                    curr_item = self.tracks_table.topLevelItem(i)
                    if curr_item.data(0, Qt.ItemDataRole.UserRole) == current_state['item_id']:
                        curr_item.setText(0, "▶")
                        break
            
            # If the same track was playing, just stop and return
            if current_state['item_id'] == track_id:
                self.playing_track_id = None
                return
        
        # Find the track
        for track in self.playlist.tracks:
            if id(track) == track_id:
                # Play the track
                if track.file_path and os.path.exists(track.file_path):
                    if self.audio_manager.play_file(track.file_path, track_id):
                        item.setText(0, "⏸")
                        self.playing_track_id = track_id
                    else:
                        QMessageBox.warning(self, "File Not Found", 
                                            f"The audio file for this track could not be found.")
                break
    
    def closeEvent(self, event):
        """Handle window close event."""
        self.audio_manager.stop()
        self.audio_manager.cleanup()
        event.accept()

class LogDialog(QDialog):
    """Dialog for displaying log messages."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conversion Log")
        self.resize(800, 500)
        self.setStyleSheet(f"background-color: {AppConfig.COLORS['bg_dark']}; color: {AppConfig.COLORS['fg_light']};")
        
        # Setup UI
        layout = QVBoxLayout(self)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                font-family: 'Consolas', monospace;
                font-size: 9pt;
            }}
        """)
        
        layout.addWidget(self.log_text)
        
        # Add buttons frame
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        
        # Add Clear button
        clear_button = QPushButton("Clear Log")
        clear_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {AppConfig.COLORS['bg_light']};
            }}
        """)
        clear_button.clicked.connect(self.clear_log)
        
        # Add Close button
        close_button = QPushButton("Close")
        close_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {AppConfig.COLORS['bg_light']};
            }}
        """)
        close_button.clicked.connect(self.accept)
        
        # Add buttons to layout
        button_layout.addWidget(clear_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addWidget(button_frame)
    
    def append_log(self, message):
        """Append message to log."""
        self.log_text.append(message)
        # Scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def clear_log(self):
        """Clear all log content."""
        self.log_text.clear()


class AboutDialog(QDialog):
    """Dialog for displaying application information."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        self.resize(400, 200)
        self.setStyleSheet(f"background-color: {AppConfig.COLORS['bg_dark']}; color: {AppConfig.COLORS['fg_light']};")
        
        # Setup UI
        layout = QVBoxLayout(self)
        
        # App name
        app_name = QLabel(AppConfig.APP_NAME)
        app_name.setStyleSheet("font-size: 18pt; font-weight: bold;")
        app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Version
        version = QLabel(f"Version: {AppConfig.VERSION}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Author
        author = QLabel(f"Author: {AppConfig.AUTHOR}")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Website
        website = QLabel(f"Website: {AppConfig.WEBSITE}")
        website.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(app_name)
        layout.addWidget(version)
        layout.addWidget(author)
        layout.addWidget(website)
        layout.addStretch()
        
        # Close button
        close_button = QPushButton("Close")
        close_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {AppConfig.COLORS['bg_light']};
            }}
        """)
        close_button.clicked.connect(self.accept)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)


class UsageDialog(QDialog):
    """Dialog for displaying usage instructions."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Usage Guide")
        self.resize(500, 400)
        self.setStyleSheet(f"background-color: {AppConfig.COLORS['bg_dark']}; color: {AppConfig.COLORS['fg_light']};")
        
        # Setup UI
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("USAGE GUIDE")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Content
        content = QTextEdit()
        content.setReadOnly(True)
        content.setStyleSheet(f"""
            QTextEdit {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
            }}
        """)
        
        usage_text = """
<h3>How to Use:</h3>
<ol>
<li>Select your Traktor .nml file.</li>
<li>(Optional) Select your music root folder to find moved files.</li>
<li>Choose one or more playlists/folders from the list.</li>
<li>Select export format (Database or XML).</li>
<li>Click CONVERT and select your destination drive.</li>
</ol>

<h3>Audio Playback:</h3>
<ul>
<li>Tracks play in full length</li>
<li>Click the ▶ button or press P to play/stop tracks</li>
<li>Double-click on Cue column to open Cue List</li>
</ul>

<h3>Export Formats:</h3>
<ul>
<li><strong>Database:</strong> Creates SQLite database (rekordbox.pdb) for CDJs</li>
<li><strong>XML:</strong> Creates rekordbox.xml file for Rekordbox software like Serato</li>
</ul>
"""
        content.setHtml(usage_text)
        
        layout.addWidget(title)
        layout.addWidget(content)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {AppConfig.COLORS['bg_light']};
            }}
        """)
        close_button.clicked.connect(self.accept)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)


class ConverterGUI(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        # Set window properties
        self.setWindowTitle(f"{AppConfig.APP_NAME} v{AppConfig.VERSION}")
        self.resize(AppConfig.WINDOW_WIDTH, AppConfig.WINDOW_HEIGHT)
        self.setMinimumSize(AppConfig.MIN_WIDTH, AppConfig.MIN_HEIGHT)
        
        # Application state variables
        self.config_file = Path(sys.argv[0]).parent / "converter_config.json"
        self.nml_path = ""
        self.output_path = ""
        self.music_root_path = ""
        self.copy_music = True
        self.verify_copy = False
        self.key_format = "Open Key"
        self.export_format = "Database"
        self.playlist_structure = []
        self.selected_playlists = []
        
        # Threading and communication
        self.cancel_event = threading.Event()
        self.progress_queue = queue.Queue()
        
        # Enhanced audio system
        self.audio_manager = AudioManager()
        
        # UI elements
        self.playlist_tree = None
        self.convert_button = None
        self.cancel_button = None
        self.progress_bar = None
        self.progress_label = None
        self.playlist_info = None
        
        # Logging
        self.log_handler = LogHandler()
        self.log_dialog = None
        
        # Utilities
        self.key_translator = AudioKeyTranslator()
        
        # Setup UI
        self._setup_ui()
        self._load_configuration()
        self._center_window()
        self._set_default_nml_path()
        
        # Start progress update timer
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self._check_progress_queue)
        self.progress_timer.start(100)  # Check every 100ms

    def _set_default_nml_path(self):
        """Set default NML path if not already set."""
        if not self.nml_path:
            traktor_folder = self.find_latest_traktor_version()
            if traktor_folder:
                filename = traktor_folder + os.sep + "collection.nml"
                self.nml_path = filename
                self.nml_input.setText(filename)
                self._load_playlists()
                print(f"DEBUG: Setting default NML path to: {filename}")
            else:
                print("DEBUG: No Traktor folder found, cannot set default NML path.")
        else:
            print("DEBUG: NML path already set.")
    
    def _setup_ui(self):
        """Set up the main UI."""
        # Set application style
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {AppConfig.COLORS['bg_dark']};
                color: {AppConfig.COLORS['fg_light']};
            }}
            QLabel {{
                color: {AppConfig.COLORS['fg_light']};
            }}
            QPushButton {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {AppConfig.COLORS['bg_light']};
            }}
            QLineEdit {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                padding: 6px;
            }}
            QComboBox {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                padding: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                selection-background-color: {AppConfig.COLORS['accent_primary']};
            }}
            QProgressBar {{
                border: none;
                background-color: {AppConfig.COLORS['bg_medium']};
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {AppConfig.COLORS['accent_primary']};
            }}
            QTreeWidget {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                alternate-background-color: {AppConfig.COLORS['bg_light']};
            }}
            QHeaderView::section {{
                background-color: {AppConfig.COLORS['bg_dark']};
                color: {AppConfig.COLORS['fg_light']};
                padding: 5px;
                border: none;
            }}
            QCheckBox {{
                color: {AppConfig.COLORS['fg_light']};
            }}
        """)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Create UI sections
        self._create_title_section(main_layout)
        self._create_file_sections(main_layout)
        self._create_playlist_section(main_layout)
        self._create_options_section(main_layout)
        self._create_progress_section(main_layout)
        self._create_action_section(main_layout)
        self._create_close_section(main_layout)  # AJOUTEZ CETTE LIGNE
        self._create_menu()
    
    def _create_title_section(self, parent_layout):
        """Create application title and description."""
        title_frame = QFrame()
        title_layout = QVBoxLayout(title_frame)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        title_label = QLabel("Traktor Bridge")
        title_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        
        # Subtitle
        subtitle_label = QLabel("Professional Traktor to Pioneer CDJ/XML Converter")
        subtitle_label.setStyleSheet(f"color: {AppConfig.COLORS['fg_muted']};")
        
        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)
        
        parent_layout.addWidget(title_frame)
        parent_layout.addSpacing(15)
    
    def _create_file_sections(self, parent_layout):
        """Create file selection sections."""
        file_frame = QFrame()
        file_layout = QVBoxLayout(file_frame)
        file_layout.setContentsMargins(0, 0, 0, 0)
        
        # NML file section
        nml_frame = QFrame()
        nml_layout = QVBoxLayout(nml_frame)
        nml_layout.setContentsMargins(0, 0, 0, 0)
        
        nml_label_frame = QFrame()
        nml_label_layout = QHBoxLayout(nml_label_frame)
        nml_label_layout.setContentsMargins(0, 0, 0, 0)
        
        nml_label = QLabel("1. Traktor NML File")
        nml_label.setStyleSheet("color: #00b4d8; font-weight: bold;")
        nml_required = QLabel("*")
        nml_required.setStyleSheet("color: #dc3545;")
        
        nml_label_layout.addWidget(nml_label)
        nml_label_layout.addWidget(nml_required)
        nml_label_layout.addStretch()
        
        nml_input_frame = QFrame()
        nml_input_layout = QHBoxLayout(nml_input_frame)
        nml_input_layout.setContentsMargins(0, 0, 0, 0)
        
        self.nml_input = QLineEdit()
        self.nml_input.setPlaceholderText("Select Traktor NML file...")
        
        nml_browse_button = QPushButton("Browse...")
        nml_browse_button.clicked.connect(self._browse_nml)
        
        nml_input_layout.addWidget(self.nml_input)
        nml_input_layout.addWidget(nml_browse_button)
        
        nml_layout.addWidget(nml_label_frame)
        nml_layout.addWidget(nml_input_frame)
        
        # Music root folder section
        music_frame = QFrame()
        music_layout = QVBoxLayout(music_frame)
        music_layout.setContentsMargins(0, 0, 0, 0)
        
        music_label = QLabel("2. Music Root Folder (Optional)")
        music_label.setStyleSheet("color: #00b4d8; font-weight: bold;")
        
        music_input_frame = QFrame()
        music_input_layout = QHBoxLayout(music_input_frame)
        music_input_layout.setContentsMargins(0, 0, 0, 0)
        
        self.music_input = QLineEdit()
        self.music_input.setPlaceholderText("Select music root folder...")
        
        music_browse_button = QPushButton("Browse...")
        music_browse_button.clicked.connect(self._browse_music_root)
        
        music_input_layout.addWidget(self.music_input)
        music_input_layout.addWidget(music_browse_button)
        
        music_layout.addWidget(music_label)
        music_layout.addWidget(music_input_frame)
        
        # Add to file frame
        file_layout.addWidget(nml_frame)
        file_layout.addSpacing(15)
        file_layout.addWidget(music_frame)
        
        parent_layout.addWidget(file_frame)
        parent_layout.addSpacing(10)

    def find_latest_traktor_version(self):
        """
        Finds the latest version of Traktor installed on the system.

        Returns:
            str: The path to the latest version of Traktor.
                None if Traktor folder is not found.
        """
        documents_path = os.path.join(os.path.expanduser("~"), "Documents", "Native Instruments")
        try:
            traktor_versions = [folder for folder in os.listdir(documents_path) if folder.startswith("Traktor")]
        except FileNotFoundError:
            # Documents/Native Instruments directory not found
            print("Documents/Native Instruments directory not found")
            return None

        version_pattern = re.compile(r"Traktor (\d+\.\d+\.\d+)")

        valid_versions = [version_pattern.match(version).group(1) for version in traktor_versions if version_pattern.match(version)]

        if not valid_versions:
            print("No valid Traktor versions found")
            return None

        latest_version = max(valid_versions, key=lambda v: tuple(map(int, v.split('.'))))
        traktor_path = os.path.join(documents_path, f"Traktor {latest_version}")
        print(f"Found latest Traktor version at: {traktor_path}")
        return traktor_path
    
    def _create_playlist_section(self, parent_layout):
        """Create playlist selection tree view."""
        playlist_frame = QFrame()
        playlist_layout = QVBoxLayout(playlist_frame)
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        playlist_label = QLabel("3. Select Playlist(s)")
        playlist_label.setStyleSheet("color: #00b4d8; font-weight: bold;")
        playlist_layout.addWidget(playlist_label)
        
        # Tree view
        self.playlist_tree = QTreeWidget()
        self.playlist_tree.setHeaderHidden(True)
        self.playlist_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.playlist_tree.itemSelectionChanged.connect(self._on_playlist_select)
        self.playlist_tree.itemDoubleClicked.connect(self._on_playlist_double_click)
        
        playlist_layout.addWidget(self.playlist_tree)
        
        # Info line
        info_frame = QFrame()
        info_layout = QHBoxLayout(info_frame)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        self.playlist_info = QLabel("Select an NML file to see playlists.")
        
        details_button = QPushButton("View Details")
        details_button.clicked.connect(self._show_playlist_details)
        
        info_layout.addWidget(self.playlist_info)
        info_layout.addStretch()
        info_layout.addWidget(details_button)
        
        playlist_layout.addWidget(info_frame)
        
        parent_layout.addWidget(playlist_frame, 1)  # Give this section more space
    
    def _create_options_section(self, parent_layout):
        """Create conversion options controls."""
        options_frame = QFrame()
        options_layout = QHBoxLayout(options_frame)
        options_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left side - checkboxes
        left_frame = QFrame()
        left_layout = QHBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.copy_music_check = QCheckBox("Copy music files")
        self.copy_music_check.setChecked(self.copy_music)
        self.verify_copy_check = QCheckBox("Verify file integrity")
        self.verify_copy_check.setChecked(self.verify_copy)
        
        left_layout.addWidget(self.copy_music_check)
        left_layout.addWidget(self.verify_copy_check)
        left_layout.addStretch()
        
        # Right side - bouton export et log button
        right_frame = QFrame()
        right_layout = QHBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Export format - REMPLACÉ PAR BOUTON
        format_frame = QFrame()
        format_layout = QHBoxLayout(format_frame)
        format_layout.setContentsMargins(0, 0, 0, 0)
        
        format_label = QLabel("Export:")
        self.export_format_button = QPushButton(self.export_format)
        self.export_format_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: none;
                padding: 6px 12px;
                text-align: left;
                min-width: 70px;
            }}
            QPushButton:hover {{
                background-color: {AppConfig.COLORS['bg_light']};
            }}
            QPushButton::menu-indicator {{
                image: none;
                width: 0px;
            }}
        """)
        
        # Créer le menu pour export format
        export_menu = QMenu(self)
        export_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {AppConfig.COLORS['bg_medium']};
                color: {AppConfig.COLORS['fg_light']};
                border: 1px solid {AppConfig.COLORS['bg_light']};
                padding: 2px;
            }}
            QMenu::item {{
                padding: 6px 12px;
                margin: 1px;
            }}
            QMenu::item:selected {{
                background-color: {AppConfig.COLORS['accent_primary']};
            }}
        """)
        
        db_action = export_menu.addAction("Database")
        xml_action = export_menu.addAction("XML")
        
        db_action.triggered.connect(lambda: self._change_export_format("Database"))
        xml_action.triggered.connect(lambda: self._change_export_format("XML"))
        
        self.export_format_button.setMenu(export_menu)
        
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.export_format_button)
        
        right_layout.addWidget(format_frame)
        
        options_layout.addWidget(left_frame)
        options_layout.addStretch()
        options_layout.addWidget(right_frame)
        
        parent_layout.addWidget(options_frame)
    
    def _create_progress_section(self, parent_layout):
        """Create progress monitoring controls."""
        progress_frame = QFrame()
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        
        # Progress label
        self.progress_label = QLabel("Ready to convert...")
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_label)
        
        parent_layout.addWidget(progress_frame)
        parent_layout.addSpacing(10)
    
    def _create_action_section(self, parent_layout):
        """Create main action buttons."""
        action_frame = QFrame()
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(0, 0, 0, 0)
        
        # Convert button
        self.convert_button = QPushButton("CONVERT")
        self.convert_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {AppConfig.COLORS['accent_primary']};
                color: {AppConfig.COLORS['fg_light']};
                font-weight: bold;
                font-size: 11pt;
                padding: 12px;
            }}
            QPushButton:hover {{
                background-color: {AppConfig.COLORS['accent_hover']};
            }}
        """)
        self.convert_button.clicked.connect(self._start_conversion)
        
        # Cancel button
        self.cancel_button = QPushButton("CANCEL")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_conversion)
        
        action_layout.addWidget(self.convert_button)
        action_layout.addWidget(self.cancel_button)
        
        parent_layout.addWidget(action_frame)
    
    def _create_menu(self):
        """Create application menu bar."""
        menubar = self.menuBar()
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        # Ajouter l'entrée View Log dans le menu Help
        log_action = QAction("View Log", self)
        log_action.triggered.connect(self._show_log_window)
        help_menu.addAction(log_action)
        
        usage_action = QAction("Usage Guide", self)
        usage_action.triggered.connect(self._show_usage_dialog)
        help_menu.addAction(usage_action)
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)
    
    def _browse_nml(self):
        """Browse for Traktor NML file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Traktor NML File", "", 
            "NML Files (*.nml);;All Files (*.*)"
        )
        if filename:
            self.nml_path = filename
            self.nml_input.setText(filename)
            self._load_playlists()
    
    def _browse_music_root(self):
        """Browse for music root folder."""
        folder = QFileDialog.getExistingDirectory(self, "Select Music Root Folder")
        if folder:
            self.music_root_path = folder
            self.music_input.setText(folder)
    
    def _load_playlists(self):
        """Load playlists from NML file in background thread."""
        if not self.nml_path:
            return
        
        self.convert_button.setEnabled(False)
        self.convert_button.setText("LOADING...")
        self.progress_bar.setValue(0)
        self.playlist_tree.clear()
        self.playlist_info.setText("Loading playlists...")
        
        # Start loading thread
        self.loading_thread = LoadingThread(self.nml_path, self.music_root_path, self.progress_queue)
        self.loading_thread.finished.connect(self._finalize_nml_load)
        self.loading_thread.start()
    
    def _on_playlist_select(self):
        """Handle playlist tree selection changes."""
        selected_items = self.playlist_tree.selectedItems()
        if not selected_items:
            self.selected_playlists = []
            self.playlist_info.setText("No playlist selected.")
            return
        
        self.selected_playlists = []
        for item in selected_items:
            # Get playlist node stored in user role
            playlist_node = item.data(0, Qt.ItemDataRole.UserRole)
            if playlist_node:
                self.selected_playlists.append(playlist_node)
        
        self._update_selection_info()
    
    def _on_playlist_double_click(self, item, column):
        """Handle double-click on playlist tree."""
        playlist_node = item.data(0, Qt.ItemDataRole.UserRole)
        if playlist_node and playlist_node.type == 'playlist':
            self.playlist_tree.clearSelection()
            item.setSelected(True)
            self.selected_playlists = [playlist_node]
            self._show_playlist_details()
    
    def _update_selection_info(self):
        """Update playlist selection information display."""
        if not self.selected_playlists:
            self.playlist_info.setText("No playlist selected.")
            return
        
        total_tracks = sum(len(p.tracks) for p in self.selected_playlists if p.type == 'playlist')
        
        if len(self.selected_playlists) == 1:
            node = self.selected_playlists[0]
            if node.type == 'playlist':
                total_time = sum(t.playtime for t in node.tracks) / 60
                self.playlist_info.setText(f"{len(node.tracks)} tracks | {total_time:.1f} minutes")
            else:
                self.playlist_info.setText(f"Folder '{node.name}' selected")
        else:
            playlist_count = sum(1 for p in self.selected_playlists if p.type == 'playlist')
            self.playlist_info.setText(
                f"{len(self.selected_playlists)} items selected ({playlist_count} playlists, {total_tracks} tracks)"
            )
    
    def _start_conversion(self):
        """Start the conversion process after validation."""
        if not self._validate_inputs():
            return
        
        output_folder = QFileDialog.getExistingDirectory(self, "Select USB Drive or Output Folder")
        if not output_folder:
            return
        
        self.output_path = output_folder
        self.cancel_event.clear()
        self.convert_button.setEnabled(False)
        self.convert_button.setText("CONVERTING...")
        self.cancel_button.setEnabled(True)
        
        self._log_message(f"Starting conversion of {len(self.selected_playlists)} selected item(s)")
        
        # Update state from UI
        self.copy_music = self.copy_music_check.isChecked()
        self.verify_copy = self.verify_copy_check.isChecked()
        # Supprimez cette ligne:
        # self.key_format = self.key_format_combo.currentText()
        # self.export_format = self.export_format_combo.currentText()
        
        # Start conversion thread
        self.conversion_thread = ConversionThread(
            self.output_path,
            self.selected_playlists,
            self.playlist_structure,
            self.export_format,
            self.copy_music,
            self.verify_copy,
            self.key_format,
            self.progress_queue,
            self.cancel_event
        )
        self.conversion_thread.finished.connect(self._on_conversion_finished)
        self.conversion_thread.start()
    
    def _validate_inputs(self) -> bool:
        """Validate user inputs before conversion."""
        if not self.nml_path or not Path(self.nml_path).exists():
            QMessageBox.warning(self, "Input Required", "Please select a valid Traktor NML file.")
            return False
        
        if not self.selected_playlists:
            QMessageBox.warning(self, "Selection Required", "Please select at least one playlist or folder.")
            return False
        
        return True
        
    def _change_export_format(self, format_name):
        """Change export format and update button."""
        self.export_format = format_name
        self.export_format_button.setText(format_name)    
    
    def _cancel_conversion(self):
        """Cancel ongoing conversion process."""
        self.cancel_event.set()
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("CANCELLING...")
        self._log_message("Cancellation requested by user...")
    
    def _on_conversion_finished(self, status, message):
        """Handle conversion thread completion."""
        if status == "completed":
            self.progress_bar.setValue(100)
            self._log_message(f"--- COMPLETED: {message} ---")
            QMessageBox.information(self, "Success", message)
            self._reset_button_state()
        elif status == "cancelled":
            self.progress_bar.setValue(0)
            self._log_message(f"--- CANCELLED: {message} ---")
            QMessageBox.information(self, "Cancelled", message)
            self._reset_button_state()
        elif status == "error":
            self._log_message(f"--- ERROR: {message} ---", logging.ERROR)
            QMessageBox.critical(self, "Error", f"Conversion failed:\n{message}")
            self._reset_button_state()
            
    def _create_close_section(self, parent_layout):
            """Create close button section."""
            close_frame = QFrame()
            close_layout = QHBoxLayout(close_frame)
            close_layout.setContentsMargins(0, 0, 0, 0)
            
            # Close button
            close_button = QPushButton("Close")
            close_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {AppConfig.COLORS['bg_medium']};
                    color: {AppConfig.COLORS['fg_light']};
                    border: none;
                    padding: 8px 16px;
                }}
                QPushButton:hover {{
                    background-color: {AppConfig.COLORS['bg_light']};
                }}
            """)
            close_button.clicked.connect(self.close)
            
            close_layout.addStretch()
            close_layout.addWidget(close_button)
            
            parent_layout.addWidget(close_frame)
    
    def _reset_button_state(self):
        """Reset buttons to default state."""
        self.convert_button.setText("CONVERT")
        self.convert_button.setEnabled(True)
        self.cancel_button.setText("CANCEL")
        self.cancel_button.setEnabled(False)
        
    def _log_message(self, message: str, level: int = logging.INFO):
        """Log message to both file and GUI log."""
        log_entry = f"{datetime.now().strftime('%H:%M:%S')} - {message}"
        logging.log(level, message)
        
        # Toujours stocker les logs pour un accès ultérieur
        if not hasattr(self, '_log_messages'):
            self._log_messages = []
        self._log_messages.append(log_entry)
        
        # Afficher dans la fenêtre de log si elle existe et est visible
        if self.log_dialog and self.log_dialog.isVisible():
            try:
                self.log_dialog.append_log(log_entry)
            except Exception as e:
                print(f"Erreur lors de l'ajout au journal: {e}")
    
    def _show_playlist_details(self):
        """Show detailed track information for selected playlist."""
        if not self.selected_playlists:
            QMessageBox.information(self, "No Playlist Selected", 
                                   "Please select an item from the playlist tree first.")
            return
        
        first_selected = self.selected_playlists[0]
        if first_selected.type != 'playlist':
            QMessageBox.information(self, "Folder Selected", 
                                   "Details can only be shown for a single playlist. Please select a playlist, not a folder.")
            return
        
        details_dialog = DetailsWindow(first_selected, self)
        details_dialog.exec()

    def _show_log_window(self):
        """Display application log window."""
        if not self.log_dialog:
            self.log_dialog = LogDialog(self)
            # Cette connexion est cruciale
            self.log_handler.log_text_widget = self.log_dialog.log_text
            
            # Message de test
            self._log_message("Welcome to Traktor Bridge By Benoit (BSM) Saint-Moulin", logging.INFO)
            
            # Populate with stored logs if available
            if hasattr(self, '_log_messages'):
                for log_entry in self._log_messages:
                    self.log_dialog.append_log(log_entry)
        else:
            # S'assurer que la connexion est toujours valide si la fenêtre existe déjà
            self.log_handler.log_text_widget = self.log_dialog.log_text
        
        self.log_dialog.show()
        self.log_dialog.raise_()
        self.log_dialog.activateWindow()
    
    def _check_progress_queue(self):
        """Check progress queue for updates."""
        try:
            msg_type, data = self.progress_queue.get_nowait()
            
            if msg_type == "progress":
                percent, message = data
                self.progress_bar.setValue(percent)
                self.progress_label.setText(message)
                self._log_message(message)
            
        except queue.Empty:
            pass  # No updates in queue
    
    def _finalize_nml_load(self, result):
        """Process NML loading results."""
        self.convert_button.setEnabled(True)
        self.convert_button.setText("CONVERT")
        
        if isinstance(result, Exception):
            QMessageBox.critical(
                self, 
                "NML Parse Error", 
                f"Could not read the NML file.\nError: {result}"
            )
            self.playlist_info.setText("Error loading playlists.")
            return
        
        self.playlist_structure = result
        self.playlist_tree.clear()
        
        if not self.playlist_structure:
            self.playlist_info.setText("No playlists found in this file.")
            return
            
        self._populate_playlist_tree(self.playlist_structure)
        total_playlists = self._count_playlists(self.playlist_structure)
        self.playlist_info.setText(f"Loaded {total_playlists} playlists")
        self._log_message(f"Successfully loaded {total_playlists} playlists from NML file.")
    
    def _populate_playlist_tree(self, nodes: List[PlaylistNode], parent_item=None):
        """Populate playlist tree with folder and playlist nodes avec icônes."""
        for node in nodes:
            if parent_item is None:
                item = QTreeWidgetItem(self.playlist_tree)
            else:
                item = QTreeWidgetItem(parent_item)
            
            if node.type == 'folder':
                # Icône dossier
                item.setText(0, f"📁 {node.name}")
                self._populate_playlist_tree(node.children, item)
            elif node.type == 'playlist':
                # Icône playlist avec petit symbole musical
                item.setText(0, f"🎵 {node.name} ({len(node.tracks)} tracks)")
            
            # Store node reference in item
            item.setData(0, Qt.ItemDataRole.UserRole, node)
    
    def _count_playlists(self, structure: List[PlaylistNode]) -> int:
        """Count total number of playlists in structure."""
        count = 0
        for node in structure:
            if node.type == 'playlist':
                count += 1
            elif node.type == 'folder':
                count += self._count_playlists(node.children)
        return count
    
    def _show_usage_dialog(self):
        """Display usage instructions dialog."""
        usage_dialog = UsageDialog(self)
        usage_dialog.exec()
    
    def _show_about_dialog(self):
        """Display about dialog."""
        about_dialog = AboutDialog(self)
        about_dialog.exec()
    
    def _load_configuration(self):
        """Load application configuration from file."""
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
                
                # Update UI
                self.nml_input.setText(self.nml_path)
                self.music_input.setText(self.music_root_path)
                self.copy_music_check.setChecked(self.copy_music)
                self.verify_copy_check.setChecked(self.verify_copy)
                # Supprimer cette ligne :
                # self.key_format_combo.setCurrentText(self.key_format)
                self.export_format_button.setText(self.export_format)
        except Exception as e:
            logging.warning(f"Error loading configuration: {e}")
    
    def _save_configuration(self):
        """Save application configuration to file."""
        # Update state from UI
        self.nml_path = self.nml_input.text()
        self.music_root_path = self.music_input.text()
        self.copy_music = self.copy_music_check.isChecked()
        self.verify_copy = self.verify_copy_check.isChecked()
        # Supprimez cette ligne:
        # self.key_format = self.key_format_combo.currentText()
        # self.export_format = self.export_format_combo.currentText()
        
        config = {
            'nml_path': self.nml_path,
            'output_path': self.output_path,
            'music_root_path': self.music_root_path,
            'copy_music': self.copy_music,
            'verify_copy': self.verify_copy,
            'key_format': self.key_format,  # Utiliser la valeur existante
            'export_format': self.export_format
        }
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logging.warning(f"Error saving configuration: {e}")
    
    def _center_window(self):
        """Center application window on screen."""
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        window_geometry = self.frameGeometry()
        
        x = (screen_geometry.width() - window_geometry.width()) // 2
        y = (screen_geometry.height() - window_geometry.height()) // 2
        
        self.move(x, y)
    
    def closeEvent(self, event):
        """Handle application close event."""
        self.audio_manager.cleanup()
        
        if hasattr(self, 'cancel_event'):
            self.cancel_event.set()
        
        self._save_configuration()
        event.accept()


# =============================================================================
# COMMAND LINE INTERFACE & MAIN EXECUTION
# =============================================================================

class CommandLineInterface:
    """Command line interface for batch processing operations."""
    
    def run(self, args):
        """Execute command line operations."""
        print(f"{AppConfig.APP_NAME} v{AppConfig.VERSION}")
        # CLI Logic would be implemented here for future versions
        print("Command Line Interface is not yet implemented.")
        print("Please use the GUI version by running without arguments.")
        return 0

def check_dependencies():
    """Check for required and optional dependencies with helpful guidance."""
    print("DEBUG: Starting dependency checks...")
    missing_core = []
    missing_optional = []
    
    # Check core dependencies
    try:
        import PySide6
        # Different ways to get Qt version depending on PySide6 version
        try:
            from PySide6.QtCore import qVersion
            print(f"DEBUG: Using PySide6 (Qt {qVersion()})")
        except ImportError:
            print(f"DEBUG: Using PySide6 (version info not available)")
    except ImportError as e:
        print(f"DEBUG: PySide6 import error: {e}")
        missing_core.append("PySide6")
    
    try:
        print("DEBUG: Checking pygame...")
        import pygame
        print(f"DEBUG: pygame version: {pygame.version.ver}")
        
        print("DEBUG: Checking tinytag...")
        import tinytag
        print(f"DEBUG: tinytag version: {tinytag.__version__}")
        
        print("DEBUG: Checking PIL...")
        from PIL import Image
        print(f"DEBUG: PIL version: {Image.__version__}")
        
        AUDIO_PREVIEW_AVAILABLE = True
        print("DEBUG: Initializing pygame...")
        pygame.init()
        print("DEBUG: Initializing pygame mixer...")
        pygame.mixer.init()
        print("DEBUG: Audio preview available")
    except ImportError as e:
        print(f"DEBUG: Core dependency import error: {e}")
        missing_core.append(str(e).split("'")[1] if "'" in str(e) else str(e))
    except Exception as e:
        print(f"DEBUG: Unexpected error initializing audio: {e}")
        AUDIO_PREVIEW_AVAILABLE = False
    
    # Check optional dependencies
    try:
        print("DEBUG: Checking mutagen...")
        import mutagen
        print(f"DEBUG: mutagen version: {mutagen.version_string}")
        MUTAGEN_AVAILABLE = True
    except ImportError as e:
        print(f"DEBUG: Mutagen import error: {e}")
        missing_optional.append("mutagen")
        MUTAGEN_AVAILABLE = False
    except Exception as e:
        print(f"DEBUG: Unexpected error with mutagen: {e}")
        MUTAGEN_AVAILABLE = False
    
    print(f"DEBUG: Core dependencies missing: {missing_core}")
    print(f"DEBUG: Optional dependencies missing: {missing_optional}")
    
    if missing_core:
        print("ERROR: Missing required dependencies:")
        print(f"Install with: pip install {' '.join(missing_core)} tinytag pillow")
        if missing_optional:
            print("\nOptional (for enhanced metadata):")
            print("Install with: pip install mutagen")
        return False
    
    if missing_optional:
        print("INFO: Optional dependencies missing (enhanced metadata features disabled):")
        print("Install with: pip install mutagen")
    
    print("DEBUG: All core dependencies available")
    return True

def main():
    """Main entry point for the application."""
    print("DEBUG: Starting main function")
    try:
        # Setup logging
        print("DEBUG: Setting up logging")
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        logging.basicConfig(level=logging.DEBUG, format=log_format)  # Changed to DEBUG level
        logging.debug("Logging initialized")
        
        # Check dependencies before starting
        print("DEBUG: Checking dependencies")
        if not check_dependencies():
            print("DEBUG: Missing dependencies, exiting")
            return 1
        
        if len(sys.argv) > 1:
            print("DEBUG: Command line arguments detected, using CLI")
            cli = CommandLineInterface()
            return cli.run(sys.argv)
        else:
            print("DEBUG: No command line arguments, starting GUI")
            print("DEBUG: Creating QApplication")
            app = QApplication(sys.argv)
            app.setApplicationName(AppConfig.APP_NAME)
            
            # Set application style
            print("DEBUG: Setting application style")
            app.setStyle(QStyleFactory.create("Fusion"))
            
            # Create and show main window
            print("DEBUG: Creating main window")
            window = ConverterGUI()
            print("DEBUG: Showing main window")
            window.show()
            
            print("DEBUG: Starting main event loop")
            # Try both exec forms to handle different PySide6 versions
            try:
                print("DEBUG: Using app.exec()")
                return app.exec()
            except AttributeError:
                print("DEBUG: app.exec() failed, trying app.exec_()")
                return app.exec_()
    except KeyboardInterrupt:
        print("\nDEBUG: Process cancelled by user.")
        return 1
    except Exception as e:
        error_message = f"A fatal error occurred: {str(e)}\n\n{traceback.format_exc()}"
        print(f"DEBUG: Fatal error: {error_message}")
        try:
            QMessageBox.critical(None, "Application Error", error_message)
        except Exception as msg_error:
            print(f"DEBUG: Could not show error message dialog: {msg_error}")
            # Fallback to console if GUI cannot be initialized
            print(error_message)
        return 1

if __name__ == "__main__":
    print("DEBUG: Script executed directly")
    sys.exit(main())