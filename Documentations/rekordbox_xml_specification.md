# Rekordbox XML Format Technical Specification

## Sources and Attribution

### Author
**Benoit Saint-Moulin**  
- **Website**: [www.benoitsaintmoulin.com](https://www.benoitsaintmoulin.com)  
- **GitHub**: [github.com/bsm3d](https://github.com/bsm3d)  
- **Profile**: Belgian DJ/Producer, Founder of Green Mayday

### Primary Research Sources

#### 1. crate-digger Project (Deep Symmetry)
- **Lead Author**: James Elliott
- **Organization**: Deep Symmetry
- **Repository**: [github.com/Deep-Symmetry/crate-digger](https://github.com/Deep-Symmetry/crate-digger)
- **Contact**: james@deepsymmetry.org
- **Documentation**: [djl-analysis.deepsymmetry.org](https://djl-analysis.deepsymmetry.org/djl-analysis)
- **Description**: Java library for fetching and parsing rekordbox exports and track analysis files

#### 2. pyrekordbox Project
- **Author**: Dylan Jones
- **Repository**: [github.com/dylanljones/pyrekordbox](https://github.com/dylanljones/pyrekordbox)
- **PyPI Package**: [pypi.org/project/pyrekordbox](https://pypi.org/project/pyrekordbox)
- **Description**: Python package for interacting with Rekordbox database and files (XML, ANLZ, MySettings)
- **License**: MIT License

#### 3. Direct Analysis Sources
- **Rekordbox Software**: Pioneer DJ's Rekordbox versions 5.x and 6.x
- **XML Export Files**: Direct analysis of XML files exported from various Rekordbox versions
- **Format Specifications**: Reverse-engineered from real-world export files

### Research Methodology
This specification is based on primary source analysis of XML exports, open source project integration, community research collaboration, and empirical testing with real-world Rekordbox libraries.

### Important Documentation Disclaimer
**Research Notice**: This specification documents proprietary Pioneer DJ formats through community reverse engineering efforts. Pioneer DJ provides no official XML format documentation.

**Copyright**: Pioneer DJ, Rekordbox, CDJ, and DJM are trademarks of Pioneer Corporation. This research is independent and not affiliated with Pioneer DJ.

---

## Table of Contents

1. [Introduction](#introduction)
2. [XML Document Structure](#xml-document-structure)
3. [Root Element: DJ_PLAYLISTS](#root-element-dj_playlists)
4. [PRODUCT Element](#product-element)
5. [COLLECTION Element](#collection-element)
6. [TRACK Element Structure](#track-element-structure)
7. [Temporal Data Elements](#temporal-data-elements)
8. [PLAYLISTS Element](#playlists-element)
9. [NODE Element Structure](#node-element-structure)
10. [Data Types and Encoding](#data-types-and-encoding)
11. [Validation and Compatibility](#validation-and-compatibility)

## Introduction

The Rekordbox XML format provides a standardized, text-based representation of DJ library data that serves as an interchange format between Rekordbox and other DJ software platforms. Unlike the proprietary binary formats used for CDJ hardware exports, XML offers human-readable structure and cross-platform compatibility.

This specification builds upon the extensive research performed by the Deep Symmetry team through their crate-digger project and complements the Python ecosystem developments in pyrekordbox, providing a comprehensive reference for developers working with Rekordbox data interchange.

### Key Characteristics

- **Format**: UTF-8 encoded XML
- **Architecture**: Document-oriented structure optimized for portability
- **Encoding**: UTF-8 character encoding with URL-encoded file paths
- **Compatibility**: Cross-platform interchange format
- **Security**: No encryption, plain text format

This specification covers XML exports from Rekordbox 5.x-6.x targeting software-to-software data exchange and backup scenarios.

## XML Document Structure

### Document Declaration

Rekordbox XML files begin with a standard XML declaration:

```xml
<?xml version="1.0" encoding="UTF-8"?>
```

### Character Encoding

All text content uses UTF-8 encoding. File paths are URL-encoded to handle special characters and spaces.

### Namespace Declaration

No XML namespaces are used. The format relies on simple element names and attributes.

## Root Element: DJ_PLAYLISTS

The root element encapsulates the entire library structure:

```xml
<DJ_PLAYLISTS Version="1.0.0">
    <PRODUCT Name="rekordbox" Version="6.7.0" Company="Pioneer DJ"/>
    <COLLECTION Entries="1245">
        <!-- Track entries -->
    </COLLECTION>
    <PLAYLISTS>
        <!-- Playlist tree structure -->
    </PLAYLISTS>
</DJ_PLAYLISTS>
```

### Root Attributes

- **Version**: XML schema version (typically "1.0.0")

### Child Elements

- **PRODUCT**: Software identification metadata
- **COLLECTION**: Container for all track entries
- **PLAYLISTS**: Hierarchical playlist structure

## PRODUCT Element

Identifies the software that generated the XML file:

```xml
<PRODUCT Name="rekordbox" Version="6.7.0" Company="Pioneer DJ"/>
```

### Attributes

- **Name**: Software name (always "rekordbox")
- **Version**: Rekordbox version that exported the file
- **Company**: Manufacturer (always "Pioneer DJ")

## COLLECTION Element

Contains all track metadata entries in the library.

### Attributes

- **Entries**: Total number of tracks in the collection (integer)

### Structure

```xml
<COLLECTION Entries="1245">
    <TRACK TrackID="1" Name="Track Title" Artist="Artist Name"
           Composer="" Album="Album Name" Grouping="" Genre="House"
           Kind="MP3 File" Size="8426752" TotalTime="211"
           DiscNumber="0" TrackNumber="1" Year="2023"
           AverageBpm="128.00" DateAdded="2023-03-15"
           BitRate="320" SampleRate="44100"
           Comments="" PlayCount="5" Rating="0"
           Location="file://localhost/Users/DJ/Music/track.mp3"
           Remixer="" Tonality="8A" Label="" Mix="">
        <!-- Temporal data elements -->
    </TRACK>
</COLLECTION>
```

## TRACK Element Structure

The TRACK element contains comprehensive metadata for each audio file.

### Core Attributes

#### Identification
- **TrackID**: Unique numeric identifier (integer)
- **Name**: Track title (string)
- **Artist**: Primary artist name (string)
- **Composer**: Track composer (string, optional)
- **Album**: Album name (string)
- **Grouping**: Custom grouping field (string, optional)

#### Classification
- **Genre**: Musical genre (string)
- **Kind**: File format description (e.g., "MP3 File", "AIFF File")
- **Label**: Record label (string, optional)
- **Remixer**: Remixer name (string, optional)
- **Mix**: Mix version (string, optional)

#### Technical Properties
- **Size**: File size in bytes (integer)
- **TotalTime**: Duration in seconds (integer)
- **BitRate**: Audio bitrate in kbps (integer)
- **SampleRate**: Sample rate in Hz (integer)
- **DiscNumber**: Disc number for multi-disc albums (integer, 0 if not applicable)
- **TrackNumber**: Track position on album (integer)
- **Year**: Release year (integer)

#### DJ-Specific Data
- **AverageBpm**: Beats per minute with 2 decimal precision (string)
- **Tonality**: Musical key in Open Key notation (string, e.g., "8A", "12B")
- **Rating**: User rating 0-5 stars (integer)
- **PlayCount**: Number of times played (integer)
- **Comments**: User comments (string)
- **DateAdded**: Date added to library (YYYY-MM-DD format)

#### File Location
- **Location**: File path as file:// URL (URL-encoded string)

### Example TRACK Element

```xml
<TRACK TrackID="1" Name="House Anthem" Artist="DJ Producer"
       Composer="DJ Producer" Album="Electronic Vibes" Grouping=""
       Genre="House" Kind="MP3 File" Size="8426752" TotalTime="211"
       DiscNumber="1" TrackNumber="3" Year="2023"
       AverageBpm="128.00" DateAdded="2023-03-15"
       BitRate="320" SampleRate="44100"
       Comments="Great for peak time" PlayCount="15" Rating="4"
       Location="file://localhost/Users/DJ/Music/House%20Anthem.mp3"
       Remixer="" Tonality="8A" Label="Electronic Records" Mix="">
    <TEMPO Inizio="0.000" Bpm="128.00" Metro="4/4" Battito="1"/>
    <POSITION_MARK Name="" Type="0" Start="30.500" Num="0"/>
    <POSITION_MARK Name="Chorus" Type="0" Start="95.250" Num="1"/>
</TRACK>
```

## Temporal Data Elements

Track elements contain child elements for timing-related data.

### TEMPO Element

Defines the tempo characteristics:

```xml
<TEMPO Inizio="0.000" Bpm="128.00" Metro="4/4" Battito="1"/>
```

#### Attributes
- **Inizio**: Start time in seconds (typically "0.000")
- **Bpm**: Beats per minute (decimal string)
- **Metro**: Time signature (string, e.g., "4/4", "3/4")
- **Battito**: Beat number within measure (integer)

### POSITION_MARK Element

Defines cue points and memory cues:

```xml
<POSITION_MARK Name="Intro" Type="0" Start="8.750" Num="0"/>
<POSITION_MARK Name="Verse" Type="0" Start="32.125" Num="1"/>
<POSITION_MARK Name="Chorus" Type="0" Start="64.500" Num="2"/>
```

#### Attributes
- **Name**: Cue point label (string, can be empty)
- **Type**: Cue type (integer)
  - `0`: Memory cue/hot cue
  - `4`: Loop (with additional loop data)
- **Start**: Position in seconds (decimal string)
- **Num**: Cue number/index (integer)

#### Loop Extensions

For loop cues (Type="4"), additional attributes may be present:
- **End**: Loop end position in seconds
- **Color**: Loop color identifier

## PLAYLISTS Element

Contains the hierarchical structure of playlists and folders.

### Structure

```xml
<PLAYLISTS>
    <NODE Type="0" Name="ROOT" Count="3">
        <NODE Name="House Music" Type="0" Count="2">
            <NODE Name="Peak Time" Type="1" Entries="5">
                <TRACK Key="1"/>
                <TRACK Key="5"/>
                <TRACK Key="12"/>
                <TRACK Key="23"/>
                <TRACK Key="67"/>
            </NODE>
            <NODE Name="Warm Up" Type="1" Entries="3">
                <TRACK Key="34"/>
                <TRACK Key="45"/>
                <TRACK Key="78"/>
            </NODE>
        </NODE>
        <NODE Name="Techno" Type="1" Entries="4">
            <TRACK Key="89"/>
            <TRACK Key="91"/>
            <TRACK Key="103"/>
            <TRACK Key="156"/>
        </NODE>
    </NODE>
</PLAYLISTS>
```

## NODE Element Structure

Represents folders and playlists in the hierarchy.

### Attributes

#### Node Type
- **Type**: Node classification (integer)
  - `0`: Folder (container for other nodes)
  - `1`: Playlist (contains track references)

#### Content Information
- **Name**: Display name (string)
- **Count**: Number of child nodes (for folders)
- **Entries**: Number of tracks (for playlists)

### Child Elements

#### For Folders (Type="0")
- Child **NODE** elements representing subfolders or playlists

#### For Playlists (Type="1")
- **TRACK** elements with **Key** attribute referencing TrackID

### Track References

Playlist tracks reference collection tracks by ID:

```xml
<TRACK Key="1"/>
```

- **Key**: References the TrackID from the COLLECTION

## Data Types and Encoding

### Numeric Values

#### Integers
- **TrackID**, **Size**, **TotalTime**, **BitRate**, **SampleRate**: Standard integers
- **Year**, **DiscNumber**, **TrackNumber**, **Rating**, **PlayCount**: Standard integers

#### Decimals
- **AverageBpm**: Decimal string with 2 decimal places (e.g., "128.00")
- **Start** (in POSITION_MARK): Decimal string with 3 decimal places (e.g., "30.500")

### String Values

#### Text Fields
- UTF-8 encoded
- XML entities for special characters (&amp;, &lt;, &gt;, &quot;, &apos;)
- Empty strings represented as empty attributes

#### File Paths
- URL-encoded file:// URLs
- Special characters encoded (%20 for space, etc.)
- Forward slashes for path separators (even on Windows)

### Date Format

- **DateAdded**: ISO 8601 date format (YYYY-MM-DD)
- Example: "2023-03-15"

### Musical Key Notation

- **Tonality**: Open Key notation
- Format: NumberLetter (e.g., "8A", "12B", "1A")
- Empty string if key not detected

## Validation and Compatibility

### XML Schema Validation

While no official XSD exists, the format follows these rules:

#### Required Elements
- Root DJ_PLAYLISTS element with Version attribute
- PRODUCT element with Name, Version, Company attributes
- COLLECTION element with Entries attribute
- PLAYLISTS element (can be empty)

#### Attribute Requirements
- TrackID must be unique within COLLECTION
- Location must be valid file:// URL
- Numeric attributes must contain valid numbers
- TRACK Key references must match existing TrackID values

### Cross-Platform Compatibility

#### File Path Handling
```xml
<!-- Windows path -->
Location="file://localhost/C:/Users/DJ/Music/track.mp3"

<!-- macOS/Linux path -->  
Location="file://localhost/Users/DJ/Music/track.mp3"
```

#### Character Encoding
- Always UTF-8
- URL encoding for file paths
- XML entity encoding for text content

### Software Compatibility

#### Import Considerations
- Some software may ignore unknown attributes
- TEMPO and POSITION_MARK elements optional for basic compatibility
- Playlist structure may be flattened by simpler applications

#### Export Variations
Different Rekordbox versions may:
- Include additional proprietary attributes
- Vary decimal precision
- Use different URL encoding schemes

## Performance Optimizations

### Large Library Handling

```python
def parse_rekordbox_xml_stream(file_path):
    """Streaming parser for large XML files"""
    import xml.etree.ElementTree as ET
    
    context = ET.iterparse(file_path, events=('start', 'end'))
    context = iter(context)
    event, root = next(context)
    
    for event, elem in context:
        if event == 'end' and elem.tag == 'TRACK':
            # Process track element
            track_data = extract_track_data(elem)
            yield track_data
            
            # Clear element to save memory
            elem.clear()
            root.clear()
```

### Memory Optimization
- Stream parsing for files >100MB
- Clear processed elements
- Index TrackID mappings separately

## Error Handling

### Common Issues

#### Malformed URLs
```python
def sanitize_file_url(location):
    """Fix common URL encoding issues"""
    if not location.startswith('file://'):
        return None
    
    # Remove localhost if present
    url = location.replace('file://localhost/', 'file:///')
    
    # Ensure proper encoding
    from urllib.parse import quote
    path = url[8:]  # Remove 'file:///'
    return 'file:///' + quote(path, safe='/:')
```

#### Missing Attributes
```python
def safe_get_track_attribute(track_elem, attr_name, default=None):
    """Safely extract track attributes with defaults"""
    value = track_elem.get(attr_name, default)
    
    if attr_name in ['TrackID', 'Size', 'TotalTime']:
        try:
            return int(value) if value else 0
        except ValueError:
            return 0
    
    return value or ""
```

## Supported Audio Formats

| Format | Kind Value | Extension | Notes |
|--------|------------|-----------|-------|
| MP3 | MP3 File | .mp3 | MPEG-1 Layer 3 |
| AAC | M4A File | .m4a | In MP4 container |
| FLAC | FLAC File | .flac | Lossless |
| WAV | WAV File | .wav | Uncompressed PCM |
| AIFF | AIFF File | .aiff | Apple format |

## Example Complete XML Document

```xml
<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
    <PRODUCT Name="rekordbox" Version="6.7.0" Company="Pioneer DJ"/>
    <COLLECTION Entries="2">
        <TRACK TrackID="1" Name="House Track" Artist="DJ Artist"
               Composer="" Album="Electronic Album" Grouping=""
               Genre="House" Kind="MP3 File" Size="8426752" TotalTime="211"
               DiscNumber="1" TrackNumber="1" Year="2023"
               AverageBpm="128.00" DateAdded="2023-03-15"
               BitRate="320" SampleRate="44100"
               Comments="" PlayCount="5" Rating="4"
               Location="file://localhost/Users/DJ/Music/house_track.mp3"
               Remixer="" Tonality="8A" Label="Electronic Records" Mix="">
            <TEMPO Inizio="0.000" Bpm="128.00" Metro="4/4" Battito="1"/>
            <POSITION_MARK Name="Intro" Type="0" Start="8.750" Num="0"/>
            <POSITION_MARK Name="Drop" Type="0" Start="95.250" Num="1"/>
        </TRACK>
        <TRACK TrackID="2" Name="Techno Track" Artist="Techno Producer"
               Composer="" Album="Underground Sounds" Grouping=""
               Genre="Techno" Kind="MP3 File" Size="9156432" TotalTime="284"
               DiscNumber="1" TrackNumber="5" Year="2023"
               AverageBpm="132.00" DateAdded="2023-03-20"
               BitRate="320" SampleRate="44100"
               Comments="Hard techno banger" PlayCount="12" Rating="5"
               Location="file://localhost/Users/DJ/Music/techno_track.mp3"
               Remixer="" Tonality="12A" Label="Techno Label" Mix="">
            <TEMPO Inizio="0.000" Bpm="132.00" Metro="4/4" Battito="1"/>
            <POSITION_MARK Name="Build" Type="0" Start="45.125" Num="0"/>
            <POSITION_MARK Name="Peak" Type="0" Start="120.750" Num="1"/>
        </TRACK>
    </COLLECTION>
    <PLAYLISTS>
        <NODE Type="0" Name="ROOT" Count="2">
            <NODE Name="Electronic" Type="1" Entries="2">
                <TRACK Key="1"/>
                <TRACK Key="2"/>
            </NODE>
            <NODE Name="Favorites" Type="1" Entries="1">
                <TRACK Key="2"/>
            </NODE>
        </NODE>
    </PLAYLISTS>
</DJ_PLAYLISTS>
```

## Conclusion

The Rekordbox XML format provides a robust, portable representation of DJ library data. While lacking official documentation, this reverse-engineered specification enables reliable parsing and generation of Rekordbox-compatible XML files. The format's simplicity and text-based nature make it ideal for backup, migration, and integration scenarios.

Understanding the hierarchical structure, attribute semantics, and encoding requirements allows developers to build compatible tools that can seamlessly exchange data with Rekordbox and other DJ software platforms that support this de facto standard format.