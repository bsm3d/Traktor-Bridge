# Traktor Bridge - Traktor to Pioneer CDJ/XML Converter

## Author

**Benoit (BSM) Saint-Moulin**  
- **Website**: [www.benoitsaintmoulin.com](https://www.benoitsaintmoulin.com)  
- **GitHub**: [github.com/bsm3d](https://github.com/bsm3d)  

## Overview

Traktor Bridge is a funny application from an Hidden Coder Cave Runner that converts Native Instruments Traktor collections (NML format) into Pioneer DJ compatible formats. The software supports both CDJ database exports (.pdb files) and Rekordbox XML exports, enabling seamless migration between DJ platforms while preserving all metadata, cue points, beat grids, and playlist structures.

## Key Features

### Core Functionality
- **NML Parser**: Complete Traktor collection parsing with robust error handling
- **Dual Export Formats**: CDJ database (.pdb) and Rekordbox XML export
- **Metadata Preservation**: Artist, title, BPM, musical key, cue points, and beat grids
- **Playlist Structure**: Maintains folder hierarchy and playlist organization
- **Smart File Discovery**: Intelligent cache system for relocated music files

### Advanced Features
- **Audio Preview**: Built-in audio playback with pygame integration
- **Artwork Extraction**: Album art preservation using TinyTag and mutagen
- **Cue Point Timeline**: Visual cue point editor with timeline visualization
- **Key Translation**: Camelot/Open Key and classical notation support
- **File Verification**: Optional integrity checking during music file copying

### Professional Tools
- **Batch Processing**: Handles large collections (30,000+ tracks)
- **Progress Tracking**: Real-time conversion progress with detailed logging
- **Error Recovery**: Robust error handling with detailed reporting
- **Configuration Management**: Persistent settings and project state

## System Requirements

### Minimum Requirements
- **Python**: 3.8 or higher
- **RAM**: 4GB (8GB recommended for large collections)
- **Storage**: 500MB free space + export destination space
- **Audio**: Sound card for preview playback (optional)

### Recommended Specifications
- **Python**: 3.10+ for optimal performance
- **RAM**: 16GB for professional collections (10,000+ tracks)
- **CPU**: Multi-core processor for large file operations
- **Storage**: SSD for improved file processing speed

## Dependencies

### Core Dependencies (Required)
```
PySide6>=6.5.0          # Modern Qt6-based GUI framework
pygame>=2.5.0           # Audio playback and processing
tinytag>=1.10.0         # Audio metadata and artwork extraction
mutagen>=1.47.0         # Enhanced audio format support
Pillow>=10.0.0          # Image processing for artwork
```

### Installation
```bash
# Clone or download the source code
git clone https://github.com/bsm3d/traktor-bridge.git
cd traktor-bridge

# Install dependencies
pip install -r requirements.txt

# Run the application
python Traktor_bridge.py
```

## Application Architecture

### Core Components

#### Data Models
- **Track**: Complete track metadata container
- **Node**: Hierarchical playlist/folder structure
- **CueType**: Enumeration for cue point types (Grid, Hot Cue, Load, Loop, etc.)

#### Manager Classes
- **AudioMgr**: Thread-safe audio playback management
- **Cache**: Intelligent file caching with memory management
- **DBMgr**: Database operations with retry logic
- **ArtworkMgr**: Secure artwork validation and storage

## Platform-Specific Installation

### Windows
```cmd
# Install Python 3.8+ from python.org
python -m pip install --upgrade pip
pip install PySide6 pygame tinytag mutagen Pillow

# Run application
python Traktor_bridge.py
```

### macOS
```bash
# Install via Homebrew (recommended)
brew install python@3.10
pip3 install PySide6 pygame tinytag mutagen Pillow

# Run application
python3 Traktor_bridge.py
```

## Feature Availability

| Feature | Core Requirement | Optional Enhancement | Notes |
|---------|------------------|---------------------|--------|
| NML Parsing | xml.etree.ElementTree | - | Built-in Python |
| GUI Interface | PySide6 | - | Modern Qt6 framework |
| Audio Preview | pygame | - | Requires audio drivers |
| Metadata Extraction | tinytag, mutagen | - | Dual library support |
| Artwork Processing | Pillow | - | Image validation |
| Database Export | sqlite3 | - | Built-in Python |
| XML Export | xml.etree.ElementTree | - | Built-in Python |
| File Caching | Built-in | - | Memory-optimized |

## Configuration and Usage

### Application Configuration
Settings are automatically saved to `converter_config.json`:
```json
{
  "nml_path": "/path/to/collection.nml",
  "music_root_path": "/path/to/music/folder",
  "output_path": "/path/to/export/destination",
  "copy_music": true,
  "verify_copy": false,
  "key_format": "Open Key",
  "export_format": "Database"
}
```

### Workflow Steps
1. **Select NML File**: Choose your Traktor collection.nml file
2. **Set Music Root** (Optional): Help locate moved music files
3. **Choose Playlists**: Select playlists/folders to export
4. **Configure Options**: Copy music files, verification, export format
5. **Export**: Choose destination and start conversion

### Advanced Options
- **Copy Music Files**: Include audio files in export
- **Verify Integrity**: Check file integrity after copying
- **Export Format**: Database (.pdb) for CDJs, XML for software
- **Key Format**: Open Key (Camelot) or Classical notation

## GUI Components

### Main Interface
- **File Input Sections**: NML file and music root selection
- **Playlist Tree**: Hierarchical view with multi-selection
- **Options Panel**: Export format and file handling options
- **Progress System**: Real-time progress with detailed logging
- **Audio Controls**: Preview playback with play/pause functionality

### Detail Windows
- **Track Details**: Comprehensive track information table
- **Timeline Dialog**: Visual cue point editor with waveform simulation
- **Log Viewer**: Detailed operation logging and error reporting

### Keyboard Shortcuts
- **P**: Play/Pause selected track in detail view
- **Double-click**: Open cue point timeline for track
- **Multi-select**: Ctrl/Cmd+click for multiple playlist selection

## Troubleshooting

### Common Issues

#### Audio Playback Problems
```bash
# Windows: Ensure audio drivers are installed
# macOS: No additional setup required
```

#### Large Collection Performance
```python
# Adjust cache settings for better performance
MAX_CACHE_SIZE = 50000        # Increase for more files
MAX_CACHE_MEMORY_MB = 200     # Increase memory limit
BATCH_SIZE = 50               # Reduce for lower memory usage
```

#### File Path Issues
- Use music root folder for relocated files
- Ensure proper file permissions
- Check for special characters in paths

### Log File Analysis
Application logs are saved to `traktor_bridge.log`:
```
2025-09-06 15:30:15,123 - INFO - Starting Traktor Bridge v1.1
2025-09-06 15:30:16,456 - INFO - Loading NML file: /path/to/collection.nml
2025-09-06 15:30:17,789 - WARNING - File not found: /old/path/track.mp3
2025-09-06 15:30:18,012 - INFO - Found cached file: /new/path/track.mp3
```

## Performance Optimization

### Memory Management
```python
# For collections over 10,000 tracks:
- Use music root folder for file discovery
- Enable progress tracking for monitoring
- Process in smaller batches if memory constrained
- Close detail windows when not needed
```

### File Processing
```python
# Optimize for SSD storage:
- Place cache on fastest drive
- Use verify copy only when necessary
- Process during off-peak disk usage
```

## Export Formats

### Pioneer CDJ Database (.pdb)
- **Target**: CDJ-2000, CDJ-3000, XDJ series
- **Structure**: SQLite database with Pioneer schema
- **Features**: Full metadata, cue points, beat grids, artwork
- **Compatibility**: Direct USB loading on CDJ hardware

### Rekordbox XML
- **Target**: Rekordbox software, other DJ applications
- **Structure**: XML with DJ_PLAYLISTS format
- **Features**: Cross-platform playlist exchange
- **Compatibility**: Import into various DJ software

## Pioneer Hardware Compatibility

| CDJ Model | Database Support | Features Available |
|-----------|------------------|-------------------|
| CDJ-2000 | Full | Basic metadata, cue points |
| CDJ-2000NXS | Full | Enhanced cue points, beat sync |
| CDJ-2000NXS2 | Full | Color displays, advanced features |
| CDJ-3000 | Full | Complete feature set |
| XDJ-1000MK2 | Full | Software-based features |

## Development and Customization

### Code Structure
```
Traktor_bridge.py
├── Configuration (Config class)
├── Data Models (Track, Node, CueType)
├── Utility Classes (PathValidator, KeyXlat, StyleMgr)
├── Manager Classes (AudioMgr, Cache, DBMgr, ArtworkMgr)
├── Export Modules (XMLExporter, NMLParser, CDJExporter)
├── GUI Components (Dialogs, Windows, Main Interface)
└── Application Entry Point
```

### Extending Functionality
```python
# Custom cue point types
class CustomCueType(Enum):
    INTRO, OUTRO, BREAKDOWN = range(7, 10)

# Additional export formats
class NewExporter:
    def export_to_format(self, structure, output_path):
        # Custom export implementation
        pass
```

## Legal and Technical Information

### Dependencies Licenses
- **PySide6**: LGPL/Commercial (Qt6 framework)
- **pygame**: LGPL (multimedia library)
- **tinytag**: MIT License (audio metadata)
- **mutagen**: GPL v2+ (audio format support)
- **Pillow**: PIL Software License (image processing)

### Data Processing
- No data is transmitted over networks
- All processing occurs locally
- Original files remain unmodified
- Export data follows Pioneer specifications

### Reverse Engineering Notice
This software interoperates with proprietary formats through legal reverse engineering for compatibility purposes. No official specifications exist for these formats from Pioneer DJ or Native Instruments.

## Support and Community

### Getting Help
1. **Check Documentation**: Review this README and inline help
2. **Examine Logs**: Check `traktor_bridge.log` for detailed error information
3. **Test Configuration**: Verify file paths and permissions
4. **Community Forums**: DJ software communities and GitHub discussions

### Reporting Issues
Include the following information:
- Operating system and version
- Python version (`python --version`)
- Traktor version and NML file size
- Complete error message from log file
- Steps to reproduce the issue

### Contributing
- Code improvements and bug fixes welcome
- Test with different Traktor versions
- Validate Pioneer hardware compatibility
- Documentation enhancements appreciated

## Warranty Disclaimer

**NO WARRANTY**: This software is provided "as is" without warranty of any kind, either express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose and non-infringement. In no event shall the authors be liable for any claim, damages or other liability arising from the use of this software.

**USER RESPONSIBILITY**: Users are responsible for backing up their data before conversion and verifying compatibility with their specific hardware and software configurations.

**LEGAL COMPLIANCE**: This software is provided for educational and interoperability purposes. Users must ensure compliance with all applicable laws and licenses in their jurisdiction.

---

*Application Version: 1.1*  
*Documentation Updated: September 2025*  
*Author: Benoit (BSM) Saint-Moulin*
