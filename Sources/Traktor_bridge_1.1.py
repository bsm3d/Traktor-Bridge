#!/usr/bin/env python3

# ================================================================================
# TRAKTOR BRIDGE - Professional Traktor to Pioneer CDJ/XML Converter
# ================================================================================

# Version: 1.1.2
# Author: Benoit (BSM) Saint-Moulin
# Website: www.benoitsaintmoulin.com
# GitHub: https://github.com/bsm3d/Traktor-Bridge

# ================================================================================
# LICENSE & USAGE
# ================================================================================

# **Open Source Project** - Free for educational and personal use

# **Authorized**: 
# - Educational use within academic framework
# - Personal modification and use
# - Citation with appropriate author attribution

# **Restricted**: 
# - Commercial use requires prior authorization from the author
# - Redistribution must maintain original copyright notice

# **Contact**: GitHub repository for authorization requests

# ================================================================================
# DISCLAIMERS & WARRANTY
# ================================================================================

# **Trademarks**: Pioneer DJ, Rekordbox, CDJ, XDJ are trademarks of Pioneer DJ 
# Corporation. Native Instruments, Traktor are trademarks of Native Instruments 
# GmbH. All trademarks are property of their respective owners.

# **No Warranty**: Software provided "AS IS" without warranty of any kind, express 
# or implied, including warranties of merchantability, fitness for purpose, and 
# non-infringement. Author not liable for any damages arising from software use.

# **No Affiliation**: Independent tool, not affiliated with, endorsed by, or 
# sponsored by Pioneer DJ Corporation or Native Instruments GmbH. Provided for 
# interoperability and educational purposes only.

# **User Responsibility**: Users responsible for data backup before conversion and 
# verifying hardware/software compatibility.

# **Special thanks** to all the library maintainers and contributors who make 
# tools like this possible.

# ================================================================================

import xml.etree.ElementTree as ET
import os, sqlite3, shutil, urllib.parse, traceback, sys, threading, queue, json
import logging as log, uuid, io, time
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QSize, Signal, QThread, QTimer, QEvent
from PySide6.QtGui import QColor, QFont, QPalette, QIcon, QAction, QKeyEvent

# Audio and image processing dependencies
try:
    import pygame
    from tinytag import TinyTag, TinyTagException
    from PIL import Image
    AUDIO_OK = True
    pygame.init()
    pygame.mixer.init()
except ImportError:
    AUDIO_OK = False

try:
    import mutagen
    MUTAGEN_OK = True
except ImportError:
    MUTAGEN_OK = False

ARTWORK_OK = AUDIO_OK or MUTAGEN_OK

# =============================================================================
# CONFIGURATION AND CONSTANTS
# =============================================================================

class Config:
    """Application configuration constants and settings."""
    VERSION = "1.1"
    APP_NAME = "Traktor Bridge"
    AUTHOR = "Benoit (BSM) Saint-Moulin"
    WEBSITE = "www.benoitsaintmoulin.com"

    # UI Configuration
    WINDOW_SIZE = (700, 650)
    MIN_SIZE = (700, 650)

    # File Processing
    MAX_CACHE_SIZE = 30000
    MAX_CACHE_MEMORY_MB = 100
    SUPPORTED_FORMATS = {'.mp3', '.wav', '.flac', '.aiff', '.m4a', '.ogg'}

    # Database
    BATCH_SIZE = 100
    DB_TIMEOUT_SECONDS = 30

    # Artwork
    MAX_ARTWORK_SIZE_MB = 10
    
    # Colors for consistent styling
    COLORS = {
        'bg_dark': '#212529', 'bg_med': '#343a40', 'bg_light': '#495057',
        'fg_light': '#f8f9fa', 'fg_muted': '#adb5bd',
        'accent': '#00b4d8', 'hover': '#0096c7'
    }

class CueType(Enum):
    """Cue point types for Traktor/Rekordbox mapping."""
    GRID, HOT_CUE, FADE_IN, FADE_OUT, LOAD, LOOP = range(6)

# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class Track:
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
class Node:
    """Container for playlist/folder structure, allowing nested hierarchies."""
    type: str  # 'playlist' or 'folder'
    name: str
    tracks: List[Track] = field(default_factory=list)
    children: List['Node'] = field(default_factory=list)

# =============================================================================
# UTILITY CLASSES AND FUNCTIONS
# =============================================================================

class PathValidator:
    """Validates and sanitizes file paths to prevent errors and security issues."""
    
    @staticmethod
    def validate_path(path_str: str, must_exist: bool = True) -> Optional[Path]:
        """Validates and resolves a path string with security checks."""
        if not path_str:
            return None
        try:
            path = Path(path_str).resolve()
            if '..' in str(path) or str(path).startswith('..'):
                raise ValueError("Invalid path format (path traversal detected).")
            if must_exist and not path.exists():
                raise FileNotFoundError(f"Path does not exist: {path}")
            return path
        except Exception as e:
            log.warning(f"Path validation failed for '{path_str}': {e}")
            return None

class KeyXlat:
    """Translates Traktor's numerical key values into musical notation formats."""
    
    def __init__(self):
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

class StyleMgr:
    """Centralized style management for consistent GUI theming."""
    
    @staticmethod
    def get_main_style():
        """Returns the main application stylesheet."""
        colors = Config.COLORS
        return f"""
            QMainWindow, QWidget {{
                background-color: {colors['bg_dark']};
                color: {colors['fg_light']};
            }}
            QLabel {{ color: {colors['fg_light']}; }}
            QPushButton {{
                background-color: {colors['bg_med']};
                color: {colors['fg_light']};
                border: none;
                padding: 8px 16px;
            }}
            QPushButton:hover {{ background-color: {colors['bg_light']}; }}
            QLineEdit {{
                background-color: {colors['bg_med']};
                color: {colors['fg_light']};
                border: none;
                padding: 6px;
            }}
            QComboBox {{
                background-color: {colors['bg_med']};
                color: {colors['fg_light']};
                border: none;
                padding: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['bg_med']};
                color: {colors['fg_light']};
                selection-background-color: {colors['accent']};
            }}
            QProgressBar {{
                border: none;
                background-color: {colors['bg_med']};
                text-align: center;
            }}
            QProgressBar::chunk {{ background-color: {colors['accent']}; }}
            QTreeWidget {{
                background-color: {colors['bg_med']};
                color: {colors['fg_light']};
                border: none;
                alternate-background-color: {colors['bg_light']};
            }}
            QHeaderView::section {{
                background-color: {colors['bg_dark']};
                color: {colors['fg_light']};
                padding: 5px;
                border: none;
            }}
            QCheckBox {{ color: {colors['fg_light']}; }}
        """

    @staticmethod
    def get_button_style():
        """Returns button-specific styling."""
        return f"""
            QPushButton {{
                background-color: {Config.COLORS['bg_med']};
                color: {Config.COLORS['fg_light']};
                border: none;
                padding: 8px 16px;
            }}
            QPushButton:hover {{ background-color: {Config.COLORS['bg_light']}; }}
        """

# Utility functions
def safe_float(value, default=0.0):
    """Safely convert value to float with fallback."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    """Safely convert value to int with fallback."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def handle_exceptions(operation_name: str):
    """Decorator to catch and log exceptions during critical operations."""
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                error_msg = f"Operation '{operation_name}' failed: {str(e)}"
                log.error(traceback.format_exc())
                if hasattr(self, 'log_message'):
                    self.log_message(error_msg, log.ERROR)
                if hasattr(self, 'prog_q'):
                    self.prog_q.put(("error", error_msg))
                raise
        return wrapper
    return decorator

# =============================================================================
# MANAGERS - Base classes with shared functionality
# =============================================================================

class BaseMgr:
    """Base manager class with common thread-safe operations."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._initialized = False
    
    @contextmanager
    def safe_op(self):
        """Context manager for thread-safe operations."""
        self._lock.acquire()
        try:
            yield
        finally:
            self._lock.release()

class AudioMgr(BaseMgr):
    """Thread-safe audio playback manager using pygame."""
    
    def __init__(self):
        super().__init__()
        self._current_file = None
        self._playing_item_id = None
        self._auto_stop_timer = None
        self._root_ref = None
        
    def initialize(self, root_widget):
        """Initialize pygame mixer in a thread-safe manner."""
        with self.safe_op():
            if not self._initialized:
                try:
                    if not pygame.mixer.get_init():
                        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
                    self._initialized = True
                    self._root_ref = root_widget
                    return True
                except pygame.error as e:
                    log.error(f"Failed to initialize pygame mixer: {e}")
                    return False
            return True
    
    def play_file(self, file_path: str, item_id: str, duration_callback=None) -> bool:
        """Play an audio file in a thread-safe manner."""
        with self.safe_op():
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
                log.error(f"Failed to play {file_path}: {e}")
                return False
    
    def stop(self):
        """Stop playback in a thread-safe manner."""
        with self.safe_op():
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
        with self.safe_op():
            return {
                'file': self._current_file,
                'item_id': self._playing_item_id,
                'is_playing': pygame.mixer.music.get_busy() if self._initialized else False
            }
    
    def cleanup(self):
        """Clean up audio resources."""
        with self.safe_op():
            self._stop_internal()
            if self._initialized:
                try:
                    pygame.mixer.quit()
                except:
                    pass
                self._initialized = False

class Cache(BaseMgr):
    """Intelligent file cache with memory management and access tracking."""
    
    def __init__(self, max_size=30000, max_memory_mb=100):
        super().__init__()
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self._cache = {}
        self._access_times = {}
        
    def build_cache(self, root_path: str, progress_cb=None):
        """Build file cache with memory monitoring."""
        if not root_path:
            return {}
            
        music_path = PathValidator.validate_path(root_path, must_exist=True)
        if not music_path or not music_path.is_dir():
            return {}
        
        with self.safe_op():
            self._cache.clear()
            self._access_times.clear()
            
            try:
                all_files = list(music_path.rglob('*'))
                total_files = len(all_files)
                current_memory = 0
                
                for i, file_path in enumerate(all_files):
                    if i % 1000 == 0 and progress_cb:
                        progress_cb(
                            int((i / total_files) * 4),
                            f"Scanning: {i}/{total_files} files ({len(self._cache)} cached)"
                        )
                    
                    if not file_path.is_file():
                        continue
                        
                    if file_path.suffix.lower() not in Config.SUPPORTED_FORMATS:
                        continue
                    
                    # Memory estimation (filename + path)
                    estimated_size = len(file_path.name) * 2 + len(str(file_path)) * 2
                    
                    # Limit checks
                    if (len(self._cache) >= self.max_size or 
                        current_memory + estimated_size > self.max_memory_bytes):
                        if progress_cb:
                            progress_cb(4, f"Cache limit reached: {len(self._cache)} files")
                        break
                    
                    self._cache[file_path.name] = str(file_path)
                    self._access_times[file_path.name] = 0  # Not accessed yet
                    current_memory += estimated_size
                
                if progress_cb:
                    progress_cb(5, f"Cache built: {len(self._cache)} files ({current_memory // 1024}KB)")
                    
            except Exception as e:
                log.error(f"Cache building failed: {e}")
                
            return dict(self._cache)  # Copy for thread-safety
    
    def get(self, filename: str) -> Optional[str]:
        """Retrieve file from cache with access statistics update."""
        with self.safe_op():
            if filename in self._cache:
                self._access_times[filename] = time.time()
                return self._cache[filename]
            return None

class DBMgr(BaseMgr):
    """Database manager with retry logic and transaction safety."""
    
    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = Path(db_path)
        
    @contextmanager
    def get_connection(self, max_retries=3):
        """Context manager with automatic retry functionality."""
        conn = None
        last_error = None
        
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(
                    str(self.db_path),
                    timeout=Config.DB_TIMEOUT_SECONDS,
                    isolation_level=None  # Auto-commit
                )
                conn.execute("PRAGMA journal_mode=WAL")
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

class ArtworkMgr(BaseMgr):
    """Secure artwork manager with validation and cleanup."""
    
    def __init__(self, artwork_path: Path):
        super().__init__()
        self.artwork_path = artwork_path
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
        
        with self.safe_op():
            try:
                # Format detection
                format_ext, mime_type = self._detect_format(artwork_data)
                if not format_ext:
                    log.warning(f"Unsupported image format for track: {track_title}")
                    return None
                
                # Size validation
                if len(artwork_data) > Config.MAX_ARTWORK_SIZE_MB * 1024 * 1024:
                    log.warning(f"Artwork too large ({len(artwork_data)} bytes) for track: {track_title}")
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
                    log.error(f"Failed to save artwork for '{track_title}': {e}")
                    return None
                
                # Create database entry
                try:
                    cursor.execute("SELECT MAX(ID) FROM djmdArtwork")
                    max_id = cursor.fetchone()[0] or 0
                    artwork_id = max_id + 1
                    
                    db_path = f"/ARTWORK/{artwork_filename}"
                    cursor.execute("INSERT INTO djmdArtwork (ID, Path) VALUES (?, ?)",
                                   (artwork_id, db_path))
                    
                    return artwork_id
                    
                except sqlite3.Error as e:
                    # Cleanup on database error
                    if artwork_file_path.exists():
                        artwork_file_path.unlink()
                    log.error(f"Database error saving artwork for '{track_title}': {e}")
                    return None
                
            except Exception as e:
                log.error(f"Unexpected error saving artwork for '{track_title}': {e}")
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

# =============================================================================
# XML EXPORTER
# =============================================================================

class XMLExporter:
    """Exports tracks and playlists to Rekordbox XML format."""
    
    def __init__(self, key_xlat):
        self.key_xlat = key_xlat
        
    def export_to_xml(self, structure, file_path, key_fmt="Open Key"):
        """Export playlist structure to a Rekordbox XML file."""
        # Create the root structure
        root = ET.Element('DJ_PLAYLISTS', Version="1.0.0")
        
        # Create PRODUCT element
        ET.SubElement(root, 'PRODUCT', 
                      Name="rekordbox", 
                      Version="6.0.0", 
                      Company="Pioneer DJ")
        
        # Create COLLECTION element - first collect all unique tracks
        all_tracks = self._collect_all_tracks(structure)
        collection = ET.SubElement(root, 'COLLECTION', Entries=str(len(all_tracks)))
        
        # Track ID mapping for playlists
        track_id_map = {}
        
        # Add tracks to collection
        for track in all_tracks:
            track_id = self._get_track_key(track.file_path)
            track_id_map[track.file_path] = track_id
            self._add_track_to_collection(collection, track, track_id, key_fmt)
        
        # Create playlists section
        playlists = ET.SubElement(root, 'PLAYLISTS')
        
        # Create root node
        root_node = ET.SubElement(playlists, 'NODE', Name="ROOT", Type="0")
        
        # Process playlist structure recursively
        self._process_structure(root_node, structure, track_id_map)
        
        # Write to file
        xml_str = ET.tostring(root, 'utf-8')
        from xml.dom import minidom
        pretty_xml_str = minidom.parseString(xml_str).toprettyxml(indent="  ")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml_str)
            
        return file_path
    
    def _collect_all_tracks(self, structure):
        """Recursively collect all unique tracks from the playlist structure."""
        all_tracks = []
        track_paths = set()
        
        def collect_tracks(nodes):
            for node in nodes:
                if node.type == 'playlist':
                    for track in node.tracks:
                        if track.file_path and track.file_path not in track_paths:
                            all_tracks.append(track)
                            track_paths.add(track.file_path)
                elif node.type == 'folder':
                    collect_tracks(node.children)
        
        collect_tracks(structure)
        return all_tracks
    
    def _get_track_key(self, file_path):
        """Generate a unique key for a track."""
        if not file_path:
            return str(abs(hash("unknown")) % 10000000)
        return str(abs(hash(str(file_path))) % 10000000)
    
    def _add_track_to_collection(self, collection, track, track_id, key_fmt):
        """Add a track to the Rekordbox collection."""
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
                                  Year=track.label or "",
                                  DateAdded=creation_time,
                                  BitRate=str(track.bitrate) if track.bitrate else "0",
                                  Comments=track.comment or "")
        
        # Add tempo (BPM)
        if track.bpm and track.bpm > 0:
            track_elem.set('AverageBpm', f"{track.bpm:.2f}")
        
        # Add musical key
        if track.musical_key:
            key_value = self.key_xlat.translate(track.musical_key, key_fmt)
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
            
        try:
            abs_path = Path(file_path).resolve()
            
            if os.name == 'nt':  # Windows
                path_str = str(abs_path).replace('\\', '/')
                if not path_str.startswith('/'):
                    path_str = '/' + path_str
                return f"file://localhost{path_str}"
            else:  # macOS/Linux
                return f"file://{abs_path}"
        except Exception:
            return f"file://localhost/{os.path.basename(file_path)}"
    
    def _process_structure(self, parent_node, nodes, track_id_map):
        """Recursively process playlist structure to create folders and playlists."""
        for node in nodes:
            if node.type == 'folder':
                folder_node = ET.SubElement(parent_node, 'NODE', 
                                           Name=node.name, 
                                           Type="1")
                self._process_structure(folder_node, node.children, track_id_map)
                
            elif node.type == 'playlist':
                playlist_node = ET.SubElement(parent_node, 'NODE',
                                             Name=node.name,
                                             Type="1")
                                             
                playlist = ET.SubElement(playlist_node, 'PLAYLIST',
                                        Name=node.name,
                                        Type="1",
                                        Count=str(len(node.tracks)))
                
                for track in node.tracks:
                    if track.file_path in track_id_map:
                        track_id = track_id_map[track.file_path]
                        ET.SubElement(playlist, 'TRACK', Key=track_id)

# =============================================================================
# NML PARSER MODULE
# =============================================================================

class NMLParser:
    """Parses Traktor NML files to extract track collections and playlist structures."""
    
    def __init__(self, nml_path: str, music_root: Optional[str] = None,
                 prog_q: Optional[queue.Queue] = None):
        self.nml_path = Path(nml_path)
        self.music_root = music_root
        self.prog_q = prog_q
        self.key_xlat = KeyXlat()

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
                return
            except (ET.ParseError, UnicodeDecodeError) as e:
                continue
        raise ValueError("Unable to parse NML file. The file may be corrupt or use an unsupported encoding.")

    def _report_progress(self, percent: int, message: str):
        """Report progress to the queue if available."""
        if self.prog_q:
            self.prog_q.put(("progress", (percent, message)))

    @handle_exceptions("File cache building")
    def _build_file_cache(self) -> Dict[str, str]:
        """Build file cache using Cache."""
        if not self.music_root:
            return {}
        
        smart_cache = Cache(
            max_size=Config.MAX_CACHE_SIZE,
            max_memory_mb=Config.MAX_CACHE_MEMORY_MB
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
                    traktor_key = f"{volume}{dir_path}{file_name}"
                    collection_map[traktor_key] = entry
        self._report_progress(50, "Collection indexed successfully.")
        return collection_map

    def get_playlists_with_structure(self) -> List[Node]:
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
            return []

        structure = self._parse_node_recursively(root_node)
        self._report_progress(100, f"Playlists loaded successfully using {used_strategy}.")
        return structure

    def _parse_node_recursively(self, node: ET.Element) -> List[Node]:
        """Recursively parse playlist folders and playlists."""
        results = []
        subnodes_container = node.find("SUBNODES") or node
        for child_node in subnodes_container.findall("NODE"):
            node_type = child_node.get('TYPE')
            node_name = child_node.get('NAME', 'Unnamed')

            if node_type == 'PLAYLIST':
                playlist = Node(type='playlist', name=node_name)
                playlist_container = child_node.find('PLAYLIST')
                if playlist_container is not None:
                    for entry in playlist_container.findall('ENTRY'):
                        track_info = self._parse_playlist_entry(entry)
                        if track_info:
                            playlist.tracks.append(track_info)
                if playlist.tracks:
                    results.append(playlist)

            elif node_type == 'FOLDER':
                folder = Node(type='folder', name=node_name)
                children = self._parse_node_recursively(child_node)
                if children:
                    folder.children = children
                    results.append(folder)
        return results

    def _parse_playlist_entry(self, entry: ET.Element) -> Optional[Track]:
        """Find track in collection map using primary key."""
        primary_key_elem = entry.find("PRIMARYKEY")
        if primary_key_elem is None:
            return None
        track_key = primary_key_elem.get('KEY', '')
        collection_entry = self.collection_map.get(track_key)
        if collection_entry is not None:
            return self._parse_collection_entry(collection_entry)
        return None

    def _parse_collection_entry(self, entry: ET.Element) -> Track:
        """Extract all metadata from a single track XML element."""
        track = Track(
            title=entry.get('TITLE', 'Unknown'),
            artist=entry.get('ARTIST', 'Unknown')
        )
        track.file_path = self._parse_file_location(entry)

        info = entry.find("INFO")
        if info is not None:
            track.genre = info.get('GENRE', '')
            track.comment = info.get('COMMENT', '')
            track.label = info.get('LABEL', '')
            track.bitrate = safe_int(info.get('BITRATE', '0'))
            track.playtime = safe_float(info.get('PLAYTIME', '0'))

        album = entry.find("ALBUM")
        if album is not None:
            track.album = album.get('TITLE', '')

        tempo = entry.find("TEMPO")
        if tempo is not None:
            track.bpm = safe_float(tempo.get('BPM', '0'))

        key = entry.find("MUSICAL_KEY")
        if key is not None:
            track.musical_key = key.get('VALUE', '')

        loudness = entry.find("LOUDNESS")
        if loudness is not None:
            track.gain = safe_float(loudness.get('ANALYZED_DB', '0.0'))

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

        # Handle Windows-style paths that start with slash
        if len(reconstructed) > 2 and reconstructed.startswith('/') and reconstructed[2] == ':':
            reconstructed = reconstructed[1:]

        return reconstructed

    def _parse_cue_points(self, entry: ET.Element, track: Track):
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

    def _extract_artwork(self, track: Track):
        """Robust artwork extraction using TinyTag with mutagen fallback."""
        if not (ARTWORK_OK and track.file_path and os.path.exists(track.file_path)):
            return

        # Primary method: TinyTag for reliable artwork extraction
        if AUDIO_OK:
            try:
                tag = TinyTag.get(track.file_path, image=True)
                
                if tag and tag.images and tag.images.any and tag.images.any.data:
                    track.artwork_data = tag.images.any.data
                    return
                    
            except TinyTagException as e:
                log.warning(f"TinyTag artwork extraction failed for {track.file_path}: {e}")
            except Exception as e:
                log.warning(f"Unexpected error during TinyTag extraction for {track.file_path}: {e}")

        # Fallback method: Mutagen backup
        if MUTAGEN_OK:
            try:
                audio_file = mutagen.File(track.file_path, easy=False)
                if audio_file is None:
                    return

                artwork_data = None
                
                # Method 1: FLAC, OGG, and other formats with pictures attribute
                if hasattr(audio_file, 'pictures') and audio_file.pictures:
                    artwork_data = audio_file.pictures[0].data
                    
                # Method 2: MP3 files with ID3 tags
                elif hasattr(audio_file, 'tags') and audio_file.tags:
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

            except Exception as e:
                log.warning(f"Mutagen fallback artwork extraction failed for {track.file_path}: {e}")

# =============================================================================
# DATABASE EXPORT MODULE
# =============================================================================

class CDJExporter:
    """Handles creation of Pioneer Rekordbox database and file structure."""
    
    def __init__(self, output_path: str, progress_cb: Optional[callable] = None):
        self.output_path = Path(output_path)
        self.progress_cb = progress_cb
        self.key_xlat = KeyXlat()
        self.cancel_event = None

        # Standard Pioneer USB folder structure
        self.contents_path = self.output_path / "CONTENTS"
        self.pioneer_path = self.output_path / "PIONEER"
        self.artwork_path = self.pioneer_path / "ARTWORK"
        self.db_path = self.pioneer_path / "rekordbox.pdb"
        
        # Initialize managers
        self.db_mgr = DBMgr(str(self.db_path))
        self.artwork_mgr = ArtworkMgr(self.artwork_path)

    def _update_progress(self, percent: int, message: str):
        """Update progress if callback is available."""
        if self.progress_cb:
            self.progress_cb(percent, message)

    @handle_exceptions("Database export")
    def export_playlists(self, structure: List[Node],
                         copy_music: bool = True, verify_copy: bool = False,
                         key_fmt: str = "Open Key"):
        """Main export function with enhanced error handling."""
        try:
            self._create_folder_structure()
            self._create_database_structure()
            self._process_structure(structure, key_fmt, parent_id=0)
            if copy_music:
                all_tracks = self._collect_all_tracks(structure)
                self._copy_music_files(all_tracks, verify_copy)
            self._create_export_info()
        except Exception as e:
            log.error(f"Export failed critically: {e}")
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
        with self.db_mgr.get_connection() as conn:
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

    def _process_structure(self, nodes: List[Node], key_fmt: str, parent_id: int):
        """Recursively process playlist structure to create folders and playlists."""
        for node in nodes:
            if self.cancel_event and self.cancel_event.is_set():
                return
            if node.type == 'folder':
                new_parent_id = self._create_playlist_folder(node.name, parent_id)
                self._process_structure(node.children, key_fmt, new_parent_id)
            elif node.type == 'playlist':
                self._process_single_playlist(node, key_fmt, parent_id)

    def _create_playlist_folder(self, name: str, parent_id: int) -> int:
        """Create playlist folder entry in database."""
        with self.db_mgr.get_connection() as conn:
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
    def _process_single_playlist(self, playlist: Node, key_fmt: str, parent_id: int):
        """Process all tracks within a single playlist."""
        with self.db_mgr.get_connection() as conn:
            cursor = conn.cursor()
            caches = self._build_lookup_caches(cursor)
            playlist_id = self._create_or_update_playlist(cursor, playlist.name, parent_id)
            self._process_tracks_in_playlist(cursor, playlist.tracks, playlist_id, key_fmt, caches)

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
            cursor.execute("DELETE FROM djmdSongPlaylist WHERE PlaylistID = ?", (playlist_id,))
            return playlist_id

        cursor.execute("SELECT MAX(ID) FROM djmdPlaylist")
        max_id = cursor.fetchone()[0] or 0
        playlist_id = max_id + 1
        cursor.execute("INSERT INTO djmdPlaylist (ID, Seq, Name, ParentID) VALUES (?, ?, ?, ?)",
                       (playlist_id, playlist_id, name, parent_id))
        return playlist_id

    def _process_tracks_in_playlist(self, cursor: sqlite3.Cursor, tracks: List[Track], 
                                   playlist_id: int, key_fmt: str, caches: Dict):
        """Process tracks and link them to playlist."""
        for idx, track in enumerate(tracks, 1):
            if self.cancel_event and self.cancel_event.is_set():
                return

            file_name = os.path.basename(track.file_path) if track.file_path else f"track_{idx}.mp3"
            content_id = caches['content'].get(file_name)

            if not content_id:
                content_id = self._create_track_content(cursor, track, key_fmt, caches)
                caches['content'][file_name] = content_id

            cursor.execute("INSERT INTO djmdSongPlaylist (PlaylistID, ContentID, TrackNo) VALUES (?, ?, ?)",
                           (playlist_id, content_id, idx))

    def _create_track_content(self, cursor: sqlite3.Cursor, track: Track, key_fmt: str, caches: Dict) -> int:
        """Create new track entry with all metadata."""
        # Save artwork using manager
        artwork_id = None
        if track.artwork_data:
            artwork_id = self.artwork_mgr.save_artwork(track.artwork_data, cursor, track.title)

        artist_id = self._get_or_create_id(cursor, 'djmdArtist', track.artist, caches['artists'])
        album_id = self._get_or_create_id(cursor, 'djmdAlbum', track.album, caches['albums'])
        genre_id = self._get_or_create_id(cursor, 'djmdGenre', track.genre, caches['genres'])
        label_id = self._get_or_create_id(cursor, 'djmdLabel', track.label, caches['labels'])
        key_name = self.key_xlat.translate(track.musical_key, key_fmt)
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

    def _create_beat_grid(self, cursor: sqlite3.Cursor, content_id: int, track: Track):
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

    def _collect_all_tracks(self, structure: List[Node]) -> List[Track]:
        """Gather unique list of all tracks from selected structure."""
        all_tracks = []
        def collect_recursive(nodes):
            for node in nodes:
                if node.type == 'playlist':
                    all_tracks.extend(node.tracks)
                elif node.type == 'folder':
                    collect_recursive(node.children)
        collect_recursive(structure)
        return list({t.file_path: t for t in all_tracks if t.file_path}.values())

    @handle_exceptions("Music file copying")
    def _copy_music_files(self, tracks: List[Track], verify: bool):
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
            f"Converter: {Config.APP_NAME} v{Config.VERSION}\n"
            f"Author: {Config.AUTHOR}\n"
        )
        with open(self.pioneer_path / "EXPORT.INFO", 'w', encoding='utf-8') as f:
            f.write(info_content)

# =============================================================================
# GUI MODULE
# =============================================================================

class BaseDialog(QDialog):
    """Base class for simple dialogs."""
    
    def __init__(self, title, size=(400, 300), parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(*size)
        self.setStyleSheet(StyleMgr.get_main_style())

class TimelineDialog(BaseDialog):
    """Dialog for displaying cue point timeline with enhanced visualization."""
    
    def __init__(self, track: Track, parent=None):
        super().__init__(f"Cue Points: {track.artist} - {track.title}", (700, 500), parent)
        self.track = track
        
        # Filter relevant cue points
        self.cue_points = sorted(
            [cue for cue in track.cue_points if self._is_relevant_cue(cue)],
            key=lambda c: c.get('start', 0)
        )
        
        self.show_hotcues = True
        self.show_memory_cues = True
        self.show_loops = True
        self.show_grid = True
        
        self._setup_ui()
    
    def _is_relevant_cue(self, cue):
        """Determine if a cue point is relevant for display."""
        cue_type = cue.get('type', -1)
        hotcue_num = cue.get('hotcue', -1)
        return ((cue_type == CueType.HOT_CUE.value and hotcue_num > 0) or 
                cue_type in [CueType.LOAD.value, CueType.LOOP.value])
        
    def _setup_ui(self):
        """Set up the timeline dialog UI."""
        layout = QVBoxLayout(self)
        
        # Header info
        header = QFrame()
        header_layout = QVBoxLayout(header)
        
        title_label = QLabel(f"🎵 {self.track.artist} - {self.track.title}")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        
        # Track info
        info_text = f"BPM: {self.track.bpm:.1f} | Duration: {int(self.track.playtime // 60)}:{int(self.track.playtime % 60):02d}"
        if self.track.musical_key:
            key = KeyXlat().translate(self.track.musical_key)
            info_text += f" | Key: {key}"
            
        if self.track.grid_anchor_ms is not None:
            ms = self.track.grid_anchor_ms
            minutes = int(ms // 60000)
            seconds = (ms % 60000) / 1000
            grid_time = f"{minutes:02d}:{seconds:06.3f}"
            info_text += f" | Grid Anchor: {grid_time}"
            
        info_label = QLabel(info_text)
        info_label.setStyleSheet(f"color: {Config.COLORS['fg_muted']};")
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(info_label)
        layout.addWidget(header)
        
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
        export_button.setStyleSheet(StyleMgr.get_button_style())
        export_button.clicked.connect(self._export_to_clipboard)
        
        close_button = QPushButton("Close")
        close_button.setStyleSheet(StyleMgr.get_button_style())
        close_button.clicked.connect(self.accept)
        
        button_layout.addWidget(export_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addWidget(button_frame)
    
    def _get_cue_stats(self):
        """Generate cue point statistics."""
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
        from PySide6.QtGui import QPainter, QPen, QBrush, QColor
        from PySide6.QtCore import QRect, QRectF, QPoint
        
        class TimelineView(QWidget):
            def __init__(self, track, cue_points, parent=None):
                super().__init__(parent)
                self.track = track
                self.cue_points = cue_points
                self.setMinimumHeight(100)
                self.setStyleSheet(f"background-color: {Config.COLORS['bg_med']};")
                
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
                painter.setRenderHint(QPainter.Antialiasing)
                
                width = self.width()
                height = self.height()
                
                # Background gradient
                gradient = QColor(Config.COLORS['bg_med'])
                gradient_dark = QColor(Config.COLORS['bg_dark'])
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
                
                import math
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
        table.setStyleSheet(StyleMgr.get_main_style())
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
            key = KeyXlat().translate(self.track.musical_key)
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

class DetailsWindow(BaseDialog):
    """Window for displaying detailed track information."""
    
    def __init__(self, playlist: Node, parent=None):
        super().__init__(f"Details for: {playlist.name}", (1200, 500), parent)
        self.playlist = playlist
        self.key_xlat = KeyXlat()
        self.audio_mgr = AudioMgr()
        self.audio_mgr.initialize(self)
        self.playing_track_id = None
        
        self.selected_track_id = None
        self.key_format = "Open Key"
        
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_KeyCompression, False)
        
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
        self.search_field.textChanged.connect(self._filter_tracks)
        
        # Key format selector
        key_label = QLabel("Key Format:")
        self.key_format_button = QPushButton(self.key_format)
        self.key_format_button.setStyleSheet(StyleMgr.get_button_style())
        
        # Create menu for key format
        key_menu = QMenu(self)
        key_menu.setStyleSheet(StyleMgr.get_main_style())
        
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
        self.tracks_table.setStyleSheet(StyleMgr.get_main_style())
        self.tracks_table.setAlternatingRowColors(True)
        self.tracks_table.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tracks_table.setRootIsDecorated(False)

        # Define columns
        columns = ['▶', '#', 'Artist', 'Title', 'Key', 'BPM', 'Gain', 'Grid', 'Duration', 'Cues Detail', 'Album']
        self.tracks_table.setColumnCount(len(columns))
        self.tracks_table.setHeaderLabels(columns)

        # Set column widths
        column_widths = {'▶': 30, '#': 40, 'Artist': 200, 'Title': 280, 'Key': 60, 
                         'BPM': 60, 'Gain': 60, 'Grid': 40, 'Duration': 70, 
                         'Cues Detail': 100, 'Album': 220}

        for i, col in enumerate(columns):
            self.tracks_table.setColumnWidth(i, column_widths.get(col, 100))

        self.tracks_table.setSortingEnabled(False)
        self.tracks_table.header().setSortIndicatorShown(True)
        self.tracks_table.header().setSectionsClickable(True)
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
        
    def _change_key_format(self, format_name):
        """Change key format and update display."""
        self.key_format = format_name
        self.key_format_button.setText(format_name)
        self._populate_table()
    
    def _populate_table(self):
        """Populate the table with track information."""
        if self.sort_column == -1:
            self._populate_table_with_tracks(self.playlist.tracks)
        else:
            tracks_to_sort = list(self.playlist.tracks)
            
            sort_keys = {
                2: lambda t: t.artist.lower(),
                3: lambda t: t.title.lower(), 
                4: lambda t: self.key_xlat.translate(t.musical_key, self.key_format),
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
    
    def _populate_table_with_tracks(self, tracks):
        """Populate the table with the provided tracks."""
        current_state = self.audio_mgr.get_current_state()
        currently_playing_id = current_state['item_id']
        is_playing = current_state['is_playing']
        
        selected_items = self.tracks_table.selectedItems()
        selected_track_id = None
        if selected_items:
            selected_track_id = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        
        self.tracks_table.blockSignals(True)
        self.tracks_table.clear()
        
        # Define key colors
        open_key_colors = {f'{i}A': '#FF80C0' for i in range(1, 13)} | {f'{i}B': '#FF8080' for i in range(1, 13)}
        classical_key_colors = {
            'C': '#FF8080', 'G': '#FFFF80', 'D': '#80FF80', 'A': '#80FFC0', 
            'E': '#80FFFF', 'B': '#80C0FF', 'F#': '#8080FF', 'C#': '#C080FF', 
            'G#': '#FF80FF', 'D#': '#FF80C0', 'A#': '#FFC080', 'F': '#FFC080',
            'Am': '#FF80C0', 'Em': '#FF80FF', 'Bm': '#C080FF', 'F#m': '#8080FF', 
            'C#m': '#80C0FF', 'G#m': '#80FFFF', 'D#m': '#80FFC0', 'Bbm': '#80FF80', 
            'Fm': '#C0FF80', 'Cm': '#FFFF80', 'Gm': '#FFC080', 'Dm': '#FF8080'
        }
        
        item_to_reselect = None
        
        for i, track in enumerate(tracks, 1):
            item = QTreeWidgetItem()
            track_id = id(track)
            
            # Calculate values
            play_sec = float(track.playtime)
            duration = f"{int(play_sec // 60):02d}:{int(play_sec % 60):02d}"
            key = self.key_xlat.translate(track.musical_key, self.key_format)
            gain = f"{track.gain:+.2f}" if track.gain else ""
            grid_marker = "✓" if track.grid_anchor_ms is not None else ""
            cue_summary = self._get_cue_summary(track.cue_points)
            
            play_icon = "⏸" if is_playing and track_id == currently_playing_id else "▶"
            
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
            if self.key_format == "Open Key" and key in open_key_colors:
                item.setForeground(4, QColor(open_key_colors[key]))
            elif self.key_format == "Classical" and key in classical_key_colors:
                item.setForeground(4, QColor(classical_key_colors[key]))
            
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
    
    def _on_header_clicked(self, column_index):
        """Handle header column click for sorting."""
        if column_index == 0:
            return
        
        if column_index == self.sort_column:
            self.sort_order = Qt.SortOrder.DescendingOrder if self.sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.sort_column = column_index
            self.sort_order = Qt.SortOrder.AscendingOrder
        
        self.tracks_table.header().setSortIndicator(column_index, self.sort_order)
        self._populate_table()
    
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
                for track in self.playlist.tracks:
                    if id(track) == track_id:
                        dialog = TimelineDialog(track, self)
                        dialog.exec()
                        break
    
    def _on_item_pressed(self, item, column):
        """Store item and position when mouse is pressed."""
        self.selected_track_id = item.data(0, Qt.ItemDataRole.UserRole)
    
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
            self.setFocus()
    
    def keyPressEvent(self, event):
        """Override the key press event handler."""
        if event.key() == Qt.Key.Key_P:
            selected_items = self.tracks_table.selectedItems()
            if selected_items:
                item = selected_items[0]
                track_id = item.data(0, Qt.ItemDataRole.UserRole)
                if track_id:
                    self._toggle_playback(item, track_id)
                    event.accept()
                    return
        super().keyPressEvent(event)
        
    def showEvent(self, event):
        """Ensure window has focus when it opens."""
        super().showEvent(event)
        self.setFocus()
        self.activateWindow()
        self.raise_()
    
    def _toggle_playback(self, item, track_id):
        """Toggle playback for a track."""
        if not track_id:
            return
            
        current_state = self.audio_mgr.get_current_state()
        
        if current_state['is_playing']:
            self.audio_mgr.stop()
            
            if current_state['item_id']:
                for i in range(self.tracks_table.topLevelItemCount()):
                    curr_item = self.tracks_table.topLevelItem(i)
                    if curr_item.data(0, Qt.ItemDataRole.UserRole) == current_state['item_id']:
                        curr_item.setText(0, "▶")
                        break
            
            if current_state['item_id'] == track_id:
                self.playing_track_id = None
                return
        
        for track in self.playlist.tracks:
            if id(track) == track_id:
                if track.file_path and os.path.exists(track.file_path):
                    if self.audio_mgr.play_file(track.file_path, track_id):
                        item.setText(0, "⏸")
                        self.playing_track_id = track_id
                    else:
                        QMessageBox.warning(self, "File Not Found", 
                                            f"The audio file for this track could not be found.")
                break
    
    def closeEvent(self, event):
        """Handle window close event."""
        self.audio_mgr.stop()
        self.audio_mgr.cleanup()
        event.accept()

# Simple dialogs
class AboutDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__("About", (400, 200), parent)
        
        layout = QVBoxLayout(self)
        
        for text, style in [
            (Config.APP_NAME, "font-size: 18pt; font-weight: bold;"),
            (f"Version: {Config.VERSION}", ""),
            (f"Author: {Config.AUTHOR}", ""),
            (f"Website: {Config.WEBSITE}", "")
        ]:
            label = QLabel(text)
            if style:
                label.setStyleSheet(style)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
        
        layout.addStretch()
        
        close_button = QPushButton("Close")
        close_button.setStyleSheet(StyleMgr.get_button_style())
        close_button.clicked.connect(self.accept)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

class UsageDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Usage Guide", (500, 400), parent)
        
        layout = QVBoxLayout(self)
        
        title = QLabel("USAGE GUIDE")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        content = QTextEdit()
        content.setReadOnly(True)
        content.setHtml("""
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
        """)
        
        layout.addWidget(title)
        layout.addWidget(content)
        
        close_button = QPushButton("Close")
        close_button.setStyleSheet(StyleMgr.get_button_style())
        close_button.clicked.connect(self.accept)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)

class LogDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Conversion Log", (800, 500), parent)
        
        layout = QVBoxLayout(self)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Config.COLORS['bg_med']};
                color: {Config.COLORS['fg_light']};
                border: none;
                font-family: 'Consolas', monospace;
                font-size: 9pt;
            }}
        """)
        
        layout.addWidget(self.log_text)
        
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        
        clear_button = QPushButton("Clear Log")
        clear_button.setStyleSheet(StyleMgr.get_button_style())
        clear_button.clicked.connect(self.clear_log)
        
        close_button = QPushButton("Close")
        close_button.setStyleSheet(StyleMgr.get_button_style())
        close_button.clicked.connect(self.accept)
        
        button_layout.addWidget(clear_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addWidget(button_frame)
    
    def append_log(self, message):
        """Append message to log."""
        self.log_text.append(message)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def clear_log(self):
        """Clear all log content."""
        self.log_text.clear()

# Thread classes
class LogHandler:
    def __init__(self):
        self.log_window = None
        self.log_text_widget = None
        
    def log_message(self, message: str, level: int = log.INFO):
        log_entry = f"{datetime.now().strftime('%H:%M:%S')} - {message}"
        log.log(level, message)
        if self.log_text_widget is not None:
            try:
                self.log_text_widget.append(f"{log_entry}")
                self.log_text_widget.verticalScrollBar().setValue(
                    self.log_text_widget.verticalScrollBar().maximum()
                )
            except Exception:
                self.log_text_widget = None

class LoadingThread(QThread):
    finished = Signal(object)
    
    def __init__(self, nml_path, music_root_path, prog_q):
        super().__init__()
        self.nml_path = nml_path
        self.music_root_path = music_root_path
        self.prog_q = prog_q
        
    def run(self):
        try:
            parser = NMLParser(self.nml_path, self.music_root_path, self.prog_q)
            self.finished.emit(parser.get_playlists_with_structure())
        except Exception as e:
            self.finished.emit(e)

class ConversionThread(QThread):
    finished = Signal(str, str)
    
    def __init__(self, output_path, selected_playlists, structure, 
                 export_fmt, copy_music, verify_copy, key_fmt, prog_q, cancel_event):
        super().__init__()
        self.output_path = output_path
        self.selected_playlists = selected_playlists
        self.structure = structure
        self.export_fmt = export_fmt
        self.copy_music = copy_music
        self.verify_copy = verify_copy
        self.key_fmt = key_fmt
        self.prog_q = prog_q
        self.cancel_event = cancel_event
        
    def run(self):
        try:
            if self.export_fmt == "XML":
                self._run_xml_export()
            else:
                self._run_database_export()
            
            if self.cancel_event.is_set():
                self.finished.emit("cancelled", "Conversion cancelled by user")
            else:
                self.finished.emit("completed", f"Successfully exported playlists")
                
        except Exception as e:
            self.finished.emit("error", str(e))
            
    def _run_database_export(self):
        exporter = CDJExporter(self.output_path, 
                              lambda p, m: self.prog_q.put(("progress", (p, m))))
        exporter.cancel_event = self.cancel_event
        
        structure_to_export = self._get_full_structure_for_selection()
        playlist_count = self._count_playlists(structure_to_export)
        self.prog_q.put(("progress", (0, f"Exporting {playlist_count} playlist(s) to database format.")))

        exporter.export_playlists(structure_to_export, self.copy_music, 
                                 self.verify_copy, self.key_fmt)
    
    def _run_xml_export(self):
        from pathlib import Path
        
        output_path = Path(self.output_path)
        xml_file_path = output_path / "rekordbox.xml"
        
        structure_to_export = self._get_full_structure_for_selection()
        playlist_count = self._count_playlists(structure_to_export)
        self.prog_q.put(("progress", (0, f"Exporting {playlist_count} playlist(s) to Rekordbox XML format.")))
        
        xml_exporter = XMLExporter(KeyXlat())
        output_path.mkdir(parents=True, exist_ok=True)
        
        if self.copy_music:
            all_tracks = []
            def collect_tracks_from_structure(nodes):
                for node in nodes:
                    if node.type == 'playlist':
                        all_tracks.extend(node.tracks)
                    elif node.type == 'folder':
                        collect_tracks_from_structure(node.children)
            
            collect_tracks_from_structure(structure_to_export)
            
            contents_path = output_path / "CONTENTS"
            contents_path.mkdir(exist_ok=True)
            
            unique_tracks = {}
            for track in all_tracks:
                if track.file_path and track.file_path not in unique_tracks:
                    unique_tracks[track.file_path] = track
            
            total_tracks = len(unique_tracks)
            for i, (file_path, track) in enumerate(unique_tracks.items(), 1):
                if self.cancel_event.is_set():
                    return
                    
                progress = 10 + int((i / total_tracks) * 70)
                self.prog_q.put(("progress", (progress, f"Copying file {i}/{total_tracks}: {os.path.basename(file_path)}")))
                
                try:
                    source_path = Path(file_path)
                    if source_path.exists():
                        dest_path = contents_path / source_path.name
                        
                        if not dest_path.exists() or self.verify_copy:
                            shutil.copy2(source_path, dest_path)
                            
                            if self.verify_copy and source_path.stat().st_size != dest_path.stat().st_size:
                                log.warning(f"Verification failed for {source_path.name}")
                except Exception as e:
                    log.error(f"Failed to copy {file_path}: {e}")
        
        self.prog_q.put(("progress", (80, "Generating XML file...")))
        
        try:
            xml_exporter.export_to_xml(structure_to_export, xml_file_path, self.key_fmt)
            
            pioneer_folder = output_path / "PIONEER"
            pioneer_folder.mkdir(exist_ok=True)
            
            info_content = (
                f"PIONEER DJ EXPORT\n"
                f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Format: XML\n"
                f"Converter: {Config.APP_NAME} v{Config.VERSION}\n"
                f"Author: {Config.AUTHOR}\n"
            )
            with open(pioneer_folder / "EXPORT.INFO", 'w', encoding='utf-8') as f:
                f.write(info_content)
                
        except Exception as e:
            self.prog_q.put(("error", f"XML export failed: {str(e)}"))
            
    def _get_full_structure_for_selection(self) -> List[Node]:
        new_structure = []
        selected_ids = {id(n) for n in self.selected_playlists}

        def clone_and_filter(nodes: List[Node]) -> List[Node]:
            filtered_list = []
            for node in nodes:
                if id(node) in selected_ids:
                    filtered_list.append(node)
                elif node.type == 'folder':
                    filtered_children = clone_and_filter(node.children)
                    if filtered_children:
                        new_folder = Node(type='folder', name=node.name, children=filtered_children)
                        filtered_list.append(new_folder)
            return filtered_list

        return clone_and_filter(self.structure)
    
    def _count_playlists(self, structure: List[Node]) -> int:
        count = 0
        for node in structure:
            if node.type == 'playlist':
                count += 1
            elif node.type == 'folder':
                count += self._count_playlists(node.children)
        return count

# Main GUI class
class ConverterGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle(f"{Config.APP_NAME} v{Config.VERSION}")
        self.resize(*Config.WINDOW_SIZE)
        self.setMinimumSize(*Config.MIN_SIZE)
        
        # Application state variables
        self.config_file = Path(sys.argv[0]).parent / "converter_config.json"
        self.nml_path = ""
        self.output_path = ""
        self.music_root_path = ""
        self.copy_music = True
        self.verify_copy = False
        self.key_fmt = "Open Key"
        self.export_fmt = "Database"
        self.structure = []
        self.selected_playlists = []
        
        # Threading and communication
        self.cancel_event = threading.Event()
        self.prog_q = queue.Queue()
        
        # Enhanced audio system
        self.audio_mgr = AudioMgr()
        
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
        self.key_xlat = KeyXlat()
        
        # Setup
        self.setStyleSheet(StyleMgr.get_main_style())
        self._setup_ui()
        self._load_configuration()
        self._center_window()
        
        # Start progress update timer
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self._check_progress_queue)
        self.progress_timer.start(100)
    
    def _setup_ui(self):
        """Set up the main UI."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel("Traktor Bridge")
        title_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        subtitle_label = QLabel("Professional Traktor to Pioneer CDJ/XML Converter")
        subtitle_label.setStyleSheet(f"color: {Config.COLORS['fg_muted']};")
        main_layout.addWidget(title_label)
        main_layout.addWidget(subtitle_label)
        main_layout.addSpacing(15)
        
        # File sections
        self.nml_input = self._create_file_input_section(
            main_layout, "1. Traktor NML File *", 
            "Select Traktor NML file...", self._browse_nml
        )
        main_layout.addSpacing(15)
        
        self.music_input = self._create_file_input_section(
            main_layout, "2. Music Root Folder (Optional)", 
            "Select music root folder...", self._browse_music_root
        )
        main_layout.addSpacing(10)
        
        # Playlist section
        playlist_frame = QFrame()
        playlist_layout = QVBoxLayout(playlist_frame)
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        
        playlist_label = QLabel("3. Select Playlist(s)")
        playlist_label.setStyleSheet("color: #00b4d8; font-weight: bold;")
        playlist_layout.addWidget(playlist_label)
        
        self.playlist_tree = QTreeWidget()
        self.playlist_tree.setHeaderHidden(True)
        self.playlist_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.playlist_tree.itemSelectionChanged.connect(self._on_playlist_select)
        self.playlist_tree.itemDoubleClicked.connect(self._on_playlist_double_click)
        
        playlist_layout.addWidget(self.playlist_tree)
        
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
        main_layout.addWidget(playlist_frame, 1)
        
        # Options section
        options_frame = QFrame()
        options_layout = QHBoxLayout(options_frame)
        options_layout.setContentsMargins(0, 0, 0, 0)
        
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
        
        right_frame = QFrame()
        right_layout = QHBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        format_label = QLabel("Export:")
        self.export_format_button = QPushButton(self.export_fmt)
        self.export_format_button.setStyleSheet(StyleMgr.get_button_style())
        
        export_menu = QMenu(self)
        export_menu.setStyleSheet(StyleMgr.get_main_style())
        
        db_action = export_menu.addAction("Database")
        xml_action = export_menu.addAction("XML")
        
        db_action.triggered.connect(lambda: self._change_export_format("Database"))
        xml_action.triggered.connect(lambda: self._change_export_format("XML"))
        
        self.export_format_button.setMenu(export_menu)
        
        right_layout.addWidget(format_label)
        right_layout.addWidget(self.export_format_button)
        
        options_layout.addWidget(left_frame)
        options_layout.addStretch()
        options_layout.addWidget(right_frame)
        
        main_layout.addWidget(options_frame)
        
        # Progress section
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
        
        main_layout.addWidget(progress_frame)
        main_layout.addSpacing(10)
        
        # Action section
        action_frame = QFrame()
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(0, 0, 0, 0)
        
        self.convert_button = QPushButton("CONVERT")
        self.convert_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {Config.COLORS['accent']};
                color: {Config.COLORS['fg_light']};
                font-weight: bold;
                font-size: 11pt;
                padding: 12px;
            }}
            QPushButton:hover {{
                background-color: {Config.COLORS['hover']};
            }}
        """)
        self.convert_button.clicked.connect(self._start_conversion)
        
        self.cancel_button = QPushButton("CANCEL")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_conversion)
        
        action_layout.addWidget(self.convert_button)
        action_layout.addWidget(self.cancel_button)
        
        main_layout.addWidget(action_frame)
        
        # Close section
        close_frame = QFrame()
        close_layout = QHBoxLayout(close_frame)
        close_layout.setContentsMargins(0, 0, 0, 0)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        
        close_layout.addStretch()
        close_layout.addWidget(close_button)
        
        main_layout.addWidget(close_frame)
        
        # Menu
        self._create_menu()
    
    def _create_file_input_section(self, parent_layout, label_text, placeholder, browse_callback):
        """Helper to create file input sections."""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel(label_text)
        label.setStyleSheet("color: #00b4d8; font-weight: bold;")
        layout.addWidget(label)
        
        input_frame = QFrame()
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(0, 0, 0, 0)
        
        input_field = QLineEdit()
        input_field.setPlaceholderText(placeholder)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(browse_callback)
        
        input_layout.addWidget(input_field)
        input_layout.addWidget(browse_button)
        layout.addWidget(input_frame)
        
        parent_layout.addWidget(frame)
        return input_field
    
    def _create_menu(self):
        """Create application menu bar."""
        menubar = self.menuBar()
        
        help_menu = menubar.addMenu("Help")
        
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
    
    def _change_export_format(self, format_name):
        """Change export format."""
        self.export_fmt = format_name
        self.export_format_button.setText(format_name)
        self._save_configuration()
    
    def _load_playlists(self):
        """Load playlists from NML file."""
        if not self.nml_path:
            return
        
        self.playlist_tree.clear()
        self.selected_playlists = []
        self.structure = []
        
        self.progress_label.setText("Loading playlists...")
        self.progress_bar.setValue(0)
        
        # Start loading thread
        self.loading_thread = LoadingThread(self.nml_path, self.music_root_path, self.prog_q)
        self.loading_thread.finished.connect(self._on_playlists_loaded)
        self.loading_thread.start()
    
    def _on_playlists_loaded(self, result):
        """Handle playlist loading completion."""
        if isinstance(result, Exception):
            QMessageBox.critical(self, "Error", f"Failed to load playlists:\n{str(result)}")
            self.progress_label.setText("Failed to load playlists.")
            return
        
        self.structure = result
        self._populate_playlist_tree()
        self.progress_label.setText("Playlists loaded successfully.")
        self.progress_bar.setValue(100)
        
        QTimer.singleShot(2000, lambda: self.progress_bar.setValue(0))
    
    def _populate_playlist_tree(self):
        """Populate the playlist tree widget."""
        self.playlist_tree.clear()
        
        def add_nodes_to_tree(nodes, parent_item=None):
            for node in nodes:
                if node.type == 'folder':
                    folder_item = QTreeWidgetItem()
                    folder_item.setText(0, f"📁 {node.name}")
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, node)
                    
                    if parent_item:
                        parent_item.addChild(folder_item)
                    else:
                        self.playlist_tree.addTopLevelItem(folder_item)
                    
                    add_nodes_to_tree(node.children, folder_item)
                    
                elif node.type == 'playlist':
                    playlist_item = QTreeWidgetItem()
                    playlist_item.setText(0, f"🎵 {node.name} ({len(node.tracks)} tracks)")
                    playlist_item.setData(0, Qt.ItemDataRole.UserRole, node)
                    
                    if parent_item:
                        parent_item.addChild(playlist_item)
                    else:
                        self.playlist_tree.addTopLevelItem(playlist_item)
        
        add_nodes_to_tree(self.structure)
        self.playlist_tree.expandAll()
        self._update_playlist_info()
    
    def _on_playlist_select(self):
        """Handle playlist selection changes."""
        selected_items = self.playlist_tree.selectedItems()
        self.selected_playlists = []
        
        for item in selected_items:
            node = item.data(0, Qt.ItemDataRole.UserRole)
            if node and node.type == 'playlist':
                self.selected_playlists.append(node)
        
        self._update_playlist_info()
    
    def _on_playlist_double_click(self, item, column):
        """Handle double-click on playlist item."""
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node and node.type == 'playlist':
            self._show_playlist_details()
    
    def _show_playlist_details(self):
        """Show details window for selected playlist."""
        if not self.selected_playlists:
            QMessageBox.information(self, "No Selection", "Please select a playlist first.")
            return
        
        # Show details for the first selected playlist
        playlist = self.selected_playlists[0]
        details_dialog = DetailsWindow(playlist, self)
        details_dialog.exec()
    
    def _update_playlist_info(self):
        """Update playlist information label."""
        if not self.selected_playlists:
            self.playlist_info.setText("Select playlist(s) to convert.")
            return
        
        total_tracks = sum(len(p.tracks) for p in self.selected_playlists)
        playlist_names = [p.name for p in self.selected_playlists]
        
        if len(playlist_names) == 1:
            info_text = f"Selected: {playlist_names[0]} ({total_tracks} tracks)"
        else:
            info_text = f"Selected: {len(playlist_names)} playlists ({total_tracks} total tracks)"
        
        self.playlist_info.setText(info_text)
    
    def _start_conversion(self):
        """Start the conversion process."""
        if not self.nml_path:
            QMessageBox.warning(self, "Missing Input", "Please select an NML file first.")
            return
        
        if not self.selected_playlists:
            QMessageBox.warning(self, "No Selection", "Please select at least one playlist to convert.")
            return
        
        # Get output directory
        output_dir = QFileDialog.getExistingDirectory(
            self, f"Select Output Directory for {self.export_fmt} Export",
            self.output_path
        )
        
        if not output_dir:
            return
        
        self.output_path = output_dir
        self._save_configuration()
        
        # Get options
        self.copy_music = self.copy_music_check.isChecked()
        self.verify_copy = self.verify_copy_check.isChecked()
        
        # Reset cancel event
        self.cancel_event.clear()
        
        # Update UI state
        self.convert_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        
        # Start conversion thread
        self.conversion_thread = ConversionThread(
            self.output_path, self.selected_playlists, self.structure,
            self.export_fmt, self.copy_music, self.verify_copy, 
            self.key_fmt, self.prog_q, self.cancel_event
        )
        self.conversion_thread.finished.connect(self._on_conversion_finished)
        self.conversion_thread.start()
    
    def _cancel_conversion(self):
        """Cancel the current conversion."""
        self.cancel_event.set()
        self.cancel_button.setEnabled(False)
        self.progress_label.setText("Cancelling...")
    
    def _on_conversion_finished(self, status, message):
        """Handle conversion completion."""
        self.convert_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        
        if status == "completed":
            self.progress_bar.setValue(100)
            self.progress_label.setText("Conversion completed successfully!")
            QMessageBox.information(self, "Success", f"Conversion completed!\n\nOutput: {self.output_path}")
        elif status == "cancelled":
            self.progress_bar.setValue(0)
            self.progress_label.setText("Conversion cancelled.")
        elif status == "error":
            self.progress_bar.setValue(0)
            self.progress_label.setText("Conversion failed.")
            QMessageBox.critical(self, "Error", f"Conversion failed:\n{message}")
    
    def _check_progress_queue(self):
        """Check for progress updates from worker threads."""
        try:
            while True:
                msg_type, data = self.prog_q.get_nowait()
                
                if msg_type == "progress":
                    if isinstance(data, tuple) and len(data) == 2:
                        percent, message = data
                        self.progress_bar.setValue(int(percent))
                        self.progress_label.setText(str(message))
                        
                        # Log to window if available
                        if self.log_handler.log_text_widget:
                            self.log_handler.log_message(f"Progress {percent}%: {message}")
                
                elif msg_type == "error":
                    error_msg = str(data)
                    self.progress_label.setText(f"Error: {error_msg}")
                    if self.log_handler.log_text_widget:
                        self.log_handler.log_message(f"ERROR: {error_msg}", log.ERROR)
                
        except queue.Empty:
            pass
    
    def _show_log_window(self):
        """Show the log window."""
        if not self.log_dialog:
            self.log_dialog = LogDialog(self)
            self.log_handler.log_text_widget = self.log_dialog.log_text
        
        self.log_dialog.show()
        self.log_dialog.raise_()
        self.log_dialog.activateWindow()
    
    def _show_usage_dialog(self):
        """Show usage guide dialog."""
        dialog = UsageDialog(self)
        dialog.exec()
    
    def _show_about_dialog(self):
        """Show about dialog."""
        dialog = AboutDialog(self)
        dialog.exec()
    
    def _center_window(self):
        """Center the window on screen."""
        screen = QApplication.primaryScreen().geometry()
        window = self.geometry()
        x = (screen.width() - window.width()) // 2
        y = (screen.height() - window.height()) // 2
        self.move(x, y)
    
    def _load_configuration(self):
        """Load configuration from file."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                self.nml_path = config.get('nml_path', '')
                self.music_root_path = config.get('music_root_path', '')
                self.output_path = config.get('output_path', '')
                self.copy_music = config.get('copy_music', True)
                self.verify_copy = config.get('verify_copy', False)
                self.key_fmt = config.get('key_format', 'Open Key')
                self.export_fmt = config.get('export_format', 'Database')
                
                # Update UI
                self.nml_input.setText(self.nml_path)
                self.music_input.setText(self.music_root_path)
                self.copy_music_check.setChecked(self.copy_music)
                self.verify_copy_check.setChecked(self.verify_copy)
                self.export_format_button.setText(self.export_fmt)
                
        except Exception as e:
            log.warning(f"Failed to load configuration: {e}")
    
    def _save_configuration(self):
        """Save configuration to file."""
        try:
            config = {
                'nml_path': self.nml_path,
                'music_root_path': self.music_root_path,
                'output_path': self.output_path,
                'copy_music': self.copy_music_check.isChecked(),
                'verify_copy': self.verify_copy_check.isChecked(),
                'key_format': self.key_fmt,
                'export_format': self.export_fmt
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
                
        except Exception as e:
            log.warning(f"Failed to save configuration: {e}")
    
    def closeEvent(self, event):
        """Handle application close event."""
        # Cancel any running operations
        self.cancel_event.set()
        
        # Save configuration
        self._save_configuration()
        
        # Clean up audio
        if hasattr(self, 'audio_mgr'):
            self.audio_mgr.cleanup()
        
        # Wait for threads to finish
        if hasattr(self, 'loading_thread') and self.loading_thread.isRunning():
            self.loading_thread.wait(3000)
        
        if hasattr(self, 'conversion_thread') and self.conversion_thread.isRunning():
            self.conversion_thread.wait(5000)
        
        event.accept()


# =============================================================================
# APPLICATION ENTRY POINT
# =============================================================================

def setup_logging():
    """Configure application logging."""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    log.basicConfig(
        level=log.INFO,
        format=log_format,
        handlers=[
            log.FileHandler('traktor_bridge.log', encoding='utf-8'),
            log.StreamHandler(sys.stdout)
        ]
    )

def check_dependencies():
    """Check for required dependencies and show warnings if missing."""
    warnings = []
    
    if not AUDIO_OK:
        warnings.append("Audio playback disabled: pygame or TinyTag not available")
    
    if not MUTAGEN_OK:
        warnings.append("Enhanced audio metadata disabled: mutagen not available")
    
    if not ARTWORK_OK:
        warnings.append("Artwork extraction disabled: required audio libraries not available")
    
    return warnings

def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName(Config.APP_NAME)
    app.setApplicationVersion(Config.VERSION)
    app.setOrganizationName(Config.AUTHOR)
    
    # Setup logging
    setup_logging()
    log.info(f"Starting {Config.APP_NAME} v{Config.VERSION}")
    
    # Check dependencies
    warnings = check_dependencies()
    if warnings:
        log.warning("Dependency warnings:")
        for warning in warnings:
            log.warning(f"  - {warning}")
    
    # Create and show main window
    try:
        window = ConverterGUI()
        window.show()
        
        # Show dependency warnings to user if any
        if warnings:
            warning_msg = "Some optional features are disabled:\n\n" + "\n".join(f"• {w}" for w in warnings)
            warning_msg += "\n\nThe application will work but with limited functionality."
            QMessageBox.warning(window, "Dependency Warning", warning_msg)
        
        # Initialize audio system
        if AUDIO_OK:
            window.audio_mgr.initialize(window)
        
        log.info("Application started successfully")
        return app.exec()
        
    except Exception as e:
        log.error(f"Failed to start application: {e}")
        log.error(traceback.format_exc())
        
        # Try to show error in GUI if possible
        try:
            QMessageBox.critical(
                None, "Startup Error", 
                f"Failed to start {Config.APP_NAME}:\n\n{str(e)}\n\nCheck the log file for details."
            )
        except:
            pass
        
        return 1

if __name__ == "__main__":

    sys.exit(main())

