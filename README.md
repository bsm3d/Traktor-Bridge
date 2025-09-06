# Traktor Bridge

**Professional Traktor to Pioneer CDJ/XML Converter**

Convert Native Instruments Traktor playlists to Pioneer Rekordbox format with complete metadata preservation including cue points, loops, BPM, musical keys, and artwork.

![Traktor Bridge Interface](https://github.com/user-attachments/assets/ce3ff950-ebd8-4253-8eaa-ef45e089640a)

## Quick Start

1. **Download** `Traktor_bridge_1.1.py`
2. **Install dependencies**: `pip install PySide6 pygame tinytag pillow mutagen`
3. **Run**: `python Traktor_bridge_1.1.py`

## Key Features

- **Complete metadata preservation** - Artist, title, BPM, musical key, cue points, artwork
- **Multiple export formats** - Database (.pdb) for CDJs, XML for DJ software
- **Smart file management** - Automatic file location detection
- **Audio preview** - Built-in player with timeline visualization
- **Batch processing** - Convert multiple playlists simultaneously
- **Cross-platform** - Windows, macOS, Linux support

## Export Formats

### Database (.pdb)
Pioneer-compatible SQLite database for direct CDJ USB transfer. Creates complete folder structure with artwork.

### XML (.xml)
Rekordbox XML format compatible with Serato, VirtualDJ, and other DJ software.

## Installation

**Requirements**: Python 3.8+

```bash
# Required dependencies
pip install PySide6 pygame tinytag pillow

# Optional (enhanced metadata extraction)
pip install mutagen
```

## Usage

### GUI Mode
```bash
python Traktor_bridge_1.1.py
```

1. Select Traktor NML file (usually in `Documents/Native Instruments/Traktor X.X.X/collection.nml`)
2. Optional: Set music root folder for relocated files
3. Choose playlists/folders to convert
4. Select export format and options
5. Convert to destination (USB drive for CDJs)

### CLI Mode
```bash
python Traktor_bridge_1.1.py --help
```

## Hardware Compatibility

**CDJ Players**: CDJ-2000NXS2, CDJ-3000  
**XDJ Players**: XDJ-1000 MK2  
**Software**: Rekordbox (XML compatible), Serato DJ, VirtualDJ, djay Pro

## Supported Formats

**Audio**: MP3, WAV, FLAC, AIFF, M4A, OGG  
**Artwork**: JPEG, PNG, GIF, WebP

## Cue Point Translation

| Traktor | Rekordbox | Notes |
|---------|-----------|-------|
| Hot Cue | Hot Cue | Numbered 1-8 |
| Load Cue | Memory Cue | Navigation markers |
| Loop | Loop | Auto-repeat sections |
| Grid Marker | Beat Grid | BPM sync points |

## Keyboard Shortcuts

- **P** - Play/pause selected track
- **Double-click Cue column** - Open timeline view
- **▶ button** - Play/pause in details window

## Troubleshooting

**NML Parse Error**: Close Traktor before conversion  
**Files Not Found**: Set music root folder for relocated files  
**Missing Dependencies**: Run `pip install PySide6 pygame tinytag pillow mutagen`  
**Audio Issues**: Check system audio settings, restart application

## Technical Details

- **Architecture**: Multithreaded PySide6 GUI with background processing
- **Memory**: Smart caching (30K files, 100MB limit) for large collections
- **Database**: SQLite with Pioneer schema compatibility
- **Security**: Path validation with traversal protection

## License & Usage

**Open Source Project** - Free for educational and personal use

**Authorized**: Educational use, personal modification, citation with attribution  
**Restricted**: Commercial use requires author authorization

## Disclaimers

**Trademarks**: Pioneer DJ, Rekordbox, CDJ, XDJ are trademarks of Pioneer DJ Corporation. Native Instruments, Traktor are trademarks of Native Instruments GmbH.

**Warranty**: Software provided "as is" without warranty. Users responsible for data backup and compatibility verification.

**Affiliation**: Independent tool, not affiliated with Pioneer DJ or Native Instruments.

## Author

**Benoit (BSM) Saint-Moulin**  
Website: [benoitsaintmoulin.com](http://www.benoitsaintmoulin.com)  
Contact: GitHub repository

---

*Bridge your creative workflows - 2 years of development to solve real DJ ecosystem challenges*
