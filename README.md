# Traktor Bridge

**Professional Traktor to Pioneer CDJ database, XML, M3U Converter and USB Transfert**

Convert your Native Instruments Traktor playlists to Pioneer Rekordbox format with full metadata preservation including cue points, loops, BPM, musical keys, and artwork.

<img width="877" height="851" alt="traktor_brige_interface" src="https://github.com/user-attachments/assets/726e87a7-3e3b-4c46-84b0-1cbbb4ed7fad" />


## If you have a brain you can use it :)

**Install like 1,2,3:**

1. **Download** `Traktor_bridge.py`
2. **Install** PIP dependencies: `pip install PySide6 pygame tinytag pillow mutagen`
3. **Open** Command Line and write: `python ./traktor_bridge.py`

---

## Table of Contents

- [Author](#author)
- [Overview](#overview)
- [Key Features](#key-features)
- [Export Formats](#export-formats)
- [Screenshots](#screenshots)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Required Dependencies](#required-dependencies)
  - [Optional Dependencies](#optional-dependencies-enhanced-features)
  - [Installation Steps](#installation-steps)
  - [Alternative Installation Methods](#alternative-installation-methods)
- [Usage Guide](#usage-guide)
  - [Basic Workflow](#basic-workflow)
  - [Advanced Features](#advanced-features)
  - [Keyboard Shortcuts](#keyboard-shortcuts)
- [Configuration](#configuration)
- [Use Cases](#use-cases)
  - [CDJ Performance Setup](#1-cdj-performance-setup)
  - [Software Migration](#2-software-migration)
  - [Backup and Archive](#3-backup-and-archive)
  - [Collaborative DJ Projects](#4-collaborative-dj-projects)
  - [Mobile DJ Services](#5-mobile-dj-services)
- [Technical Details](#technical-details)
  - [Supported Audio Formats](#supported-audio-formats)
  - [Cue Point Translation](#cue-point-translation)
  - [Musical Key Translation](#musical-key-translation)
  - [Database Structure](#database-structure)
- [Troubleshooting](#troubleshooting)
  - [Common Issues](#common-issues)
  - [Performance Optimization](#performance-optimization)
- [Contributing](#contributing)
- [License](#license)
- [Changelog](#changelog)
- [Support](#support)
- [Dependencies and Credits](#dependencies-and-credits)

---

## Author

**Benoit (BSM) Saint-Moulin**  
Website: [www.benoitsaintmoulin.com](http://www.benoitsaintmoulin.com)

## Overview

Traktor Bridge is a professional-grade application that converts Native Instruments Traktor collections (.nml files) to Pioneer Rekordbox format. Originally developed as a command-line tool (CLI) - a vestige from my Amiga CLI heritage - it has been refactored to include a modern graphical interface while preserving CLI usage for advanced users.

**Design Philosophy**: The code is clean but not perfect; certain areas could be optimized. The monolithic code structure is intentional to facilitate usage by non-programmers who prefer a single-file solution.

The application supports both database (.pdb) and XML export formats, making it compatible with Pioneer CDJ players and various DJ software that accept Rekordbox libraries.

### Key Features

- **Complete Metadata Preservation**: Artist, title, album, genre, BPM, musical key, comments, and artwork
- **Cue Point Translation**: Hot cues, memory cues, loops, and beat grids
- **Dual Export Formats**: Database (.pdb) for CDJs or XML for DJ software compatibility
- **Smart File Management**: Automatic file location detection with music root folder support
- **Audio Preview**: Built-in audio player for track verification
- **Advanced Cue Timeline**: Visual cue point editor with filtering and export capabilities
- **Batch Processing**: Convert multiple playlists and folder structures simultaneously
- **Memory Optimized**: Efficient caching system for large collections
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **CLI Support**: Original command-line interface preserved for batch operations

### Export Formats

#### Database Format (.pdb)
- Creates Pioneer-compatible SQLite database
- Includes full folder structure: `PIONEER/`, `CONTENTS/`, `ARTWORK/`
- Direct USB transfer to CDJ players
- Preserves all metadata including artwork and cue points

#### XML Format (.xml)
- Rekordbox XML format for software compatibility
- Compatible with Serato, VirtualDJ, and other DJ software
- Lightweight alternative to database format
- Maintains playlist structure and track metadata

<img width="1517" height="785" alt="traktor_bridge_view_detail" src="https://github.com/user-attachments/assets/fe23f343-3932-4b87-bfa5-1516f67d9bde" />

### Main Interface
The intuitive interface guides you through the conversion process:

1. **File Selection**: Choose your Traktor .nml file and optional music root folder
2. **Playlist Selection**: Browse and select playlists/folders with visual icons
3. **Export Options**: Choose format, file copying, and verification settings
4. **Progress Monitoring**: Real-time conversion progress with detailed logging

### Track Details Window
- **Sortable Track Listing**: Sort by any column (artist, title, BPM, key, etc.)
- **Audio Playback**: Play/pause tracks with keyboard shortcuts (P key)
- **Key Format Selection**: Toggle between Open Key and Classical notation
- **Search Functionality**: Filter tracks by artist, title, or album

<img width="976" height="663" alt="traktor_bridge_view_cue" src="https://github.com/user-attachments/assets/6cf0ba84-330c-4555-941e-31cb33baba4f" />

### Cue Point Timeline
- **Visual Timeline**: Graphical representation of track structure with waveform simulation
- **Interactive Filters**: Toggle display of hot cues, memory cues, loops, and grid anchors
- **Detailed Information**: Complete cue point statistics and timing information
- **Export to Clipboard**: Copy cue point data for external use

## Installation

### Prerequisites

**Python 3.8 or higher** is required.

### Required Dependencies

```bash
pip install PySide6 pygame tinytag pillow
```

### Optional Dependencies (Enhanced Features)

```bash
pip install mutagen
```

**Note**: `mutagen` provides enhanced metadata extraction capabilities for certain audio formats.

### Installation Steps

1. **Clone the Repository or Download**
   ```bash
   git clone https://github.com/yourusername/traktor-bridge.git
   cd traktor-bridge
   ```
   
   Or simply download `Traktor_bridge.py` directly.

2. **Install Dependencies**
   ```bash
   pip install PySide6 pygame tinytag pillow mutagen
   ```

3. **Run the Application**
   ```bash
   python Traktor_bridge.py
   ```

### Alternative Installation Methods

#### Using Virtual Environment (Recommended)
```bash
python -m venv traktor_bridge_env
source traktor_bridge_env/bin/activate  # On Windows: traktor_bridge_env\Scripts\activate
pip install PySide6 pygame tinytag pillow mutagen
python Traktor_bridge.py
```

#### Command Line Usage (CLI Mode)
For batch processing or automation, the original CLI interface is preserved:
```bash
python Traktor_bridge.py --help
```

## Usage Guide

### Basic Workflow

1. **Launch Traktor Bridge**
   ```bash
   python Traktor_bridge.py
   ```

2. **Select Your Traktor NML File**
   - Click "Browse..." next to "Traktor NML File"
   - Navigate to your Traktor collection file (usually in `Documents/Native Instruments/Traktor X.X.X/`)
   - The file is typically named `collection.nml`

3. **Optional: Set Music Root Folder**
   - If your music files have been moved, select the root folder containing your music
   - This enables smart file location detection

4. **Choose Playlists**
   - Browse the loaded playlist structure
   - Select individual playlists or entire folders
   - Use Ctrl+Click (Cmd+Click on Mac) for multiple selections

5. **Configure Export Options**
   - **Export Format**: Choose Database (CDJ) or XML (software)
   - **Copy Music Files**: Include audio files in export
   - **Verify File Integrity**: Ensure copied files are intact

6. **Convert**
   - Click "CONVERT"
   - Choose your destination folder (USB drive for CDJs)
   - Monitor progress in real-time

### Advanced Features

#### Track Details and Playback
- **View Details**: Select playlist and click "View Details"
- **Audio Preview**: Click ▶ buttons or press P to play/pause
- **Sort Tracks**: Click column headers to sort by any criteria
- **Search**: Use the search box to filter tracks

#### Cue Point Analysis
- **Timeline View**: Double-click "Cues Detail" column
- **Filter Cues**: Toggle hot cues, memory cues, loops, and grid anchors
- **Export Data**: Copy cue information to clipboard

#### Batch Processing
- Select multiple playlists and folders simultaneously
- The converter maintains folder hierarchy in the output
- Progress tracking shows individual file operations

#### Command Line Interface
The original CLI is preserved for automation:
```bash
python Traktor_bridge.py --nml collection.nml --output /path/to/usb --format database
```

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **P** | Play/Pause selected track (in Details window) |
| **Ctrl+A** | Select all playlists |
| **F3** | Focus search box |
| **Escape** | Clear selection |

## Configuration

Traktor Bridge automatically saves your preferences:

- Last used NML file path
- Music root folder location
- Export format preference
- File copying options

Configuration is stored in `converter_config.json` in the application directory.

## Use Cases

### 1. CDJ Performance Setup
**Scenario**: DJ preparing for a club performance with Pioneer CDJ setup

**Process**:
1. Load Traktor collection with organized performance playlists
2. Select specific event playlists
3. Export as Database format with music files
4. Copy to USB drive for CDJ compatibility

**Benefits**: Maintains all cue points, loops, and BPM information on CDJs

### 2. Software Migration
**Scenario**: Switching from Traktor to Serato/VirtualDJ

**Process**:
1. Export entire Traktor collection as XML format
2. Import XML file into new DJ software
3. All playlists and metadata transfer seamlessly

**Benefits**: No loss of years of cue point and playlist organization work

### 3. Backup and Archive
**Scenario**: Creating portable backups of DJ collection

**Process**:
1. Regular exports of updated playlists
2. Include music files for complete portability
3. Store on external drives for backup

**Benefits**: Complete collection portability and protection

### 4. Collaborative DJ Projects
**Scenario**: Sharing specific playlists with other DJs

**Process**:
1. Export selected collaborative playlists
2. Share USB drive or files with partner DJs
3. Partners can import to their preferred DJ software

**Benefits**: Cross-platform collaboration regardless of DJ software choice

### 5. Mobile DJ Services
**Scenario**: Professional DJ with multiple venue setups

**Process**:
1. Maintain master collection in Traktor
2. Create venue-specific playlist exports
3. Generate CDJ-compatible USB drives for each event

**Benefits**: Consistent performance setup across different equipment

## Technical Details

### Supported Audio Formats
- MP3
- WAV  
- FLAC
- AIFF
- M4A
- OGG

### Cue Point Translation

| Traktor Type | Rekordbox Equivalent | Notes |
|--------------|---------------------|-------|
| Hot Cue | Hot Cue | Numbered cues (1-8) |
| Memory Cue | Memory Cue | Navigation markers |
| Loop | Loop | Auto-repeating sections |
| Grid Marker | Beat Grid | BPM synchronization |

### Musical Key Translation
- **Open Key**: Camelot wheel notation (1A, 2B, etc.)
- **Classical**: Traditional notation (Am, C, etc.)

### Database Structure
The exported database follows Pioneer's official schema:
- `djmdContent`: Track metadata
- `djmdPlaylist`: Playlist structure  
- `djmdSongPlaylist`: Track-playlist relationships
- `djmdCue`: Cue point data
- `djmdBeatGrid`: Beat grid information
- `djmdArtwork`: Album artwork

## Troubleshooting

### Common Issues

#### "NML Parse Error"
**Cause**: Corrupted or unsupported NML file format  
**Solution**: 
- Ensure Traktor is closed when accessing the NML file
- Try exporting a fresh collection from Traktor
- Check file isn't corrupted

#### "File Not Found" During Conversion
**Cause**: Music files moved since last Traktor scan  
**Solution**:
- Set the Music Root Folder to your current music location
- The smart cache will locate moved files automatically

#### "Missing Dependencies" Error
**Cause**: Required Python packages not installed  
**Solution**:
```bash
pip install PySide6 pygame tinytag pillow mutagen
```

#### Audio Preview Not Working
**Cause**: Audio system conflicts or missing codecs  
**Solution**:
- Restart the application
- Check system audio settings
- Install additional audio codecs if needed

### Performance Optimization

#### Large Collections (>10,000 tracks)
- Use Music Root Folder for faster file location
- Process playlists in smaller batches
- Ensure sufficient RAM (4GB+ recommended)

#### Network Storage
- Copy NML file locally before processing
- Map network drives persistently
- Use wired connections for better stability

## Contributing

Contributions are welcome! Please read our contributing guidelines:

1. **Fork the Repository**
2. **Create Feature Branch**: `git checkout -b feature/amazing-feature`
3. **Commit Changes**: `git commit -m 'Add amazing feature'`
4. **Push to Branch**: `git push origin feature/amazing-feature`
5. **Open Pull Request**

### Development Setup

```bash
git clone https://github.com/yourusername/traktor-bridge.git
cd traktor-bridge
python -m venv dev_env
source dev_env/bin/activate  # On Windows: dev_env\Scripts\activate
pip install PySide6 pygame tinytag pillow mutagen
```

### Code Style
- Follow PEP 8 guidelines
- Use type hints where possible
- Add docstrings for public functions
- Include unit tests for new features

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

### Version 1.1 (Current)
- Enhanced PySide6 GUI with modern styling
- Advanced cue point timeline visualization
- Smart file caching system
- XML export format support
- Improved error handling and logging
- Audio preview with playback controls
- Memory-optimized processing for large collections
- Preserved CLI interface for batch operations

### Version 1.0
- Initial release
- Basic NML to database conversion
- Playlist structure preservation
- Cue point translation
- Command-line interface

## Support
Site : https://www.benoitsaintmoulin.com/traktor_bridge/

- **Discussions**: [GitHub Discussions](https://github.com/yourusername/traktor-bridge/discussions)
- **Web**: [Traktor Bridge web site](https://www.benoitsaintmoulin.com/traktor_bridge/)
- **Email**: Contact via [www.benoitsaintmoulin.com](http://www.benoitsaintmoulin.com)

## Dependencies and Credits

This application relies on excellent open-source libraries:

### Required Dependencies
- **[PySide6](https://pypi.org/project/PySide6/)** - Qt for Python GUI framework by The Qt Company
- **[pygame](https://pypi.org/project/pygame/)** - Multimedia library for audio playback by Pete Shinners and pygame community  
- **[tinytag](https://pypi.org/project/tinytag/)** - Audio metadata extraction library by Tom Wallroth (devsnd)
- **[Pillow](https://pypi.org/project/Pillow/)** - Python Imaging Library fork by Jeffrey A. Clark (Alex) and contributors

### Optional Dependencies
- **[mutagen](https://pypi.org/project/mutagen/)** - Audio metadata handling library by Michael Urman, Lukáš Lalinský, and contributors

**Special thanks** to all the library maintainers and contributors who make tools like this possible.

---

**Made with ❤️ by Benoit (BSM) Saint-Moulin**
