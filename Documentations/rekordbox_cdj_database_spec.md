# Rekordbox CDJ and Database Technical Specification

## Sources and Attribution

### Author
**Benoit Saint-Moulin**  
- **Website**: [www.benoitsaintmoulin.com](https://www.benoitsaintmoulin.com)  
- **GitHub**: [github.com/bsm3d](https://github.com/bsm3d)  

### Primary Research Sources

#### 1. Deep Symmetry Research (Crate Digger Project)
- **Lead Researcher**: James Elliott (brunchboy)
- **Organization**: Deep Symmetry  
- **Repository**: [github.com/Deep-Symmetry/crate-digger](https://github.com/Deep-Symmetry/crate-digger)
- **Contact**: james@deepsymmetry.org
- **Documentation**: [djl-analysis.deepsymmetry.org](https://djl-analysis.deepsymmetry.org/djl-analysis)
- **Description**: Comprehensive Java library for fetching and parsing Rekordbox exports and track analysis files

#### 2. Henry Betts - Binary Format Research
- **Author**: Henry Betts
- **Repository**: [github.com/henrybetts/Rekordbox-Decoding](https://github.com/henrybetts/Rekordbox-Decoding)  
- **Contribution**: Initial reverse engineering of Pioneer .pdb database format
- **Description**: Early analysis of DeviceSQL database structure and encoding

#### 3. Fabian Lesniak - Network Protocol Analysis
- **Author**: Fabian Lesniak
- **Repository**: [github.com/flesniak/python-prodj-link](https://github.com/flesniak/python-prodj-link)
- **Contact**: fabian@lesniak-it.de
- **Contribution**: Python ProDJ Link protocol implementation and network analysis
- **Description**: Real-time CDJ communication protocols and UDP packet structures

#### 4. Jan Holthuis - Rust Implementation
- **Author**: Jan Holthuis (Holzhaus)
- **Repository**: [github.com/Holzhaus/rekordcrate](https://github.com/Holzhaus/rekordcrate)
- **Description**: Rust library for parsing Pioneer Rekordbox device exports
- **Documentation**: [holzhaus.github.io/rekordcrate](https://holzhaus.github.io/rekordcrate/rekordcrate/pdb/index.html)

### Research Methodology
This specification is based on hardware reverse engineering, binary format analysis, collaborative research integration, practical implementation validation, and community testing with professional DJ hardware.

### Important Legal and Technical Disclaimers
**Reverse Engineering Notice**: This specification documents proprietary Pioneer DJ formats through legal reverse engineering for interoperability purposes. No official documentation exists from Pioneer DJ for these internal formats.

**Copyright**: Pioneer DJ, CDJ, DJM, and Rekordbox are trademarks of Pioneer Corporation. This research is independent and not affiliated with Pioneer DJ.


---

## Table of Contents

1. [Introduction](#introduction)
2. [CDJ Hardware Integration](#cdj-hardware-integration)
3. [Database Export Formats](#database-export-formats)
4. [Track Analysis Files](#track-analysis-files)
5. [Network Protocols](#network-protocols)
6. [File System Structure](#file-system-structure)
7. [Data Types and Encoding](#data-types-and-encoding)
8. [Hardware Compatibility](#hardware-compatibility)

## Introduction

The Rekordbox CDJ and Database system encompasses the binary file formats and network protocols used by Pioneer DJ hardware for track playback, metadata access, and real-time performance data exchange. Unlike the XML export format, these systems are optimized for low-power embedded hardware with limited memory and processing capabilities.

This specification builds upon over a decade of community reverse engineering efforts, pioneered by Henry Betts and comprehensively documented by the Deep Symmetry team led by James Elliott. The documented formats enable deep integration between Pioneer DJ hardware and third-party software for lighting control, visualization, and advanced DJ workflows.

### Key Characteristics

- **Architecture**: Binary database format designed for 16-bit devices with 32KB RAM
- **Storage**: Fixed-size pages with heap-based row allocation
- **Networking**: UDP-based protocols for real-time performance data
- **File System**: NFS v2 for media access and file retrieval
- **Encoding**: Mixed little-endian and big-endian depending on component

This specification covers the complete ecosystem used by CDJ-2000, CDJ-3000, DJM mixers, and related Pioneer DJ hardware.

## CDJ Hardware Integration

### Supported Hardware

#### CDJ Players
- **CDJ-2000/2000NXS**: First generation with USB/SD support
- **CDJ-2000NXS2**: Enhanced networking and analysis features
- **CDJ-3000**: Latest generation with advanced waveforms and lighting control
- **CDJ-900**: Entry-level model with limited feature set

#### Mixer Integration
- **DJM-900NXS/2000**: Network-capable mixers
- **DJM-A9/V10**: Professional series with advanced connectivity

### Media Compatibility

#### Storage Media
```
USB Storage:     FAT32/exFAT formatted
SD Cards:        FAT32 formatted (up to 32GB optimal)
File Systems:    NFS v2 server on each player
Mount Points:    /B/ (SD slot), /C/ (USB slot)
```

#### Supported Audio Formats
- **MP3**: MPEG-1 Layer 3 (up to 320 kbps)
- **AAC**: In MP4 container (.m4a)
- **FLAC**: Lossless compression
- **WAV**: Uncompressed PCM
- **AIFF**: Apple format

## Database Export Formats

### Primary Database: export.pdb

The main database file contains track metadata and playlist information:

```
Location: /PIONEER/rekordbox/export.pdb
Format:   DeviceSQL binary database
Endian:   Little-endian
Pages:    Fixed-size blocks (typically 8192 bytes)
```

### Database Structure

#### File Header
```
Offset  Size  Description
0x00    4     Magic bytes (always 0x00000000)
0x04    4     Page size in bytes
0x08    4     Number of table entries
0x0C    4     Next unused page index
0x10    4     Unknown field
0x14    4     Sequence number
0x18    4     Zero padding
0x1C    var   Table pointer entries
```

#### Table Types

| Type | Name | Description |
|------|------|-------------|
| 0 | tracks | Track metadata and file information |
| 1 | genres | Musical genre definitions |
| 2 | artists | Artist name records |
| 3 | albums | Album information |
| 4 | labels | Record label data |
| 5 | keys | Musical key definitions |
| 6 | colors | Color label assignments |
| 7 | playlist_tree | Hierarchical playlist structure |
| 8 | playlist_entries | Track-to-playlist associations |
| 13 | artwork | Album artwork file paths |
| 17 | history_playlists | Performance history playlists |
| 18 | history_entries | History playlist track entries |

### Extended Database: exportExt.pdb

Additional database for extended features:

```
Location: /PIONEER/rekordbox/exportExt.pdb
Tables:   Tags (3), Tag-Track associations (4)
Purpose:  DJ tags and categorization system
```

### Track Row Structure

Track records contain comprehensive metadata:

```c
struct track_row {
    uint16_t  unknown1;           // Usually 0x2400
    uint16_t  index_shift;        // Purpose unknown
    uint32_t  bitmask;            // Bit flags (purpose unknown)
    uint32_t  sample_rate;        // Audio sample rate (Hz)
    uint32_t  composer_id;        // References artist table
    uint32_t  file_size;          // File size in bytes
    uint32_t  unknown2;           // Unknown ID field
    uint16_t  unknown3;           // Always 19048?
    uint16_t  unknown4;           // Always 30967?
    uint32_t  artwork_id;         // References artwork table
    uint32_t  key_id;             // References key table
    uint32_t  original_artist_id; // Original artist for covers
    uint32_t  label_id;           // References label table
    uint32_t  remixer_id;         // References artist table
    uint32_t  bitrate;            // Audio bitrate (kbps)
    uint32_t  track_number;       // Position in album
    uint32_t  tempo;              // BPM * 100
    uint32_t  genre_id;           // References genre table
    uint32_t  album_id;           // References album table
    uint32_t  artist_id;          // References artist table
    uint32_t  id;                 // Unique track identifier
    uint16_t  disc_number;        // Multi-disc albums
    uint16_t  play_count;         // Number of plays
    uint16_t  year;               // Release year
    uint16_t  sample_depth;       // Bits per sample
    uint16_t  duration;           // Track length (seconds)
    uint16_t  unknown5;           // Always 41?
    uint8_t   color_id;           // References color table
    uint8_t   rating;             // 0-5 stars
    uint16_t  unknown6;           // Always 1?
    uint16_t  unknown7;           // Alternating 2/3
    uint16_t  string_offsets[21]; // Pointers to DeviceSQL strings
};
```

### DeviceSQL String Format

Variable-length strings with complex encoding:

#### Short ASCII Strings
```c
struct device_sql_short_ascii {
    uint8_t  length_and_kind;  // Length*2+1 for ASCII
    char     data[length-1];   // String content
};
```

#### Long Strings
```c
struct device_sql_long_string {
    uint8_t  format_flags;     // 0x40=ASCII, 0x90=UTF16LE
    uint16_t length;           // Total field length
    uint8_t  padding;          // Usually zero
    char     data[length-4];   // String content
};
```

## Track Analysis Files

### Analysis File Types

Rekordbox generates three types of analysis files:

#### Primary Analysis (.DAT)
```
Location: /PIONEER/rekordbox/share/ANLZ0001.DAT
Content:  Beat grids, cue points, waveform previews
Target:   All CDJ models
```

#### Extended Analysis (.EXT)
```
Location: /PIONEER/rekordbox/share/ANLZ0001.EXT
Content:  Color waveforms, detailed previews, song structure
Target:   CDJ-2000NXS2 and newer
```

#### Advanced Analysis (.2EX)
```
Location: /PIONEER/rekordbox/share/ANLZ0001.2EX
Content:  3-band waveforms, advanced lighting data
Target:   CDJ-3000 only
```

### Analysis File Structure

#### File Header
```c
struct anlz_header {
    char     magic[4];         // "PMAI"
    uint32_t header_length;    // Header size (usually 0x1C)
    uint32_t file_length;      // Total file size
    uint8_t  unknown[16];      // Padding/unknown data
};
```

#### Tagged Sections

Analysis files contain tagged sections:

```c
struct tagged_section {
    char     fourcc[4];        // Section type identifier
    uint32_t header_length;    // Section header size
    uint32_t total_length;     // Section total size
    uint8_t  data[];           // Section-specific content
};
```

### Section Types

#### Beat Grid (PQTZ)
```c
struct beat_grid_entry {
    uint16_t beat_number;      // 1-4 (position in bar)
    uint16_t tempo;            // BPM * 100
    uint32_t time;             // Time in milliseconds
};
```

#### Cue Points (PCOB/PCO2)
```c
struct cue_entry {
    char     magic[4];         // "PCPT" or "PCP2"
    uint32_t header_length;    // Entry header size
    uint32_t entry_length;     // Total entry size
    uint32_t hot_cue_number;   // 0=memory cue, 1-8=hot cue
    uint32_t status;           // 0=disabled, 1=enabled, 4=active loop
    uint32_t type;             // 1=cue point, 2=loop
    uint32_t time;             // Position in milliseconds
    uint32_t loop_time;        // Loop end time (if applicable)
    // Extended format (PCO2) includes:
    uint32_t comment_length;   // Comment string length
    char     comment[];        // UTF-16BE comment text
    uint8_t  color_code;       // Color palette index
    uint8_t  color_red;        // RGB red component
    uint8_t  color_green;      // RGB green component  
    uint8_t  color_blue;       // RGB blue component
};
```

#### Waveform Preview (PWAV)
```c
struct waveform_preview {
    uint32_t data_length;      // Always 400 bytes
    uint32_t unknown;          // Always 0x10000
    uint8_t  waveform[400];    // Waveform data
};

// Each byte encodes:
// Bits 0-4: Height (0-31)
// Bits 5-7: Whiteness level
```

#### Song Structure (PSSI)
```c
struct song_structure {
    uint32_t entry_bytes;      // Always 24 bytes per entry
    uint16_t num_entries;      // Number of phrases
    uint16_t mood;             // 1=high, 2=mid, 3=low
    uint8_t  unknown[6];       // Padding
    uint16_t end_beat;         // Last phrase end beat
    uint16_t unknown2;         // Unknown field
    uint8_t  bank;             // Lighting style bank (0-8)
    uint8_t  unknown3;         // Padding
};

struct phrase_entry {
    uint16_t index;            // Phrase number (1-based)
    uint16_t beat;             // Start beat number
    uint16_t kind;             // Phrase type (depends on mood)
    uint8_t  unknown;          // Padding
    uint8_t  k1, k2, k3;       // Phrase variant flags
    uint8_t  b;                // Additional beat count flag
    uint16_t beat2, beat3, beat4; // Additional beat positions
    uint8_t  unknown2;         // Padding
    uint8_t  fill;             // Fill-in flag
    uint16_t beat_fill;        // Fill-in start beat
};
```

## Network Protocols

### DJ Link Protocol

Real-time communication between players and mixers:

#### Protocol Characteristics
```
Transport:    UDP (User Datagram Protocol)
Port:         50002 (status), 50001 (beat sync)
Frequency:    Status packets every ~160ms
Beat Sync:    On every beat boundary
Addressing:   Broadcast and directed packets
```

#### Status Packet Structure
```c
struct cdj_status {
    uint8_t  magic[10];        // Packet identifier
    uint8_t  type;             // 0x0A = CDJ status
    uint8_t  length;           // Packet length
    uint8_t  device_number;    // Player number (1-4)
    uint8_t  unknown1[3];      // Padding
    uint8_t  activity;         // Playback state flags
    uint8_t  track_bank;       // 0=no track, 1=CD, 2=SD, 3=USB
    uint8_t  track_type;       // 0=no track, 1=rekordbox, 5=unanalyzed
    uint8_t  unknown2[2];      // Padding
    uint32_t track_id;         // Currently loaded track ID
    uint32_t track_number;     // Track number in playlist
    uint32_t next_track_id;    // Next track in playlist
    uint32_t position;         // Playback position (beats * 100)
    uint32_t length;           // Track length (beats * 100)
    uint16_t bpm;              // Current BPM * 100
    uint16_t pitch;            // Pitch adjustment * 100
    uint8_t  unknown3[16];     // Additional fields
};
```

#### Beat Sync Packets
```c
struct beat_packet {
    uint8_t  magic[10];        // Beat packet identifier
    uint8_t  type;             // 0x28 = beat
    uint8_t  length;           // Packet length
    uint8_t  device_number;    // Player number
    uint8_t  beat_within_bar;  // 1-4
    uint16_t bpm;              // Current BPM * 100
    uint8_t  unknown[10];      // Additional timing data
};
```

### RemoteDB Protocol

Database query protocol for track metadata:

#### Query Types
- **Track Lookup**: Get metadata by track ID
- **Menu Requests**: Browse playlists and folders  
- **Search Queries**: Find tracks by artist/title/genre
- **Artwork Requests**: Retrieve album art images

#### Example Queries
```c
// Track metadata request
struct remotedb_track_request {
    uint8_t  magic[11];        // RemoteDB identifier
    uint8_t  request_type;     // 0x2002 = track metadata
    uint32_t track_id;         // Target track ID
    uint8_t  arguments[40];    // Query parameters
};

// Menu browse request  
struct remotedb_menu_request {
    uint8_t  magic[11];        // RemoteDB identifier
    uint8_t  request_type;     // 0x3000 = menu
    uint32_t sort_order;       // Sort criteria
    uint32_t folder_id;        // Parent folder ID
    uint32_t offset;           // Pagination offset
    uint8_t  arguments[32];    // Additional parameters
};
```

## File System Structure

### Media Layout

Pioneer DJ uses a specific directory structure:

```
/PIONEER/
├── rekordbox/
│   ├── export.pdb              # Main database
│   ├── exportExt.pdb          # Extended database (optional)
│   └── share/
│       ├── ANLZ0001.DAT       # Track analysis files
│       ├── ANLZ0001.EXT       # Extended analysis
│       ├── ANLZ0001.2EX       # Advanced analysis (CDJ-3000)
│       └── ...
├── USBANLZ/                   # Alternative analysis location
└── Contents/                  # Track audio files
    ├── House/
    ├── Techno/
    └── ...
```

### File Organization Principles

#### Database Location
```
Primary:     /PIONEER/rekordbox/export.pdb
Extended:    /PIONEER/rekordbox/exportExt.pdb
```

#### Analysis Files
```
Pattern:     ANLZ{nnnn}.{ext}
nnnn:        4-digit sequential number (0001, 0002, etc.)
ext:         DAT (basic), EXT (enhanced), 2EX (advanced)
```

#### Audio File Storage
- **Contents Directory**: Organized by user preference
- **Supported Paths**: Any subdirectory structure within media root
- **File References**: Stored as relative paths in database
```

## Data Types and Encoding

### Numeric Formats

#### Database Files (Little-Endian)
```c
uint16_t value = *(uint16_t*)data;           // Direct access
uint32_t value = data[0] | (data[1] << 8) |  // Manual parsing
                (data[2] << 16) | (data[3] << 24);
```

#### Analysis Files (Big-Endian)  
```c
uint16_t value = (data[0] << 8) | data[1];   // Manual parsing
uint32_t value = (data[0] << 24) | (data[1] << 16) |
                (data[2] << 8) | data[3];
```

### Time Representations

#### Beat-Based Timing
```c
// Position in beats * 100
uint32_t beat_position = milliseconds * bpm / 60000 * 100;

// Convert back to milliseconds
uint32_t milliseconds = beat_position * 60000 / (bpm * 100);
```

#### Frame-Based Analysis
```c
// Waveform detail entries (150 per second)
uint32_t frame_index = milliseconds * 150 / 1000;
uint32_t time_offset = frame_index * 1000 / 150;
```

### Musical Key Encoding

Pioneer uses multiple key representations:

#### Key Table Format
```c
struct key_entry {
    uint32_t id;               // Key identifier
    uint32_t id2;              // Duplicate ID
    device_sql_string name;    // Key name (e.g., "8A", "Cm")
};
```

#### Common Key Values
| ID | Name | Musical Key | Camelot |
|----|------|-------------|---------|
| 1 | 8A | C minor | 8A |
| 2 | 3A | G minor | 3A |
| 3 | 10A | F minor | 10A |
| 4 | 5A | D minor | 5A |
| 5 | 12A | Bb minor | 12A |

## Hardware Compatibility

### Model-Specific Features

#### CDJ-2000/2000NXS
```
Database:     export.pdb only
Analysis:     .DAT files only
Waveforms:    Monochrome preview (400 bytes)
Cue Points:   Standard format (PCOB)
Network:      Basic DJ Link
```

#### CDJ-2000NXS2
```
Database:     export.pdb + exportExt.pdb
Analysis:     .DAT + .EXT files
Waveforms:    Color waveforms (6-channel)
Cue Points:   Extended format (PCO2) with colors
Network:      Enhanced DJ Link with ProDJ Link
```

#### CDJ-3000
```
Database:     Full database support
Analysis:     .DAT + .EXT + .2EX files
Waveforms:    3-band analysis support
Song Structure: Phrase analysis for lighting
Network:      Full DJ Link + lighting control
```

### Memory Limitations

#### Database Constraints
```c
// CDJ memory limitations
#define MAX_TRACKS_CDJ2000    10000   // Practical limit
#define MAX_TRACKS_CDJ3000    20000   // Enhanced capacity
#define MAX_PLAYLISTS         1000    // All models
#define MAX_FOLDER_DEPTH      8       // Playlist hierarchy
```

#### Analysis File Limits
```c
// Waveform data sizes
#define PREVIEW_WAVEFORM_SIZE     400     // Monochrome
#define COLOR_PREVIEW_SIZE        7200    // 6-channel color
#define DETAIL_WAVEFORM_VARIABLE  true    // Depends on track length
#define SONG_STRUCTURE_MAX_PHRASES 100    // Typical maximum
```

### Performance Optimizations

#### Database Query Optimization
```c
// Efficient track lookup
struct track_index {
    uint32_t track_id;
    uint16_t page_index;
    uint16_t row_index;
};

// Index building for fast access
void build_track_index(database_t* db) {
    for (each table page) {
        for (each row in page) {
            if (row.present && row.type == TRACK_ROW) {
                index[track_count++] = {
                    .track_id = row.data.id,
                    .page_index = page.index,
                    .row_index = row.index
                };
            }
        }
    }
    sort_index_by_track_id(index, track_count);
}
```

#### Network Bandwidth Management
```c
// RemoteDB connection pooling
#define MAX_CONCURRENT_QUERIES    4
#define QUERY_TIMEOUT_MS         5000
#define MAX_RETRIES              3

// Artwork caching strategy
struct artwork_cache {
    uint32_t artwork_id;
    size_t   data_size;
    uint8_t* data;
    time_t   last_access;
};
```

## Error Handling and Recovery

### Common Issues

#### Database Corruption
```c
// Validate page integrity
bool validate_page(page_t* page) {
    if (page->magic != PAGE_MAGIC) return false;
    if (page->type > MAX_PAGE_TYPE) return false;
    if (page->free_size + page->used_size > PAGE
