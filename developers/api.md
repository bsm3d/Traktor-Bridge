# Traktor Bridge 2.0 - API Reference

## Introduction

This document provides a complete API reference for Traktor Bridge 2.0, covering all modules, classes, and functions available for developers. The API enables integration with Traktor collections, advanced audio analysis, and export to multiple DJ hardware and software formats.

## Sources and Attribution

### Author
**Benoit (BSM) Saint-Moulin**
* **Website**: www.benoitsaintmoulin.com
* **Developer Portfolio**: www.bsm3d.com
* **GitHub**: [github.com/bsm3d](https://github.com/bsm3d)
* **Instagram**: [@benoitsaintmoulin](https://www.instagram.com/benoitsaintmoulin)

## Table of Contents

1. [Parser API](#parser-api)
2. [Exporter APIs](#exporter-apis)
3. [Utility APIs](#utility-apis)
4. [Data Structures](#data-structures)
5. [Examples](#examples)

---

## Parser API

### create_traktor_parser()

Factory function for creating a Traktor NML parser instance.

```python
from parser.bsm_nml_parser import create_traktor_parser

parser = create_traktor_parser(
    nml_path: str,
    music_root: Optional[str] = None,
    progress_queue: Optional[queue.Queue] = None
) -> TraktorNMLParser
```

**Parameters:**
- `nml_path` (str): Path to Traktor collection.nml file
- `music_root` (Optional[str]): Root directory for music files (for relocated tracks)
- `progress_queue` (Optional[queue.Queue]): Queue for progress reporting

**Returns:**
- `TraktorNMLParser`: Configured parser instance

**Example:**
```python
import queue
from parser.bsm_nml_parser import create_traktor_parser

progress_q = queue.Queue()
parser = create_traktor_parser(
    nml_path="/path/to/collection.nml",
    music_root="/path/to/music",
    progress_queue=progress_q
)
```

---

### TraktorNMLParser

Main parser class for Traktor NML files.

#### parse_xml()

Parse the NML file and build collection map.

```python
def parse_xml(self) -> bool
```

**Returns:**
- `bool`: True if parsing succeeded, False otherwise

**Raises:**
- `FileNotFoundError`: If NML file doesn't exist
- `xml.etree.ElementTree.ParseError`: If XML is malformed

**Example:**
```python
parser = create_traktor_parser("collection.nml")
if parser.parse_xml():
    print("Parsing successful!")
```

---

#### get_playlists_with_structure()

Get playlist structure as a hierarchical tree.

```python
def get_playlists_with_structure(self) -> List[Node]
```

**Returns:**
- `List[Node]`: List of root-level nodes (folders/playlists)

**Example:**
```python
structure = parser.get_playlists_with_structure()

for node in structure:
    print(f"Name: {node.name}, Type: {node.type}")
    if node.type == 'folder':
        for child in node.children:
            print(f"  - {child.name}")
```

---

#### get_stats()

Get collection statistics.

```python
def get_stats(self) -> Dict[str, Any]
```

**Returns:**
```python
{
    'total_tracks': int,
    'total_playlists': int,
    'total_folders': int,
    'nml_version': str,
    'encoding': str,
    'parse_time': float
}
```

**Example:**
```python
stats = parser.get_stats()
print(f"Total tracks: {stats['total_tracks']}")
print(f"NML version: {stats['nml_version']}")
```

---

#### validate_track()

Validate track metadata and return issues.

```python
def validate_track(self, track: Track) -> List[str]
```

**Parameters:**
- `track` (Track): Track to validate

**Returns:**
- `List[str]`: List of validation issues (empty if valid)

**Example:**
```python
issues = parser.validate_track(track)
if issues:
    print(f"Track has issues: {issues}")
```

---

## Exporter APIs

### CDJ Export Engine

#### CDJExportEngine

Main orchestrator for CDJ hardware exports.

```python
from exporter.cdj_integration import CDJExportEngine, CDJModel

engine = CDJExportEngine(
    target_model: CDJModel = CDJModel.CDJ_2000NXS2,
    use_encryption: bool = False,
    progress_queue: Optional[queue.Queue] = None
)
```

**Parameters:**
- `target_model` (CDJModel): Target CDJ model
- `use_encryption` (bool): Enable encryption (always False for CDJ hardware)
- `progress_queue` (Optional[queue.Queue]): Queue for progress reporting

**CDJModel Enum:**
```python
class CDJModel(Enum):
    CDJ_2000 = "CDJ-2000"
    CDJ_2000NXS2 = "CDJ-2000NXS2"
    CDJ_3000 = "CDJ-3000"
    XDJ_1000MK2 = "XDJ-1000MK2"
```

---

#### export_collection_to_cdj()

Export complete collection to CDJ format.

```python
def export_collection_to_cdj(
    self,
    tracks: List[Track],
    playlist_structure: List[Node],
    output_dir: Path,
    copy_audio: bool = True
) -> Dict[str, Any]
```

**Parameters:**
- `tracks` (List[Track]): List of tracks to export
- `playlist_structure` (List[Node]): Playlist hierarchy
- `output_dir` (Path): Output directory (USB drive)
- `copy_audio` (bool): Copy audio files to USB

**Returns:**
```python
{
    'status': 'success' | 'error',
    'tracks_exported': int,
    'playlists_created': int,
    'anlz_files_generated': int,
    'total_size_mb': float,
    'errors': List[str]
}
```

**Example:**
```python
from pathlib import Path
from exporter.cdj_integration import CDJExportEngine, CDJModel

engine = CDJExportEngine(target_model=CDJModel.CDJ_2000NXS2)
result = engine.export_collection_to_cdj(
    tracks=all_tracks,
    playlist_structure=structure,
    output_dir=Path("/media/usb"),
    copy_audio=True
)

print(f"Exported {result['tracks_exported']} tracks")
print(f"Created {result['playlists_created']} playlists")
```

---

### Rekordbox XML Exporter

#### RekordboxXMLExporter

Standard Rekordbox XML export.

```python
from exporter.bsm_xml_exporter import RekordboxXMLExporter

exporter = RekordboxXMLExporter()
```

---

#### export_collection()

Export collection to Rekordbox XML format.

```python
def export_collection(
    self,
    tracks: List[Track],
    playlist_structure: List[Node],
    output_path: Path
) -> str
```

**Parameters:**
- `tracks` (List[Track]): Tracks to export
- `playlist_structure` (List[Node]): Playlist hierarchy
- `output_path` (Path): Output XML file path

**Returns:**
- `str`: XML content as string

**Example:**
```python
from pathlib import Path
from exporter.bsm_xml_exporter import RekordboxXMLExporter

exporter = RekordboxXMLExporter()
xml_content = exporter.export_collection(
    tracks=all_tracks,
    playlist_structure=structure,
    output_path=Path("rekordbox.xml")
)

print(f"Generated XML: {len(xml_content)} bytes")
```

---

### M3U Exporter

#### M3UExporter

Universal M3U playlist export.

```python
from exporter.bsm_m3u_exporter import M3UExporter

exporter = M3UExporter(output_path: str)
```

**Parameters:**
- `output_path` (str): Output directory for M3U files

---

#### export_playlists()

Export playlists to M3U format.

```python
def export_playlists(
    self,
    playlist_structure: List[Node],
    relative_paths: bool = True,
    copy_music: bool = False
) -> int
```

**Parameters:**
- `playlist_structure` (List[Node]): Playlist hierarchy
- `relative_paths` (bool): Use relative paths in M3U
- `copy_music` (bool): Copy audio files alongside M3U

**Returns:**
- `int`: Number of playlists exported

**Example:**
```python
from exporter.bsm_m3u_exporter import M3UExporter

exporter = M3UExporter(output_path="/output/playlists")
count = exporter.export_playlists(
    playlist_structure=structure,
    relative_paths=True,
    copy_music=False
)

print(f"Exported {count} playlists")
```

---

### Rekordbox Database Exporter

#### RekordboxDatabaseManager

SQLite/SQLCipher database for Rekordbox software.

```python
from exporter.bsm_rb_exporter import RekordboxDatabaseManager

manager = RekordboxDatabaseManager()
```

---

#### create_database()

Create Rekordbox software database.

```python
def create_database(
    self,
    tracks: List[Track],
    playlist_structure: List[Node],
    output_path: Path,
    use_encryption: bool = True
) -> None
```

**Parameters:**
- `tracks` (List[Track]): Tracks to export
- `playlist_structure` (List[Node]): Playlist hierarchy
- `output_path` (Path): Output database path
- `use_encryption` (bool): Use SQLCipher encryption

**Example:**
```python
from pathlib import Path
from exporter.bsm_rb_exporter import RekordboxDatabaseManager

manager = RekordboxDatabaseManager()
manager.create_database(
    tracks=all_tracks,
    playlist_structure=structure,
    output_path=Path("rekordbox.db"),
    use_encryption=True
)
```

---

## Utility APIs

### KeyTranslator

Musical key notation translator.

```python
from utils.key_translator import KeyTranslator

translator = KeyTranslator()
```

---

#### translate()

Translate key from Traktor to target format.

```python
def translate(
    self,
    traktor_key: str,
    target_format: str
) -> str
```

**Parameters:**
- `traktor_key` (str): Traktor key index (0-23)
- `target_format` (str): Target format ("Open Key", "Classical", "Flat Classical", "Pioneer")

**Returns:**
- `str`: Translated key notation

**Example:**
```python
translator = KeyTranslator()

# Traktor key 5 to Open Key
open_key = translator.translate("5", "Open Key")  # "12B"

# Traktor key 5 to Classical
classical = translator.translate("5", "Classical")  # "B"

# Traktor key 5 to Pioneer
pioneer = translator.translate("5", "Pioneer")  # "B"
```

---

#### get_rekordbox_key_id()

Get Rekordbox key ID for PDB export.

```python
def get_rekordbox_key_id(self, traktor_key: str) -> int
```

**Parameters:**
- `traktor_key` (str): Traktor key index (0-23)

**Returns:**
- `int`: Rekordbox key ID (0-25)

**Example:**
```python
key_id = translator.get_rekordbox_key_id("5")  # 5
```

---

#### get_harmonic_mixing_info()

Get harmonic mixing suggestions for DJ sets.

```python
def get_harmonic_mixing_info(self, key: str) -> Dict[str, Any]
```

**Parameters:**
- `key` (str): Key in Open Key format (e.g., "12B")

**Returns:**
```python
{
    'perfect_matches': List[str],     # Same key
    'energy_up': List[str],            # +1 semitone
    'energy_down': List[str],          # -1 semitone
    'harmonic_matches': List[str],     # +/- 7 semitones (perfect fifth)
    'dominant_matches': List[str],     # +/- 2 semitones
    'relative_key': str                # Relative major/minor
}
```

**Example:**
```python
mixing_info = translator.get_harmonic_mixing_info("12B")

print(f"Perfect matches: {mixing_info['perfect_matches']}")  # ['12A']
print(f"Energy up: {mixing_info['energy_up']}")              # ['1B']
print(f"Energy down: {mixing_info['energy_down']}")          # ['11B']
print(f"Harmonic: {mixing_info['harmonic_matches']}")        # ['7B', '5B']
```

---

#### suggest_key_progression()

Suggest key progression for DJ sets.

```python
def suggest_key_progression(
    self,
    current_key: str,
    direction: str = "up"
) -> List[str]
```

**Parameters:**
- `current_key` (str): Current key in Open Key format
- `direction` (str): "up", "down", or "harmonic"

**Returns:**
- `List[str]`: Suggested next keys

**Example:**
```python
next_keys = translator.suggest_key_progression("12B", "up")
# Returns: ['1B', '12A', '7B']
```

---

#### get_camelot_color()

Get Camelot wheel color for UI display.

```python
def get_camelot_color(self, key: str) -> str
```

**Parameters:**
- `key` (str): Key in Open Key format

**Returns:**
- `str`: Hex color code

**Example:**
```python
color = translator.get_camelot_color("12B")  # "#FF0000" (red)
```

---

### AudioManager

Thread-safe audio playback manager.

```python
from utils.audio_manager import AudioManager

audio_manager = AudioManager()
```

---

#### initialize()

Initialize audio system.

```python
def initialize(self, parent: QWidget) -> None
```

**Parameters:**
- `parent` (QWidget): Parent widget for error dialogs

---

#### play()

Play audio file.

```python
def play(self, file_path: str, item_id: Any = None) -> None
```

**Parameters:**
- `file_path` (str): Path to audio file
- `item_id` (Any): Optional identifier for tracking

**Example:**
```python
audio_manager.play("/path/to/track.mp3", item_id="track_001")
```

---

#### stop()

Stop current playback.

```python
def stop(self) -> None
```

---

#### is_playing()

Check if audio is currently playing.

```python
def is_playing(self) -> bool
```

**Returns:**
- `bool`: True if playing, False otherwise

---

#### cleanup()

Clean up audio resources.

```python
def cleanup(self) -> None
```

---

### PlaylistManager

Playlist operations and statistics.

```python
from utils.playlist import PlaylistManager

manager = PlaylistManager()
```

---

#### count_tracks_in_structure()

Count total tracks in playlist structure.

```python
@staticmethod
def count_tracks_in_structure(structure: List[Node]) -> int
```

**Parameters:**
- `structure` (List[Node]): Playlist hierarchy

**Returns:**
- `int`: Total unique tracks

**Example:**
```python
track_count = PlaylistManager.count_tracks_in_structure(structure)
print(f"Total tracks: {track_count}")
```

---

#### collect_all_tracks()

Collect all unique tracks from structure.

```python
@staticmethod
def collect_all_tracks(structure: List[Node]) -> List[Track]
```

**Parameters:**
- `structure` (List[Node]): Playlist hierarchy

**Returns:**
- `List[Track]`: Deduplicated track list

**Example:**
```python
all_tracks = PlaylistManager.collect_all_tracks(structure)
```

---

#### find_playlist_by_name()

Find playlist by name in structure.

```python
@staticmethod
def find_playlist_by_name(
    structure: List[Node],
    name: str
) -> Optional[Node]
```

**Parameters:**
- `structure` (List[Node]): Playlist hierarchy
- `name` (str): Playlist name to search

**Returns:**
- `Optional[Node]`: Found playlist or None

**Example:**
```python
playlist = PlaylistManager.find_playlist_by_name(structure, "House Music")
if playlist:
    print(f"Found: {playlist.name} with {len(playlist.tracks)} tracks")
```

---

#### get_playlist_statistics()

Get comprehensive playlist statistics.

```python
@staticmethod
def get_playlist_statistics(playlist: Node) -> Dict[str, Any]
```

**Parameters:**
- `playlist` (Node): Playlist to analyze

**Returns:**
```python
{
    'track_count': int,
    'total_duration_seconds': float,
    'total_duration_formatted': str,
    'average_bpm': float,
    'bpm_range': Tuple[float, float],
    'key_distribution': Dict[str, int],
    'genre_distribution': Dict[str, int],
    'artist_count': int,
    'average_rating': float
}
```

**Example:**
```python
stats = PlaylistManager.get_playlist_statistics(playlist)

print(f"Tracks: {stats['track_count']}")
print(f"Duration: {stats['total_duration_formatted']}")
print(f"Avg BPM: {stats['average_bpm']:.1f}")
print(f"Keys: {stats['key_distribution']}")
```

---

## Data Structures

### Track

Complete track metadata.

```python
from dataclasses import dataclass
from typing import List, Optional, Dict

@dataclass
class Track:
    # Core metadata
    title: str
    artist: str
    album: str
    genre: str
    label: str
    comment: str
    remixer: str

    # File information
    file_path: str
    file_size: int
    volume_id: str
    bitrate: int

    # Audio analysis
    bpm: float
    musical_key: str  # Traktor index (0-23)
    gain: float
    playtime: float

    # User data
    ranking: int  # 0-5 stars
    play_count: int

    # Timestamps
    date_added: str
    date_modified: str
    last_played: str

    # T4 enhancements
    lock_status: bool
    lock_time: str
    playtime_float: float
    color_tag: int

    # Performance data
    cue_points: List[Dict]
    grid_anchor_ms: Optional[float]

    # System data
    audio_id: str
    artwork_data: Optional[bytes]
    stem_data: Optional[Dict]
```

---

### Node

Playlist/folder structure node.

```python
@dataclass
class Node:
    type: str  # 'playlist', 'folder', 'smartlist'
    name: str
    tracks: List[Track]
    children: List['Node']  # Recursive structure
    uuid: str
    search_expression: str  # For smartlists
```

---

### Cue Point

Cue point structure.

```python
{
    'name': str,           # Cue point name
    'type': int,           # CueType enum value
    'start': int,          # Position in milliseconds
    'len': int,            # Duration for loops (0 for regular cues)
    'hotcue': int,         # -1 for memory cues, 0-7 for hot cues
    'color': str           # T4 color tag (hex color)
}
```

**CueType Enum:**
```python
class CueType(Enum):
    CUE = 0          # Standard cue point
    FADE_IN = 1      # Fade in marker
    FADE_OUT = 2     # Fade out marker
    LOAD = 3         # Memory cue (load marker)
    GRID = 4         # Beatgrid anchor
    LOOP = 5         # Loop start
```

---

## Examples

### Complete CDJ Export Example

```python
import queue
from pathlib import Path
from parser.bsm_nml_parser import create_traktor_parser
from exporter.cdj_integration import CDJExportEngine, CDJModel
from utils.playlist import PlaylistManager

# 1. Create progress queue
progress_q = queue.Queue()

# 2. Parse NML file
parser = create_traktor_parser(
    nml_path="/path/to/collection.nml",
    music_root="/path/to/music",
    progress_queue=progress_q
)

if not parser.parse_xml():
    print("Failed to parse NML")
    exit(1)

# 3. Get playlist structure
structure = parser.get_playlists_with_structure()

# 4. Collect all tracks
all_tracks = PlaylistManager.collect_all_tracks(structure)

print(f"Found {len(all_tracks)} unique tracks")

# 5. Create CDJ exporter
engine = CDJExportEngine(
    target_model=CDJModel.CDJ_2000NXS2,
    use_encryption=False,
    progress_queue=progress_q
)

# 6. Export to USB
result = engine.export_collection_to_cdj(
    tracks=all_tracks,
    playlist_structure=structure,
    output_dir=Path("/media/usb"),
    copy_audio=True
)

# 7. Check results
if result['status'] == 'success':
    print(f"✓ Exported {result['tracks_exported']} tracks")
    print(f"✓ Created {result['playlists_created']} playlists")
    print(f"✓ Generated {result['anlz_files_generated']} ANLZ files")
    print(f"✓ Total size: {result['total_size_mb']:.2f} MB")
else:
    print(f"✗ Export failed: {result['errors']}")
```

---

### Key Translation Example

```python
from utils.key_translator import KeyTranslator

translator = KeyTranslator()

# Current track key
current_key = "5"  # Traktor index

# Get Open Key notation
open_key = translator.translate(current_key, "Open Key")
print(f"Open Key: {open_key}")  # "12B"

# Get harmonic mixing suggestions
mixing_info = translator.get_harmonic_mixing_info(open_key)

print("\nNext track suggestions:")
print(f"Perfect match: {mixing_info['perfect_matches']}")
print(f"Energy up: {mixing_info['energy_up']}")
print(f"Energy down: {mixing_info['energy_down']}")
print(f"Harmonic: {mixing_info['harmonic_matches']}")

# Get suggested progression
next_keys = translator.suggest_key_progression(open_key, "up")
print(f"\nSuggested progression: {' → '.join(next_keys)}")

# Get Camelot color for UI
color = translator.get_camelot_color(open_key)
print(f"Camelot color: {color}")
```

---

### Playlist Statistics Example

```python
from utils.playlist import PlaylistManager

# Get statistics for a playlist
stats = PlaylistManager.get_playlist_statistics(playlist)

print(f"Playlist: {playlist.name}")
print(f"Tracks: {stats['track_count']}")
print(f"Duration: {stats['total_duration_formatted']}")
print(f"Average BPM: {stats['average_bpm']:.1f}")
print(f"BPM Range: {stats['bpm_range'][0]:.0f} - {stats['bpm_range'][1]:.0f}")
print(f"Artists: {stats['artist_count']}")
print(f"Average Rating: {stats['average_rating']:.1f}/5")

print("\nKey Distribution:")
for key, count in sorted(stats['key_distribution'].items()):
    print(f"  {key}: {count} tracks")

print("\nGenre Distribution:")
for genre, count in sorted(stats['genre_distribution'].items(),
                           key=lambda x: x[1], reverse=True)[:5]:
    print(f"  {genre}: {count} tracks")
```

---

### XML Export Example

```python
from pathlib import Path
from parser.bsm_nml_parser import create_traktor_parser
from exporter.bsm_xml_exporter import RekordboxXMLExporter
from utils.playlist import PlaylistManager

# Parse NML
parser = create_traktor_parser("/path/to/collection.nml")
parser.parse_xml()
structure = parser.get_playlists_with_structure()
all_tracks = PlaylistManager.collect_all_tracks(structure)

# Export to XML
exporter = RekordboxXMLExporter()
xml_content = exporter.export_collection(
    tracks=all_tracks,
    playlist_structure=structure,
    output_path=Path("rekordbox.xml")
)

print(f"Generated XML: {len(xml_content)} bytes")
```

---

### M3U Export Example

```python
from parser.bsm_nml_parser import create_traktor_parser
from exporter.bsm_m3u_exporter import M3UExporter

# Parse NML
parser = create_traktor_parser("/path/to/collection.nml")
parser.parse_xml()
structure = parser.get_playlists_with_structure()

# Export to M3U
exporter = M3UExporter(output_path="/output/playlists")
count = exporter.export_playlists(
    playlist_structure=structure,
    relative_paths=True,
    copy_music=False
)

print(f"Exported {count} M3U playlists")
```

---

Documentation version 2.0 - November 2025

**Made with ❤️ by Benoit (BSM) Saint-Moulin**
