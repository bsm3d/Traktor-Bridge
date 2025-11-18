# -*- coding: utf-8 -*-
"""
Traktor NML Parser Module
Professional-grade parser for Traktor Pro 3.x and 4.x NML files

Supports:
- NML versions 19-20 (Traktor Pro 3.x/4.x)
- Robust encoding detection and error recovery
- Complete metadata extraction
- Artwork extraction with multiple fallbacks
- Progress reporting
- File relocation detection
"""

import xml.etree.ElementTree as ET
import os
import urllib.parse
import logging
import queue
import re
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Optional dependencies for enhanced features
try:
    from lxml import etree as lxml_et
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False

try:
    import chardet
    CHARDET_AVAILABLE = True
except ImportError:
    CHARDET_AVAILABLE = False

try:
    from tinytag import TinyTag, TinyTagException
    TINYTAG_AVAILABLE = True
except ImportError:
    TINYTAG_AVAILABLE = False

try:
    import mutagen
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

ARTWORK_OK = TINYTAG_AVAILABLE or MUTAGEN_AVAILABLE

class NMLVersion(Enum):
    """Supported NML versions"""
    V19 = "19"  # Traktor Pro 3.x
    V20 = "20"  # Traktor Pro 4.x

class CueType(Enum):
    """Traktor cue point types"""
    CUE = 0         # Standard cue
    FADE_IN = 1     # Fade in marker
    FADE_OUT = 2    # Fade out marker
    LOAD = 3        # Load marker
    GRID = 4        # Beatgrid anchor
    LOOP = 5        # Loop start

@dataclass
class Track:
    """Complete track metadata container"""
    # Core metadata
    title: str = "Unknown"
    artist: str = "Unknown"
    album: str = ""
    genre: str = ""
    label: str = ""
    comment: str = ""
    remixer: str = ""
    
    # File information
    file_path: str = ""
    file_size: int = 0
    volume_id: str = ""
    bitrate: int = 0
    
    # Audio analysis
    bpm: float = 0.0
    musical_key: str = ""
    gain: float = 0.0
    playtime: float = 0.0
    
    # User data
    ranking: int = 0
    play_count: int = 0
    
    # Timestamps
    date_added: str = ""
    date_modified: str = ""
    last_played: str = ""
    
    # T4 enhancements
    lock_status: bool = False
    lock_time: str = ""
    playtime_float: float = 0.0
    color_tag: int = 0
    
    # Performance data
    cue_points: List[Dict] = field(default_factory=list)
    grid_anchor_ms: Optional[float] = None
    
    # System data
    audio_id: str = ""
    artwork_data: Optional[bytes] = None
    stem_data: Optional[Dict] = field(default_factory=dict)

@dataclass 
class Node:
    """Playlist/folder node"""
    type: str  # 'playlist', 'folder', 'smartlist'
    name: str
    tracks: List[Track] = field(default_factory=list)
    children: List['Node'] = field(default_factory=list)
    uuid: str = ""
    search_expression: str = ""

class KeyTranslator:
    """Musical key translator for Traktor key values"""
    
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
        """Translate Traktor key index to specified format"""
        if not traktor_key or not traktor_key.isdigit():
            return ""
        try:
            key_index = int(traktor_key)
            if not 0 <= key_index < len(self.open_key_map):
                return ""
            return self.classical_map[key_index] if target_format == "Classical" else self.open_key_map[key_index]
        except (IndexError, ValueError):
            return ""

class FileCache:
    """Intelligent file cache for relocated music files"""
    
    def __init__(self, max_size: int = 30000):
        self.max_size = max_size
        self._cache = {}
        self._access_times = {}
    
    def build_cache(self, root_path: str, progress_cb=None) -> Dict[str, str]:
        """Build filename -> full path cache"""
        if not root_path:
            return {}
            
        music_path = Path(root_path)
        if not music_path.exists() or not music_path.is_dir():
            return {}
        
        self._cache.clear()
        self._access_times.clear()
        
        try:
            supported_formats = {'.mp3', '.wav', '.flac', '.aiff', '.m4a', '.ogg'}
            all_files = list(music_path.rglob('*'))
            total_files = len(all_files)
            
            for i, file_path in enumerate(all_files):
                if i % 1000 == 0 and progress_cb:
                    progress_cb(
                        int((i / total_files) * 45),  # Use 45% of progress
                        f"Scanning: {i}/{total_files} files"
                    )
                
                if (file_path.is_file() and 
                    file_path.suffix.lower() in supported_formats and
                    len(self._cache) < self.max_size):
                    
                    self._cache[file_path.name] = str(file_path)
                    self._access_times[file_path.name] = 0
            
            if progress_cb:
                progress_cb(45, f"Cache built: {len(self._cache)} files")
                
        except Exception as e:
            logging.error(f"Cache building failed: {e}")
            
        return dict(self._cache)
    
    def get(self, filename: str) -> Optional[str]:
        """Get file path from cache"""
        if filename in self._cache:
            import time
            self._access_times[filename] = time.time()
            return self._cache[filename]
        return None

class NMLParsingError(Exception):
    """Custom exception for NML parsing errors"""
    pass

def safe_float(value, default=0.0):
    """Safely convert value to float"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    """Safely convert value to int"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

class TraktorNMLParser:
    """
    Professional Traktor NML Parser
    
    Features:
    - Supports Traktor Pro 3.x and 4.x (NML v19-20)
    - Robust encoding detection and error recovery
    - Complete metadata extraction including artwork
    - Smart file relocation handling
    - Progress reporting
    - Comprehensive error handling
    """
    
    def __init__(self, nml_path: str, music_root: Optional[str] = None,
                 progress_queue: Optional[queue.Queue] = None):
        """
        Initialize parser
        
        Args:
            nml_path: Path to Traktor NML file
            music_root: Optional root path for music files (for relocation handling)
            progress_queue: Optional queue for progress reporting
        """
        self.nml_path = Path(nml_path)
        self.music_root = music_root
        self.prog_q = progress_queue
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.key_translator = KeyTranslator()
        self.file_cache = FileCache()
        
        # Parse XML
        self._parse_xml()
        
        # Detect version
        self.version = self._detect_version()
        self._report_progress(0, f"Detected NML version {self.version.value}")
        
        # Build file cache
        self._report_progress(5, "Building file cache...")
        self.cache_data = self.file_cache.build_cache(
            self.music_root, 
            lambda p, m: self._report_progress(5 + p, m)
        ) if self.music_root else {}
        
        # Build collection mapping
        self._report_progress(50, "Indexing collection entries...")
        self.collection_map = self._build_collection_map()
        
        self._report_progress(100, f"Parser ready: {len(self.collection_map)} tracks indexed")
        self.logger.info(f"NML Parser initialized: v{self.version.value}, {len(self.collection_map)} tracks")
    
    def _report_progress(self, percent: int, message: str):
        """Report progress if queue available"""
        if self.prog_q:
            self.prog_q.put(("progress", (percent, message)))
    
    def _detect_encoding(self, file_path: Path) -> str:
        """Detect file encoding with chardet if available"""
        if not CHARDET_AVAILABLE:
            return 'utf-8'
        
        try:
            detector = chardet.UniversalDetector()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    detector.feed(chunk)
                    if detector.done:
                        break
            
            result = detector.close()
            confidence = result.get('confidence', 0) if result else 0
            
            return result['encoding'] if confidence > 0.7 else 'utf-8'
        except Exception:
            return 'utf-8'
    
    def _parse_xml(self):
        """Parse NML with multiple encoding attempts and error recovery"""
        if not self.nml_path.exists():
            raise NMLParsingError(f"NML file not found: {self.nml_path}")
        
        # Try encoding detection first
        detected_encoding = self._detect_encoding(self.nml_path)
        encodings = [detected_encoding, 'utf-8', 'utf-8-sig', 'iso-8859-1', 'cp1252']
        
        for encoding in encodings:
            try:
                if LXML_AVAILABLE:
                    # Use lxml for better error recovery
                    parser = lxml_et.XMLParser(recover=True, encoding=encoding)
                    tree = lxml_et.parse(str(self.nml_path), parser)
                    # Convert to ElementTree for compatibility
                    xml_str = lxml_et.tostring(tree, encoding='unicode')
                    self.root = ET.fromstring(xml_str)
                else:
                    # Standard ElementTree
                    with open(self.nml_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    
                    # Clean up common XML issues
                    content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content)
                    self.root = ET.fromstring(content)
                
                self.logger.info(f"Successfully parsed NML with encoding: {encoding}")
                return
                
            except (ET.ParseError, UnicodeDecodeError) as e:
                self.logger.debug(f"Failed with encoding {encoding}: {e}")
                continue
        
        raise NMLParsingError("Unable to parse NML file with any supported encoding")
    
    def _detect_version(self) -> NMLVersion:
        """Detect NML version with feature analysis"""
        version_attr = self.root.get('VERSION', '19')
        
        # Check for T4 specific features
        program = self.root.find('HEAD')
        if program is not None:
            program_name = program.get('PROGRAM', '')
            if 'Pro 4' in program_name or 'Traktor Pro 4' in program_name:
                return NMLVersion.V20
        
        # Feature detection
        has_stems = bool(self.root.find('.//STEMS'))
        has_smart_playlists = bool(self.root.find('.//SMARTLIST'))
        has_flexible_grids = bool(self.root.find('.//GRID'))
        has_lock_time = bool(self.root.find('.//ENTRY[@LOCK_MODIFICATION_TIME]'))
        
        if (version_attr == '20' or has_stems or has_smart_playlists or 
            has_flexible_grids or has_lock_time):
            return NMLVersion.V20
        else:
            return NMLVersion.V19
    
    def _build_collection_map(self) -> Dict[str, ET.Element]:
        """Build collection mapping from track keys to XML elements"""
        collection_map = {}
        collection = self.root.find('COLLECTION')
        
        if collection is None:
            self.logger.warning("No COLLECTION section found in NML")
            return {}
        
        entries = collection.findall('ENTRY')
        total_entries = len(entries)
        
        for i, entry in enumerate(entries):
            if i % 500 == 0:
                progress = 50 + int((i / total_entries) * 40)
                self._report_progress(progress, f"Indexing: {i}/{total_entries}")
            
            location = entry.find('LOCATION')
            if location is not None:
                volume = location.get('VOLUME', '')
                dir_path = location.get('DIR', '')
                file_name = location.get('FILE', '')
                
                if volume and dir_path and file_name:
                    traktor_key = f"{volume}{dir_path}{file_name}"
                    collection_map[traktor_key] = entry
        
        self._report_progress(90, f"Collection indexed: {len(collection_map)} tracks")
        return collection_map
    
    def get_playlists_with_structure(self) -> List[Node]:
        """Parse complete playlist and folder structure"""
        self._report_progress(90, "Parsing playlist structure...")
        
        # Try different playlist root strategies
        strategies = [
            (".//PLAYLISTS/NODE[@NAME='$ROOT']", "Traktor Pro 3.5+ format"),
            (".//PLAYLISTS", "Legacy Traktor format"),
            (".//PLAYLISTS/NODE", "Alternative format")
        ]
        
        playlist_root = None
        used_strategy = "Unknown"
        
        for xpath, description in strategies:
            playlist_root = self.root.find(xpath)
            if playlist_root is not None:
                used_strategy = description
                break
        
        if playlist_root is None:
            self.logger.warning("No playlist structure found")
            return []
        
        structure = self._parse_node_recursive(playlist_root)
        self._report_progress(100, f"Structure parsed using {used_strategy}")
        
        return structure
    
    def _parse_node_recursive(self, node: ET.Element) -> List[Node]:
        """Recursively parse playlist nodes"""
        results = []
        
        # Handle both direct children and SUBNODES wrapper
        children_container = node.find('SUBNODES') or node
        
        for child_node in children_container.findall('NODE'):
            node_type = child_node.get('TYPE')
            node_name = child_node.get('NAME', 'Unnamed')
            
            if node_type == 'PLAYLIST':
                playlist = self._parse_playlist_node(child_node, node_name)
                if playlist and playlist.tracks:
                    results.append(playlist)
            
            elif node_type == 'SMARTLIST' and self.version == NMLVersion.V20:
                smartlist = self._parse_smartlist_node(child_node, node_name)
                if smartlist:
                    results.append(smartlist)
            
            elif node_type == 'FOLDER':
                folder = Node(type='folder', name=node_name)
                folder.children = self._parse_node_recursive(child_node)
                
                if folder.children:
                    results.append(folder)
        
        return results
    
    def _parse_playlist_node(self, node: ET.Element, name: str) -> Optional[Node]:
        """Parse standard playlist node"""
        playlist = Node(type='playlist', name=name)
        playlist_elem = node.find('PLAYLIST')
        
        if playlist_elem is not None:
            playlist.uuid = playlist_elem.get('UUID', '')
            
            for entry in playlist_elem.findall('ENTRY'):
                track = self._parse_playlist_entry(entry)
                if track:
                    playlist.tracks.append(track)
        
        return playlist if playlist.tracks else None
    
    def _parse_smartlist_node(self, node: ET.Element, name: str) -> Optional[Node]:
        """Parse T4 smart playlist node"""
        smartlist_elem = node.find('SMARTLIST')
        if smartlist_elem is None:
            return None
        
        smartlist = Node(type='smartlist', name=name)
        smartlist.uuid = smartlist_elem.get('UUID', '')
        
        search_expr = smartlist_elem.find('SEARCH_EXPRESSION')
        if search_expr is not None:
            smartlist.search_expression = search_expr.get('QUERY', '')
        
        return smartlist
    
    def _parse_playlist_entry(self, entry: ET.Element) -> Optional[Track]:
        """Parse playlist entry and find corresponding track"""
        primary_key = entry.find('PRIMARYKEY')
        if primary_key is None:
            return None
        
        track_key = primary_key.get('KEY', '')
        collection_entry = self.collection_map.get(track_key)
        
        if collection_entry is not None:
            return self._parse_collection_entry(collection_entry)
        
        return None
    
    def _parse_collection_entry(self, entry: ET.Element) -> Track:
        """Parse complete track entry with all metadata"""
        track = Track()
        
        # Basic metadata
        track.audio_id = entry.get('AUDIO_ID', '')
        track.title = entry.get('TITLE', 'Unknown')
        track.artist = entry.get('ARTIST', 'Unknown')
        track.remixer = entry.get('REMIXER', '')
        track.date_modified = entry.get('MODIFICATION_DATE', '')
        
        # T4 lock information
        if entry.get('LOCK') == '1':
            track.lock_status = True
            track.lock_time = entry.get('LOCK_MODIFICATION_TIME', '')
        
        # File location with smart resolution
        track.file_path, track.volume_id = self._parse_file_location(entry)
        
        # INFO section - comprehensive metadata
        info = entry.find('INFO')
        if info is not None:
            track.bitrate = safe_int(info.get('BITRATE', '0'))
            track.file_size = safe_int(info.get('FILESIZE', '0'))
            track.playtime = safe_float(info.get('PLAYTIME', '0'))
            track.ranking = safe_int(info.get('RANKING', '0'))
            track.genre = info.get('GENRE', '')
            track.comment = info.get('COMMENT', '')
            track.label = info.get('LABEL', '')
            track.color_tag = safe_int(info.get('COLOR', '0'))
            track.date_added = info.get('IMPORT_DATE', '')
            
            # T4 specific fields
            if self.version == NMLVersion.V20:
                track.playtime_float = safe_float(info.get('PLAYTIME_FLOAT', str(track.playtime)))
                track.play_count = safe_int(info.get('PLAYCOUNT', '0'))
                track.last_played = info.get('LAST_PLAYED', '')
        
        # ALBUM section
        album = entry.find('ALBUM')
        if album is not None:
            track.album = album.get('TITLE', '')
        
        # TEMPO section
        tempo = entry.find('TEMPO')
        if tempo is not None:
            track.bpm = safe_float(tempo.get('BPM', '0'))
        
        # MUSICAL_KEY section with translation
        key_elem = entry.find('MUSICAL_KEY')
        if key_elem is not None:
            raw_key = key_elem.get('VALUE', '')
            track.musical_key = self.key_translator.translate(raw_key, "Open Key")
        
        # LOUDNESS section
        loudness = entry.find('LOUDNESS')
        if loudness is not None:
            track.gain = safe_float(loudness.get('ANALYZED_DB', '0'))
        
        # Parse cue points
        self._parse_cue_points(entry, track)
        
        # Parse stems data (T4)
        if self.version == NMLVersion.V20:
            self._parse_stem_data(entry, track)
        
        # Extract artwork
        self._extract_artwork(track)
        
        return track
    
    def _parse_file_location(self, entry: ET.Element) -> Tuple[str, str]:
        """Parse and resolve file location with cache fallback"""
        location = entry.find('LOCATION')
        if location is None:
            return '', ''
        
        volume_id = location.get('VOLUME', '')
        file_from_nml = location.get('FILE', '')
        
        # Strategy 1: Use file cache for relocated files
        if self.cache_data and file_from_nml:
            filename = urllib.parse.unquote(os.path.basename(file_from_nml))
            cached_path = self.file_cache.get(filename)
            if cached_path:
                return cached_path, volume_id
        
        # Strategy 2: Reconstruct original path
        dir_path = location.get('DIR', '').replace('/:', '/')
        
        reconstructed = urllib.parse.unquote(f"{volume_id}{dir_path}{file_from_nml}")
        
        # Clean up URI prefixes
        for prefix in ['file://localhost/', 'file:///', 'file://']:
            if reconstructed.startswith(prefix):
                reconstructed = reconstructed[len(prefix):]
                break
        
        # Handle Windows paths starting with slash
        if len(reconstructed) > 2 and reconstructed.startswith('/') and reconstructed[2] == ':':
            reconstructed = reconstructed[1:]
        
        return reconstructed, volume_id
    
    def _parse_cue_points(self, entry: ET.Element, track: Track):
        """Parse cue points with T3/T4 compatibility"""
        for cue in entry.findall('CUE_V2'):
            try:
                cue_type = safe_int(cue.get('TYPE', '-1'))
                start_ms = safe_float(cue.get('START', '0'))
                
                # Store grid anchor for first TYPE=4 cue
                if cue_type == CueType.GRID.value and track.grid_anchor_ms is None:
                    track.grid_anchor_ms = start_ms
                
                cue_point = {
                    'name': cue.get('NAME', ''),
                    'type': cue_type,
                    'start': int(start_ms),
                    'len': safe_int(cue.get('LEN', '0')),
                    'hotcue': safe_int(cue.get('HOTCUE', '-1'))
                }
                
                # T4 color information
                if self.version == NMLVersion.V20:
                    cue_point['color'] = cue.get('COLOR', '')
                
                track.cue_points.append(cue_point)
                
            except Exception as e:
                self.logger.warning(f"Invalid cue point data: {e}")
                continue
    
    def _parse_stem_data(self, entry: ET.Element, track: Track):
        """Parse T4 stems data"""
        stems = entry.find('STEMS')
        if stems is None:
            return
        
        track.stem_data = {
            'enabled': stems.get('ENABLED') == '1',
            'file_path': stems.get('FILE', ''),
            'volume_gain': safe_float(stems.get('VOLUME_GAIN', '0'))
        }
        
        # Parse individual stem channels
        track.stem_data['channels'] = []
        for stem in stems.findall('STEM'):
            channel = {
                'name': stem.get('NAME', ''),
                'color': stem.get('COLOR', ''),
                'volume': safe_float(stem.get('VOLUME', '1.0')),
                'filter_on': stem.get('FILTER_ON') == '1',
                'filter_value': safe_float(stem.get('FILTER_VALUE', '0'))
            }
            track.stem_data['channels'].append(channel)
    
    def _extract_artwork(self, track: Track):
        """Extract artwork using TinyTag with mutagen fallback"""
        if not (ARTWORK_OK and track.file_path and os.path.exists(track.file_path)):
            return
        
        # Primary method: TinyTag
        if TINYTAG_AVAILABLE:
            try:
                tag = TinyTag.get(track.file_path, image=True)
                if tag and tag.images and tag.images.any and tag.images.any.data:
                    track.artwork_data = tag.images.any.data
                    return
            except TinyTagException:
                pass
            except Exception as e:
                self.logger.debug(f"TinyTag artwork extraction failed: {e}")
        
        # Fallback method: Mutagen
        if MUTAGEN_AVAILABLE:
            try:
                audio_file = mutagen.File(track.file_path, easy=False)
                if audio_file is None:
                    return
                
                artwork_data = None
                
                # FLAC, OGG with pictures
                if hasattr(audio_file, 'pictures') and audio_file.pictures:
                    artwork_data = audio_file.pictures[0].data
                
                # MP3 with ID3 tags
                elif hasattr(audio_file, 'tags') and audio_file.tags:
                    for key in audio_file.tags.keys():
                        if key.startswith('APIC'):
                            frame = audio_file.tags[key]
                            if hasattr(frame, 'data'):
                                artwork_data = frame.data
                                break
                
                # MP4/M4A files
                elif 'covr' in audio_file and audio_file.get('covr'):
                    cover_art = audio_file.get('covr')[0]
                    if isinstance(cover_art, bytes):
                        artwork_data = cover_art
                    elif hasattr(cover_art, 'data'):
                        artwork_data = cover_art.data
                
                if artwork_data:
                    track.artwork_data = artwork_data
                    
            except Exception as e:
                self.logger.debug(f"Mutagen artwork extraction failed: {e}")
    
    def get_version(self) -> str:
        """Get detected NML version"""
        return self.version.value
    
    def get_stats(self) -> Dict:
        """Get parsing statistics"""
        return {
            'version': self.version.value,
            'total_tracks': len(self.collection_map),
            'file_cache_size': len(self.cache_data),
            'has_music_root': bool(self.music_root),
            'artwork_support': ARTWORK_OK,
            'lxml_available': LXML_AVAILABLE,
            'chardet_available': CHARDET_AVAILABLE
        }
    
    def validate_track(self, track: Track) -> List[str]:
        """Validate track data and return issues"""
        issues = []
        
        if not track.audio_id:
            issues.append("Missing AUDIO_ID")
        if not track.file_path:
            issues.append("Missing file path")
        if track.bpm <= 0:
            issues.append("Invalid BPM")
        if track.playtime <= 0:
            issues.append("Invalid duration")
        
        # Validate unique hotcue numbers
        hotcue_numbers = [c['hotcue'] for c in track.cue_points if c['hotcue'] > 0]
        if len(hotcue_numbers) != len(set(hotcue_numbers)):
            issues.append("Duplicate hotcue numbers")
        
        return issues


# Factory function for easy instantiation
def create_traktor_parser(nml_path: str, music_root: Optional[str] = None,
                         progress_queue: Optional[queue.Queue] = None) -> TraktorNMLParser:
    """
    Create a Traktor NML parser instance
    
    Args:
        nml_path: Path to Traktor NML file
        music_root: Optional root path for music files
        progress_queue: Optional queue for progress reporting
    
    Returns:
        Configured TraktorNMLParser instance
    """
    return TraktorNMLParser(nml_path, music_root, progress_queue)


# Example usage and testing
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 2:
        print("Usage: python traktor_nml_parser.py <nml_file> [music_root]")
        sys.exit(1)
    
    nml_file = sys.argv[1]
    music_root = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        # Create parser
        parser = create_traktor_parser(nml_file, music_root)
        
        # Display stats
        stats = parser.get_stats()
        print(f"\nNML Parser Statistics:")
        print(f"Version: {stats['version']}")
        print(f"Total tracks: {stats['total_tracks']}")
        print(f"File cache size: {stats['file_cache_size']}")
        print(f"Artwork support: {stats['artwork_support']}")
        
        # Parse playlists
        playlists = parser.get_playlists_with_structure()
        
        print(f"\nPlaylist Structure:")
        for playlist in playlists:
            if playlist.type == 'playlist':
                print(f"  Playlist: {playlist.name} ({len(playlist.tracks)} tracks)")
                
                # Sample track validation
                for track in playlist.tracks[:3]:  # First 3 tracks
                    issues = parser.validate_track(track)
                    status = "✓" if not issues else f"⚠ {len(issues)} issues"
                    print(f"    {track.artist} - {track.title} {status}")
                    
            elif playlist.type == 'smartlist':
                print(f"  Smart Playlist: {playlist.name}")
                print(f"    Query: {playlist.search_expression}")
                
            elif playlist.type == 'folder':
                print(f"  Folder: {playlist.name} ({len(playlist.children)} children)")
        
        print(f"\nTotal playlists found: {len([p for p in playlists if p.type == 'playlist'])}")
        
    except NMLParsingError as e:
        print(f"Parsing error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)