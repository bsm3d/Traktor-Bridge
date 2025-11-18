# Traktor Bridge 2.0 - Export Format Specifications

**Author**: Benoit (BSM) Saint-Moulin
**Version**: 2.0
**Last Updated**: November 2025

---

## Table of Contents

1. [Overview](#overview)
2. [CDJ/USB Format](#cdjusb-format)
3. [Rekordbox Database Format](#rekordbox-database-format)
4. [Rekordbox XML Format](#rekordbox-xml-format)
5. [M3U Format](#m3u-format)
6. [Format Comparison](#format-comparison)
7. [Technical Specifications](#technical-specifications)

---

## Overview

Traktor Bridge 2.0 supports multiple export formats, each optimized for different use cases and hardware/software compatibility.

### Supported Formats

| Format | Type | Use Case | Hardware/Software |
|--------|------|----------|-------------------|
| CDJ/USB | Binary PDB + ANLZ | CDJ hardware playback | CDJ-2000NXS2, CDJ-3000, XDJ-1000MK2 |
| Rekordbox Database | SQLite/SQLCipher | Rekordbox software import | Rekordbox 6/7 |
| Rekordbox XML | XML | Universal DJ software | Rekordbox, Serato, VirtualDJ, djay Pro |
| M3U | Text playlist | Media players, DJ software | Universal compatibility |

---

## CDJ/USB Format

### Overview

The CDJ/USB format creates a complete Pioneer-compatible USB drive structure for direct playback on CDJ hardware. This is the **primary format** for professional DJ setups.

### Directory Structure

```
USB Drive (FAT32, MBR partition)
├── PIONEER/
│   ├── rekordbox/
│   │   └── export.pdb              # Main database file
│   ├── DeviceSQL.edb               # Copy for CDJ recognition
│   └── USBANLZ/                    # Analysis files directory
│       ├── P000/                   # Path hash prefix
│       │   ├── 00000001/           # Full path hash
│       │   │   ├── ANLZ0000.DAT    # Basic waveform
│       │   │   └── ANLZ0000.EXT    # Color waveform (NXS2)
│       │   └── 00000002/
│       │       ├── ANLZ0000.DAT
│       │       └── ANLZ0000.EXT
│       └── P001/
│           └── ...
└── Contents/                       # Music files (if copied)
    ├── track001.mp3
    ├── track002.mp3
    └── ...
```

### PDB Database Format

**File**: `export.pdb` (also copied as `DeviceSQL.edb`)

#### Database Structure

The PDB database uses a custom binary format with **8192-byte pages** (not standard SQLite).

**Page Types:**

| Type ID | Name | Content |
|---------|------|---------|
| 0x00 | TRACKS | Track metadata rows |
| 0x01 | GENRES | Genre strings |
| 0x02 | ARTISTS | Artist strings |
| 0x03 | ALBUMS | Album strings |
| 0x04 | LABELS | Label strings |
| 0x05 | KEYS | Musical key strings |
| 0x06 | COLORS | Color tags |
| 0x07 | PLAYLISTS | Playlist structure |
| 0x08 | PLAYLIST_TRACKS | Track-playlist mappings |
| 0x09 | ARTWORK | Album artwork |

#### Page Header Structure

**Size**: 28 bytes

```
Offset | Size | Field           | Description
-------|------|-----------------|---------------------------
0x00   | 4    | page_type       | Page type ID (see table above)
0x04   | 4    | next_page       | Next page index (or 0)
0x08   | 4    | sequence        | Sequence number
0x0C   | 4    | row_count       | Number of rows in page
0x10   | 4    | heap_offset     | Offset to string heap
0x14   | 4    | free_space      | Free space in page
0x18   | 4    | reserved1       | Reserved (0)
0x1C   | 4    | reserved2       | Reserved (0)
```

#### Track Row Structure

**Fixed Size**: 88 bytes + variable string data

```
Offset | Size | Field           | Type         | Description
-------|------|-----------------|--------------|---------------------------
0x00   | 2    | row_header      | uint16       | Row type marker
0x02   | 2    | row_size        | uint16       | Total row size
0x04   | 4    | track_id        | uint32       | Unique track ID
0x08   | 4    | artist_id       | uint32       | Artist table reference
0x0C   | 4    | album_id        | uint32       | Album table reference
0x10   | 4    | genre_id        | uint32       | Genre table reference
0x14   | 4    | label_id        | uint32       | Label table reference
0x18   | 4    | key_id          | uint32       | Musical key ID (0-25)
0x1C   | 4    | bpm             | uint32       | BPM * 100 (12800 = 128.00)
0x20   | 4    | duration        | uint32       | Duration in seconds
0x24   | 4    | sample_rate     | uint32       | Sample rate (44100, 48000)
0x28   | 4    | file_size       | uint32       | File size in bytes
0x2C   | 2    | bitrate         | uint16       | Bitrate in kbps
0x2E   | 2    | rating          | uint16       | Rating (0-5)
0x30   | 4    | color_id        | uint32       | Color tag ID
0x34   | 4    | date_added      | uint32       | Unix timestamp
0x38   | 4    | play_count      | uint32       | Play count
0x3C   | 4    | year            | uint32       | Release year
0x40   | 8    | reserved        | -            | Reserved (0)
0x48   | var  | title_string    | DeviceSQL    | Title (DeviceSQL encoded)
0x??   | var  | file_path       | DeviceSQL    | Relative file path
...
```

#### DeviceSQL String Encoding

Pioneer uses a custom string encoding called "DeviceSQL":

**Short ASCII** (length ≤ 127 bytes):
```
[1 byte: length] [N bytes: ASCII data]
```

**Long ASCII** (length > 127 bytes):
```
[1 byte: 0x80 | length_high] [1 byte: length_low] [N bytes: ASCII data]
```

**UTF-16LE** (for non-ASCII):
```
[1 byte: 0x90] [2 bytes: length] [N bytes: UTF-16LE data]
```

### ANLZ Waveform Files

ANLZ files contain waveform data and analysis information for CDJ display.

#### File Types

- **`.DAT`**: Basic waveform (all CDJ models)
- **`.EXT`**: Color waveform (CDJ-2000NXS2, CDJ-3000)

#### Path Hashing Algorithm

ANLZ files are organized by path hash:

```python
def calculate_path_hash(file_path: str) -> str:
    """
    Calculate Pioneer path hash.

    Path: /path/to/track.mp3
    Hash: 01234567 (8 hex digits)
    Directory: USBANLZ/P012/01234567/
    """
    import hashlib

    # Normalize path
    normalized = file_path.replace('\\', '/').lower()

    # Calculate hash
    hash_obj = hashlib.md5(normalized.encode('utf-8'))
    hash_int = int.from_bytes(hash_obj.digest()[:4], 'little')

    # Format as 8-digit hex
    hash_str = f"{hash_int:08X}"

    return hash_str
```

**Directory Structure:**
```
USBANLZ/P{first 3 digits}/{full 8 digits}/ANLZ0000.DAT
USBANLZ/P{first 3 digits}/{full 8 digits}/ANLZ0000.EXT
```

**Example:**
```
Hash: 01234567
Directory: USBANLZ/P012/01234567/
Files: ANLZ0000.DAT, ANLZ0000.EXT
```

#### ANLZ File Structure

**DAT File Format:**

```
Offset | Size | Field           | Description
-------|------|-----------------|---------------------------
0x00   | 4    | magic           | "PMAI" (0x50 0x4D 0x41 0x49)
0x04   | 4    | header_size     | Header size (400 bytes)
0x08   | 4    | file_size       | Total file size
0x0C   | 4    | reserved1       | Reserved (0)
0x10   | 4    | beat_grid_tag   | "PQTZ" if beat grid present
0x14   | 388  | header_data     | Additional header fields
0x190  | var  | beat_grid       | Beat grid data
0x???  | var  | waveform        | Waveform data
0x???  | var  | cue_points      | Cue point data
```

**Waveform Data:**
- **Resolution**: 150 samples per second
- **Format**: 8-bit or 16-bit amplitude values
- **Channels**: Mono or stereo

**Beat Grid:**
```
[4 bytes: tag "PQTZ"]
[4 bytes: entry count]
For each beat:
    [2 bytes: beat position]
    [2 bytes: tempo]
```

**Cue Points:**
```
[4 bytes: tag "PCPT"]
[4 bytes: entry count]
For each cue:
    [4 bytes: position (milliseconds)]
    [4 bytes: cue type]
    [1 byte: hot cue number (0-7 or 0xFF)]
    [1 byte: color (R)]
    [1 byte: color (G)]
    [1 byte: color (B)]
```

### Hardware Requirements

**USB Format:**
- **File System**: FAT32 (exFAT not supported on older CDJs)
- **Partition Table**: MBR (not GPT)
- **Cluster Size**: 32KB recommended

**File Naming:**
- **Characters**: ASCII only (no accents, special characters)
- **Path Length**: Maximum 256 characters
- **Reserved Names**: Avoid CON, PRN, AUX, NUL, etc.

**Capacity Limits:**
- **Tracks**: ~10,000 tracks maximum (CDJ hardware limit)
- **File Size**: Individual files up to 4GB (FAT32 limit)
- **USB Size**: Up to 2TB (practical limit)

### Compatibility Matrix

| CDJ Model | PDB Support | ANLZ DAT | ANLZ EXT | Max Tracks |
|-----------|-------------|----------|----------|------------|
| CDJ-2000 | ✓ | ✓ | ✗ | ~10,000 |
| CDJ-2000NXS | ✓ | ✓ | ✓ | ~10,000 |
| CDJ-2000NXS2 | ✓ | ✓ | ✓ | ~10,000 |
| CDJ-3000 | ✓ | ✓ | ✓ | ~20,000 |
| XDJ-1000MK2 | ✓ | ✓ | ✓ | ~10,000 |
| XDJ-RX2 | ✓ | ✓ | ✓ | ~10,000 |

---

## Rekordbox Database Format

### Overview

SQLite/SQLCipher database for **Rekordbox software** (not CDJ hardware).

### File Format

- **Database**: SQLite 3
- **Encryption**: SQLCipher (optional)
- **Cipher Key**: `402fd482c38817c35ffa8ffb8c7d2bad` (standard Rekordbox key)
- **Extension**: `.db` or `.edb`

### Database Schema

#### Main Tables

**djmdContent** - Track metadata

```sql
CREATE TABLE djmdContent (
    ID TEXT PRIMARY KEY,
    FolderPath TEXT,
    FileNameL TEXT,
    FileSize INTEGER,
    Title TEXT,
    ArtistID TEXT,
    AlbumID TEXT,
    GenreID TEXT,
    BPM INTEGER,      -- BPM * 100
    Length INTEGER,   -- Duration in seconds
    TrackNo INTEGER,
    BitRate INTEGER,
    SampleRate INTEGER,
    FileType INTEGER,
    Key INTEGER,      -- Musical key ID (0-25)
    Rating INTEGER,   -- 0-5
    Color INTEGER,    -- Color tag ID
    DateCreated TEXT,
    DateAdded TEXT,
    rb_file_id TEXT,
    rb_LocalFolderTrack INTEGER,
    rb_cue_count INTEGER,
    FOREIGN KEY(ArtistID) REFERENCES djmdArtist(ID),
    FOREIGN KEY(AlbumID) REFERENCES djmdAlbum(ID),
    FOREIGN KEY(GenreID) REFERENCES djmdGenre(ID)
);
```

**djmdArtist** - Artists

```sql
CREATE TABLE djmdArtist (
    ID TEXT PRIMARY KEY,
    Name TEXT
);
```

**djmdAlbum** - Albums

```sql
CREATE TABLE djmdAlbum (
    ID TEXT PRIMARY KEY,
    Name TEXT,
    AlbumArtistID TEXT,
    FOREIGN KEY(AlbumArtistID) REFERENCES djmdArtist(ID)
);
```

**djmdGenre** - Genres

```sql
CREATE TABLE djmdGenre (
    ID TEXT PRIMARY KEY,
    Name TEXT
);
```

**djmdPlaylist** - Playlists

```sql
CREATE TABLE djmdPlaylist (
    ID TEXT PRIMARY KEY,
    Seq INTEGER,
    Name TEXT,
    ImagePath TEXT,
    Attribute INTEGER,
    ParentID TEXT,
    FOREIGN KEY(ParentID) REFERENCES djmdPlaylist(ID)
);
```

**djmdSongPlaylist** - Track-Playlist mapping

```sql
CREATE TABLE djmdSongPlaylist (
    ID TEXT PRIMARY KEY,
    PlaylistID TEXT,
    ContentID TEXT,
    TrackNo INTEGER,
    FOREIGN KEY(PlaylistID) REFERENCES djmdPlaylist(ID),
    FOREIGN KEY(ContentID) REFERENCES djmdContent(ID)
);
```

**djmdCue** - Cue points

```sql
CREATE TABLE djmdCue (
    ID TEXT PRIMARY KEY,
    ContentID TEXT,
    InMsec INTEGER,    -- Position in milliseconds
    InFrame INTEGER,
    InMpegFrame INTEGER,
    InMpegAbs INTEGER,
    OutMsec INTEGER,   -- For loops
    OutFrame INTEGER,
    OutMpegFrame INTEGER,
    OutMpegAbs INTEGER,
    Kind INTEGER,      -- Cue type
    Color INTEGER,     -- RGB color
    ColorTableIndex INTEGER,
    ActiveLoop INTEGER,
    Comment TEXT,
    BeatLoopSize INTEGER,
    CueMicrosec INTEGER,
    InPointSeekInfo TEXT,
    OutPointSeekInfo TEXT,
    FOREIGN KEY(ContentID) REFERENCES djmdContent(ID)
);
```

**Cue Types:**
- `0`: Memory cue
- `1`: Hot cue
- `2`: Loop

**djmdBeatGrid** - Beat grid

```sql
CREATE TABLE djmdBeatGrid (
    ID TEXT PRIMARY KEY,
    ContentID TEXT,
    Msec INTEGER,     -- Grid anchor position (milliseconds)
    Count INTEGER,    -- Beat count
    BPM INTEGER,      -- BPM * 100
    FOREIGN KEY(ContentID) REFERENCES djmdContent(ID)
);
```

**djmdArtwork** - Album artwork

```sql
CREATE TABLE djmdArtwork (
    ID TEXT PRIMARY KEY,
    Path TEXT
);
```

### Encryption

**SQLCipher Configuration:**

```python
import sqlite3
from pysqlcipher3 import dbapi2 as sqlcipher

# Open encrypted database
conn = sqlcipher.connect('rekordbox.db')
conn.execute(f"PRAGMA key = '402fd482c38817c35ffa8ffb8c7d2bad'")
conn.execute("PRAGMA cipher_page_size = 1024")
conn.execute("PRAGMA kdf_iter = 64000")
```

### Import to Rekordbox

1. Open Rekordbox
2. Go to **Preferences** → **Advanced** → **Database**
3. Click **Import Database**
4. Select the `.db` file
5. Restart Rekordbox

---

## Rekordbox XML Format

### Overview

Standard XML format compatible with Rekordbox and other DJ software (Serato, VirtualDJ, djay Pro).

### File Structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="Traktor Bridge" Version="2.0" Company="BSM"/>

  <COLLECTION Entries="5234">
    <TRACK TrackID="1" Name="Track Title" Artist="Artist Name"
           Album="Album Name" Genre="House" Kind="MP3 File"
           Size="8765432" TotalTime="300" DiscNumber="1"
           TrackNumber="1" Year="2024" AverageBpm="128.00"
           DateAdded="2024-11-17" BitRate="320"
           SampleRate="44100" Comments=""
           Rating="4" PlayCount="10"
           Tonality="12B" Location="file://localhost/path/to/track.mp3">

      <!-- Cue Points -->
      <POSITION_MARK Name="Hot Cue 1" Type="0" Start="32.5"
                     Num="0" Red="255" Green="0" Blue="0"/>
      <POSITION_MARK Name="Memory Cue" Type="0" Start="64.0"
                     Num="-1" Red="0" Green="255" Blue="0"/>
      <POSITION_MARK Name="Loop 1" Type="4" Start="96.0" End="128.0"
                     Num="0" Red="0" Green="0" Blue="255"/>

      <!-- Beat Grid -->
      <TEMPO Inizio="0.000" Bpm="128.00" Metro="4/4" Battito="1"/>
    </TRACK>

    <!-- More tracks... -->
  </COLLECTION>

  <PLAYLISTS>
    <NODE Type="0" Name="ROOT" Count="3">

      <!-- Folder -->
      <NODE Name="House Music" Type="0" Count="2">

        <!-- Playlist -->
        <NODE Name="Deep House" Type="1" Entries="50">
          <TRACK Key="1"/>
          <TRACK Key="2"/>
          <!-- More track references... -->
        </NODE>

        <NODE Name="Tech House" Type="1" Entries="42">
          <TRACK Key="3"/>
          <TRACK Key="4"/>
          <!-- More track references... -->
        </NODE>
      </NODE>

      <!-- More folders/playlists... -->
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
```

### Element Specifications

**TRACK Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| TrackID | int | Unique track identifier |
| Name | string | Track title |
| Artist | string | Artist name |
| Album | string | Album name |
| Genre | string | Genre |
| Kind | string | File type (e.g., "MP3 File") |
| Size | int | File size in bytes |
| TotalTime | int | Duration in seconds |
| Year | int | Release year |
| AverageBpm | float | BPM with 2 decimal places |
| DateAdded | date | Date added (YYYY-MM-DD) |
| BitRate | int | Bitrate in kbps |
| SampleRate | int | Sample rate (44100, 48000) |
| Rating | int | Rating 0-5 |
| PlayCount | int | Play count |
| Tonality | string | Musical key (Open Key notation) |
| Location | URI | File path (file://localhost/...) |

**POSITION_MARK Types:**

| Type | Description |
|------|-------------|
| 0 | Cue point (memory cue or hot cue) |
| 4 | Loop |

**POSITION_MARK Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| Name | string | Cue point name |
| Type | int | Cue type (0 or 4) |
| Start | float | Start position (seconds.milliseconds) |
| End | float | End position for loops |
| Num | int | Hot cue number (0-7) or -1 for memory cues |
| Red | int | Color R component (0-255) |
| Green | int | Color G component (0-255) |
| Blue | int | Color B component (0-255) |

**NODE Types:**

| Type | Description |
|------|-------------|
| 0 | Folder |
| 1 | Playlist |

### Software Compatibility

| Software | Import | Export | Cue Points | Loops | Keys |
|----------|--------|--------|------------|-------|------|
| Rekordbox 6/7 | ✓ | ✓ | ✓ | ✓ | ✓ |
| Serato DJ Pro | ✓ | ✓ | ✓ | ✓ | ✓ |
| VirtualDJ | ✓ | ✓ | ✓ | ✓ | ✓ |
| djay Pro | ✓ | ✗ | ✓ | ✓ | ✓ |
| Traktor Pro | ✗ | ✓ | ✗ | ✗ | ✗ |

---

## M3U Format

### Overview

Universal text-based playlist format compatible with media players and DJ software.

### File Format

**M3U8** (UTF-8 encoded):

```
#EXTM3U
#EXTINF:300,Artist Name - Track Title
/path/to/music/track001.mp3
#EXTINF:245,Another Artist - Another Track
/path/to/music/track002.mp3
#EXTINF:320,Third Artist - Third Track
/path/to/music/track003.mp3
```

### Format Specification

**Header:**
```
#EXTM3U
```

**Track Entry:**
```
#EXTINF:<duration>,<artist> - <title>
<file_path>
```

**Fields:**
- `duration`: Track duration in seconds
- `artist`: Artist name
- `title`: Track title
- `file_path`: Absolute or relative file path

### Path Types

**Absolute Paths:**
```
#EXTM3U
#EXTINF:300,Artist - Title
/home/user/Music/track.mp3
```

**Relative Paths:**
```
#EXTM3U
#EXTINF:300,Artist - Title
../Music/track.mp3
```

**Windows Paths:**
```
#EXTM3U
#EXTINF:300,Artist - Title
C:\Users\User\Music\track.mp3
```

### Extended M3U

**Extended format with additional metadata:**

```
#EXTM3U
#EXTINF:300,Artist - Title
#EXTGENRE:House
#EXTBPM:128
#EXTKEY:12B
#EXTRATING:4
/path/to/track.mp3
```

### Folder Structure

```
Playlists/
├── House Music/
│   ├── Deep House.m3u
│   └── Tech House.m3u
├── Techno/
│   ├── Minimal.m3u
│   └── Peak Time.m3u
└── All Tracks.m3u
```

### Software Compatibility

| Software | Support | Metadata | Folder Structure |
|----------|---------|----------|------------------|
| iTunes | ✓ | Basic | ✗ |
| VLC | ✓ | Basic | ✗ |
| Winamp | ✓ | Extended | ✗ |
| Serato DJ | ✓ | Extended | ✓ |
| VirtualDJ | ✓ | Extended | ✓ |
| djay Pro | ✓ | Basic | ✓ |

---

## Format Comparison

### Feature Matrix

| Feature | CDJ/USB | RB Database | RB XML | M3U |
|---------|---------|-------------|--------|-----|
| **Metadata** |
| Track metadata | ✓ | ✓ | ✓ | Limited |
| Cue points | ✓ | ✓ | ✓ | ✗ |
| Loops | ✓ | ✓ | ✓ | ✗ |
| Beat grid | ✓ | ✓ | ✓ | ✗ |
| Waveforms | ✓ | ✗ | ✗ | ✗ |
| Album artwork | ✓ | ✓ | ✗ | ✗ |
| Musical key | ✓ | ✓ | ✓ | Extended |
| Rating | ✓ | ✓ | ✓ | Extended |
| Play count | ✓ | ✓ | ✓ | ✗ |
| **Structure** |
| Playlists | ✓ | ✓ | ✓ | ✓ |
| Folders | ✓ | ✓ | ✓ | ✓ |
| Smart playlists | ✗ | ✓ | ✗ | ✗ |
| **Compatibility** |
| CDJ hardware | ✓ | ✗ | ✗ | ✗ |
| Rekordbox software | ✗ | ✓ | ✓ | ✓ |
| Other DJ software | ✗ | ✗ | ✓ | ✓ |
| Media players | ✗ | ✗ | ✗ | ✓ |

### Use Case Recommendations

**CDJ/USB** - Best for:
- CDJ hardware performance (clubs, events)
- Offline playback without laptop
- Complete metadata preservation
- Professional DJ setups

**Rekordbox Database** - Best for:
- Rekordbox software users
- Complete collection migration
- Advanced features (hot cues, loops, comments)
- Encrypted backups

**Rekordbox XML** - Best for:
- Cross-platform compatibility
- Importing to multiple DJ software
- Backup and archival
- Sharing with other DJs

**M3U** - Best for:
- Simple playlist sharing
- Media player compatibility
- Lightweight exports
- Quick playlist creation

---

## Technical Specifications

### File Size Estimates

**Per Track:**

| Format | Size | Components |
|--------|------|------------|
| CDJ/USB | ~500KB | PDB entry + ANLZ files + metadata |
| RB Database | ~5KB | Database row + indices |
| RB XML | ~2KB | XML element |
| M3U | ~200B | Text entry |

**1000 Tracks:**

| Format | Total Size |
|--------|------------|
| CDJ/USB | ~500 MB (without audio files) |
| RB Database | ~5 MB |
| RB XML | ~2 MB |
| M3U | ~200 KB |

### Performance Characteristics

**Export Time (1000 tracks):**

| Format | Time | Bottleneck |
|--------|------|------------|
| CDJ/USB | 5-10 min | ANLZ generation, audio copy |
| RB Database | 30-60 sec | Database inserts, encryption |
| RB XML | 10-20 sec | XML serialization |
| M3U | 5-10 sec | File I/O |

**Memory Usage:**

| Format | RAM | Notes |
|--------|-----|-------|
| CDJ/USB | 100-200 MB | ANLZ waveform processing |
| RB Database | 50-100 MB | In-memory database |
| RB XML | 30-50 MB | XML tree construction |
| M3U | 10-20 MB | String concatenation |

---

**Document Version**: 1.0
**Last Updated**: November 2025
**Author**: Benoit (BSM) Saint-Moulin

For technical support or format-specific questions, please consult the [API Reference](API.md) or open an issue on GitHub.
