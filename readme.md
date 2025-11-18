# Traktor Bridge 2.0

## Introduction

**Professional Traktor to Pioneer CDJ Hardware Converter**

Convert Native Instruments Traktor playlists to Pioneer CDJ hardware and Rekordbox formats with complete metadata preservation including cue points, loops, BPM, musical keys, and artwork. Now with native CDJ-2000NXS2 hardware support.

Traktor Bridge 2.0 is a professional-grade application designed for DJs who want to seamlessly migrate their Traktor collections to Pioneer hardware and Rekordbox software. With complete metadata preservation and native CDJ hardware support, it's the ultimate conversion tool for professional DJs.

## Sources and Attribution

### Author
**Benoit (BSM) Saint-Moulin**
* **Website**: www.benoitsaintmoulin.com
* **Developer Portfolio**: www.bsm3d.com
* **GitHub**: [github.com/bsm3d](https://github.com/bsm3d)
* **Instagram**: [@benoitsaintmoulin](https://www.instagram.com/benoitsaintmoulin)

## Table of Contents

- [Quick Start](#quick-start)
- [Key Features](#key-features)
- [Export Formats](#export-formats)
- [Installation](#installation)
- [Usage](#usage)
- [Hardware Compatibility](#hardware-compatibility)
- [Supported Formats](#supported-formats)
- [Cue Point Translation](#cue-point-translation)
- [Technical Architecture](#technical-architecture)
- [Configuration Options](#configuration-options)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Troubleshooting](#troubleshooting)
- [Version 2.0 Improvements](#version-20-improvements)
- [License & Usage](#license--usage)
- [Disclaimers & Warranty](#disclaimers--warranty)

---

![Traktor Bridge Interface](https://github.com/user-attachments/assets/ce3ff950-ebd8-4253-8eaa-ef45e089640a)

## Quick Start

1. **Download** Traktor Bridge 2.0
2. **Install dependencies**: `pip install -r requirements.txt`
3. **Run**: `python main.py`

## Key Features

- **Native CDJ hardware support** - Direct CDJ-2000NXS2 binary export with PDB DeviceSQL
- **ANLZ waveform generation** - Creates .DAT/.EXT files for CDJ display
- **Complete metadata preservation** - Artist, title, BPM, musical key, cue points, artwork
- **Multiple export formats** - CDJ hardware, Rekordbox software, XML, M3U playlists
- **Smart file management** - Automatic file location detection and path sanitization
- **Audio preview** - Built-in player with timeline visualization
- **Batch processing** - Convert multiple playlists simultaneously
- **Cross-platform** - Windows, macOS, Linux support

## Export Formats

### CDJ/USB
Native Pioneer CDJ hardware format with binary PDB DeviceSQL database. Creates complete folder structure with ANLZ waveforms for direct CDJ-2000NXS2 USB transfer.

### Rekordbox Database
SQLite/SQLCipher database compatible with Rekordbox software for import via preferences.

### Rekordbox XML
Standard XML format compatible with Rekordbox software import and other DJ applications.

### M3U Playlists
Universal playlist format compatible with most DJ software and media players.

## Installation

**Requirements**: Python 3.13+

```bash
# Core dependencies
pip install PySide6 pygame tinytag pillow mutagen

# Or install from requirements
pip install -r requirements.txt
```

## Usage

### GUI Mode
```bash
python main.py
```

1. Select Traktor NML file (usually in `Documents/Native Instruments/Traktor Pro 3/collection.nml`)
2. Optional: Set music root folder for relocated files
3. Choose playlists/folders to convert
4. Select export format (CDJ/USB recommended for hardware)
5. Configure CDJ model and options
6. Convert to destination (USB drive for CDJs)

### CDJ Hardware Requirements

**USB Format**: FAT32 (MBR partition table)  
**File Limits**: ASCII-only filenames, 256 character path maximum  
**Capacity**: Maximum ~10,000 tracks supported by CDJ hardware  
**Structure**: Automatic `/PIONEER/USBANLZ/` folder creation

## Hardware Compatibility

**CDJ Players**: CDJ-2000NXS2 (primary), CDJ-2000, CDJ-3000  
**XDJ Players**: XDJ-1000MK2  
**Software**: Rekordbox 6/7, Serato DJ, VirtualDJ, djay Pro

## Supported Formats

**Audio**: MP3, WAV, FLAC, AIFF, M4A, OGG  
**Artwork**: JPEG, PNG, GIF, WebP

## Cue Point Translation

| Traktor | Rekordbox/CDJ | Notes |
|---------|---------------|-------|
| Hot Cue | Hot Cue | Numbered 1-8 |
| Load Cue | Memory Cue | Navigation markers |
| Loop | Loop | Auto-repeat sections |
| Grid Marker | Beat Grid | BPM sync points |

## Technical Architecture

### Modular Export System
- **CDJ PDB Exporter** - Native binary DeviceSQL generation
- **ANLZ Generator** - Waveform files for CDJ display
- **Rekordbox Exporter** - SQLite/SQLCipher database creation
- **XML Exporter** - Standard Rekordbox XML format
- **M3U Exporter** - Universal playlist generation

### Performance Optimization
- **Smart caching** - 30K track limit with 100MB memory management
- **Background processing** - Non-blocking UI with progress tracking  
- **Resource management** - Automatic cleanup and memory optimization
- **Error recovery** - Comprehensive validation and fallback mechanisms

## Configuration Options

**Export Settings**: Format selection, key notation system, file copy options  
**CDJ Settings**: Target CDJ model, ANLZ generation, Rekordbox version  
**Application**: Startup behavior, performance tuning, logging level

## Keyboard Shortcuts

- **Ctrl+O** - Open NML file
- **Ctrl+R** - Reload collection
- **Ctrl+,** - Open preferences
- **F1** - Show usage guide
- **P** - Play/pause selected track

## Troubleshooting

**NML Parse Error**: Close Traktor before conversion  
**CDJ Not Recognizing USB**: Ensure FAT32 format and proper folder structure  
**Files Not Found**: Set music root folder for relocated files  
**Missing Dependencies**: Run `pip install -r requirements.txt`  
**Audio Issues**: Check system audio settings, restart application

## Version 2.0 Improvements

**CDJ Hardware Support**: Native PDB DeviceSQL export replacing SQLite compatibility layer  
**ANLZ Waveforms**: Full .DAT/.EXT generation for CDJ display compatibility  
**Enhanced UI**: CDJ-focused workflow with hardware-specific options  
**Modular Architecture**: Separate exporters for each format with improved maintainability  
**Performance**: Optimized memory usage and faster conversion processing

## License & Usage

**Open Source Project** - Free for educational and personal use

**Authorized**: Educational use within academic framework, personal modification and use, citation with appropriate author attribution  
**Restricted**: Commercial use requires prior authorization from the author, redistribution must maintain original copyright notice

**Contact**: GitHub repository for authorization requests

## Disclaimers & Warranty

**Trademarks**: Pioneer DJ, Rekordbox, CDJ, XDJ are trademarks of Pioneer DJ Corporation. Native Instruments, Traktor are trademarks of Native Instruments GmbH. All trademarks are property of their respective owners.

**No Warranty**: Software provided "AS IS" without warranty of any kind, express or implied, including warranties of merchantability, fitness for purpose, and non-infringement. Author not liable for any damages arising from software use.

**No Affiliation**: Independent tool, not affiliated with, endorsed by, or sponsored by Pioneer DJ Corporation or Native Instruments GmbH. Provided for interoperability and educational purposes only.

**User Responsibility**: Users responsible for data backup before conversion and verifying hardware/software compatibility. Always test CDJ exports on target hardware before live performance use.

**Special thanks** to the Deep Symmetry community and all library maintainers who make tools like this possible.

---

Documentation version 2.0 - November 2025

**Made with ❤️ by Benoit (BSM) Saint-Moulin**
