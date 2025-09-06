# Traktor Bridge

**Author**: Benoit (BSM) Saint-Moulin  
**Website**: [benoitsaintmoulin.com](http://www.benoitsaintmoulin.com)

**Professional Traktor to Pioneer CDJ/XML Converter**

<img width="1310" height="573" alt="traktor_bridge_logo" src="https://github.com/user-attachments/assets/358bd3e6-929d-44c0-b7c8-ccbbc2e4f602" />


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

<img width="968" height="620" alt="traktor_bridge_view_cue" src="https://github.com/user-attachments/assets/4f953826-745b-41c3-8733-a27f10784140" />


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

**Contact**: GitHub repository for authorization requests

## Disclaimers & Warranty

**Trademarks**: Pioneer DJ, Rekordbox, CDJ, XDJ are trademarks of Pioneer DJ Corporation. Native Instruments, Traktor are trademarks of Native Instruments GmbH. All trademarks are property of their respective owners.

**No Warranty**: Software provided "AS IS" without warranty of any kind, express or implied, including warranties of merchantability, fitness for purpose, and non-infringement. Author not liable for any damages arising from software use.

**No Affiliation**: Independent tool, not affiliated with, endorsed by, or sponsored by Pioneer DJ Corporation or Native Instruments GmbH. Provided for interoperability and educational purposes only.

**User Responsibility**: Users responsible for data backup before conversion and verifying hardware/software compatibility.

**Special thanks** to all the library maintainers and contributors who make tools like this possible.

---

**Made with ❤️ by Benoit (BSM) Saint-Moulin**
