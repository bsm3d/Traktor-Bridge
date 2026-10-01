# Traktor Bridge 3.2 - Developer documentation

> The source code is not published. File and module names below are given to explain how the
> program is organised, they are not files of this repository.

This document covers how Traktor Bridge is built and what I know about the formats it reads
and writes, the Pioneer USB export above all. Facts checked against keys written by rekordbox
and played on a CDJ-2000NXS2 are marked **[verified]**. Facts taken from public documentation
and not yet confirmed on real files are marked **[published]**.

## Contents

1. [Why Traktor Bridge](#1-why-traktor-bridge)
2. [Research method and legal basis](#2-research-method)
3. [Architecture](#3-architecture)
4. [Data model](#4-data-model)
5. [Sources](#5-sources)
6. [File exports](#6-file-exports)
7. [rekordbox XML](#7-rekordbox-xml)
8. [CDJ USB export](#8-cdj-usb-export)
9. [Audio analysis](#9-audio-analysis)
10. [Portable build and command line](#10-portable-build-and-command-line)
11. [References](#11-references)

---

## 1. Why Traktor Bridge

I have played with Traktor for more than twenty years and I keep running into CDJ booths. I
wanted a simple tool, easy to use on any operating system, to take my playlists to those
players. DJs who paid for their CDJs should be able to play the playlists they sometimes built
over years in another program, without redoing them. Pioneer has made real
efforts with the newer open library formats, but the CDJ-2000NXS2 does not support them: one
more form of obsolescence for hardware that still works perfectly.

Traktor Bridge writes the USB key the player expects, straight from the collection you
already have. The name comes from the first version, which only read Traktor. It now reads
Traktor, rekordbox XML, VirtualDJ, Serato, Mixxx and M3U playlists.

## 2. Research method

I did not reverse engineer the players. I worked by trial and error, closer to fuzzing than to
disassembly.

I started from the Deep Symmetry documentation (crate-digger, beat-link) and every other
source I could find on the rekordbox formats. Many times I thought I had found the right
document, and many times I had not. A lot of what exists on the subject is outdated, belongs
to projects that never reached a working key, contains wrong information, or worse, was
invented by AI tools and reads convincingly. I kept only what several independent sources
agreed on and treated it as a hypothesis, never as a fact.

To test those hypotheses I exported keys with rekordbox itself as golden samples: the same
tracks, the same playlists, exported by rekordbox and by my own code. From there I rebuilt each
file format and ran tens, then hundreds of differential comparisons, byte by byte, until my
files and rekordbox's matched where the players care. The player and rekordbox were the only
judges: a key rekordbox opens and the CDJ plays is right, anything else is not.

I also captured the network traffic of the players (Pro DJ Link). The IP layer and the DJ Link
packets tell a lot about what a player reads from a USB key and when, which helped to know what
to look at in the files.

For the binary files I wrote my own analysis tools in Python, portable across systems: PDB
and ANLZ parsers, a differential comparator and a USB key validator. They only ever looked at
data files, the files rekordbox writes on a key, never at program code.

A word on the firmware. Studying the CDJ firmware to understand the USB format is useless.
Decompiling it is legally restricted, and it is a waste of time anyway: Pioneer protected it
well, with layers of compression and encryption. Anyone who wants to write their own tool for
CDJ USB keys should work from exported keys, as I did, and leave the firmware alone.

### Legal basis

Traktor Bridge is an interoperability tool, built the way European law allows. This is my
understanding of it, not legal advice.

- File formats are not protected by copyright. The Court of Justice of the EU ruled in 2012
  (SAS Institute v World Programming, C-406/10) that the functionality of a program and the
  format of its data files are not protected. Writing an `export.pdb` or ANLZ files a player
  can read is interoperability, not copying.
- The lawful user of a program may observe, study and test how it works (Directive
  2009/24/EC, article 5.3). Exporting keys with rekordbox, comparing the files and capturing
  the traffic of my own players is exactly that. No program was decompiled.
- A licence cannot take those rights away: article 8 of the same directive voids contract
  terms that contradict them.
- Traktor Bridge ships no Pioneer code, no Pioneer file and no audio. The few files only
  rekordbox writes (player settings, menu pages) are taken from each user's own rekordbox
  export, and the trademarks are only used to describe compatibility.

---

## 3. Architecture

```
main.py                        launcher
traktor_bridge/
  __init__.py                  name, version, links
  app.py                       start up: logging, GUI, or --export without a window
  settings.py                  traktor_bridge.json next to the program, cache folder
  model.py                     Track, Cue, Node and tree helpers
  keys.py                      one key table for every notation
  tags.py                      artwork and embedded tags (ID3, FLAC, MP4), no dependency
  sources/                     one reader per format, detect() and load()
    nml.py rbxml.py vdj.py serato.py mixxx.py m3u.py
  export/
    __init__.py                run(format, ...), the single entry point
    files.py                   FAT32 names, copies (verified, sequential on a USB key)
    common.py                  audio copy shared by the file exports, XML output
    rbxml.py m3u.py nml.py     file exports
    cdj/
      devicesql.py             pages, rows and strings of export.pdb
      native.py                loader of the C++ core (native/tbcore.cpp), None when absent
      pdbwrite.py              tables: tracks, artists, albums, keys, playlists...
      pdbread.py               export.pdb reader
      anlz.py                  ANLZ0000.DAT / .EXT
      analysis.py              audio decoding and waveform bands
      usb.py                   complete key export
      reference.py             player files imported from the user's own rekordbox export
  ui/                          main window, details, player, timeline, dialogs
build.py Build.bat traktor_bridge.spec   portable build
```

A few rules hold everywhere:

- One model. Every source converts to `Track` / `Node` on the way in, every export converts
  on the way out.
- A track shared by several playlists is one `Track` object, so a relocation or a cue edit is
  seen everywhere.
- No tag library. `tags.py` reads ID3 (including the ID3 chunk of AIFF and WAV files), FLAC and
  MP4 itself, soundfile gives the duration when a source has none.
- Heavy work stays off the GUI thread: loading and export run in a QThread, the ANLZ analysis
  in separate processes.

---

## 4. Data model

Units are fixed once in `model.py`, sources convert to them, exports convert from them.

| Field | Unit |
| --- | --- |
| `duration` | seconds |
| `Cue.start`, `Cue.length`, `grid` | milliseconds |
| `bitrate` | kbps |
| `size` | bytes |
| `rating` | 0 to 5 |
| `key` | Traktor key index 0-23 (0-11 majors from C, 12-23 minors from Cm) |
| `color` | rekordbox colour id 1-8 (pink, red, orange, yellow, green, aqua, blue, purple), 0 = none |
| dates | ISO `YYYY-MM-DD` |

A cue keeps the Traktor kinds (`CUE, FADE_IN, FADE_OUT, LOAD, GRID, LOOP`). `hotcue` is 0-7 for
pads A-H and -1 for a memory cue, a loop has `length > 0`. The beatgrid is not a cue:
`Track.grid` holds the first beat in ms, `Track.bpm` the tempo.

`keys.py` maps each index to its rekordbox name (flats), Open Key and Camelot. `parse()`
accepts any of them, sharps, `minor` / `min` suffixes and `08A` as VirtualDJ writes it.

---

## 5. Sources

`sources.detect(path)` picks the reader:

| File | Reader |
| --- | --- |
| `.nml`, XML containing `<NML` | nml |
| XML containing `<DJ_PLAYLISTS` | rbxml |
| XML containing `<VirtualDJ_Database`, `.vdjfolder` | vdj |
| `database V2`, `.crate` | serato |
| `.sqlite` / `.db` with a `track_locations` table | mixxx |
| `.m3u`, `.m3u8` | m3u |

Every reader takes an optional music folder: a file that is not where the collection says is
looked up there by name, sub-folders included. Only missing files are relocated.

### Traktor NML [verified]

- Tracks are keyed by `VOLUME + DIR + FILE`, the same key the playlists use in `PRIMARYKEY`.
- `DIR` uses `/:` as separator. On macOS `VOLUME` is the disk name.
- `INFO`: `BITRATE` in bps, `FILESIZE` in KB, `RANKING` 0-255 (divided by 51), `IMPORT_DATE`
  written `2026/9/28`, `COLOR` 1-7 mapped to the rekordbox colours.
- `MUSICAL_KEY VALUE` is the key index. `CUE_V2 TYPE 4` is the grid anchor, `HOTCUE` 0-7 or -1,
  `START` and `LEN` in ms.
- Smartlists are listed, their query is not evaluated.

### rekordbox XML [verified]

See [section 7](#7-rekordbox-xml), the reader and the writer share the same mapping.

### VirtualDJ [published]

- `Documents/VirtualDJ/database.xml`, one `Song` per track with `Tags`, `Infos`, `Comment`,
  `Scan` and `Poi` children.
- `Scan Bpm` is the time between two beats in seconds: bpm = 60 / value.
- Grid anchor: `Poi Type="beatgrid" Pos` in seconds, or `Scan Phase` (same value) with the
  fluid beatgrid of VirtualDJ 2026.
- Hot cues: `Poi` without `Type` (or `Type="cue"`) with `Num` 1-8 for pads A-H, higher numbers
  become memory cues. Saved loops: `Type="loop"`, `Size` read as a length in beats.
  `automix`, `remix` and `action` points are skipped.
- Playlists: `Playlists/*.m3u` and `Folders/**/*.vdjfolder`, the folder tree on disk becomes
  the playlist tree. A single playlist can be opened on its own.

### Serato DJ [published]

- Library `_Serato_/database V2`, crates `_Serato_/Subcrates/*.crate`, `Parent%%Child.crate`
  for a nested crate.
- Record format: 4 character ASCII tag, big-endian u32 length, payload. Tags starting with `o`
  nest, `t` and `p` are UTF-16BE text, `u` / `s` 32 bit integers, `b` a byte. Useful fields:
  `pfil` / `ptrk` path, `tsng` title, `tart` artist, `talb`, `tgen`, `tbpm`, `tkey`, `tlen`
  (`05:23.42`), `tbit` (`320.0kbps`), `tsmp` (`44.1k`), `uadd` (unix time).
- Paths are relative to the root of the drive holding `_Serato_`: `C:\` for the one in Music,
  `E:\` for a key, `/` or `/Volumes/Name` on a Mac.
- Cues, loops and the beatgrid live in the audio files: ID3 GEOB objects `Serato Markers2` and
  `Serato BeatGrid` in MP3, AIFF and WAV, base64 Vorbis comments `SERATO_MARKERS_V2` and
  `SERATO_BEATGRID` in FLAC. MP4 tags are not read yet.
- `Markers2`: `01 01`, then base64 (no padding, a line feed every 72 characters) that decodes
  to `01 01` and entries of (NUL terminated name, u32 length, payload). `CUE`: slot at byte 1,
  position u32 ms at byte 2, RGB colour at bytes 7-9, UTF-8 name from byte 12. `LOOP`: start
  and end u32 ms at bytes 2 and 6, name from byte 20. Serato loops have their own slots, so
  they become memory loops and pads A-H stay with the cues.
- `BeatGrid`: `01 00`, u32 marker count, 8 byte markers (float position in seconds and u32
  beats to the next marker, the last one float position and float bpm), one trailing byte.

### Mixxx [published]

`mixxxdb.sqlite`, opened read only. `key_id` 1-24 follows the Traktor order. Cue positions are
interleaved stereo samples: ms = position / (2 x sample rate) x 1000. Playlists with
`hidden = 0` only (the others are Auto DJ and the history), crates go into a Crates folder.

### M3U / M3U8

UTF-8 with or without BOM, or the Windows code page for old `.m3u` files. `#EXTINF` gives
duration, artist and title, relative paths are resolved from the playlist folder, `file://`
URLs are accepted.

---

## 6. File exports

`export.run(format, nodes, out, cfg)` returns a `Report` (tracks, missing files, errors,
output path). No export ever writes back to the source collection.

Audio copies (`files.copy_all`) go to `Contents/Artist/Album/file`. Names are made FAT32 safe
with accents kept, duplicates are numbered case-insensitively, each copy is written to `.part`
then renamed and hashed on the way. A file already there with the same size is not copied
again, unless the export is verified: then it has to match the source byte for byte. On a removable drive files are copied one at a
time, which is faster on flash memory than parallel writes, and the progress shows the speed
and the time left.

- M3U8: one file per playlist under `Playlists/`, folders become sub-folders, relative paths
  when the audio is copied along.
- Traktor NML: version 19, `LOCATION` split the way Traktor does, grid written back as
  `CUE_V2 TYPE 4`, smartlists kept with their query.
- rekordbox XML: see the next section.

### Checksums

Every export writes `traktor_bridge_checksums.json` at its root (`export/manifest.py`):

```json
{"format": 1, "program": "Traktor Bridge 3.2", "created": "2026-09-30T12:00:00",
 "algorithm": "sha256",
 "files": {"Contents/Artist/Album/track.mp3": {"size": 9000000, "mtime": 1790000000, "sha256": "..."}},
 "seal": "sha256 of the files object, compact JSON, sorted keys"}
```

- Paths are relative to the export root, with `/`.
- Audio is hashed while it is copied, the ANLZ files, artwork and M3U from the bytes written:
  building the manifest costs no extra read. A file left in place by a later export keeps its
  entry when its size and time did not change (2 seconds of tolerance, FAT).
- The previous manifest is read then removed when an export starts, a cancelled export leaves
  none rather than an outdated one. The new one is written atomically at the end.
- `manifest.verify(root)` reads every listed file back. A manifest whose seal does not match is
  refused. With `verify_copy`, `export.run` runs it right after the export.
- Every file Traktor Bridge writes goes through a temporary file and a rename, the analysis
  cache included, and a cached ANLZ file is used only when its length matches its PMAI header.

---

## 7. rekordbox XML

The XML is a software import: rekordbox reads it, analyses the audio again and builds its own
database, so no binary constraint applies. It is the way to go when you want rekordbox to do
the analysis, the USB export is the way to go when you want a key ready without rekordbox.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="Traktor Bridge" Version="3.2" Company="..."/>
  <COLLECTION Entries="N">
    <TRACK TrackID="1" Name="..." Artist="..." ... Location="file://localhost/C:/Music/a.mp3">
      <TEMPO Inizio="0.068" Bpm="121.90" Metro="4/4" Battito="1"/>
      <POSITION_MARK Name="Intro" Type="0" Start="1.500" Num="0" Red="40" Green="226" Blue="20"/>
      <POSITION_MARK Name="Build" Type="4" Start="96.000" End="104.000" Num="-1"/>
    </TRACK>
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT" Count="1">
      <NODE Name="Friday" Type="1" KeyType="0" Entries="1">
        <TRACK Key="1"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
```

### TRACK attributes

| Attribute | Value |
| --- | --- |
| `TrackID` | 1..N, the key playlists refer to |
| `Name`, `Artist`, `Album`, `Genre`, `Label`, `Remixer`, `Composer`, `Comments` | text |
| `Kind` | `MP3 File`, `M4A File`, `FLAC File`, `WAV File`, `AIFF File` |
| `Size` | bytes |
| `TotalTime` | seconds |
| `AverageBpm` | `%.2f` |
| `Tonality` | rekordbox key name (`Am`, `Dbm`...) |
| `Rating` | 0, 51, 102, 153, 204, 255 |
| `Colour` | `0xRRGGBB` of one of the 8 rekordbox colours |
| `DateAdded` | `YYYY-MM-DD` |
| `BitRate`, `SampleRate`, `PlayCount`, `Year`, `TrackNumber`, `DiscNumber` | numbers |
| `Location` | `file://localhost/` + absolute path, `/` separators, URL encoded except `/` and `:` |

`TEMPO Inizio` is the first beat in seconds, `Battito="1"` makes it the downbeat. One `TEMPO`
element describes a constant grid.

### POSITION_MARK

| Attribute | Meaning |
| --- | --- |
| `Type` | 0 cue, 1 fade-in, 2 fade-out, 3 load, 4 loop |
| `Num` | 0-7 hot cue A-H, -1 memory cue or memory loop |
| `Start`, `End` | seconds, `%.3f`, `End` only for a loop |
| `Red`, `Green`, `Blue` | hot cue colour |

### PLAYLISTS

`NODE Type="0"` is a folder (`Count` = direct children), `NODE Type="1"` a playlist
(`Entries` = tracks). `KeyType="0"` means the `TRACK Key` values are TrackIDs, `KeyType="1"`
that they are locations. The root is always `NODE Type="0" Name="ROOT"`.

---

## 8. CDJ USB export

Target: CDJ-2000NXS2 and the players reading a rekordbox 6 export. Everything in this section
is **[verified]**.

### Key layout

```
Contents/Artist/Album/file              every level cut at 48 characters
PIONEER/rekordbox/export.pdb
PIONEER/USBANLZ/Pxxx/xxxxxxxx/ANLZ0000.DAT and .EXT
PIONEER/Artwork/00001/aN.jpg (80 px) and aN_m.jpg (240 px)
PIONEER/MYSETTING.DAT, MYSETTING2.DAT, DJMMYSETTING.DAT, DEVSETTING.DAT
```

- `Contents` and `PIONEER` sit side by side at the root of the key.
- FAT32 or exFAT: the players show NO DISK on an NTFS key.
- The player settings files and four `export.pdb` pages (columns, the two menu tables and an
  empty history) are only written by rekordbox. Traktor Bridge does not ship them: each user
  imports them once from a key exported by their own rekordbox (`export/cdj/reference.py`,
  stored in `%LOCALAPPDATA%/TraktorBridge/rekordbox_reference`). Empty settings give
  "MY SETTINGS DATA NOT FOUND". `exportExt.pdb` and `RBFLTR.DAT` are not needed.
- The ANLZ folder is a hash of the `/Contents/...` path, computed exactly as rekordbox does:

```python
h = 0
for c in usb_path:
    u = ord(c) & 0xFFFF
    h = ((h * 0x5BC9 + u) * 0x93B5 + u) & 0xFFFFFFFF
r = h % 200003
p = (r & 1) | (r >> 1 & 2) | (r >> 4 & 4) | (r >> 4 & 8) | (r >> 5 & 0x10) | (r >> 8 & 0x20) | (r >> 10 & 0x40)
folder = f"/PIONEER/USBANLZ/P{p:03X}/{r:08X}"
```

### export.pdb, file

- 4096 byte pages, little-endian. Page 0: `[0, 4096, 20, next_unused, 5, sequence, 0]`, then
  20 table pointers `{type, empty_candidate, first_page, last_page}`.
- Table `t`: index page at `1 + 2t`, first data page at `2 + 2t`, overflow pages appended at the
  end of the file. An empty table only has its index page and its `empty_candidate` points to
  `2 + 2t`. The other `empty_candidate` values are page numbers past the end of the file,
  `next_unused` follows them.
- The header sequence must be higher than the sequence of every page, or rekordbox reports the
  library as corrupt.

### export.pdb, pages

Page header (0x28 bytes): `0x04` index, `0x08` type, `0x0C` next page, `0x10` sequence,
`0x18` 24 bit packed count `n | (n << 13)` (row slots, live rows), `0x1B` flags, `0x1C` free
space, `0x1E` used space, `0x20` `u5`, `0x22` `nrl`, `0x24` `u6`, `0x26` `u7`.

- Data page: flags `0x24`, `0x34` for Tracks and History. `u5 + nrl` = row count, a fresh file
  writes `u5 = n`, `nrl = 0`.
- Free space is exact: `4056 - used - index`, the row index costing 36 bytes per full group of
  16 rows and `4 + 2 x remainder` for the last group.
- Row index at the end of the page, in groups of 16: offsets in reverse order, then a u16 mask
  of present rows, then a u16 mask of the rows touched by the last write (equal to the first in
  a fresh file).
- Index page: flags `0x64`, `u5 = nrl = 0x1FFF`, `u6 = 1004`, `u7 = 1` when it has entries.
  Body: page index, first data page, `0x03FFFFFF`, 0, u16 entry count, u16 `0x1FFF`, entries
  `page << 3`, then `f8 ff ff 1f` filler up to 20 trailing zero bytes. Only Tracks and History
  have entries. The page holds 1004 entries, the players follow the page chain for the data
  pages beyond.
- Columns (16), types 17 and 18 and History (19) hold the player menu configuration and are
  the same in every rekordbox export: they are copied from the user's reference key.

### export.pdb, strings

- Empty: `03`. Short ASCII (up to 126): `((n + 1) << 1) | 1` then the bytes. Long ASCII: `40`,
  u16 total length (n + 4), `00`. UTF-16LE: `90`, u16 (2n + 4), `00`.
- A long string starts on a 4 byte boundary inside its row, rekordbox pads with zeros before it.

### export.pdb, rows

Track row, 0x88 fixed bytes then 21 strings:

| Offset | Field |
| --- | --- |
| `0x00` | subtype `0x24` |
| `0x02` | index shift (slot in the page x 0x20) |
| `0x04` | `0x000C0700` |
| `0x08` | sample rate |
| `0x10` | file size |
| `0x14` | rekordbox internal checksum, 0 is accepted |
| `0x18` | `0xC25930BF` |
| `0x1C` | artwork id |
| `0x20` | key id |
| `0x30` | bitrate kbps |
| `0x34` | track number |
| `0x38` | tempo x 100 |
| `0x3C`, `0x40`, `0x44` | genre, album, artist ids |
| `0x48` | track id |
| `0x4C`, `0x4E`, `0x50` | disc, play count, year |
| `0x52` | 16 (bits) |
| `0x54` | duration in seconds |
| `0x56` | 41 |
| `0x58`, `0x59` | colour, rating 0-5 |
| `0x5A` | file type: mp3 1, m4a 4, flac 5, wav 11, aiff 12 |
| `0x5C` | 3 |
| `0x5E` | 21 u16 string offsets |

Strings: `[2]` and `[3]` = `2`, `[6]` and `[7]` = `ON`, `[10]` date added, `[14]` ANLZ path,
`[15]` analysis date, `[16]` comment, `[17]` title, `[19]` file name, `[20]` path on the key.

The other tables:

| Table | Row |
| --- | --- |
| Artist | `0x60`, index shift, u32 id, `03`, u8 name offset |
| Album | `0x80`, index shift, 0, artist id, id, 0, `03`, u8 name offset |
| Genre, Label | u32 id, name |
| Key | u32 id, u32 id, rekordbox key name |
| Colour | 0, u8 id, u16 id, 0, name |
| Playlist tree | parent, 0, sort order, id, is folder, name |
| Playlist entry | position (1..n), track id, playlist id |
| Artwork | u32 id, `/PIONEER/Artwork/00001/aN.jpg` |

Artist, album and key ids follow the order of first use, the way rekordbox numbers them,
not a fixed table.

### ANLZ

Big-endian. `PMAI` header: header length 28, total length, then `1, 0x10000, 0x10000, 0`.
Every section: tag, header length, total length.

- `.DAT`: `PPTH` (UTF-16BE path with a NUL), `PVBR`, `PQTZ`, `PWAV`, `PWV2`, `PCOB` hot cues,
  `PCOB` memory cues.
- `.EXT`: `PPTH`, `PWV3`, `PCOB` x2, `PCO2` x2, `PWV5`, `PWV4`. `PQT2`, `PSSI` and the `.2EX`
  file only matter to the CDJ-3000 and are not written.
- `PVBR`: the last value is the total number of samples. The 400 index values before it can
  stay at 0.
- `PQTZ`: `0, 0x80000, n`, then per beat u16 beat in bar (1-4), u16 tempo x 100, u32 ms. Beats
  are laid from the grid anchor, which is beat 1.
- `PWAV` has 400 columns, `PWV2` 100, `PWV3` and `PWV5` 150 per second, `PWV4` 1200.
  `PWAV` / `PWV3`: `whiteness << 5 | height` (0-31). `PWV5`: `r << 13 | g << 10 | b << 7 |
  height << 2`. `PWV4`: 6 bytes per column, the players draw bytes 3-5 (red, green, blue).
- `PCPT` (56 bytes): `hot_cue` 0 for a memory cue, 1-8 for A-H, type 1 cue or 2 loop, time and
  loop end in ms. `PCP2` adds the name in UTF-16BE.

---

## 9. Audio analysis

Traktor, and the other sources, already did the musical analysis: bpm, grid, key and cues come
from the collection. Only the waveforms need the audio.

`analysis.Audio` decodes each track once with soundfile, block by block into one reused buffer.
Loading a whole track at once allocates about 150 MB of fresh memory per file, and on Windows
those page faults serialise between processes. Mono and a quarter of the sample rate are
computed in the same pass (11 kHz for a CD rip, plenty for a picture of the sound). Two second
order Butterworth filters split low (below 200 Hz) and high (above 2500 Hz), mid is what
remains, and peaks are taken at 150 columns per second, the overviews coming from there.

The analysis runs in up to 8 processes. Beyond that they fight over memory bandwidth instead of
helping. Traktor Bridge is not a live application, so it can use the whole machine for the
job. Results are cached in `%LOCALAPPDATA%/TraktorBridge/anlz`, keyed on the audio file (size,
date), its path on the key, bpm, grid, cues and `ANLZ_VERSION`, to be raised whenever the
generator changes.

On a recent desktop, 121 AIFF tracks (8 GB) are exported in under 5 seconds, audio copy
included. On a USB key the write speed of the key is the limit.

---

## 10. Portable build and command line

`Build.bat` creates a clean venv and runs `build.py`, `python build.py` uses the current Python.
The result is `dist/TraktorBridge/` (windowed exe, `runtime/` folder) and
`dist/TraktorBridge-3.2-win64.zip`. No `.py` file ships, the modules are compiled into the PYZ,
unused Qt parts are removed and librosa is left out. `build.py` renames `dist/` and `build/`
before clearing them and stops if a running copy of the app holds them.

The core (`tags.py`, `sources/`, `export/cdj/`) is compiled to native modules first:
`compile_core.py` copies the package to `build/stage`, turns each core module into a `.pyd`
with Nuitka (`pip install nuitka`, it fetches MinGW64 on the first run) and PyInstaller
then packs that staged copy. The sources in the repository are never touched, the tests
run unchanged against `build/stage` (`PYTHONPATH=build/stage`, from another folder).
Two rules came out of it: modules are compiled one at a time (parallel Nuitka runs shared
caches and produced modules that crash on import), and no module may carry the name of a
standard module (`pdb.py` became `pdbwrite.py`). The `__init__.py` files stay Python, and
PyInstaller cannot see imports inside a `.pyd`, so `traktor_bridge.spec` lists them by hand.

Two pieces also exist in C++, `native/tbcore.cpp`, built by `compile_core.py` into
`tbcore.dll` next to `export/cdj/native.py` (ctypes, plain C interface, no exception crosses it):
the page layout of `export.pdb` (`tb_pdb_build`, same as `devicesql.build_py`) and the waveform
bands (`tb_fold`, `tb_bands`, same as `analysis.fold` and `Audio.bands_py`). The Python versions
stay as the reference and the fallback: without the DLL, or with `TB_PURE_PYTHON=1`, they run.
`tests/test_native.py` compares both (the page file byte for byte, the bands to the last float32
bit) and an export made by the built exe is identical to a pure Python one. The compiler is
`g++` or `clang++` if present, `TB_CXX`, or the zig that Nuitka downloaded. Built with
`-ffp-contract=off`: a fused multiply-add would change the last bit of the filters.
`python compile_core.py --native` builds only the DLL next to the sources.

`multiprocessing.freeze_support()` and the `__main__` guard are required: the analysis
processes start the exe again.

Settings and log live next to the exe, the cache in `%LOCALAPPDATA%/TraktorBridge`.

```
TraktorBridge.exe --export COLLECTION OUTPUT [--format FORMAT] [--music FOLDER] [--reference KEY]
TraktorBridge.exe --verify OUTPUT
```

`--reference` imports the player files from a key exported by rekordbox, once. FORMAT is `CDJ/USB` (default), `Rekordbox XML`, `M3U` or `Traktor NML`. The report goes to
`traktor_bridge.log`, the exit code is 0 when nothing failed. `--verify` exits with 1 when a
file is damaged or missing. The exe has no console, use `start /wait` from a prompt.

---

## 11. References

- Deep Symmetry, crate-digger and beat-link: rekordbox PDB and ANLZ formats, Pro DJ Link.
- openboxxx: a minimal CDJ export from Mixxx.
- Mixxx wiki: VirtualDJ database, Serato database and crates.
- Holzhaus/serato-tags: Serato Markers2 and BeatGrid.
- Pioneer DJ: rekordbox XML import and export.
