# Traktor Bridge 3.5.1 - Developer documentation

This document covers how Traktor Bridge is built and what I know about the formats it reads
and writes, the Pioneer USB export above all.

Facts checked against keys written by rekordbox and played on a CDJ-2000NXS2 are marked
**[verified]**. Facts taken from public documentation and not yet confirmed on real files are
marked **[published]**.

## Contents

1. [Why Traktor Bridge](#1-why-traktor-bridge)
2. [Research method and legal basis](#2-research-method)
3. [Architecture](#3-architecture)
4. [Data model](#4-data-model)
5. [Sources](#5-sources)
    - [Recipe: Reading Traktor NML](#recipe-reading-traktor-nml)
    - [Recipe: Reading rekordbox XML](#recipe-reading-rekordbox-xml)
    - [Recipe: Reading VirtualDJ](#recipe-reading-virtualdj)
    - [Recipe: Reading Serato DJ](#recipe-reading-serato-dj)
    - [Recipe: Reading Mixxx](#recipe-reading-mixxx)
    - [Recipe: Reading M3U and M3U8](#recipe-reading-m3u-and-m3u8)
    - [Recipe: Reading a music folder](#recipe-reading-a-music-folder)
    - [Recipe: Reading a Traktor Bridge project](#recipe-reading-a-traktor-bridge-project)
6. [File exports](#6-file-exports)
    - [Recipe: Copying audio files](#recipe-copying-audio-files)
    - [Recipe: Writing M3U8](#recipe-writing-m3u8)
    - [Recipe: Writing Traktor NML](#recipe-writing-traktor-nml)
    - [Recipe: Writing the checksum manifest](#recipe-writing-the-checksum-manifest)
7. [rekordbox XML](#7-rekordbox-xml)
    - [Recipe: Writing rekordbox XML](#recipe-writing-rekordbox-xml)
8. [CDJ USB export](#8-cdj-usb-export)
    - [Recipe: CDJ key, layout and file names](#recipe-cdj-key-layout-and-file-names)
    - [Recipe: CDJ key, export.pdb](#recipe-cdj-key-exportpdb)
    - [Recipe: CDJ key, ANLZ files](#recipe-cdj-key-anlz-files)
    - [Recipe: CDJ key, artwork](#recipe-cdj-key-artwork)
    - [Recipe: CDJ key, settings files](#recipe-cdj-key-settings-files)
    - [Recipe: CDJ key, order of writing](#recipe-cdj-key-order-of-writing)
9. [Audio analysis](#9-audio-analysis)
    - [Recipe: Writing a ZIP backup](#recipe-writing-a-zip-backup)
    - [Recipe: Formatting a key as FAT32](#recipe-formatting-a-key-as-fat32)
10. [Portable build and command line](#10-portable-build-and-command-line),
    [layered validation and operational safeguards](#layered-validation-and-operational-safeguards)
11. [References](#11-references)

---

## 1. Why Traktor Bridge

Traktor Bridge was designed for users of Traktor, the DJ software from Native Instruments.
It is a central hub: the leading DJ programs exchange playlists through it, and with them the
hundreds of hours of work it takes to build those playlists. It imports your collections into
Traktor, and it takes your Traktor collection out to the other programs and to the players.

Traktor Bridge is not a competitor of Traktor. It is not a DJ program, it does not mix, and it
does not replace any of the programs it connects. It works alongside them.

I have played with Traktor for more than twenty years and I keep running into CDJ booths. I
wanted a simple tool, easy to use on any operating system, to take my playlists to those
players.

DJs who own CDJs should be able to play the playlists they built, sometimes over several years,
in another program, without redoing them. Pioneer's newer open library formats are made for its
recent players. The CDJ-2000NXS2 is a player that still performs very well, and it reads the
rekordbox USB export format. Traktor Bridge writes that format.

Traktor Bridge is a bridge between Traktor, many other DJ programs and the CDJ players.
Traktor, rekordbox, VirtualDJ, Serato and Mixxx are complete programs for mixing, effects,
analysis and library management. Traktor Bridge sits alongside them.

It also works on its own. It builds playlists from a music library and reorders them. It places
cues and loops (real time drag and drop, a precise cue editor, keys A-H). It formats USB keys
safely for the players. It copies with checksums and several safeguards (see sections 6 and 8)
to make the copy as reliable as possible.

Traktor Bridge writes the USB key the player expects, straight from the collection you already
have. The name comes from the first version, which only read Traktor. It now reads Traktor,
rekordbox XML, VirtualDJ, Serato, Mixxx and M3U playlists.

## 2. Research method

I did not study the players or their firmware. I worked from exported keys, by trial and error:
export, compare the files, test on a player, start again.

I started from the research published by Deep Symmetry (crate-digger, beat-link) and by the
openboxxx project, then from every other source I could find on the rekordbox formats. Their
work made this project possible. Traktor Bridge itself is written from scratch, in Python.

Public sources do not always agree, and some are out of date or incomplete. More than once a
document I trusted turned out to be wrong. Some texts written by AI tools read convincingly and
are not reliable.

I kept only what several independent sources agreed on, and I treated it as a hypothesis, never
as a fact.

To test those hypotheses I exported keys with rekordbox itself as golden samples: the same
tracks and the same playlists, exported by rekordbox and by my own code. From there I rebuilt
each file format and ran tens, then hundreds of differential comparisons, byte by byte, until my
files and rekordbox's matched where the players care.

The player and rekordbox were the only judges. A key rekordbox opens and the CDJ plays is
right, anything else is not.

I also captured the network traffic of the players (Pro DJ Link). The IP layer and the DJ Link
packets tell a lot about what a player reads from a USB key and when, which helped me decide
what to look at in the files.

For the binary files I wrote my own analysis tools in Python, portable across systems: PDB and
ANLZ parsers, a differential comparator and a USB key validator. They only ever looked at data
files, the files rekordbox writes on a key, never at program code.

Anyone who wants to write their own tool for CDJ USB keys can do the same: work from keys
exported by rekordbox and compare the files.

### Legal basis

Traktor Bridge is an interoperability tool, built the way European law allows. This is my
understanding of it, not legal advice.

- File formats are not protected by copyright. The Court of Justice of the EU ruled in 2012
  (SAS Institute v World Programming, C-406/10) that the functionality of a program and the
  format of its data files are not protected. Writing an `export.pdb` or ANLZ files a player
  can read is interoperability, not copying.
- The lawful user of a program may observe, study and test how it works (Directive 2009/24/EC,
  article 5.3). Exporting keys with rekordbox, comparing the files and testing the result on my
  own players is exactly that. No program was decompiled.
- A licence cannot take those rights away: article 8 of the same directive voids contract terms
  that contradict them.
- Method: black box only. The format was worked out by exporting keys, comparing the data files
  byte by byte and testing the result on real players. No program, firmware or library of
  Pioneer was disassembled, decompiled or copied, and no code or resource of rekordbox is in
  this repository. Anyone contributing must follow the same rule.

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
      native.py                loader of the C++ core (core/tbcore.cpp), None when absent
      pdbwrite.py              tables: tracks, artists, albums, keys, playlists...
      pdbread.py               export.pdb reader
      anlz.py                  ANLZ0000.DAT / .EXT
      analysis.py              audio decoding and waveform bands
      usb.py                   complete key export
  fat32.py drives.py           FAT32 writer, removable drive listing, privileged format helper
  ui/                          main window, details, player, timeline, dialogs, formatter,
                               zoomwave (zoomable waveform shared by the player and the timeline),
                               worker (background jobs, stopped at exit)
build.py Build.bat traktor_bridge.spec   portable build
```

A few rules hold everywhere.

- One model. Every source converts to `Track` / `Node` on the way in, every export converts on
  the way out.
- A track shared by several playlists is one `Track` object, so a relocation or a cue edit is
  seen everywhere.
- No tag library. `tags.py` reads ID3 (including the ID3 chunk of AIFF and WAV files), FLAC and
  MP4 itself. soundfile gives the duration when a source has none.
- Heavy work stays off the GUI thread. Loading and export run in a QThread, the ANLZ analysis in
  separate processes.

---

## 4. Data model

Units are fixed once in `model.py`. Sources convert to them, exports convert from them.

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
pads A-H and -1 for a memory cue. A loop has `length > 0`.

The beatgrid is not a cue. `Track.grid` holds the first beat in ms and `Track.bpm` the tempo.

`keys.py` maps each index to its rekordbox name (flats), Open Key and Camelot. `parse()` accepts
any of them, sharps, `minor` / `min` suffixes and `08A` as VirtualDJ writes it.

### From the model to the key

The CDJ export reads only these `Track` fields. Section 8 gives the byte positions.

| Track field | Where it lands |
| --- | --- |
| `title` | track row string 17 |
| `artist`, `album_artist`, `remixer`, `composer` | Artists table, ids at `0x44`, `0x2C`, `0x0C` of the track row. `album_artist` owns the Albums row. |
| `album` | Albums table, id at `0x40` |
| `genre`, `label` | Genres and Labels tables, ids at `0x3C` and `0x28` |
| `key` | Keys table (`keys.name`, flats), id at `0x20` |
| `comment` | track row string 16 |
| `added` | track row string 10, today's date when empty |
| `samplerate`, `bitrate` | `0x08` (44100 when 0), `0x30` |
| `size` | not used: the row holds the size of the file copied to the key (`0x10`) |
| `track_no`, `disc_no`, `plays`, `year` | `0x34`, `0x4C`, `0x4E`, `0x50` |
| `duration` | `0x54` in whole seconds (rounded), and the number of waveform columns |
| `bpm` | `0x38` as bpm x 100 (rounded), and the PQTZ tempo |
| `rating`, `color` | `0x59` (capped at 5), `0x58` |
| `path` | its extension picks the file type at `0x5A`, its file name is string 19 |
| `grid` | first beat of the PQTZ grid, no grid when `None` |
| `cues` | PCOB and PCO2 lists, see "Cues" in section 8 |

`gain`, `modified`, `last_played`, `locked`, `audio_id` and the project-only fields are not written
to a key.

Two helpers decide which cues reach the key. `Track.hot_cues()` returns the cues of kind `CUE`,
`LOOP` or `LOAD` with `hotcue >= 0`, sorted by slot. `Track.memory_cues()` returns the same kinds
with `hotcue < 0`, in model order. Fade-in, fade-out and grid cues are never written.

Traktor numbers its `CUE_V2 TYPE` as in `model.py` (0 cue, 1 fade-in, 2 fade-out, 3 load, 4 grid,
5 loop). rekordbox XML numbers its `POSITION_MARK Type` differently (0 cue, 1 fade-in, 2 fade-out,
3 load, 4 loop). Each format converts at its own boundary.

`Track.uid` is `audio_id` or, without one, the source path. `unique_tracks()` lists each uid once,
in the order of first appearance when the playlist tree is walked depth first. That order gives the
track ids of every export.

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
| `.json` containing `traktor-bridge-project` | project (saved work, see Editors) |
| a folder | folder (audio files read as they are) |

For `.xml` files the first 4096 bytes decide. `.json` is a project only when `traktor-bridge-project`
appears in its first 2048 bytes.

Every reader takes an optional music folder. A file that is not where the collection says is
looked up there by name, sub-folders included. Only missing files are relocated.

Every reader returns the same thing: a list of `Node` (folders and playlists) whose `Track`
objects use the units of section 4. A file larger than 1 GiB is refused before it is read (64 MiB
for an M3U, 256 MiB for a project).

A number that is not finite (`inf`, `nan`, `1e999`) or beyond 1e15 is dropped by every reader, as if
the attribute were missing. A cue or a beat grid whose position is such a number is skipped.

An XML file whose encoding label Python does not know (`encoding="TTF-8"`) is refused with a
`ValueError` by the rekordbox and VirtualDJ readers. A `.vdjfolder` with such a label is skipped,
and a Traktor file is read as UTF-8.

The recipes below follow one shape. **You need** lists the inputs, **Steps** the order of work,
**Pitfalls** what breaks and why, **Check** how to know it worked. The reference part under each
recipe keeps the field-level facts.

### Recipe: Reading Traktor NML

**You need:**

- A `collection.nml` from Traktor Pro 3 or 4 and, optionally, a music folder.
- An XML parser that rejects entities (the code uses `defusedxml`).
- The `keys.py` table and the colour map below.

**Steps:**

1. Refuse the file if it is over 1 GiB. Read the bytes and parse. If the parse fails, decode as
   UTF-8 with replacement, delete the control characters `\x00-\x08`, `\x0b`, `\x0c`, `\x0e-\x1f` and
   parse again.
2. If a music folder was given, index every audio file under it by lower case file name
   (`.mp3 .wav .flac .aiff .aif .m4a .mp4 .aac .ogg .alac`).
3. For each `COLLECTION/ENTRY` that has a `LOCATION`, build a `Track` from the attributes in the
   reference table. Build its path from `VOLUME`, `DIR` and `FILE`. Remember the playlist key
   `VOLUME + DIR + FILE`.
4. If the path does not exist, look the file name up in the music folder index and take the first
   hit.
5. Walk `PLAYLISTS/NODE` (the `$ROOT` folder). `FOLDER` becomes a folder, kept only if something
   survives below it. `PLAYLIST` becomes a playlist: each `ENTRY/PRIMARYKEY KEY` is looked up in
   the key map, and the playlist is kept only if it has tracks. `SMARTLIST` becomes a smartlist
   with its `SEARCH_EXPRESSION QUERY` text, not evaluated.

**Pitfalls:**

- Paths. `DIR` separates folders with `/:` (`/:Music/:House/:`). Replace `/:` with `/` and append
  `FILE`. A two character `VOLUME` such as `C:` is a Windows drive. Any other `VOLUME` is a macOS
  disk name: the path is `/Volumes/<VOLUME>` plus the rest when that exists, else the rest from `/`
  (the boot disk).
- Units. `BITRATE` is in bps (divide by 1000), `FILESIZE` in KB (multiply by 1024), `PLAYTIME_FLOAT`
  in seconds (`PLAYTIME` is the integer fallback), `START` and `LEN` in milliseconds, `RANKING` is
  0-255 (integer division by 51 gives 0-5).
- Dates are `2026/9/28`, without zero padding. The reader rewrites them as `2026-09-28`. The year
  of `RELEASE_DATE` is the part before the first `/`.
- Colours. `COLOR` 1-7 is Traktor's own and maps to the rekordbox ids (table below). Anything else
  is 0.
- Key. `MUSICAL_KEY VALUE` is the key index and wins. `INFO KEY` (text) is parsed with
  `keys.parse` only when no `MUSICAL_KEY` came first.
- Cues. Traktor's `TYPE` numbers are not rekordbox's: 0 cue, 1 fade-in, 2 fade-out, 3 load, 4 grid,
  5 loop. The first grid cue sets `Track.grid` and is not kept as a cue. A loop with `LEN` of 0 or
  less becomes a plain cue. `HOTCUE` is 0-7 for pads A-H and -1 for a memory cue.
- A same-named file elsewhere could be another mix, so only missing files are relocated.

**Check:** the count printed at the end is the number of collection entries that had a `LOCATION`.
Compare it with the track count Traktor shows. Export the result back with the NML writer and read
it again: the tracks, cues and grids must come out the same.

#### Traktor NML [verified]

- Tracks are keyed by `VOLUME + DIR + FILE`, the same key the playlists use in `PRIMARYKEY`.
- `DIR` uses `/:` as separator. On macOS `VOLUME` is the disk name.
- `INFO`: `BITRATE` in bps, `FILESIZE` in KB, `RANKING` 0-255 (divided by 51), `IMPORT_DATE`
  written `2026/9/28`, `COLOR` 1-7 mapped to the rekordbox colours.
- `MUSICAL_KEY VALUE` is the key index. `CUE_V2 TYPE 4` is the grid anchor, `HOTCUE` 0-7 or -1,
  `START` and `LEN` in ms.
- Smartlists are listed, their query is not evaluated.

Fields read:

| Element and attribute | Track field |
| --- | --- |
| `ENTRY TITLE`, `ARTIST`, `AUDIO_ID`, `LOCK="1"`, `MODIFIED_DATE` | `title`, `artist`, `audio_id`, `locked`, `modified` |
| `ALBUM TITLE`, `TRACK` | `album`, `track_no` |
| `INFO GENRE`, `LABEL`, `COMMENT` | `genre`, `label`, `comment` |
| `INFO REMIXER` (else `ENTRY REMIXER`), `PRODUCER` | `remixer`, `composer` |
| `INFO BITRATE`, `FILESIZE`, `PLAYTIME_FLOAT` or `PLAYTIME`, `RANKING`, `PLAYCOUNT` | `bitrate`, `size`, `duration`, `rating`, `plays` |
| `INFO COLOR`, `IMPORT_DATE`, `LAST_PLAYED`, `RELEASE_DATE`, `KEY` | `color`, `added`, `last_played`, `year`, `key` |
| `TEMPO BPM` | `bpm` |
| `MUSICAL_KEY VALUE` | `key` |
| `LOUDNESS ANALYZED_DB` | `gain` |
| `CUE_V2 NAME`, `TYPE`, `START`, `LEN`, `HOTCUE`, `COLOR` | `Cue` fields |

Traktor `COLOR` to rekordbox colour id: 1 to 2 (red), 2 to 3 (orange), 3 to 4 (yellow), 4 to 5
(green), 5 to 7 (blue), 6 to 8 (purple), 7 to 1 (pink).

### Recipe: Reading rekordbox XML

**You need:** a `DJ_PLAYLISTS` XML file (File > Export in rekordbox, or a Traktor Bridge export),
the same XML parser as for NML, optionally a music folder.

**Steps:**

1. Parse the file (size check first).
2. For each `COLLECTION/TRACK`, build a `Track` from the attributes (reference table in section 7)
   and convert `Location` to a path. Store the track under its `TrackID` and under its raw
   `Location` text.
3. Convert the first `TEMPO Inizio` (seconds) to the grid in ms. Convert each `POSITION_MARK`
   to a cue (reference below).
4. Relocate missing files through the music folder index.
5. Walk `PLAYLISTS/NODE`. `Type="0"` is a folder. Any other node is a playlist whose `TRACK Key`
   values are `TrackID`s, or raw `Location` texts when `KeyType="1"`. Drop empty folders and
   playlists.

**Pitfalls:**

- `Location` is `file://localhost/C:/x`. The path part is URL-decoded and the leading `/` before a
  drive letter is dropped, then the path is normalised. A value that does not start with `file:` is
  taken as a path.
- Seconds, not milliseconds: `Inizio`, `Start` and `End` are multiplied by 1000. A loop length is
  `End - Start`.
- `POSITION_MARK Type` 4 is a loop here, whereas Traktor's 4 is the grid.
- `Num` is 0-7 for hot cues A-H and -1 for a memory cue. The colour is read from `Red`, `Green` and
  `Blue` when all three exist, and stored as `#RRGGBB`.
- `Rating` is 0-255 in steps of 51: integer division by 51. `Colour` is `0xRRGGBB` and only the
  eight rekordbox values are recognised (section 8). The date is the first 10 characters of
  `DateAdded`.
- Only `AverageBpm` gives the tempo. The `Bpm` of `TEMPO` is not read.
- `Tonality` is parsed with `keys.parse`, which accepts the rekordbox name (`Am`, `Dbm`), sharps, Open
  Key, Camelot and forms such as `08A`, and returns the key index of section 4.
- The parser rejects XML entities and external references. The standard escapes (`&amp;`, `&lt;`) are
  decoded as usual.
- A `KeyType="1"` playlist matches the `Location` text exactly as written in the collection.
- Only the first `NODE` under `PLAYLISTS` (normally `ROOT`) is walked.

**Check:** read a file written by Traktor Bridge and compare the track count and each playlist
length with the `Entries` and `Count` attributes. Read a file exported by rekordbox and compare a
few tracks by hand.

#### rekordbox XML [verified]

See [section 7](#7-rekordbox-xml). The reader and the writer share the same mapping.

### Recipe: Reading VirtualDJ

**You need:** `database.xml` and the `Playlists` and `Folders` folders next to it (usually in
`Documents/VirtualDJ`), or one `.vdjfolder`, `.m3u` or `.m3u8` of that tree.

**Steps:**

1. Find the VirtualDJ folder: walk up from the picked file until a folder holds `database.xml`.
2. Read every `Song` of `database.xml` into a `Track` (reference below). Index the tracks by the
   case-folded `FilePath`.
3. If a single playlist was picked, read only that one and stop.
4. Otherwise read `Playlists/` and `Folders/` recursively, in case-insensitive name order. A
   `.vdjfolder` is read for its `song path` elements, an `.m3u` or `.m3u8` by line. Each file is a
   playlist named after its file stem and each directory is a folder. Add the two top folders
   `Playlists` and `Folders` when they hold something.
5. Add a final playlist `All tracks` with every `Song` of the database.

**Pitfalls:**

- `Scan Bpm` is the time between two beats in seconds, not beats per minute: bpm is
  `60 / value`. The module header of the code says the same.
- Positions (`Pos`, `Phase`) are in seconds. Multiply by 1000.
- The grid anchor is a `Poi Type="beatgrid"` or, with the fluid beatgrid of VirtualDJ 2026, the
  `Scan Phase` attribute. `Scan Phase` wins when present, otherwise the first beatgrid `Poi` is used.
- Loop `Size` is a length in beats. A loop needs a known bpm: without it the point stays a plain cue.
- Hot cues use `Num` 1-8 for pads A-H (subtract 1). Other numbers become memory cues.
- `Poi` types other than cue and loop (`automix`, `remix`, `action`) are skipped.
- `Poi Color` is `#rrggbb` or a decimal ARGB number: keep the low 24 bits.
- `Key` text (`Tags` or `Scan`) may be in any notation, including `08A`: it goes through `keys.parse`.
  The rating is `Stars`, already 0-5.
- A track that is in a playlist but not in the database is created from the playlist attributes
  (`title`, `artist`, `songlength`, `bpm`) or from the file name for an M3U.
- Relative paths inside a playlist are resolved from the playlist's folder.

**Check:** compare the track count of `All tracks` with the VirtualDJ browser, then open one
playlist and compare its order.

#### VirtualDJ [published]

- `Documents/VirtualDJ/database.xml`, one `Song` per track with `Tags`, `Infos`, `Comment`,
  `Scan` and `Poi` children.
- `Scan Bpm` is the time between two beats in seconds: bpm = 60 / value.
- Grid anchor: `Poi Type="beatgrid" Pos` in seconds, or `Scan Phase` (same value) with the fluid
  beatgrid of VirtualDJ 2026.
- Hot cues: `Poi` without `Type` (or `Type="cue"`) with `Num` 1-8 for pads A-H, higher numbers
  become memory cues. Saved loops: `Type="loop"`, `Size` read as a length in beats. `automix`,
  `remix` and `action` points are skipped.
- Playlists: `Playlists/*.m3u` and `Folders/**/*.vdjfolder`. The folder tree on disk becomes the
  playlist tree. A single playlist can be opened on its own.

Fields read:

| Element and attribute | Track field |
| --- | --- |
| `Song FilePath`, `FileSize` | `path`, `size` |
| `Tags Title`, `Author`, `Album`, `Genre`, `Label`, `Composer`, `Remix` | `title`, `artist`, `album`, `genre`, `label`, `composer`, `remixer` |
| `Tags TrackNumber`, `Year` (first 4 characters), `Stars` (capped at 5), `Key` | `track_no`, `year`, `rating`, `key` |
| `Infos SongLength`, `Bitrate`, `PlayCount`, `FirstSeen`, `LastPlay` | `duration`, `bitrate`, `plays`, `added`, `last_played` (unix times become dates) |
| `Comment` text | `comment` |
| `Scan Bpm`, `Key`, `Phase` | `bpm`, `key` (overrides `Tags Key`), `grid` |
| `Poi Type`, `Pos`, `Num`, `Name`, `Color`, `Size` | `Cue` fields |

### Recipe: Reading Serato DJ

**You need:** the `_Serato_` folder (`database V2` and `Subcrates/*.crate`), or one `.crate`; the
audio files themselves, because cues and grids live in them (`tags.py` reads the ID3 and FLAC
tags).

**Steps:**

1. Take the `_Serato_` folder (the parent of `Subcrates` when a crate was picked). The drive root
   used for paths is the drive of that folder: `E:\`, or `/` on a Mac, or `/Volumes/<Name>/` when the
   folder is under `/Volumes`.
2. Read `database V2` as records (4 character tag, big-endian u32 length, payload). Every `otrk`
   record is a track: parse its inner records and build a `Track` with the path `root + pfil`.
3. Read the crates. For each `.crate` read its `otrk` records and take `ptrk` as the path. A crate
   named `Parent%%Child.crate` is the playlist `Child` inside the folder `Parent`, to any depth.
   Without a picked crate, also add a playlist `All tracks`.
4. For every track that will be shown, relocate the file and, if it exists, read its Serato tags:
   `Serato Markers2` for cues and loops, `Serato BeatGrid` for the grid.

**Pitfalls:**

- Cues, loops and the beatgrid are not in the library. They live in the audio file: an ID3 GEOB
  object in MP3, AIFF and WAV, a base64 Vorbis comment (`SERATO_MARKERS_V2`, `SERATO_BEATGRID`) in
  FLAC. MP4 tags are not read yet. A track without a readable file has no cues.
- The Markers2 payload is base64 with no padding and a line feed every 72 characters. Remove the
  line feeds, add the `=` padding, decode, then parse. In FLAC the comment holds the whole GEOB
  object base64 encoded: find the description text and its NUL, the payload follows.
- Text tags (`t`, `p` first letter) are UTF-16BE with NULs. Integer tags (`u` unsigned, `s` signed)
  are 4 bytes big endian. `b` is one byte.
- Paths are relative to the drive that holds `_Serato_`, so the root depends on where the library
  lives (`C:\` for the one in Music, `E:\` for a key).
- Serato loops have their own slots. They become memory loops and pads A-H stay with the cues.
- `tlen` is `05:23.42` or plain seconds. `tbit` is `320.0kbps`. `tsmp` is `44.1k`.
- `tkey` goes through `keys.parse` like every other key text. Serato stores no rating in this reader, so
  the rating stays 0.

**Check:** open a track in Serato that has a hot cue and compare its position in ms with the
imported cue. Compare the first-beat time with the Serato grid marker.

#### Serato DJ [published]

- Library `_Serato_/database V2`, crates `_Serato_/Subcrates/*.crate`, `Parent%%Child.crate` for
  a nested crate.
- Record format: 4 character ASCII tag, big-endian u32 length, payload. Tags starting with `o`
  nest, `t` and `p` are UTF-16BE text, `u` / `s` 32 bit integers, `b` a byte.
- Useful fields: `pfil` / `ptrk` path, `tsng` title, `tart` artist, `talb`, `tgen`, `tbpm`,
  `tkey`, `tlen` (`05:23.42`), `tbit` (`320.0kbps`), `tsmp` (`44.1k`), `uadd` (unix time).
- Paths are relative to the root of the drive holding `_Serato_`: `C:\` for the one in Music,
  `E:\` for a key, `/` or `/Volumes/Name` on a Mac.
- Cues, loops and the beatgrid live in the audio files: ID3 GEOB objects `Serato Markers2` and
  `Serato BeatGrid` in MP3, AIFF and WAV, base64 Vorbis comments `SERATO_MARKERS_V2` and
  `SERATO_BEATGRID` in FLAC. MP4 tags are not read yet.
- `Markers2`: `01 01`, then base64 (no padding, a line feed every 72 characters) that decodes to
  `01 01` and entries of (NUL terminated name, u32 length, payload).
  - `CUE`: slot at byte 1, position u32 ms at byte 2, RGB colour at bytes 7-9, UTF-8 name from
    byte 12.
  - `LOOP`: start and end u32 ms at bytes 2 and 6, name from byte 20. Serato loops have their own
    slots, so they become memory loops and pads A-H stay with the cues.
- `BeatGrid`: `01 00`, u32 marker count, 8 byte markers (float position in seconds and u32 beats
  to the next marker, the last one float position and float bpm), one trailing byte.

How the reader uses them: a `CUE` with slot 0-7 is a hot cue, a larger slot is a memory cue; its
colour is stored as `#RRGGBB`. A `LOOP` is kept only if its end is after its start. From the
`BeatGrid`, the position of the first marker (seconds, times 1000, not below 0) is the grid, and
the bpm of the last marker is used only when the library has none.

Library fields: `tsng` title, `tart` artist, `talb` album, `tgen` genre, `tcom` comment, `tlbl`
label, `trmx` remixer, `tcmp` composer, `tbpm`, `tkey`, `tlen`, `tbit`, `tsmp` (44100 when
missing), `ttyr` (first 4 characters are the year), `uadd` (unix time, the date added).

### Recipe: Reading Mixxx

**You need:** `mixxxdb.sqlite` (Mixxx 2.x library) and Python's `sqlite3`. The file is opened
read only (`mode=ro`).

**Steps:**

1. Select the tracks: `library` joined to `track_locations`, keeping `mixxx_deleted = 0` and
   `fs_deleted = 0`. Build a `Track` per row (reference below), relocate missing files.
2. Read `cues`. Keep the types 1 (hot cue), 2 (main cue), 4 (loop), 5 (jump), 6 (intro) and
   7 (outro). Convert the positions (see the pitfall) and attach them to the tracks.
3. Read the playlists with `hidden = 0` in `position` order, with their `PlaylistTracks` in
   `position` order.
4. Read the crates with `show = 1` in name order, their tracks in `track_id` order, and put them
   in a folder `Crates`.

**Pitfalls:**

- Cue positions are interleaved stereo samples: ms = position / (2 x sample rate) x 1000. Use the
  sample rate of the track.
- A cue becomes a loop when it has type 4 and a length above 0 (length converted the same way). Type 2
  without length becomes a `LOAD` cue, everything else a plain cue. The `hotcue` column is the slot,
  a negative or null value is a memory cue.
- `key_id` 1-24 follows the Traktor order, so the key index is `key_id - 1`. 0 means no key.
- `hidden` other than 0 are Auto DJ and the history, not user playlists.
- Mixxx has no beat grid in this reader: tracks get the bpm of the library and no first beat. The
  CDJ export writes no beat entries for them until a first beat is set in the cue editor.
- `year` is taken from its first 4 characters, `tracknumber` from the part before `/`.
- Types 0 (invalid), 3 (beat) and 8 (audible) are internal markers and are skipped.

**Check:** compare the number of tracks with Mixxx's library count, and one hot cue time with the
Mixxx cue list.

#### Mixxx [published]

`mixxxdb.sqlite`, opened read only. `key_id` 1-24 follows the Traktor order.

Cue positions are interleaved stereo samples: ms = position / (2 x sample rate) x 1000.

Only playlists with `hidden = 0` are read (the others are Auto DJ and the history). Crates go
into a Crates folder.

Columns read from `library`: `artist`, `title`, `album`, `year`, `genre`, `comment`, `composer`,
`bpm`, `duration`, `rating` (0-5 as stored), `timesplayed`, `datetime_added` (first 10
characters), `bitrate`, `samplerate`, `key_id`, `tracknumber`. From `track_locations`: `location`
(the absolute path) and `filesize`.

### Recipe: Reading M3U and M3U8

**You need:** an `.m3u` or `.m3u8` file, optionally a music folder.

**Steps:**

1. Read the bytes (up to 64 MiB). Decode as UTF-8, with or without BOM. If that fails, decode as the
   Windows code page 1252.
2. Split into lines and strip them. Skip blank lines.
3. A line `#EXTINF:<seconds>,<label>` is kept for the next track line. The duration is the number
   before the comma (negative values become 0). The label is split at the first ` - ` into artist and
   title. Without ` - `, the whole label is the title.
4. Any other `#` line is ignored (this includes `#EXTM3U` and `#PLAYLIST:`).
5. A track line that contains `://` and does not start with `file:` is a network stream and is
   skipped. A `file:` line is converted to a path like a rekordbox `Location`.
6. A relative path is joined to the folder of the playlist and normalised.
7. Relocate missing files through the music folder (by name). If there was no label, the title is
   the file stem.
8. The playlist is named after the file stem. A file with no track line gives no playlist.

**Pitfalls:**

- Relative paths are relative to the playlist file, not to the program's working directory.
- Old `.m3u` files are usually in the Windows code page, not UTF-8. Decode UTF-8 first, fall back to
  cp1252 with replacement.
- `#EXTINF` applies to the next track line only. A skipped stream line clears it.
- `file:` URLs are percent-encoded: decode them.

**Check:** the playlist length equals the number of non-comment lines minus the skipped streams.

#### M3U / M3U8

UTF-8 with or without BOM, or the Windows code page for old `.m3u` files. `#EXTINF` gives
duration, artist and title. Relative paths are resolved from the playlist folder, `file://` URLs
are accepted.

### Recipe: Reading a music folder

**You need:** a folder, `tags.py` (ID3, FLAC and MP4 tags without any library), `soundfile` for the
duration.

**Steps:**

1. Walk the folder. Entries are sorted in natural order (digits compare as numbers, case is
   ignored). Symbolic links are skipped, because a link back up would loop.
2. A folder that holds audio files becomes a playlist named after the folder. A folder that holds
   sub-folders becomes a folder node that contains its own playlist, if any, then the sub-folders.
3. For each audio file read the tags (`tags.basic`): title (the file stem when empty), artist,
   album, album artist, label, remixer, composer, genre (a leading `(12)` ID3v1 number is removed),
   comment, year (first 4 characters), track and disc number (the part before `/`), bpm and key.
4. Accept a tagged bpm only between 40 and 300. Parse the key with `keys.parse`.
5. Fill the duration, sample rate and bitrate from the audio header when the tags have none.

**Pitfalls:**

- No collection means no grid and no cues. There is no beat entry on the key until a first beat is
  set in the cue editor.
- Audio extensions are `.mp3 .wav .flac .aiff .aif .m4a .mp4 .aac .ogg .alac`.
- Natural order treats only decimal digits as numbers. A superscript digit in a name is plain text.
- The tagged bpm is only a number. A track that does not start on a beat has no valid grid.

**Check:** the playlist count equals the number of folders that directly hold audio files.

### Recipe: Reading a Traktor Bridge project

**You need:** a `.json` file written by Traktor Bridge (`format` is `traktor-bridge-project`).

**Steps:**

1. Refuse a file over 256 MiB. Read it as UTF-8 (a BOM is accepted) and parse the JSON.
2. Check `format` and that `version` is an integer not above the supported version (1).
3. Read `settings`, keeping only the known keys with a string, number or boolean value.
4. Build each `Track` from `tracks[i]`: every `Track` field except `cues`, then its `cues` list. Each
   value is coerced to the type of its default. A wrong type is ignored. `key` and `grid` may be
   `null`.
5. Resolve relative `path` values and the settings `music_root`, `source_path`, `output_path` from the
   folder of the JSON file. If a music folder is known and some files are missing, relocate them
   there.
6. Rebuild `tree`: each node has `kind`, `name`, `uuid`, an optional `query`, and `children` for a
   folder or `tracks` (indexes into `tracks`) for a playlist. Indexes out of range are dropped.
   The depth is limited to 32.

**Pitfalls:**

- A shared track is stored once and referenced by index, so two playlists that list the same track
  share one object after loading. Keep that if you write a project.
- Unknown keys are ignored and a newer `version` is refused.
- `tracks`, `cues` and `children` must be lists, and a missing one is empty. Any other type refuses
  the load with a `ValueError`. A settings path that is not text is dropped.
- Paths written relative to the JSON make a project movable. A backup restored to a new folder
  relies on it.

**Check:** load the file, save it again and compare the two JSON files.

Reference: the layout is described in section 9 (Projects > Project file).

---

## 6. File exports

`export.run(format, nodes, out, cfg)` returns a `Report` (tracks, missing files, errors, output
path). No export ever writes back to the source collection.

`run` creates the output folder, opens a checksum manifest, calls the writer of the format, saves
the manifest and, with `verify_copy`, reads everything back. The formats are `CDJ/USB`,
`Rekordbox XML`, `M3U` and `Traktor NML`. Each file export takes `copy_music` (copy the audio along
with the playlists) and `verify_copy`.

### Recipe: Copying audio files

**You need:** the list of tracks (`unique_tracks`), the output folder, the `safe_name` and `Planner`
helpers of `export/files.py`.

**Steps:**

1. Take each track once, in `unique_tracks` order. Skip a track whose file is missing and report it.
2. Build the destination `Contents/<artist>/<album>/<file name>` with `safe_name` on every level.
   The file exports use `Unknown Artist` and `Unknown Album` for empty tags and do not cut the names.
   The CDJ export cuts every level at 48 characters (section 8).
3. Ask the `Planner` for the name. It never returns the same name twice, compared case-insensitively,
   and numbers a duplicate ` (2)`, ` (3)` before the extension.
4. Copy each file to `<destination>.part` in 4 MiB blocks, hash it while it is read, then rename
   it to the final name. A file already there with the same size is not copied, unless the export
   is verified: then it has to match the source byte for byte.
5. On a removable drive (Windows drive type 2) use one writer fed by a read-ahead thread. Elsewhere
   use four worker threads.
6. Record each copied file in the manifest with the hash computed on the way.

**Pitfalls:**

- FAT compares names without case. Two tracks that differ only by case must not collide, hence the
  lower-cased set in the `Planner`.
- A cut or full drive leaves a `.part` file, never a half-written final name.
- Parallel writes fragment the FAT of a key and the flash controller serialises them anyway, so
  the removable case is sequential.
- The audio is copied from the source, not from the key: the analysis reads the source too.

**Check:** the manifest holds one entry per copied file, and `manifest.verify` reads them back.

#### Audio copies

`files.copy_all` writes audio to `Contents/Artist/Album/file`. Names are made FAT32 safe with
accents kept, and duplicates are numbered case-insensitively.

Each copy is written to `.part`, then renamed, and hashed on the way. A file already there with
the same size is not copied again, unless the export is verified: then it has to match the source
byte for byte.

On a removable drive files are copied one at a time, which is faster on flash memory than
parallel writes. The progress shows the speed and the time left.

`safe_name(name, limit)` replaces `< > : " / \ | ? *` and the control characters `\x00-\x1f` with `_`,
strips white space at both ends, strips trailing dots and spaces, and returns `_` for an empty
result. When `limit` is set and the name is longer, the extension is kept and the stem is cut to
`limit - len(extension)` characters (at least 1) and stripped again of trailing dots and spaces.
Reserved Windows device names such as `CON` or `NUL` are not handled.

### Other formats

- M3U8: one file per playlist under `Playlists/`, folders become sub-folders, relative paths when
  the audio is copied along.
- Traktor NML: version 19, `LOCATION` split the way Traktor does, grid written back as
  `CUE_V2 TYPE 4`, smartlists kept with their query.
- rekordbox XML: see the next section.

### Recipe: Writing M3U8

**You need:** the playlist tree, the output folder, `copy_music` (true or false), the map from track
uid to the copied path when the audio was copied.

**Steps:**

1. If `copy_music` is on, copy the audio first (recipe above) and keep the new paths.
2. Create `<out>/Playlists`. Walk the tree. A folder becomes a sub-folder named with `safe_name`
   (no length limit). A playlist without tracks is skipped.
3. For each playlist, claim `<folder>/<safe_name(name)>.m3u8` from a `Planner`, so two playlists with the
   same name get ` (2)`.
4. Write the lines: `#EXTM3U`, then `#PLAYLIST:<name>`, then for each track with a path
   `#EXTINF:<seconds>,<label>` and the path. `seconds` is the rounded duration, or `-1` when it is 0.
   The label is `artist - title`, or the title alone when there is no artist. Carriage returns and
   line feeds in names are replaced by a space.
5. With the audio copied, write the path relative to the playlist's folder with `/` separators. Without
   the copy, write the original absolute path. If the relative path cannot be built (another drive on
   Windows), keep the absolute one.
6. Encode as UTF-8 without BOM, `\n` line ends, a final newline. Write atomically and add the file
   to the manifest.

**Pitfalls:**

- Relative paths only make sense when the audio travels with the playlists, hence the link to
  `copy_music`.
- Folder and playlist names go through `safe_name`, so characters such as `:` or `/` in a name become `_`.
- The reader decodes UTF-8 first and the Windows code page second, so keep UTF-8.

**Check:** read the files back with the M3U reader and compare track counts, or open one in a player.

### Recipe: Writing Traktor NML

**You need:** the tracks and tree, the output folder, `copy_music`. Traktor reads version 19 files
from Traktor Pro 3 and 4.

**Steps:**

1. Copy the audio if `copy_music` is on. Each track then uses its new path.
2. Create the root `NML VERSION="19"` with `HEAD COMPANY="www.native-instruments.com" PROGRAM="Traktor"`
   and an empty `MUSICFOLDERS`.
3. Write `COLLECTION ENTRIES="N"` with one `ENTRY` per unique track (reference below).
4. Write `PLAYLISTS` with one top `NODE TYPE="FOLDER" NAME="$ROOT"` holding `SUBNODES COUNT`. Folders,
   smartlists and playlists are written as shown below.
5. Write the XML with two-space indentation and the declaration
   `<?xml version="1.0" encoding="UTF-8" standalone="no" ?>`, to a temporary file, then rename. The
   file is `collection.nml`.
6. Add the file to the manifest.

**Pitfalls:**

- Split every path into three attributes. For `C:\Music\House\a.mp3`: `VOLUME="C:"`,
  `DIR="/:Music/:House/:"`, `FILE="a.mp3"`. A POSIX path under `/Volumes/<Name>/` uses `<Name>` as
  `VOLUME`, any other POSIX path uses `Macintosh HD`.
- The key of a playlist entry is `VOLUME + DIR + FILE`, exactly the concatenation Traktor uses.
- Units: `BITRATE` in bps, `FILESIZE` in KB, `RANKING` 0-255 (rating x 51), dates as `2026/9/28`
  without zero padding, `RELEASE_DATE` as `<year>/1/1`.
- Empty and zero attributes of `INFO` are left out. `TEMPO` is written only when the bpm is above 0,
  `MUSICAL_KEY` only when the key is known, `LOUDNESS` only when there is a gain.
- Control characters are removed from every text before it goes into the XML (`clean`). ElementTree
  escapes `&`, `<`, `>` and quotes. Without the clean-up the file can no longer be parsed.
- The grid becomes a `CUE_V2` named `AutoGrid` with `TYPE="4"` and `HOTCUE="0"`, written first. Every
  cue keeps its model kind number (0 cue, 1 fade-in, 2 fade-out, 3 load, 4 grid, 5 loop).
- Traktor's colour is its own 1-7, converted back from the rekordbox id.

**Check:** read the file back with the NML reader and compare tracks, cues and grids, then open it in
Traktor.

#### Traktor NML writer reference [verified]

`ENTRY` attributes: `MODIFIED_DATE` (the track's `modified`, else today), `MODIFIED_TIME="0"`, `TITLE`,
`ARTIST`, then `AUDIO_ID` and `LOCK="1"` when set. Children in this order:

| Element | Attributes |
| --- | --- |
| `LOCATION` | `DIR`, `FILE`, `VOLUME` |
| `ALBUM` | `TITLE`, `TRACK` (only when not 0) |
| `MODIFICATION_INFO` | `AUTHOR_TYPE="user"` |
| `INFO` | `BITRATE`, `GENRE`, `LABEL`, `COMMENT`, `REMIXER`, `PRODUCER` (composer), `KEY` (rekordbox name), `PLAYCOUNT`, `PLAYTIME` (rounded), `PLAYTIME_FLOAT` (`%.6f`), `RANKING`, `IMPORT_DATE`, `LAST_PLAYED`, `FILESIZE`, `RELEASE_DATE`, `COLOR` |
| `TEMPO` | `BPM` (`%.6f`), `BPM_QUALITY="100.000000"` |
| `LOUDNESS` | `PEAK_DB="0.000000"`, `PERCEIVED_DB`, `ANALYZED_DB` (both the gain, `%.6f`) |
| `MUSICAL_KEY` | `VALUE` (key index 0-23) |
| `CUE_V2` | `NAME`, `DISPL_ORDER` (0, 1, 2... in file order), `TYPE`, `START` and `LEN` (ms, `%.6f`), `REPEATS="-1"`, `HOTCUE`, `COLOR` (only when set) |

Playlist nodes:

- Folder: `NODE TYPE="FOLDER" NAME`, with `SUBNODES COUNT`.
- Smartlist: `NODE TYPE="SMARTLIST" NAME` with `SMARTLIST UUID` and
  `SEARCH_EXPRESSION VERSION="1" QUERY`.
- Playlist: `NODE TYPE="PLAYLIST" NAME` with `PLAYLIST ENTRIES TYPE="LIST" UUID`, then one
  `ENTRY/PRIMARYKEY TYPE="TRACK" KEY` per track that has a path.

### Recipe: Writing the checksum manifest

**You need:** every file the export wrote, with its bytes or its path, and `export/manifest.py`.

**Steps:**

1. When the export starts, read the previous manifest if there is one (to reuse its hashes) and delete it.
2. As each file is written, add it with its relative path (`/` separators), size, modification time
   (whole seconds) and SHA-256. Audio is hashed during the copy, generated files are hashed from the
   bytes written. Files an earlier export left in place keep their old hash when size and time are
   the same within 2 seconds.
3. At the end, sort the entries by path and compute the seal.
4. Write `traktor_bridge_checksums.json` atomically at the root.
5. Optionally read every listed file back (`manifest.verify`).

**Pitfalls:**

- The seal is the SHA-256 of `json.dumps(files, sort_keys=True, separators=(",", ":"))` encoded as
  UTF-8, with the default `ensure_ascii=True`. The file itself is written with indent 1 and
  `ensure_ascii=False`. Hash the compact, ASCII-escaped form, not the file text.
- Paths in the manifest must be relative, without drive letter, colon, backslash, `.` or `..`
  segments, or the manifest is refused.
- FAT stores times with a 2 second resolution, hence the tolerance.
- A cancelled export removes the previous manifest and writes none, so the manifest never describes
  an older state.
- The manifest does not list itself.

**Check:** `manifest.verify(root)` returns a `Check` with no damaged and no missing file. In the
application this is **Tools > Verify an export**.

#### Checksums

Every export writes `traktor_bridge_checksums.json` at its root (`export/manifest.py`):

```json
{"format": 1, "program": "Traktor Bridge 3.5.1", "created": "2026-09-30T12:00:00",
 "algorithm": "sha256",
 "files": {"Contents/Artist/Album/track.mp3": {"size": 9000000, "mtime": 1790000000, "sha256": "..."}},
 "seal": "sha256 of the files object, compact JSON, sorted keys"}
```

- Paths are relative to the export root, with `/`.
- Audio is hashed while it is copied. The ANLZ files, artwork, M3U and `export.pdb` are hashed from
  the bytes written. Building the manifest costs no extra read.
- Only audio left in place by a later export keeps its entry, when its size and time did not change
  (2 seconds of tolerance, because of FAT). A file the export writes always gets the hash of the
  bytes written, never an entry carried over: two exports of the same size within 2 seconds would
  otherwise keep a stale hash.
- The previous manifest is read, then removed, when an export starts. A cancelled export leaves
  none rather than an outdated one. The new one is written atomically at the end.

### Verifying an export

`manifest.verify(root)` reads every listed file back. A manifest whose seal does not match is
refused. With `verify_copy` (on by default), `export.run` runs it right after the export.

The read-back goes through `sha256_drive`. On Windows the file is opened with
`FILE_FLAG_NO_BUFFERING` (sector aligned 1 MiB reads), so the bytes come from the key and not
from the cache the copy just filled. Elsewhere, or when that open fails, it is a normal read. A
read error counts as a damaged file instead of stopping the check.

Verification is strict by default. The standalone UI and CLI pass `allow_player_changes=True`,
because a player can rewrite some of its own files. Readable mismatches at
`PIONEER/rekordbox/export.pdb` and `PIONEER/USBANLZ/.../ANLZ0000.DAT/.EXT/.2EX` are then
recorded in `Check.modified` instead of `damaged`.

That classification does not validate the player's edits or attribute them to a CDJ. Details:

- Missing or unreadable files remain errors, and audio and artwork mismatches stay strict.
- `Check.good` stays false when a file is modified. The UI warns without recommending a blind
  replacement, and the CLI exits 1 for any result that is not an exact match.
- No hash is rebased automatically.
- The generation validators (see the safeguards at the end of section 10) are not applied here.
  Their layout requirements are specific to the exporter and do not describe every legitimate
  file written by a player.

The report groups files in four categories: Audio (by extension), Artwork (under
`PIONEER/Artwork`), Pioneer database / analysis (`export.pdb` and the `ANLZ0000` files) and Other
files.

### Writing generated files

Generated PDB, DAT and EXT files go through a validated temporary write, a read-back and a
rename. Analysis cache writes also use temporary files.

Cached DAT and EXT files are reused only when their required sections, roles, internal
lengths and counts, and the expected track path all validate.

The steps are the same for each file: validate the bytes, write `<name>.verified`, read it back with
`sha256_drive` and compare with the digest of the bytes, then rename over the destination. The
temporary files are removed if anything fails. Artwork and the settings files are the exception:
artwork is written straight to its final name (`write_direct`, no rename, because a cut leaves one
file to write again) and settings use a plain atomic write (`write_atomic`).

---

## 7. rekordbox XML

The XML is a software import: rekordbox reads it, analyses the audio again and builds its own
database, so no binary constraint applies.

Use it when you want rekordbox to do the analysis. Use the USB export when you want a key ready
without rekordbox.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="Traktor Bridge" Version="3.5.1" Company="..."/>
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

### Recipe: Writing rekordbox XML

**You need:** the tracks and tree, the output folder, `copy_music`, the 8 track colours of
`RB_COLORS` and the 8 default hot cue colours of `HOT_RGB`.

**Steps:**

1. Copy the audio if `copy_music` is on, and use the new paths.
2. Create `DJ_PLAYLISTS Version="1.0.0"` and a `PRODUCT` element with the program name, its version and the author.
3. Number the unique tracks from 1 in `unique_tracks` order. Write
   `COLLECTION Entries` and one `TRACK` per track (reference below).
4. Under each `TRACK`, write one `TEMPO` when the grid is known, then one `POSITION_MARK` per
   cue.
5. Write `PLAYLISTS` with a `NODE Type="0" Name="ROOT" Count` and the tree below it.
6. Write the file `rekordbox.xml` with the declaration `<?xml version="1.0" encoding="UTF-8"?>` and
   two-space indentation, through a temporary file and a rename. Add it to the manifest.

**Pitfalls:**

- Units. `TotalTime` is in whole seconds, `Start`, `End` and `Inizio` in seconds with six decimals,
  `Rating` is 0, 51, 102, 153, 204 or 255, `BitRate` in kbps.
- `POSITION_MARK Type` 4 is a loop, while Traktor's 4 is the grid. Grid cues are not written as marks.
- Hot cues are `Num` 0-7. Memory cues and everything above 7 are `Num="-1"`.
- Colours. Only hot cues carry `Red`, `Green`, `Blue`. The value is the cue colour (`#RRGGBB`, or an
  8 digit ARGB whose first byte is dropped) or, without colour, the default of the slot. A
  track colour is written as `0x` plus one of the eight `RB_COLORS`.
- `Location` is `file://localhost` plus the POSIX form of the path (`C:\a b.mp3` becomes
  `/C:/a%20b.mp3`), percent-encoded except `/` and `:`.
- Control characters are removed from all text (`clean`), otherwise ElementTree writes them as is
  and nothing can read the file again.
- `KeyType="0"` playlists refer to `TrackID`. A track that was not exported is left out of the
  playlist, and `Entries` counts what remains.

**Check:** read it back with the rekordbox XML reader, or import it in rekordbox (File > Import).

#### Written structure

The root has `Version="1.0.0"`. `PRODUCT` carries `Name` (program name), `Version` (program version)
and `Company` (the author). The `TRACK` attributes are in the next table in the order they are
written, and `Colour` is added only when the track has a colour.

#### TRACK attributes

| Attribute | Value |
| --- | --- |
| `TrackID` | 1..N, the key playlists refer to |
| `Name`, `Artist`, `Album`, `Genre`, `Label`, `Remixer`, `Composer`, `Comments` | text |
| `Grouping`, `Mix` | written empty |
| `Kind` | `MP3 File`, `M4A File`, `FLAC File`, `WAV File`, `AIFF File`, `AAC File`; any other extension gives the upper case extension plus ` File` |
| `Size` | bytes |
| `TotalTime` | seconds |
| `AverageBpm` | `%.6f` |
| `Tonality` | rekordbox key name (`Am`, `Dbm`...) |
| `Rating` | 0, 51, 102, 153, 204, 255 |
| `Colour` | `0xRRGGBB` of one of the 8 rekordbox colours |
| `DateAdded` | `YYYY-MM-DD` |
| `BitRate`, `SampleRate`, `PlayCount`, `Year`, `TrackNumber`, `DiscNumber` | numbers |
| `Location` | `file://localhost/` + absolute path, `/` separators, URL encoded except `/` and `:` |

The eight track colours, as `0xRRGGBB` for ids 1 to 8: `FF007F` pink, `FF0000` red, `FFA500` orange,
`FFFF00` yellow, `00FF00` green, `25FDE9` aqua, `0000FF` blue, `660099` purple.

`TEMPO Inizio` is the first beat in seconds, and `Battito="1"` makes it the downbeat. One
`TEMPO` element describes a constant grid. BPM and seconds are written with six decimals.

No `TEMPO` is written when the grid has been cleared. A marker with an unknown BPM is written
with `Bpm="0"` (in practice `0.000000`), and it does not define a usable grid until a BPM is
supplied.

#### POSITION_MARK

| Attribute | Meaning |
| --- | --- |
| `Type` | 0 cue, 1 fade-in, 2 fade-out, 3 load, 4 loop |
| `Num` | 0-7 hot cue A-H, -1 memory cue or memory loop |
| `Start`, `End` | seconds, `%.6f`, `End` only for a loop |
| `Red`, `Green`, `Blue` | hot cue colour |

Default hot cue colours (`HOT_RGB`) for the slots A to H: (40, 226, 20), (48, 90, 255), (255, 18, 123),
(255, 127, 0), (48, 210, 255), (170, 114, 255), (224, 100, 27), (16, 177, 118).

#### PLAYLISTS

`NODE Type="0"` is a folder (`Count` = direct children), `NODE Type="1"` a playlist
(`Entries` = tracks). `KeyType="0"` means the `TRACK Key` values are TrackIDs, `KeyType="1"`
that they are locations. The root is always `NODE Type="0" Name="ROOT"`.

The writer always uses `KeyType="0"`. The reader accepts both.

---

## 8. CDJ USB export

Target: CDJ-2000NXS2 and the players reading a rekordbox 6 export. Everything in this section is
**[verified]**.

The layouts below are what the writer produces, checked byte for byte against keys written by
rekordbox and against a key written by the built program (3 synthetic tracks). Where the writer
puts a constant whose meaning is not known, the text says so: the value is copied from rekordbox
keys and the CDJ expects it.

Byte order: `export.pdb` is little endian, the ANLZ files are big endian, the settings files are
little endian. All offsets are in bytes from the start of the structure, hexadecimal with `0x`.

A reader who wants to write a key without the code needs six recipes, in this order: layout and
file names, `export.pdb`, the ANLZ files, artwork, the settings files, and the order of writing.
The last one ties the others together.

### Recipe: CDJ key, layout and file names

**You need:**

- A FAT32 (or exFAT) volume. The players show NO DISK on an NTFS key.
- For each track: the source file, its artist, album and file name.
- The `safe_name` rule and the folder hash below.

**Steps:**

1. Create `Contents` and `PIONEER` side by side at the root of the volume.
2. For each track, build its path on the key: `/Contents/<artist>/<album>/<file name>`. An empty artist
   becomes `Unknown Artist` and an empty album `Unknown Album`. Run each of the three parts through
   `safe_name(part, 48)`.
3. Claim the name from a planner that compares names without case. A duplicate gets ` (2)`, ` (3)`
   before the extension, added after the 48 character cut.
4. Copy the audio to that path. The same string (with `/` separators and a leading `/`) goes in the
   track row (string 20) and in the `PPTH` section of the ANLZ files.
5. From that path compute the analysis folder (hash below) and create
   `PIONEER/USBANLZ/Pxxx/xxxxxxxx/`. The same string, with `/ANLZ0000.DAT` appended, goes in
   the track row (string 14).
6. Create `PIONEER/rekordbox/` for `export.pdb`, `PIONEER/Artwork/00001/` for the pictures, and put
   the four settings files in `PIONEER/`.

**Pitfalls:**

- Each level is cut at 48 characters, the extension included for the file name. A longer name is
  not what rekordbox writes, and the row path must be identical to the real one.
- FAT32 forbids `< > : " / \ | ? *` and control characters. `safe_name` replaces them with `_`, strips
  trailing dots and spaces, and keeps accents. A name that becomes empty is `_`. Windows device names
  (`CON`, `NUL`, `COM1`...) are not handled by `safe_name`.
- Two names that differ only by case are the same file on FAT, hence the case-insensitive planner.
- The hash adds `ord(c) & 0xFFFF` for each character of the path. A character above U+FFFF is masked to
  16 bits, not split into surrogates, and a path with accents must be tested against rekordbox.
- Two paths can hash to the same folder: take the next number (below), or the second track overwrites
  the first one's analysis.
- NTFS keys show NO DISK. exFAT is accepted by the players, but the key formatter of the program writes
  FAT32 only.

**Check:** `pdbread` on the finished `export.pdb` returns paths in string 20 that exist on the key,
and `validate.anlz(data, path, "DAT")` accepts each ANLZ file with the same path. List the key and look
for any file of the manifest that is missing.

#### Key layout

```
Contents/Artist/Album/file              every level cut at 48 characters
PIONEER/rekordbox/export.pdb
PIONEER/USBANLZ/Pxxx/xxxxxxxx/ANLZ0000.DAT and .EXT
PIONEER/Artwork/00001/aN.jpg (80 px) and aN_m.jpg (240 px)
PIONEER/MYSETTING.DAT, MYSETTING2.DAT, DJMMYSETTING.DAT, DEVSETTING.DAT
```

- `Contents` and `PIONEER` sit side by side at the root of the key.
- FAT32 or exFAT: the players show NO DISK on an NTFS key.
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

The writer also resolves collisions. It tries `r = (h + k) % 200003` for k = 0, 1, 2... and keeps
the first folder not used yet by another track of the same export. The key has 200003 possible folders.

Examples from the sample key: `/Contents/A0/Unknown Album/t0.wav` gives `/PIONEER/USBANLZ/P007/00008455`
and `/Contents/A1/Unknown Album/t1.wav` gives `/PIONEER/USBANLZ/P02C/00022DE0`.

#### File name rules

`usb_path` calls `safe_name(x, 48)` for the artist, the album and the file name. The planner key is the
lower-cased path. The path stored in the database is the claimed one, with `/` and a leading `/`.
Accented characters are kept. The audio file keeps its source extension.

### Recipe: CDJ key, export.pdb

**You need:**

- The list of exported tracks with: id (1..N), path on the key, ANLZ path, size of the copied file,
  artwork id (0 if none), plus the `Track` fields of section 4.
- The playlist tree (`Node` objects).
- Today's date as `YYYY-MM-DD`.
- The four fixed pages of the reference tables (columns, two menu tables, history), see "export.pdb,
  the fixed tables".

**Steps:**

1. Build the lookups by walking the tracks in id order. For each track register, in this order: its
   artist, its album artist (the artist when empty), its album (key: album name and album artist id),
   genre, label, remixer (as an artist), composer (as an artist) and key name. An id is the number
   of distinct entries seen so far plus one, so ids follow the order of first use. An empty name
   gives id 0 and no row.
2. Build the rows (reference tables below): a track row per track, the Genres, Artists, Albums, Labels
   and Keys rows from the lookups, the 8 fixed Colour rows, the playlist tree and playlist entry rows,
   and one Artwork row per used artwork id (ascending).
3. Number the pages. Table `t` (0 to 19) owns the index page `1 + 2t` and the first data page
   `2 + 2t`. Page 0 is the header. A table with more rows than one page holds gets overflow pages
   numbered from 41 upward, one after another in table order.
4. Pack the rows of each table into pages: add rows to the current page until the next row would
   push `used + row + index_size(rows + 1)` past 4056, then start a new page.
5. Write each data page: the rows from offset `0x28`, the row index at the end of the page, the header
   fields. Number the sequence of the pages 2, 3, 4... in table order, page by page.
6. Write the 20 index pages (tables 0 and 19 list their data pages).
7. Write page 0: header and 20 table pointers. The header sequence is the last data page sequence
   plus 2.
8. Validate the result (`validate.pdb`), write it to a temporary file, read it back and compare, rename.

**Pitfalls:**

- The header sequence (page 0, offset `0x14`) must be higher than the sequence of every page,
  index pages included. Otherwise rekordbox reports the library as corrupt, and a CDJ-2000NXS2
  browses a file that breaks this rule and then locks up on the next screen.
- Pages are exactly 4096 bytes and the file is a whole number of pages.
- `free` is exact: `4056 - used - index_size(rows)`. The validator recomputes it.
- Strings. A long string (a long ASCII string or any UTF-16 string) starts on a 4 byte boundary
  counted from the start of its row, so the row is padded with zero bytes before it. Every row is
  padded to a multiple of 4. The string offsets of the track row are u16 and the name offset of an
  Artist or Album row is a u8.
- Every table needs its index page and its pointer, even when empty. An empty table still has a zeroed
  page at `2 + 2t` in the file. The directory has 20 entries.
- Only Tracks (0) and History (19) list their data pages in their index page, and only these two have
  data pages flagged `0x34`.
- Tracks, Artists, Albums and History rows carry the slot of the row in the page at offset 2 as
  `slot x 0x20`. Write it when the row is placed.
- An id used in a row must exist in its table. An id of 0 means none.
- A track in a playlist but not on the key (missing file) must not get an entry.
- The `u16` fields (disc, plays, year, duration in seconds) overflow above 65535. The native core
  refuses such a value, the Python reference raises.
- A numeric value is rounded half to even, like Python `round`: `tempo = round(bpm * 100)`.
- The ANLZ path (string 14) and the file path (string 20) must be the real ones, or the player finds
  the row but no analysis or no audio.
- An export replaces the whole database. Files an older export left in `Contents` stay on the key but
  are not referenced.

**Check:** `pdbread.read(data)` returns the tables, the pages and the rows. `pdbread.track_strings(row)` lists
the 21 strings of a track row. `validate.pdb(data)` accepts the file. Then export the same tracks
with rekordbox and compare row by row (the method of section 2), and finally try the key on a CDJ.

#### export.pdb, file

- 4096 byte pages, little-endian. Page 0: `[0, 4096, 20, next_unused, 5, sequence, 0]`, then 20
  table pointers `{type, empty_candidate, first_page, last_page}`.
- Table `t`: index page at `1 + 2t`, first data page at `2 + 2t`, overflow pages appended at the
  end of the file.
- An empty table only has its index page, and its `empty_candidate` points to `2 + 2t`. The
  other `empty_candidate` values are page numbers past the end of the file, and `next_unused`
  follows them.
- The header sequence must be higher than the sequence of every page, or rekordbox reports the
  library as corrupt.

Page 0 in detail:

| Offset | Size | Value |
| --- | --- | --- |
| `0x00` | u32 | 0 |
| `0x04` | u32 | 4096, the page size |
| `0x08` | u32 | 20, the number of tables |
| `0x0C` | u32 | `next_unused`: the first page number after the last empty candidate |
| `0x10` | u32 | 5, constant, meaning unknown |
| `0x14` | u32 | sequence |
| `0x18` | u32 | 0 |
| `0x1C + 16 t` | 4 x u32 | table `t`: `type` (= t), `empty_candidate`, `first_page` (= `1 + 2t`), `last_page` |

The rest of page 0 (from `0x15C`) is zero. `last_page` is the last data page of the table, or the index
page `1 + 2t` when the table is empty. The `first_page` of every table is its index page, and the chain
goes from the index page to the first data page and on through the `next` field of each page.

Page numbers of the file with N overflow pages in total: the file has `41 + N` pages (0 to
`40 + N`). A table with data takes the next free number past the end as its `empty_candidate`, in
table order: the first such table gets `41 + N`, the next one `42 + N`... Empty tables use
`2 + 2t`. `next_unused` is the first number after the last of them. With nothing overflowing
and 9 non-empty tables (as in the sample) the candidates are 41 to 49 and `next_unused` is 50.

The `type` numbers: 0 Tracks, 1 Genres, 2 Artists, 3 Albums, 4 Labels, 5 Keys, 6 Colours, 7 Playlist
tree, 8 Playlist entries, 13 Artwork, 16 browse columns, 17 and 18 menus, 19 History. Types 9 to
12, 14 and 15 are written empty.

The sequence is assigned as follows. It starts at 1. Each data page, in table order and page order,
takes the next value, beginning at 2. The index pages of tables 0 and 19 (when they have entries)
take the last data page value plus 1. All other index pages have sequence 1. The header takes the
last data page value plus 2. In the sample key the nine data pages are 2 to 10, the two index
pages 11 and the header 12.

#### export.pdb, pages

Page header (0x28 bytes): `0x04` index, `0x08` type, `0x0C` next page, `0x10` sequence, `0x18`
24 bit packed count `n | (n << 13)` (row slots, live rows), `0x1B` flags, `0x1C` free space,
`0x1E` used space, `0x20` `u5`, `0x22` `nrl`, `0x24` `u6`, `0x26` `u7`.

- Data page: flags `0x24`, `0x34` for Tracks and History. `u5 + nrl` = row count, a fresh file
  writes `u5 = n`, `nrl = 0`.
- Free space is exact: `4056 - used - index`. The row index costs 36 bytes per full group of 16
  rows and `4 + 2 x remainder` for the last group.
- Row index at the end of the page, in groups of 16: offsets in reverse order, then a u16 mask of
  present rows, then a u16 mask of the rows touched by the last write (equal to the first in a
  fresh file).
- Index page: flags `0x64`, `u5 = nrl = 0x1FFF`, `u6 = 1004`, `u7 = 1` when it has entries.
  - Body: page index, first data page, `0x03FFFFFF`, 0, u16 entry count, u16 `0x1FFF`, entries
    `page << 3`, then `f8 ff ff 1f` filler up to 20 trailing zero bytes.
  - Only Tracks and History have entries. The page holds 1004 entries, and the players follow the
    page chain for the data pages beyond.

Data page layout:

| Offset | Size | Value |
| --- | --- | --- |
| `0x00` | u32 | 0 |
| `0x04` | u32 | page index |
| `0x08` | u32 | table type |
| `0x0C` | u32 | next page: the next data page of the table, or the table's `empty_candidate` on the last one |
| `0x10` | u32 | sequence |
| `0x14` | u32 | 0 |
| `0x18` | 3 bytes | `n + (n << 13)`, little endian, `n` = rows in the page |
| `0x1B` | u8 | flags: `0x24`, or `0x34` for tables 0 and 19 |
| `0x1C` | u16 | free space = `4056 - used - index_size(n)` |
| `0x1E` | u16 | used space: the sum of the lengths of the rows |
| `0x20` | u16 | `u5` = n |
| `0x22` | u16 | `nrl` = 0 |
| `0x24`, `0x26` | u16 | 0, 0 |
| `0x28` | rows | the rows, back to back, each padded to a multiple of 4 |
| `4096 - 36 g - 4` | u16 | mask of present rows of group `g` |
| `4096 - 36 g - 2` | u16 | mask of rows touched by the last write (same value) |
| `4096 - 36 g - 6 - 2 k` | u16 | offset of row `16 g + k` from `0x28` |

`index_size(n)` is `36 x (n div 16)` plus `4 + 2 x (n mod 16)` when `n mod 16` is not 0. A page is
full when adding the next row would push `used + row + index_size(n + 1)` above 4056 (`0x28` bytes of
header out of 4096). A row of more than `4056 - 6` bytes is an error.

Index page layout (4096 bytes, `0x1B` = `0x64`):

| Offset | Size | Value |
| --- | --- | --- |
| `0x00` to `0x14` | 6 x u32 | 0, page index (`1 + 2t`), table type, next page (`2 + 2t`), sequence, 0 |
| `0x18` | 3 bytes | 0 |
| `0x1C`, `0x1E` | u16 | 0, 0 |
| `0x20`, `0x22` | u16 | `0x1FFF`, `0x1FFF` |
| `0x24` | u16 | 1004, the number of entry slots |
| `0x26` | u16 | 1 when the table has entries, else 0 |
| `0x28` | u32 | page index |
| `0x2C` | u32 | first data page (`2 + 2t`) |
| `0x30` | u32 | `0x03FFFFFF` |
| `0x34` | u32 | 0 |
| `0x38` | u16 | number of entries |
| `0x3A` | u16 | `0x1FFF` |
| `0x3C` | u32 each | entries: `page << 3` for each data page of the table (tables 0 and 19 only) |
| after the entries | u32 each | `0x1FFFFFF8` (bytes `f8 ff ff 1f`) up to offset 4076 |
| 4076 to 4095 | 20 bytes | 0 |

Sequence for index pages: see "export.pdb, file". The entries are `page << 3`, so data page 2 is
`0x10`. A table with more than 1004 data pages lists only the first 1004 and the players find the
rest through the `next` chain.

#### export.pdb, strings

- Empty: `03`.
- Short ASCII (up to 126): `((n + 1) << 1) | 1` then the bytes.
- Long ASCII: `40`, u16 total length (n + 4), `00`.
- UTF-16LE: `90`, u16 (2n + 4), `00`.
- A long string starts on a 4 byte boundary inside its row, and rekordbox pads with zeros before
  it.

A string is ASCII only when every character is below 128. One accented character makes the whole string
UTF-16LE, with surrogate pairs above U+FFFF. The 16 bit length of a long string includes its 4 header
bytes, so a string cannot exceed 65531 bytes. In the track row, the offset stored for a string is the
position of its first byte (the flag byte) from the start of the row.

Read a string: if bit 0 of the first byte is 1 it is short, the length is `(b >> 1) - 1` and the text
follows. Otherwise read the u16 at +1: the text runs from +4 to +length, as ASCII for `40` and as
UTF-16LE for `90`.

#### export.pdb, rows

Track row, 0x88 fixed bytes then 21 strings:

| Offset | Field |
| --- | --- |
| `0x00` | subtype `0x24` |
| `0x02` | index shift (slot in the page x 0x20) |
| `0x04` | `0x000C0700` |
| `0x08` | sample rate |
| `0x0C` | composer id (Artists table), 0 when none |
| `0x10` | file size |
| `0x14` | rekordbox internal checksum, 0 is accepted |
| `0x18` | `0xC25930BF` |
| `0x1C` | artwork id |
| `0x20` | key id |
| `0x24` | 0 |
| `0x28` | label id |
| `0x2C` | remixer id (Artists table), 0 when none |
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

Widths: `0x00`, `0x02`, `0x4C` to `0x56`, `0x5A`, `0x5C` and the string offsets are u16, `0x58` and `0x59` are
u8, everything else is u32. The constants at `0x04`, `0x18`, `0x56` (41), `0x5C` (3) and `0x52` (16)
have no meaning the code can state, they are copied from rekordbox keys. The file type comes from the extension of
the path on the key: `.mp3` 1, `.m4a`, `.mp4`, `.aac` 4, `.flac` 5, `.wav` 11, `.aif`, `.aiff` 12, anything
else 1.

Strings: `[2]` and `[3]` = `2`, `[6]` and `[7]` = `ON`, `[10]` date added, `[14]` ANLZ path,
`[15]` analysis date, `[16]` comment, `[17]` title, `[19]` file name, `[20]` path on the key.

The other string slots (0, 1, 4, 5, 8, 9, 11, 12, 13, 18) are written empty (`03`). The writer puts
the strings one after the other in slot order, so the 21 offsets increase. Date added is the date of
the track when known, else today. The analysis date is today.

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

Artist, album and key ids follow the order of first use, the way rekordbox numbers them, not a
fixed table.

With offsets:

| Table (type) | Fixed bytes | Layout |
| --- | --- | --- |
| Artist (2) | 10 | `0x00` u16 `0x60`, `0x02` u16 shift, `0x04` u32 id, `0x08` u8 3, `0x09` u8 offset of the name, name from `0x0A` |
| Album (3) | 22 | `0x00` u16 `0x80`, `0x02` u16 shift, `0x04` u32 0, `0x08` u32 album artist id, `0x0C` u32 album id, `0x10` u32 0, `0x14` u8 3, `0x15` u8 offset of the name, name from `0x16` |
| Genre (1), Label (4) | 4 | `0x00` u32 id, name from `0x04` |
| Key (5) | 8 | `0x00` u32 id, `0x04` u32 id (same value), name from `0x08` |
| Colour (6) | 8 | `0x00` u32 0, `0x04` u8 id, `0x05` u16 id (same value), `0x07` u8 0, name from `0x08` |
| Playlist tree (7) | 20 | `0x00` u32 parent id (0 at the top), `0x04` u32 0, `0x08` u32 sort order, `0x0C` u32 id, `0x10` u32 1 for a folder else 0, name from `0x14` |
| Playlist entry (8) | 12 | u32 position (from 1), u32 track id, u32 playlist id; no string |
| Artwork (13) | 4 | `0x00` u32 id, path from `0x04` |

The name offset of an Artist or Album row is the position of the name string in the row (10 or 22,
or a little more when a long name is padded to a multiple of 4). `3` is a constant, meaning unknown.

Rules for the rows:

- Artist rows hold every artist, album artist, remixer and composer name, one row per distinct
  name, with the id given by order of first use. The same name is one row.
- An Album row is one per (album name, album artist id). The same title under two album artists
  gives two rows. The row stores the album artist id.
- Genre, Label and Key rows are one per distinct name, in order of first use. The key name is
  the rekordbox name (flats): `C`, `Db`, `D`, `Eb`, `E`, `F`, `Gb`, `G`, `Ab`, `A`, `Bb`, `B` for the
  majors and `Cm`, `Dbm`... for the minors (section 4).
- Colour rows are always the same 8, with ids 1 to 8: Pink, Red, Orange, Yellow, Green, Aqua, Blue,
  Purple.
- The playlist tree is walked depth first, ids count from 1 in that order. `sort` is the index among
  the siblings, starting at 0. Smartlists have no track list and are written as empty playlists.
  Folders are written with `is folder` = 1 and no entries.
- Playlist entries are written playlist by playlist, in tree order, with position 1..n. A track
  without an id (missing file) is skipped and the following ones close the gap.
- The Artwork table holds one row per used artwork id, in ascending order.

#### export.pdb, the fixed tables

Four tables are written from constants: the browse columns (16), two menu tables (17 and 18) and
the history (19). Each is one prebuilt 4096 byte page. The writer rewrites only the page index, the
`next` field and the sequence (offsets `0x04`, `0x0C`, `0x10`) when it places them. Nothing here is copied from
Pioneer files: the constants are listed in this document and generated by `reference.py`.

Browse columns (table 16, 27 rows, flags `0x24`). A row is: u16 id, u16 display code, then a UTF-16LE
string in the long form (`90`, u16 length, `00`) whose text is U+FFFA, the name, U+FFFB.

| Id | Display code | Name |
| --- | --- | --- |
| 1 | `0x80` | GENRE |
| 2 | `0x81` | ARTIST |
| 3 | `0x82` | ALBUM |
| 4 | `0x83` | TRACK |
| 5 | `0x85` | BPM |
| 6 | `0x86` | RATING |
| 7 | `0x87` | YEAR |
| 8 | `0x88` | REMIXER |
| 9 | `0x89` | LABEL |
| 10 | `0x8A` | ORIGINAL ARTIST |
| 11 | `0x8B` | KEY |
| 12 | `0x8D` | CUE |
| 13 | `0x8E` | COLOR |
| 14 | `0x92` | TIME |
| 15 | `0x93` | BITRATE |
| 16 | `0x94` | FILE NAME |
| 17 | `0x84` | PLAYLIST |
| 18 | `0x98` | HOT CUE BANK |
| 19 | `0x95` | HISTORY |
| 20 | `0x91` | SEARCH |
| 21 | `0x96` | COMMENTS |
| 22 | `0x8C` | DATE ADDED |
| 23 | `0x97` | DJ PLAY COUNT |
| 24 | `0x90` | FOLDER |
| 25 | `0xA1` | DEFAULT |
| 26 | `0xA2` | ALPHABET |
| 27 | `0xAA` | MATCHING |

Menu table 17 (22 rows, flags `0x24`): each row is four u16. The meaning of the fields is not
documented by the code, copy the values.

| a | b | c | d |
| --- | --- | --- | --- |
| `0x1` | `0x1` | `0x163` | `0x0` |
| `0x5` | `0x6` | `0x105` | `0x0` |
| `0x6` | `0x7` | `0x163` | `0x0` |
| `0x7` | `0x8` | `0x163` | `0x0` |
| `0x8` | `0x9` | `0x163` | `0x0` |
| `0x9` | `0xA` | `0x163` | `0x0` |
| `0xA` | `0xB` | `0x163` | `0x0` |
| `0xD` | `0xF` | `0x163` | `0x0` |
| `0xE` | `0x13` | `0x104` | `0x0` |
| `0xF` | `0x14` | `0x106` | `0x0` |
| `0x10` | `0x15` | `0x163` | `0x0` |
| `0x12` | `0x17` | `0x163` | `0x0` |
| `0x2` | `0x2` | `0x2` | `0x1` |
| `0x3` | `0x3` | `0x3` | `0x2` |
| `0x4` | `0x4` | `0x1` | `0x3` |
| `0xB` | `0xC` | `0x63` | `0x4` |
| `0x11` | `0x5` | `0x63` | `0x5` |
| `0x13` | `0x16` | `0x63` | `0x6` |
| `0x14` | `0x12` | `0x63` | `0x7` |
| `0x1B` | `0x1A` | `0x263` | `0x8` |
| `0x18` | `0x11` | `0x63` | `0x9` |
| `0x16` | `0x1B` | `0x63` | `0xA` |

Menu table 18 (17 rows, flags `0x24`): each row is four u16.

| a | b | c | d |
| --- | --- | --- | --- |
| `0x1` | `0x6` | `0x1` | `0x0` |
| `0x15` | `0x7` | `0x1` | `0x0` |
| `0xE` | `0x8` | `0x1` | `0x0` |
| `0x8` | `0x9` | `0x1` | `0x0` |
| `0x9` | `0xA` | `0x1` | `0x0` |
| `0xA` | `0xB` | `0x1` | `0x0` |
| `0xF` | `0xD` | `0x1` | `0x0` |
| `0xD` | `0xF` | `0x1` | `0x0` |
| `0x17` | `0x10` | `0x1` | `0x0` |
| `0x16` | `0x11` | `0x1` | `0x0` |
| `0x19` | `0x0` | `0x100` | `0x0` |
| `0x1A` | `0x1` | `0x200` | `0x0` |
| `0x2` | `0x2` | `0x300` | `0x0` |
| `0x3` | `0x3` | `0x400` | `0x0` |
| `0x5` | `0x4` | `0x500` | `0x0` |
| `0x6` | `0x5` | `0x600` | `0x0` |
| `0xB` | `0xC` | `0x700` | `0x0` |

History (table 19, flags `0x34`, 4 rows of 40 bytes): each row is `u16 0x0280`, `u16` slot x `0x20`, `u16` row
number (0 to 3), 6 zero bytes, then at offset 12 the date string `YYYY-MM-DD` (short ASCII form, 11 bytes),
the 8 bytes `19 1e 0b 31 30 30 30 03`, and zeros up to 40 bytes. The meaning of the trailer bytes is not known.
The page header is then patched: bytes `0x18` to `0x1A` become `04 20 00`, `u5` and `nrl` (`0x20`, `0x22`)
become 2 and 2, and the last four bytes of the page, which are normally the masks of the first group,
become `0x0008` and `0x000C`. The meaning is not known. A rekordbox history page counts its
rows in two parts and keeps two of the four masks, which is what this reproduces.
The date is the day of the first call in the process.

#### export.pdb, worked example

These dumps come from the key written by the built program with three synthetic WAV tracks (3 seconds
each) in one playlist named `list`.

Page 0, first 0x80 bytes. Table `t` starts at `0x1C + 16 t`:

```
0000  00 00 00 00 00 10 00 00 14 00 00 00 32 00 00 00
0010  05 00 00 00 0c 00 00 00 00 00 00 00 00 00 00 00
0020  29 00 00 00 01 00 00 00 02 00 00 00 01 00 00 00
0030  04 00 00 00 03 00 00 00 03 00 00 00 02 00 00 00
0040  2a 00 00 00 05 00 00 00 06 00 00 00 03 00 00 00
0050  08 00 00 00 07 00 00 00 07 00 00 00 04 00 00 00
0060  0a 00 00 00 09 00 00 00 09 00 00 00 05 00 00 00
0070  0c 00 00 00 0b 00 00 00 0b 00 00 00 06 00 00 00
```

Reading it: page size `0x1000`, 20 tables, `next_unused` `0x32` (50), constant 5, sequence `0x0C` (12).
Table 0: type 0, `empty_candidate` `0x29` (41), `first_page` 1, `last_page` 2. Table 1 (Genres) has no
rows: `empty_candidate` 4 (= 2 + 2 x 1), first and last page 3. Table 2 (Artists): candidate `0x2A` (42),
pages 5 to 6.

Index page 1 (table 0), first 0x40 bytes:

```
0000  00 00 00 00 01 00 00 00 00 00 00 00 02 00 00 00
0010  0b 00 00 00 00 00 00 00 00 00 00 64 00 00 00 00
0020  ff 1f ff 1f ec 03 01 00 01 00 00 00 02 00 00 00
0030  ff ff ff 03 00 00 00 00 01 00 ff 1f 10 00 00 00
```

Flags `0x64` at `0x1B`, `0x1FFF 0x1FFF` at `0x20`, 1004 (`0x03EC`) at `0x24`, 1 at `0x26`. The body starts at `0x28`:
page 1, first data page 2, `0x03FFFFFF`, 0, one entry, `0x1FFF`, then the entry `0x10` (page 2, shifted by 3).

Data page 2 (table 0, three rows), header and the end of the page:

```
0000  00 00 00 00 02 00 00 00 00 00 00 00 29 00 00 00
0010  02 00 00 00 00 00 00 00 03 60 00 34 aa 0c 24 03
0020  03 00 00 00 00 00 00 00 24 00 00 00 00 07 0c 00
0030  44 ac 00 00 00 00 00 00 5c 13 08 00 00 00 00 00
...
0ff0  00 00 00 00 00 00 18 02 0c 01 00 00 07 00 07 00
```

The sequence is 2. The packed count `03 60 00` is 3 | (3 << 13). Flags `0x34`. Free space
`0x0CAA` = 3242 = 4056 - 804 - 10, used `0x0324` = 804 = 3 x 268, `u5` 3. The row index at the end:
offsets 0, `0x10C`, `0x218` (reverse order), masks `0x0007` and `0x0007`.

The first track row (268 bytes, track id 1, no bpm, no artwork, no key):

```
0000  24 00 00 00 00 07 0c 00 44 ac 00 00 00 00 00 00
0010  5c 13 08 00 00 00 00 00 bf 30 59 c2 00 00 00 00
0020  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0030  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0040  00 00 00 00 01 00 00 00 01 00 00 00 00 00 00 00
0050  00 00 10 00 03 00 29 00 00 00 0b 00 03 00 88 00
0060  89 00 8a 00 8c 00 8e 00 8f 00 90 00 93 00 96 00
0070  97 00 98 00 a3 00 a4 00 a5 00 a6 00 d2 00 dd 00
0080  de 00 e1 00 e2 00 e9 00 03 03 05 32 05 32 03 03
0090  07 4f 4e 07 4f 4e 03 03 17 32 30 32 36 2d 31 30
00a0  2d 30 37 03 03 03 59 2f 50 49 4f 4e 45 45 52 2f
00b0  55 53 42 41 4e 4c 5a 2f 50 30 30 37 2f 30 30 30
00c0  30 38 34 35 35 2f 41 4e 4c 5a 30 30 30 30 2e 44
00d0  41 54 17 32 30 32 36 2d 31 30 2d 30 37 03 07 54
00e0  30 03 0f 74 30 2e 77 61 76 45 2f 43 6f 6e 74 65
00f0  6e 74 73 2f 41 30 2f 55 6e 6b 6e 6f 77 6e 20 41
0100  6c 62 75 6d 2f 74 30 2e 77 61 76 00
```

- `0x00` `24 00`, `0x02` `00 00` (slot 0), `0x04` `00 07 0c 00`, `0x08` `44 ac 00 00` (44100), `0x10` `5c 13 08 00`
  (529244 bytes), `0x18` `bf 30 59 c2`.
- `0x44` artist id 1, `0x48` track id 1, `0x52` `10 00` (16), `0x54` `03 00` (3 seconds), `0x56` `29 00` (41),
  `0x5A` `0b 00` (WAV, 11), `0x5C` `03 00`.
- `0x5E` the 21 string offsets: `88 00`, `89 00`, `8a 00`, `8c 00`... The first string is at `0x88`, the empty
  strings take one byte each (`03`), `05 32` is the string `2`, `07 4f 4e` is `ON`, `17` followed by
  `2026-10-07` is the date (`((10 + 1) << 1) | 1 = 0x17`).
- String 14 starts at `0xA6` with `59` (`((43 + 1) << 1) | 1`): `/PIONEER/USBANLZ/P007/00008455/ANLZ0000.DAT`.
- String 20 (offset `0xE9`) starts with `45`: `/Contents/A0/Unknown Album/t0.wav`. Its last byte is followed by
  one zero pad byte to make the row 268 bytes.

Other rows of the same key:

```
Artist  (id 1, "A0"):    60 00 00 00 01 00 00 00 03 0a 07 41 30 00 00 00
Colour  (id 1, "Pink"):  00 00 00 00 01 01 00 00 0b 50 69 6e 6b 00 00 00
Tree    (id 1, "list"):  00 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00 0b 6c 69 73 74 00 00 00
Entry   (1, track 1, playlist 1):  01 00 00 00 01 00 00 00 01 00 00 00
```

In the Artist row the bytes are `60 00`, `00 00`, id `01 00 00 00`, `03`, name offset `0a`, then `07 41 30`
(short ASCII, 2 characters, `A0`). The tree row has parent 0, 0, sort 0, id 1, folder 0, then `0b 6c 69 73 74`
(`list`). The entry row is position 1, track 1, playlist 1.

A track with a non-ASCII title, from the same writer run on a synthetic track (the title is `Cafe del Mar`
with an acute accent on the e): the title is stored as UTF-16LE, so it starts with `90`, the u16 length
`1c 00` (2 x 12 + 4 = 28) and a `00` byte, and it is aligned on a 4 byte boundary. The two zero bytes before it
are the pad.

```
00d0  41 54 17 32 30 32 36 2d 31 30 2d 30 37 03 00 00
00e0  90 1c 00 00 43 00 61 00 66 00 e9 00 20 00 64 00
00f0  65 00 6c 00 20 00 4d 00 61 00 72 00 03 13 63 61
0100  66 65 2e 77 61 76 41 2f 43 6f 6e 74 65 6e 74 73
0110  2f 41 72 74 69 73 74 2f 41 6c 62 75 6d 2f 63 61
0120  66 65 2e 77 61 76 00 00
```

The offsets of strings 16 (`dd`) and 17 (`e0`) show it: string 16, the empty comment, is the single byte
`03` at `0xDD`, followed by the two pad bytes `00 00`, and the title begins at `0xE0`.

### Recipe: CDJ key, ANLZ files

**You need:**

- For each track: the path on the key (the one stored in the row), bpm, grid anchor in ms, duration in
  seconds, the hot cues and the memory cues.
- The audio, decoded, to compute the waveforms (see "Waveform columns" below).
- A big-endian writer.

**Steps:**

1. Compute the folder with the hash of section "Key layout" and the file names `ANLZ0000.DAT` and
   `ANLZ0000.EXT`.
2. Compute the waveform columns: a fine array at 150 columns per second with the three bands
   (low, mid, high), then 400, 100 and 1200 column versions.
3. Build the `.DAT` sections in this order: `PPTH`, `PVBR`, `PQTZ`, `PWAV`, `PWV2`, `PCOB` (hot cues),
   `PCOB` (memory cues).
4. Build the `.EXT` sections in this order: `PPTH`, `PWV3`, `PCOB` (hot), `PCOB` (memory), `PCO2`
   (hot), `PCO2` (memory), `PWV5`, `PWV4`.
5. Put each list of sections behind a `PMAI` header whose second length field is the total file size.
6. Check both files (`validate.anlz`), then write them (temporary file, read-back, rename).

**Pitfalls:**

- Big endian everywhere in ANLZ, little endian in the PDB.
- Every section is `tag(4)`, `header length u32`, `total length u32`, then the rest of the header, then
  the data. The `PMAI` file header length is 28 and its total length is the length of the whole file.
- The lengths must be consistent: each total length is exactly the section size, the sum of the
  sections plus 28 is the file size, `PQTZ` data is `8 x count` bytes, waveform data is
  `width x count` bytes, a cue list ends exactly after its last cue.
- `PPTH` holds the path in UTF-16BE with a final zero character, and the length field counts those 2
  bytes. It must equal the path in the PDB row.
- `PVBR` is always 1620 bytes: 16 header bytes, 400 offsets of 4 bytes left at 0, then the sample count.
- `PQTZ` tempo is a u16, so the tempo x 100 must not exceed 65535 (655.35 BPM). The exporter raises an
  error above that when a grid is set.
- A track without a grid or without bpm gets a `PQTZ` with zero beats. The section is still written.
- The `PCOB` non-loop end is `0xFFFFFFFF`, the `PCP2` non-loop end is 0.
- At most 8 hot cues are written. A hot cue colour must be one of the 62 palette colours or the player
  ignores it.
- Waveforms are normalised on the whole track, so a very loud peak flattens the rest.
- `PQT2`, `PSSI` and the `.2EX` file only matter to the CDJ-3000 and are not written.

**Check:** parse the file with `validate.anlz(raw, path, "DAT")` or `"EXT"`. Compare each section with
the one rekordbox writes for the same file (header fields and section order). The first thing to look
at when a CDJ ignores a track is the folder name and the `PPTH` path.

#### ANLZ

Big-endian. `PMAI` header: header length 28, total length, then `1, 0x10000, 0x10000, 0`. Every
section: tag, header length, total length.

- `.DAT`: `PPTH` (UTF-16BE path with a NUL), `PVBR`, `PQTZ`, `PWAV`, `PWV2`, `PCOB` hot cues,
  `PCOB` memory cues.
- `.EXT`: `PPTH`, `PWV3`, `PCOB` x2, `PCO2` x2, `PWV5`, `PWV4`. `PQT2`, `PSSI` and the `.2EX`
  file only matter to the CDJ-3000 and are not written.
- `PVBR`: the last value is the total number of samples. The 400 index values before it can stay
  at 0.
- `PQTZ`: `0, 0x80000, n`, then per beat u16 beat in bar (1-4), u16 tempo x 100, u32 ms. Beats
  are laid from the grid anchor, which is beat 1.
- `PWAV` has 400 columns, `PWV2` 100, `PWV3` and `PWV5` 150 per second, `PWV4` 1200.
  - `PWAV` / `PWV3`: `whiteness << 5 | height` (0-31).
  - `PWV5`: `r << 13 | g << 10 | b << 7 | height << 2`.
  - `PWV4`: 6 bytes per column, the players draw bytes 3-5 (red, green, blue).
- `PCPT` (56 bytes): `hot_cue` 0 for a memory cue, 1-8 for A-H, type 1 cue or 2 loop, time and
  loop end in ms.
- `PCP2` adds the name in UTF-16BE. For hot cues it also holds the rekordbox colour id (byte 28)
  and the hot cue palette code, R, G, B as its last 4 bytes (code 0 and 0, 0, 0 for a memory cue).

Cue colours: a hot cue takes the colour read from its source (`#RRGGBB`) or, when it has none, the
default colour of its pad (A to H, see section 7), and the result goes to the nearest of the 62
palette colours below. The `PCP2` colour id is the nearest of the 8 rekordbox colours (1 pink to 8
purple) to that palette colour. Memory cues stay uncoloured. Fade and grid cues are not exported.

File layout of a section, all numbers big endian:

| Section | Header length | Header after the 12 byte start | Data |
| --- | --- | --- | --- |
| `PMAI` | 28 | `0x0C` u32 1, `0x10` u32 `0x10000`, `0x14` u32 `0x10000`, `0x18` u32 0 | the sections |
| `PPTH` | 16 | `0x0C` u32 byte length of the path field | UTF-16BE path, `00 00` |
| `PVBR` | 16 | `0x0C` u32 0 | 400 x u32 0, u32 total sample count (1604 bytes) |
| `PQTZ` | 24 | `0x0C` u32 0, `0x10` u32 `0x80000`, `0x14` u32 number of beats | per beat: u16 beat number 1-4, u16 tempo x 100, u32 time in ms |
| `PWAV` | 20 | `0x0C` u32 column count (400), `0x10` u32 `0x10000` | 1 byte per column |
| `PWV2` | 20 | `0x0C` u32 column count (100), `0x10` u32 `0x10000` | 1 byte per column |
| `PWV3` | 24 | `0x0C` u32 1 (bytes per column), `0x10` u32 column count, `0x14` u16 150, `0x16` u16 0 | 1 byte per column |
| `PWV5` | 24 | `0x0C` u32 2, `0x10` u32 column count, `0x14` u16 150, `0x16` u16 `0x0305` | u16 per column |
| `PWV4` | 24 | `0x0C` u32 6, `0x10` u32 column count (1200), `0x14` u32 0 | 6 bytes per column |
| `PCOB` | 24 | `0x0C` u32 list (1 hot cues, 0 memory cues), `0x10` u16 0, `0x12` u16 number of cues, `0x14` u32 `0xFFFFFFFF` | the `PCPT` entries |
| `PCO2` | 20 | `0x0C` u32 list (1 hot cues, 0 memory cues), `0x10` u16 number of cues, `0x12` u16 0 | the `PCP2` entries |

The `PMAI` start is `PMAI`, u32 28, u32 total size. In `PWAV` and `PWV2` the first value after the
12 byte start is the column count, whereas `PWV3`, `PWV4` and `PWV5` first give the bytes per column
and then the count. `0x0305` and `0x10000` are constants, meaning unknown.

`PVBR` stores the number of frames of the audio file at its own sample rate (not of the reduced
signal).

Section sizes of the sample key (3 second track, no grid, no cue): `.DAT` is 2344 bytes: `PMAI` 28, `PPTH` 84,
`PVBR` 1620, `PQTZ` 24, `PWAV` 420, `PWV2` 120, `PCOB` 24, `PCOB` 24. `.EXT` is 8822 bytes: `PMAI` 28, `PPTH` 84,
`PWV3` 474 (450 columns), `PCOB` 24, `PCOB` 24, `PCO2` 20, `PCO2` 20, `PWV5` 924, `PWV4` 7224.

Headers of the sample `.DAT` (the first 28 bytes, then the start of the `PPTH`):

```
0000  50 4d 41 49 00 00 00 1c 00 00 09 28 00 00 00 01
0010  00 01 00 00 00 01 00 00 00 00 00 00 50 50 54 48
0020  00 00 00 10 00 00 00 54 00 00 00 44 00 2f 00 43
0030  00 6f 00 6e 00 74 00 65 00 6e 00 74
```

`50 4d 41 49` is `PMAI`, `1c` the header length 28, `0928` the file size 2344, then 1, `0x10000`, `0x10000`, 0.
`PPTH` has header length `0x10` (16), total `0x54` (84) and a path length `0x44` (68 = 2 x 33 + 2).

#### Beat grid (PQTZ)

Inputs: `bpm`, `grid` (the anchor, a beat in ms) and `duration` in seconds.

- No beat is written when `bpm` is 0 or less, `grid` is unset or the duration is 0.
- `step = 60000 / bpm` (ms, a float).
- `back = floor(grid / step)` and `first = grid - back x step`: the first beat at or after 0.
- Beat `i` (from 0) is at `first + i x step` ms, and is written while that time is below
  `duration x 1000`.
- Its position in the bar is `((i - back) mod 4) + 1`. The anchor itself is beat 1, and a bar goes on
  in 4s before and after it.
- The time is rounded half to even to a whole millisecond, the tempo of every entry is
  `round(bpm x 100)`.

Example (synthetic track, bpm 123.5, anchor 80 ms, 3 seconds). The step is 485.83 ms and 7 beats fit:

```
0000  50 51 54 5a 00 00 00 18 00 00 00 50 00 00 00 00
0010  00 08 00 00 00 00 00 07 00 01 30 3e 00 00 00 50
0020  00 02 30 3e 00 00 02 36 00 03 30 3e 00 00 04 1c
0030  00 04 30 3e 00 00 06 01
```

`PQTZ`, header 24, total `0x50` (80), 0, `0x80000`, 7 beats. First entry: beat `00 01`, tempo `30 3e`
(12350), time `00 00 00 50` (80 ms). Second entry: beat 2, same tempo, `0x236` (566 ms).

#### Waveform columns

The audio is decoded once per track.

1. Decode with `soundfile` in blocks of 65536 frames (`librosa` for MP3 and M4A that libsndfile cannot
   read). Each group of 4 frames, all channels averaged, becomes one mono sample (rate divided by 4,
   integer division).
2. Two second order Butterworth filters (`scipy.signal.butter`, forward `sosfilt`, zero state) split
   the signal: low pass at 200 Hz, high pass at 2500 Hz. Both cut-offs are lowered to 45 percent of the
   reduced rate if that is smaller. The mid band is the signal minus the low and the high band.
3. The number of fine columns is `max(1, round(seconds x 150))`, with `seconds = samples / rate`. Column `c`
   covers samples `c x per` to `(c + 1) x per - 1` where `per = samples div columns`, and the tail
   is dropped. Each band keeps its peak absolute value in the column.
4. All values are divided by the largest peak of the three bands over all columns (by 1 if that is 0)
   and clipped to the range 0 to 1.
5. The other widths are taken from the fine columns: column `k` of `n` covers the fine columns from
   `floor(k x L / n)` up to `floor((k + 1) x L / n)` (the last one to the end) and keeps the largest
   value of each band.
6. If the file cannot be decoded, or has fewer samples than columns, the bands are all zero. The fine
   column count is then `round(duration x 150)` and the `PVBR` sample count 0.

The `.DAT` takes the 400 and 100 column versions. The `.EXT` takes the fine columns for `PWV3` and `PWV5`
and the 1200 column version for `PWV4`.

For a column let `top = max(low, mid, high)`.

| Section | Byte or word |
| --- | --- |
| `PWAV`, `PWV3` | `(whiteness << 5) + height`. `height = round(31 x top)`. `ratio = high / top` (1 if `top` is 0.01 or less), `whiteness = round(7 x ratio)`. |
| `PWV2` | `round(15 x top)` |
| `PWV5` | u16: `(r << 13) + (g << 10) + (b << 7) + (height << 2)`, `height = round(31 x top)`. When `top` is above 0.01: `r = round(7 x low / top)`, `g = round(7 x mid / top)`, `b = round(7 x high / top)`. Otherwise r, g, b are 0. |
| `PWV4` | 6 bytes: `top, top, top, low, mid, high`, with each value `round(127 x v)` and `top` the largest of the three. The players draw bytes 3 to 5. |

`round` is half to even (numpy `rint`). Example: the first bytes of the `PWAV` of the sample are `b2 b3 99 d1`, that
is whiteness 5 height 18, whiteness 5 height 19, whiteness 4 height 25, whiteness 6 height 17.

#### Cues

Lists. The hot cue list (`PCOB`/`PCO2` list 1) holds the cues with `hotcue >= 0` of kind cue, loop or load,
sorted by slot, at most 8. The memory list (list 0) holds those with `hotcue < 0`, in model order.
Each list is written even when empty (count 0, header only).

`PCPT` (56 bytes, big endian):

| Offset | Size | Value |
| --- | --- | --- |
| `0x00` | 4 | `PCPT` |
| `0x04` | u32 | 28, header length |
| `0x08` | u32 | 56, total length |
| `0x0C` | u32 | slot: `hotcue + 1` (1 to 8 for A to H), 0 for a memory cue |
| `0x10` | u32 | 0 |
| `0x14` | u32 | `0x10000` |
| `0x18`, `0x1A` | u16 | `0xFFFF`, `0xFFFF` |
| `0x1C` | u8 | 1 for a cue, 2 for a loop |
| `0x1D` | u8 | 0 |
| `0x1E` | u16 | 1000, constant, meaning unknown |
| `0x20` | u32 | start in ms, rounded, never below 0 |
| `0x24` | u32 | end in ms for a loop (start + length), `0xFFFFFFFF` otherwise |
| `0x28` | 16 bytes | zeros |

`PCP2` (big endian, `0x2C + name + 4` bytes):

| Offset | Size | Value |
| --- | --- | --- |
| `0x00` | 4 | `PCP2` |
| `0x04` | u32 | 16, header length |
| `0x08` | u32 | total length: `0x2C` + name bytes + 4 |
| `0x0C` | u32 | slot as in `PCPT` |
| `0x10` | u8 | 1 cue, 2 loop |
| `0x11` | u8 | 0 |
| `0x12` | u16 | 1000 |
| `0x14` | u32 | start in ms |
| `0x18` | u32 | end in ms for a loop, 0 otherwise |
| `0x1C` | u8 | rekordbox colour id 1 to 8, 0 for a memory cue |
| `0x1D` | 7 bytes | zeros |
| `0x24` | u16, u16 | 0, 0 |
| `0x28` | u32 | name length in bytes, including the final `00 00`; 0 when there is no name |
| `0x2C` | n bytes | name in UTF-16BE with `00 00` (the name is stripped of white space first) |
| after the name | 4 bytes | hot cue palette code (1 to 62), R, G, B; all zero for a memory cue |

A loop is a cue with a length above 0. Positions are rounded half to even. The cue colour is chosen as
described above: source colour (`#RRGGBB` or 8 digits, the last 6 are used) else the default of the
slot (`HOT_RGB[slot mod 8]`), then the nearest entry (smallest sum of squared differences in R, G, B,
the first one on a tie) of the palette.

Hot cue palette, codes 1 to 62 (the player shows the code and ignores a colour it does not find; code 0 is the old default green):

```
 1:305AFF   2:5073FF   3:508CFF   4:50A0FF   5:50B4FF   6:50B0F2
 7:50AEE8   8:45ACDB   9:00E0FF  10:19DAF0  11:32D2E6  12:21B4B9
13:20AAA0  14:1FA392  15:19A08C  16:14A584  17:14AA7D  18:10B176
19:30D26E  20:37DE5A  21:3CEB50  22:28E214  23:7DC13D  24:8CC832
25:9BD723  26:A5E116  27:A5DC0A  28:AAD208  29:B4C805  30:B4BE04
31:BAB404  32:C3AF04  33:E1AA00  34:FFA000  35:FF9600  36:FF8C00
37:FF7500  38:E0641B  39:E0461E  40:E0301E  41:E02823  42:E62828
43:FF376F  44:FF2D6F  45:FF127B  46:F51E8C  47:EB2DA0  48:E637B4
49:DE44CF  50:DE448D  51:E630B4  52:E619DC  53:E600FF  54:DC00FF
55:CC00FF  56:B432FF  57:B93CFF  58:C542FF  59:AA5AFF  60:AA72FF
61:8272FF  62:6473FF
```

Example from the same synthetic track as above: a hot cue A named `Intro` at 1500 ms and a memory loop from
1000 to 2000 ms (no name). `PCOB` hot cue list with one `PCPT`:

```
0000  50 43 4f 42 00 00 00 18 00 00 00 50 00 00 00 01
0010  00 00 00 01 ff ff ff ff 50 43 50 54 00 00 00 1c
0020  00 00 00 38 00 00 00 01 00 00 00 00 00 01 00 00
0030  ff ff ff ff 01 00 03 e8 00 00 05 dc ff ff ff ff
0040  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

Reading it: `PCOB`, header 24, total `0x50`, list `00 00 00 01`, `00 00`, count `00 01`, `ff ff ff ff`, then `PCPT`, 28,
`0x38` (56), slot 1, 0, `0x10000`, `ffff ffff`, type 1, 0, `03e8` (1000), start `0x5dc` (1500), end `ffffffff`,
16 zero bytes.

The `PCO2` entry of the same hot cue and of the memory loop:

```
0000  50 43 4f 32 00 00 00 14 00 00 00 50 00 00 00 01
0010  00 01 00 00 50 43 50 32 00 00 00 10 00 00 00 3c
0020  00 00 00 01 01 00 03 e8 00 00 05 dc 00 00 00 00
0030  05 00 00 00 00 00 00 00 00 00 00 00 00 00 00 0c
0040  00 49 00 6e 00 74 00 72 00 6f 00 00 16 28 e2 14

0000  50 43 4f 32 00 00 00 14 00 00 00 44 00 00 00 00
0010  00 01 00 00 50 43 50 32 00 00 00 10 00 00 00 30
0020  00 00 00 00 02 00 03 e8 00 00 03 e8 00 00 07 d0
0030  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0040  00 00 00 00
```

For the hot cue: `PCP2`, 16, `0x3c` (60 = 0x2C + 12 + 4), slot 1, type 1, 0, 1000, start 1500, end 0, colour id `05` (green, byte
`0x1C`), 7 zeros, `0000 0000`, name length `0c` (12 bytes: `Intro` = 5 characters x 2 + 2), the name `00 49 00 6e 00 74 00 72 00 6f 00 00`, then
`16 28 e2 14`: palette code 22 and the colour 40, 226, 20. For the memory loop: total `0x30` (48), slot 0, type 2, start
1000, end 2000, colour id 0, no name, last four bytes zero.

### Recipe: CDJ key, artwork

**You need:** the artwork embedded in the audio file (ID3 picture, FLAC picture, MP4 cover), Pillow (PIL)
to decode and resize, and the `PIONEER/Artwork/00001/` folder.

**Steps:**

1. For each track in id order, read the embedded picture. A track without picture keeps artwork id 0.
2. Hash the picture bytes with SHA-1. A picture already seen gives the same artwork id again and writes
   no new file.
3. Reject a picture of more than 40,000,000 pixels before decoding its pixels. A picture that cannot be decoded is
   skipped as well.
4. Convert the picture to RGB. The new id `n` is the number of distinct pictures written so far plus 1.
5. Write two JPEG files, quality 90, both squares resized with the Lanczos filter (the picture is stretched
   to a square, the aspect ratio is not kept): `a<n>.jpg` at 80 x 80 and `a<n>_m.jpg` at 240 x 240.
6. Store `n` in the track row (offset `0x1C`) and add one Artwork row per id to the database
   (`/PIONEER/Artwork/00001/a<n>.jpg`).

**Pitfalls:**

- Write the pictures before the database: the track rows need the ids.
- Without Pillow the export has no artwork at all and every track row has artwork id 0.
- The folder is always `00001` in this writer, and ids are numbered from 1 in order of first use.
- The picture is stretched, not cropped.
- The files are written directly (no temporary name), hashed for the manifest from the bytes written.
- The database refers to the 80 pixel name. The 240 pixel file has the same name plus `_m`.

**Check:** every Artwork row has its file, every track row with a non-zero artwork id has a row in the
Artwork table, and the manifest lists the JPEG files (category Artwork).

### Recipe: CDJ key, settings files

**You need:** the four layouts below and the CRC16 XMODEM function (`binascii.crc_hqx(data, 0)`).

**Steps:**

1. For each file, build the body: the magic bytes first (if any), then the setting bytes at their
   positions, zero for the others, padded to the body size.
2. Build the header: u32 `0x60`, then three 32 byte fields (padded with zeros): the brand, `rekordbox`,
   the version; then a u32 with the body length. The header is 0x68 bytes.
3. Append the CRC16 as a u16 little endian and two zero bytes. The CRC covers the body for
   `MYSETTING.DAT`, `MYSETTING2.DAT` and `DEVSETTING.DAT`, and the header plus the body for
   `DJMMYSETTING.DAT`.
4. Write each file into `PIONEER/` only if it does not exist yet, so a settings file a player or
   rekordbox changed is kept.

**Pitfalls:**

- Positions in the tables below are 1-based positions in the body, so position 9 is `body[8]`.
- All the setting values are enum values counted from `0x80` (one byte each).
- The mixer file is the only one where the CRC includes the header.
- Brand and version differ per file: `PIONEER` `0.001` for `MYSETTING.DAT` and `MYSETTING2.DAT`,
  `PioneerDJ` `1.000` for `DJMMYSETTING.DAT`, `PIONEER DJ` `7.2.11` for `DEVSETTING.DAT`.
- The values are neutral defaults chosen in the code. They are not copied from Pioneer files. The
  layout follows the open source projects pyrekordbox and rekordcrate. The meanings in the tables are
  the code comments.

**Check:** the size of each file is 148, 148, 160 and 140 bytes (header 104, body, 4). Recompute the CRC from
the bytes. Open the key on a player and look at the settings shown in the menu.

#### Settings files

| File | Brand, version | Body size | Magic (start of the body) | CRC covers | File size |
| --- | --- | --- | --- | --- | --- |
| `MYSETTING.DAT` | `PIONEER`, `0.001` | 40 | `78 56 34 12 02 00 00 00` | body | 148 |
| `MYSETTING2.DAT` | `PIONEER`, `0.001` | 40 | none | body | 148 |
| `DJMMYSETTING.DAT` | `PioneerDJ`, `1.000` | 52 | `78 56 34 12 01 00 00 00 20 00 00 00` | header and body | 160 |
| `DEVSETTING.DAT` | `PIONEER DJ`, `7.2.11` | 32 | `78 56 34 12 01 00 00 00`, then nine bytes `01`, then 15 zero bytes | body | 140 |

`DEVSETTING.DAT` has no other setting.

File layout: `0x00` u32 `0x60`, `0x04` 32 bytes brand, `0x24` 32 bytes `rekordbox`, `0x44` 32 bytes version,
`0x64` u32 body length, `0x68` body, then u16 CRC (little endian) and 2 zero bytes.

Example, `MYSETTING.DAT` of the sample key: header `60 00 00 00`, `PIONEER`, `rekordbox`, `0.001`, `28 00 00 00` (40), then the body
`78 56 34 12 02 00 00 00 81 83 81 88 80 01 82 81 81 01 01 01 82 80 80 80 80 81 81 00 00 80 00 00 80 80 81 80 81 80 00 00`
and the CRC `a4 12` (0x12A4), `00 00`.

`MYSETTING.DAT` bytes (position in the body, value, meaning as commented in the code):

| Position | Value | Meaning in the code |
| --- | --- | --- |
| 9 | `0x81` | on air display: on |
| 10 | `0x83` | LCD brightness: three |
| 11 | `0x81` | quantize: on |
| 12 | `0x88` | auto cue level: memory |
| 13 | `0x80` | language: english |
| 14 | `0x01` | no comment in the code |
| 15 | `0x82` | jog ring brightness: bright |
| 16 | `0x81` | jog ring indicator: on |
| 17 | `0x81` | slip flashing: on |
| 18 | `0x01` | no comment in the code |
| 19 | `0x01` | no comment in the code |
| 20 | `0x01` | no comment in the code |
| 21 | `0x82` | disc slot illumination: bright |
| 22 | `0x80` | eject lock: unlock |
| 23 | `0x80` | sync: off |
| 24 | `0x80` | play mode: continue |
| 25 | `0x80` | quantize beat value: one |
| 26 | `0x81` | hot cue auto load: on |
| 27 | `0x81` | hot cue colour: on |
| 30 | `0x80` | needle lock: unlock |
| 33 | `0x80` | time mode: elapsed |
| 34 | `0x80` | jog mode: cdj |
| 35 | `0x81` | auto cue: on |
| 36 | `0x80` | master tempo: off |
| 37 | `0x81` | tempo range: ten |
| 38 | `0x80` | phase meter: type 1 |

`MYSETTING2.DAT` bytes:

| Position | Value | Meaning in the code |
| --- | --- | --- |
| 1 | `0x81` | vinyl speed adjust: touch |
| 2 | `0x80` | jog display mode: auto |
| 3 | `0x83` | pad / button brightness: three |
| 4 | `0x83` | jog LCD brightness: three |
| 5 | `0x81` | waveform divisions: phrase |
| 11 | `0x80` | waveform: waveform |
| 12 | `0x81` | no comment in the code |
| 13 | `0x85` | beat jump beat value: sixteen |

`DJMMYSETTING.DAT` bytes:

| Position | Value | Meaning in the code |
| --- | --- | --- |
| 13 | `0x81` | channel fader curve: linear |
| 14 | `0x82` | cross fader curve: fast cut |
| 15 | `0x80` | headphones: post EQ |
| 16 | `0x80` | headphones: stereo |
| 17 | `0x81` | beat FX quantize: on |
| 18 | `0x80` | mic low cut: off |
| 19 | `0x80` | talk over mode: advanced |
| 20 | `0x82` | talk over level: minus 12 dB |
| 21 | `0x80` | MIDI channel: one |
| 22 | `0x80` | MIDI button type: toggle |
| 23 | `0x85` | display brightness: five |
| 24 | `0x82` | indicator brightness: three |
| 25 | `0x81` | channel fader curve: smooth |

### Recipe: CDJ key, order of writing

This is the recipe that ties the others together. It follows `usb.export`.

**You need:** the playlist tree, the output folder (the root of the key), the music files, Pillow for
artwork, the audio decoder for the waveforms, and the helpers of the previous recipes.

**Steps:**

1. Collect the tracks: `unique_tracks(nodes)`, in order. A track whose file is missing is skipped
   and reported. Fill a missing duration, sample rate or bitrate from the audio header.
2. Assign ids 1..N to the tracks that remain, in that order. Compute each path on the key (recipe
   "layout and file names").
3. Compute each ANLZ folder (path hash, collisions resolved against the folders already used) and
   the ANLZ path `<folder>/ANLZ0000.DAT`.
4. Look up each track in the analysis cache (key: the analysis version 7, source size, source
   modification time in seconds, key path, bpm, grid, duration and cues, hashed with SHA-1). A hit
   gives the DAT and EXT bytes, which are written at once.
5. For the others, start the analysis in worker processes (8 at most by default) and copy the audio to the key at
   the same time. The analysis reads the source, not the copy.
6. As each analysis result arrives, build the DAT and EXT bytes, validate them, write both files
   (temporary file, read-back, rename), then store the pair in the cache (DAT first, EXT last).
7. When the copy is over, read the size of every copied file. The size goes in the row.
8. Write the artwork and assign the artwork ids.
9. Build and write `export.pdb` (recipe "export.pdb"), validated and read back.
10. Write the four settings files if they do not exist.
11. Add `export.pdb` and the settings files to the manifest (the other files were added as they were
    written), save the manifest, and read the whole key back when `verify_copy` is on.

**Pitfalls:**

- Consistency between the files: the same path string in the track row (string 20), in the `PPTH` of both
  ANLZ files and as the real file on the key. The ANLZ path in the row (string 14) is the folder
  of that track plus `/ANLZ0000.DAT`. Artwork ids in the rows are ids of files that
  exist. Playlist entries refer to track ids that exist. Ids are the 1-based order of the exported
  tracks.
- The ANLZ files and the artwork are written before the database, which is written after the files
  it refers to. The previous database is replaced only at step 9.
- The header sequence rule, the 4096 byte pages, the exact free space and the 20 table pointers are
  traps of the database (recipe "export.pdb").
- ANLZ lengths must match their headers (recipe "ANLZ files").
- FAT32 name rules and the NTFS NO DISK trap (recipe "layout and file names").
- An existing settings file is never overwritten.
- A cached analysis is reused only if it validates for the expected path. A stale cache after a change
  to the ANLZ writer is avoided by raising `ANLZ_VERSION`.
- The C++ core and the Python code write the same bytes. The tests compare them. With `TB_PURE_PYTHON`
  set, or without `tbcore`, Python builds the files.
- The export does not merge with an older key: files of tracks that are no longer in the playlists stay
  on the key, and the database does not list them.

**Check:**

- `validate.pdb` and `validate.anlz` accept the files. They run before every write.
- The manifest holds every file, and `manifest.verify` reads the key back (**Tools > Verify an export**).
- `pdbread` lists every track and playlist.
- A CDJ-2000NXS2 browses the key, shows the cover pictures and the waveforms, and loads the cues and
  the grid.
- Compare byte by byte, field by field, with a key that rekordbox wrote from the same tracks.

#### What validate.py checks

`validate.pdb(data)`:

- The size is a whole number of 4096 byte pages (at least one).
- Header: the first u32 is 0, the page size is 4096, there are 20 tables, `next_unused` is at least the
  number of pages.
- For each table: `type` equals its position. Follow the chain from `first_page`: every page number is
  greater than 0 and inside the file, not seen before in the chain and not used by another table. Each page has the right index
  and type. The chain stops at `last_page`.
- For every page without the index flag `0x40`: `0x28 + used + index_size(rows) + free` equals 4096, and every
  row offset is below `used`.

It does not check the sequence numbers, the index page contents, the row contents or the masks. Section 10 lists
the same checks in the safeguards.

`validate.anlz(data, expected_path, extension)`:

- Starts with `PMAI`, header length 28, total length equal to the length of the data.
- Every section: its header is 12 or more bytes and not more than its total length, and it fits in the file.
- `PPTH`: header 16, path length equal to the payload, at least 2, even, ends with `00 00`, decodes
  as UTF-16BE, equals `expected_path` when given.
- `PQTZ`: header 24, payload equal to 8 x the count.
- `PWAV`, `PWV2`, `PWV3`, `PWV4`, `PWV5`: header at least 20, width 1, 1, 1, 6, 2, payload equal to width x count.
- `PVBR`: header 16 and total 1620.
- `PCOB` (header 24) and `PCO2` (header 20): the count of entries, each entry begins with `PCPT` or `PCP2`, has sane
  lengths, and the entries end exactly at the end of the section.
- A `PPTH` must exist. A `.DAT` needs `PVBR`, `PQTZ`, `PWAV`, `PWV2` and `PCOB`. A `.EXT` needs `PWV3`,
  `PWV4`, `PWV5`, `PCOB` and `PCO2`.

`write_verified(path, data, validator)` runs the validator, writes `<path>.verified`, reads it back with
`sha256_drive`, compares with the digest of the data and renames. This happens whatever the audio
verification option says.

---

## 9. Audio analysis

Traktor and the other sources already did the musical analysis: bpm, grid, key and cues come
from the collection. Only the waveforms need the audio.

### Sources without a collection

A music folder (`sources/folder.py`) has no collection. Its bpm and key are read from the tags
(`tags.basic`, ID3, FLAC, MP4), and there is no grid until a first beat is set in the cue
editor.

The export never detects a tempo from the audio. The editors can, see Editors below.

CDJ exports leave out the beat entries when the grid or the tempo is missing. They do not invent
a zero anchor.

Beat positions are rounded to whole milliseconds and the tempo to hundredths. A tempo above the
unsigned 16-bit limit (655.35 BPM) is reported as an error.

### Decoding and waveform bands

`analysis.Audio` decodes each track once with soundfile, block by block into one reused buffer.
Loading a whole track at once allocates a large block of fresh memory per file, and on Windows
those page faults serialise between processes.

Mono and a quarter of the sample rate are computed in the same pass (11 kHz for a CD rip, plenty
for a picture of the sound). Two second order Butterworth filters split low (below 200 Hz) and
high (above 2500 Hz), and mid is what remains. Peaks are taken at 150 columns per second, and
the overviews come from there.

### Processes and cache

The analysis runs in up to 8 processes. Beyond that they fight over memory bandwidth instead of
helping. Traktor Bridge is not a live application, so it can use the whole machine for the job.

Results are cached in `%LOCALAPPDATA%/TraktorBridge/anlz`. The cache key is made of the audio
file (size, date), its path on the key, bpm, grid, duration, cues and `ANLZ_VERSION`.
`ANLZ_VERSION` must be raised whenever the generator changes, and it is also bumped when the
missing-grid behaviour above changes.

On a USB key the write speed of the key is the limit.

---

### Editors

This part covers the playlist window, the cue editor and the pieces they share.

#### Tempo and first-beat detection

`beatdetect.py` estimates a constant tempo and the first audible pulse from decoded audio.

It is tested with synthetic fixtures: fractional tempos, phase, octave ambiguity, silence and
noise. It is not validated against a representative corpus of real music, nor against a variable
tempo.

`analyze_many` reports errors per file and supports cancellation.

#### Detecting grids for a playlist

The playlist detection captures the initial BPM and grid pair of each track. When a result comes
back, it is applied on the GUI thread only if the track is reliable and unchanged. Removed or
edited tracks are skipped.

A `timing` history entry stores all the before and after pairs of one batch, so one Undo or Redo
covers the whole batch without replacing cues.

Cancelling, or closing the window, discards even the successful results that are still queued.

#### Playlist history

Each playlist keeps a history of 200 entries. It mixes track-list snapshots, project-field
applications, cue-history references and timing batches.

- Cue edit counters tell a fresh edit from an Undo or Redo.
- Reload clears the playlist history.
- Writing tags to audio files cannot be undone.
- The "Also in" index looks at audio IDs and at normalized absolute paths across the other
  loaded playlists.
- Keyboard shortcuts keep the native selection and text entry working. Keyboard reordering is
  refused while sorting or filtering is active.

#### Tag editor

`ui/tageditor.py` replaces the read-only Properties through the **ID Tag** column of the
playlist.

Applying changes modifies only the edited Track fields, never the source audio. An edit is
rejected as stale when its field changed elsewhere in the meantime. A BPM change joins the shared
timing history without moving cues or the grid anchor.

The engine's `metadata_changed` signal updates the open playlists and the cue editor headers,
and marks projects dirty. Table rebuilds block selection signals, so the preview position and the
active loops are kept.

#### Writing tags to the audio file

The separate, confirmed **Write** action runs `tagwrite.write` in a Job.

1. Mutagen updates a temporary copy in the same directory.
2. The standard tags are verified on that copy.
3. The first `.tb-tags.bak` backup is kept.
4. The source fingerprints are checked.
5. The copy replaces the file atomically.

Supported containers are MP3, WAV, AIFF, FLAC, MP4/M4A/ALAC and Ogg Vorbis. Unrelated frames and
comments, artwork and embedded DJ analysis are left intact.

Details of what is written:

- Only the canonical ID3 comment (empty description, English) is written.
- A blank field removes the matching tag.
- The rating is stored in the project only.
- MP4 precise BPM uses a freeform atom next to the compatible integer `tmpo`.

Playback sources must be released first, and closing the editor or the playlist is blocked while
a write runs. Project Reload and cue Undo do not cover audio file writes.

Frozen builds collect the modules that Mutagen imports dynamically.

#### Waveform view

`ui/zoomwave.py` draws the waveform for the player and the cue timeline.

- Ctrl+wheel zooms, down to a minimum span of 500 ms.
- A 14 px strip under the wave scrubs and moves the zoom window.
- A white line with its label marks each minute.
- A column of three buttons at the right of the wave: + zooms in around the cursor, the reset
  button shows the whole track, - zooms out.

Zoomed views read a detailed wave at 1000 points/s, computed from the decoded audio on first use
by `waveform.Loader` and cached as `<key>.hi1000`. Older `.hi` files are not reused.
`analysis.Audio(detail=1000)` computes that resolution directly, while the CDJ waveforms keep
their 150 points/s default.

A click moves the needle without playing. The engine is only seeked when it plays that very file.

`hot_key()` is the shared test of the A-H keys (Shift deletes). An application event filter uses
it in the playlist window and in the cue timeline, and ignores keys typed in a text field.

Save as NML calls `export.nml.export` with a file name and the resolved paths of the tracks.

#### Grid handle

The first-beat handle has its own header row, separate from the cue letters, so coincident
markers can still be dragged independently.

The cue editor can apply BPM and anchor together, set the anchor at the cursor, clear it, or
nudge it by 1/10 ms. Grid drags are never quantized and stay inside the track. They cancel on
Escape, when the widget is hidden, or on a release outside.

`cuehistory` snapshots cues, BPM and grid. A grid-only undo keeps the cue objects and the active
loops. Playlist grid drags emit both the change and the dirty notifications.

#### Metronome

`ui/metronome.py` synthesizes 12 ms PCM clicks at absolute beat positions, with an accent on the
downbeat. Fractional beat periods are never rounded again and again.

One engine owns the state and the volume, shared by both editors. A shared offset of -250..+250
ms compensates for device latency: negative advances the click, positive delays it.

How the output works:

- A precise 5 ms timer feeds a 30 ms `QAudioSink` buffer, rather than triggering individual
  clicks.
- The output follows the media player's position notifications, extrapolated with a monotonic
  clock.
- Drift correction adjusts future PCM after the device has started consuming data.
- Pause, seek, grid edits and deck changes flush the old output. Crossfades mute it.
- An output error disables the metronome, is logged and is shown in the active editor.

Queue and timing rules:

- Queued PCM is capped at 30 ms (written minus processed frames), whatever buffer size the
  backend allocated.
- Phase correction runs only when `processedUSecs` advances. It uses a 250 ms exponential time
  constant, not a multiplier per callback.
- A position jump beyond 100 ms flushes the old PCM. An underrun with more than 100 ms of drift
  restarts at the current media position.
- Frame-aligned partial writes advance only by the frames the device accepted.

The metronome is not sample-locked to the music's audio output. Real hardware and driver
latency, and the position granularity of the backend, remain limits.

#### Moving a cue

A cue is moved by dragging its letter (hot cue) or its triangle (memory cue).

- `ZoomWave.cue_at` hit-tests them.
- `drag_cue` changes `Cue.start` live. A loop keeps its length and stays inside the track, and
  Shift snaps to the beat grid.
- `cue_moved` tells the player or the timeline.

The press records the cue position and the cues as they were (`origin`, `before`), and grabs the
keyboard. Esc, or a release farther than `OUT_X` / `OUT_Y` px outside the widget, puts the cue
back. While the mouse is out, the cue already shows its old place and the cursor turns to
forbidden. Nothing is recorded or emitted in that case.

#### Cue undo

`ui/cuehistory.py` keeps, per track (100 steps, 32 tracks), the cue lists as they were before
each edit. `mark` is called before an edit, `record` for a drag.

The player and the timeline share it, so Ctrl+Z / Ctrl+Y (`QShortcut` on both windows, text
fields keep their own undo) work whichever window made the change. Restoring rebuilds the `Cue`
objects, and the player drops a loop whose cue no longer exists.

### Recipe: Writing a ZIP backup

**You need:** a `project.dump` snapshot (section 5, "Reading a Traktor Bridge project"), a destination
path, the music folder of the project (to relocate missing files), and the standard `zipfile` module.

**Steps:**

1. Walk `tracks`. For each audio path, if the file is missing and a music folder is set, look it up there.
   If any file is still missing, stop: the backup is not created.
2. Give each distinct file (compared after resolving links, without case on Windows) the entry name
   `Audio/<n>_<stem>.<ext>`, where `<n>` counts from 1 on six digits and `<stem>` and `<ext>` go through `safe_name`
   (the characters `< > : " / \ | ? *` and control characters become `_`, leading and trailing spaces
   and dots are removed, 100 characters at most, `Untitled` when empty).
3. Write the project with `settings.music_root = "Audio"`, `source_path = ""`, `output_path = ""` and each
   track path replaced by its entry name.
4. Create a temporary ZIP in the folder of the destination (`.tb-backup-*.zip`). Write the audio entries
   first, stored (no compression, ZIP64 forced), hashing each file while it is read. After each file,
   check that its size, modification time and inode did not change; if they did, abort.
5. Write `project.json` (JSON, indent 1, no ASCII escaping, deflated).
6. Write one playlist per non-folder node, numbered from 1: `Playlists/<n>_<safe name>.m3u8` (deflated). The
   lines are `#EXTM3U`, then for each track `#EXTINF:<seconds>,<artist> - <title>` and `../Audio/<entry>`.
7. Write `manifest.json`: `{"sha256": {"Audio/...": "<hex>", ...}}` (deflated).
8. Read every entry back and compare the audio hashes. Flush the ZIP to disk. Hash the whole ZIP with SHA-256.
9. Rename the temporary file to the destination, then write `<backup>.zip.sha256` atomically with the line
   `<hex> *<zip file name>`.

**Pitfalls:**

- The ZIP must not replace one of the source audio files.
- A restore accepts only the entries `project.json`, `manifest.json` and files directly under `Audio/` and
  `Playlists/`. Any other name, a duplicate (case-insensitive), a directory entry, a link, a path with
  `..`, a Windows reserved name or a name ending with a space or a dot is refused.
- An archive without `project.json` or without `manifest.json` is refused with a `ValueError` before
  anything is written. So is a ZIP whose "version needed to extract" is above what Python reads.
- On Windows, the legacy `ctime` can differ after an atomic tag-file replacement. The change check is
  stricter there (section 9, Backup).
- The sidecar line uses two characters between hash and name: a space and `*`.
- The `Playlists` entries use `../Audio/...` so that an extracted folder plays as is.
- Limits at restore time: 100,000 entries, 1 TiB expanded, 100:1 ratio per entry, 256 MiB for each of
  the two JSON files, 1 GiB of free disk space kept. Entries must be stored or deflated and not encrypted.

**Check:** `backup.verify(zip)` reads the sidecar and compares the digest. `backup.restore(zip, new folder)`
rebuilds the folder, checking CRCs and the audio hashes of `manifest.json`, and loads `project.json` with
the project reader.

### Projects

#### Backup

`backup.create` takes a detached `project.dump` snapshot from the GUI and writes a ZIP in a
background Job.

The ZIP contains:

- every loaded node, not just the export selection;
- `project.json`;
- numbered safe M3U8 names;
- deduplicated audio paths, with SHA-256 hashes in `manifest.json`.

Audio is stored without recompression. JSON and playlists are deflated.

Missing files can be relocated through the configured music root. Any path that stays unresolved
aborts the backup.

The copy and the verification work in chunks and support cancellation. They check the source
fingerprints and the ZIP CRC and SHA-256 before the destination is replaced atomically.

On Windows, the legacy `stat` and `fstat` ctime values can differ after an atomic tag-file
replacement. The backup checks ctime between path snapshots there, and checks size, mtime and
inode against both the handle and the path. On POSIX the handle ctime is checked too.

#### Checksum sidecar

The complete ZIP is hashed before the replacement. An external `<backup>.zip.sha256` file is
saved atomically in the standard checksum format, and its digest is shown in the UI.

If that sidecar cannot be saved, the error states explicitly that the ZIP was created.

#### Verify and restore

`backup.verify` validates the digest and the filename of the adjacent checksum file.

`backup.restore` requires that file. It validates the ZIP entry paths and the manifest and
project references, checks the disk space, and streams into a temporary sibling folder with CRC
and audio SHA-256 verification. It then renames the folder to a new destination. A failure or a
cancellation removes the staging folder.

The main window offers verification and restoration. It can open the restored project when the
job finishes, and the unsaved-work prompt is preserved.

Only the paths in the archived snapshot are rewritten, never the live tracks or the dirty state.

Restore through **Tools > Backup > Load / restore backup...**, not by unzipping by hand. The
panel applies the path, structure, expansion and checksum checks before the result is published.

Project loading resolves relative audio and settings paths from the directory of the JSON file,
so a restored project can be moved.

#### Project file

`sources/project.py` saves and reads the work as JSON (`format` `traktor-bridge-project`,
`version` 1):

- `settings`: collection, music folder, output, format, copy, verify, key format, waveform
  colour, crossfade.
- `tracks`: every Track field and its cues, each track written once.
- `tree`: folders and playlists. A playlist lists track numbers, so a track shared by two
  playlists stays one object.

`sources.detect` recognises the file by its content, so File > Open collection and the command
line read it like any other source.

The reader checks every type, ignores what it does not know, refuses a newer `version` and
relocates missing files in the music folder. The file is written with `write_atomic`.

The main window keeps the project path and a dirty flag (title `*`, a prompt before replacing or
closing).

### Recipe: Formatting a key as FAT32

**You need:** a raw device or an image file that accepts sector writes (on Windows `\\.\PhysicalDriveN`,
on Linux `/dev/sdX`, on macOS `/dev/rdiskN`), its size in bytes, the sector size (512), a label and
administrator rights. `fat32.py` has the layout code. The program wipes everything on the drive.

**Steps:**

1. Compute the layout (below): partition start, sectors, cluster size, reserved sectors, FAT size,
   cluster count. The partition starts at 1 MiB (sector 2048 with 512 byte sectors).
2. Write zeros over the first and the last 8 MiB of the device (or half of the device if smaller),
   so that no old partition table or signature survives.
3. Write zeros over the reserved area of the partition.
4. Write the boot sector (partition sector 0), the FSInfo sector (1) and the tail sector (2), then
   their copies at 6, 7 and 8.
5. Write zeros over both FATs, then the first FAT entries in each FAT.
6. Write the root directory cluster (cluster 2) as zeros, with the volume label entry at its start when a label exists.
7. Write the MBR at sector 0 of the device, last.
8. Flush to disk, read back sector 0 and the boot sector and compare. Fail if they differ.

**Pitfalls:**

- Sector writes: offsets and lengths must be multiples of the sector size. Windows refuses anything else
  on a physical drive.
- The MBR is written last. A drive interrupted before is blank, not half formatted.
- Clusters. Below 65525 clusters a volume is FAT16 by definition, so small drives get a smaller cluster size,
  and a drive that is too small is refused (about 34 MB at least). Above 0x0FFFFFF5 clusters the cluster size is doubled.
- The FSInfo free-cluster count is `clusters - 1` (the root directory takes cluster 2) and the next free
  cluster hint is 3.
- The label is upper case, 11 characters at most, and the characters `* ? . , ; : / \ | + = < > [ ] "`, control
  characters and anything above 126 become `_`. An empty label is written `NO NAME` in the boot sector and no
  entry is created in the root directory.
- The player needs FAT32 (or exFAT). A key left as NTFS shows NO DISK.
- The system disk and the disk the program runs from are refused by `drives.py`.

**Check:** the volume mounts on the OS, `chkdsk` or `fsck.vfat` reports no error, a copy of an export works, and
the CDJ shows the key. The read-back in step 8 is automatic.

#### FAT32 layout

Geometry (`layout`):

| Value | Rule |
| --- | --- |
| Partition start | 1 MiB (`2048` sectors of 512 bytes) |
| Partition sectors | `min(device sectors - start, 0xFFFFFFFF - start)` |
| Cluster size | by device size: up to 8 GiB 4 KiB, up to 16 GiB 8 KiB, up to 32 GiB 16 KiB, above 32 KiB |
| Reserved sectors | `32 + (-(32 + 2 x fat)) mod sectors_per_cluster`, so the data area starts on a cluster boundary |
| Number of FATs | 2 |
| FAT size | smallest `fat` such that `ceil((clusters + 2) x 4 / sector size) <= fat`, where `clusters = (total - reserved - 2 x fat) div sectors_per_cluster` |
| Volume id | random 32 bit |

Boot sector (sector 0 of the partition, also copied to sector 6):

| Offset | Size | Value |
| --- | --- | --- |
| `0x00` | 3 | `EB 58 90` |
| `0x03` | 8 | `MSDOS5.0` |
| `0x0B` | u16 | bytes per sector |
| `0x0D` | u8 | sectors per cluster |
| `0x0E` | u16 | reserved sectors |
| `0x10` | u8 | 2, number of FATs |
| `0x11`, `0x13` | u16 | 0, 0 (root entries and 16 bit sector count) |
| `0x15` | u8 | `0xF8`, media |
| `0x16` | u16 | 0 |
| `0x18`, `0x1A` | u16 | 63, 255 (sectors per track, heads) |
| `0x1C` | u32 | hidden sectors (the partition start) |
| `0x20` | u32 | total sectors |
| `0x24` | u32 | sectors per FAT |
| `0x28`, `0x2A` | u16 | 0, 0 (flags, version) |
| `0x2C` | u32 | 2, root directory cluster |
| `0x30` | u16 | 1, FSInfo sector |
| `0x32` | u16 | 6, backup boot sector |
| `0x34` | 12 | zeros |
| `0x40` | u8 | `0x80`, drive number |
| `0x41` | u8 | 0 |
| `0x42` | u8 | `0x29`, extended boot signature |
| `0x43` | u32 | volume id |
| `0x47` | 11 | label, space padded (`NO NAME` if empty) |
| `0x52` | 8 | `FAT32   ` |
| `0x5A` | 64 | boot code that prints "This is not a bootable disk." and halts |
| `0x1FE` | 2 | `55 AA` |

FSInfo sector (partition sector 1, copied to 7): `0x00` u32 `0x41615252`, `0x1E4` u32 `0x61417272`,
`0x1E8` u32 `clusters - 1`, `0x1EC` u32 3, `0x1FC` `00 00 55 AA`. The tail sector (2, copied to 8) is zeros
with `00 00 55 AA` at `0x1FC`.

FAT (both copies, from sector `reserved` and `reserved + fat`): the first three u32 entries are `0x0FFFFFF8`,
`0x0FFFFFFF`, `0x0FFFFFFF` (media, end of chain, end of chain for the root directory at cluster 2). The rest is zero. The data
area starts at sector `reserved + 2 x fat`, and cluster 2 is its first cluster.

Root directory label entry (32 bytes): the label (11 bytes), attribute `0x08`, two zero bytes, the DOS time, the
DOS date, the DOS date, a zero u16, the time, the date, a zero u16 and a zero u32 size. The DOS date is
`((year - 1980) << 9) | (month << 5) | day` and the time `(hour << 11) | (minute << 5) | (second div 2)`.

MBR (device sector 0): `0x1B8` u32 random disk signature. One partition entry at `0x1BE`: status 0 (not active),
CHS of the first sector, type `0x0C` (FAT32 with LBA), CHS of the last sector, u32 start LBA, u32 sector count.
The CHS is computed with 255 heads and 63 sectors (`FE FF FF` beyond cylinder 1023). `55 AA` at `0x1FE`.

### Formatting a key

#### FAT32 writer

`fat32.py` writes the MBR and the FAT32 structures itself, so the 32 GB limit of the Windows
formatter does not apply.

- The partition starts at 1 MiB. There are 32 reserved sectors, two FATs, a backup boot sector,
  an FSInfo sector, and the label in the root directory.
- The cluster size follows the drive: 4 KiB up to 8 GB, then 8, 16 and 32 KiB. It is lowered for
  small drives to stay above 65524 clusters.
- The MBR is written last, so a drive interrupted half way is not taken for a formatted one.

#### Choosing the drive

`drives.py` lists the removable drives (PowerShell, `lsblk`, `diskutil`). It refuses the system
disk and the disk the program runs from.

#### Writing the disk

- Windows cleans the disk with diskpart, then writes `\\.\PhysicalDriveN`.
- Linux unmounts, writes `/dev/sdX` and re-reads the partition table.
- macOS unmounts with `diskutil`, writes the raw `/dev/rdiskN` node with the same FAT32 writer,
  then asks `diskutil` to mount the new volume.

Raw access needs elevation, so the program starts itself again with `--format-disk`. It uses UAC
on Windows, pkexec on Linux and an administrator authorization prompt through osascript on macOS.

That helper checks the drive id, size and serial again, and reports through a `tb_format_*` file
in the temp folder.

## 10. Portable build and command line

### Build

`Build.bat` creates a clean venv and runs `build.py`. `python build.py` uses the current Python.

The result is `dist/TraktorBridge/` (windowed exe, `runtime/` folder) and
`dist/Portable_TraktorBridge-3.5.1-win64.zip`.

- No `.py` file ships. The modules are compiled into the PYZ.
- Unused Qt parts are removed and librosa is left out.
- `build.py` renames `dist/` and `build/` before clearing them, and stops if a running copy of
  the app holds them.
- Packaging removes Python, stub and C/C++ source files from the runtime and fails if any remain
  in the portable folder. The installer uses this same checked folder.

Removing source files does not prevent anyone from analysing the native binaries or the embedded
bytecode.

### Native compilation

Every module of the package, the interface included, is compiled to a native module first.
`compile_core.py` copies the package to `build/stage`, turns each module into a `.pyd` with
Nuitka (`pip install nuitka`, it fetches MinGW64 on the first run), and PyInstaller then packs
that staged copy.

The sources in the repository are never touched. PyInstaller packs the staged copy in
`build/stage`, and `build/stage` can be inspected or run on its own.

Two rules came out of it:

- Modules are compiled one at a time. Parallel Nuitka runs shared caches and produced modules
  that crash on import.
- No module may carry the name of a standard module (`pdb.py` became `pdbwrite.py`).

The `__init__.py` files stay Python, and so does `__main__.py`, the launcher of `python -m`.
PyInstaller cannot see imports inside a `.pyd`, so `traktor_bridge.spec` lists them by hand.

#### PyArmor

Two of the files that stay Python carry real code: `sources/__init__.py` (`detect()` and
`load()`) and `export/__init__.py` (`run()`). `compile_core.py` passes them through PyArmor
(`pip install pyarmor`, the free version, which allows distribution in a noncommercial open
source project). The `PROTECT` list in `compile_core.py` names them.

The PyArmor runtime is stored inside the package, in `traktor_bridge/pyarmor_runtime_000000/`.
That is on purpose. The seal below hashes every native module under `traktor_bridge/`, so the
runtime is sealed like the rest. The protected files are only imported after the startup check
has passed, so no unverified native file runs before it.

`traktor_bridge/__init__.py`, `integrity.py` and `_seal.py` stay plain Python. They run before
the check, and the seal needs to stay readable and simple. `compile_core.py` stops if a
protected file is still readable after PyArmor has run.

### C++ core

The CDJ exporters also exist in C++: `core/tbcore.cpp` with `rows.inc`, `anlz.inc` and
`anlz_build.inc`. `compile_core.py` builds them into `tbcore.dll` next to `export/cdj/native.py`.

The interface is plain C, loaded with ctypes: flat arrays in, bytes out, and no exception
crosses it.

- `tb_pdb_write`: the whole `export.pdb` from the tracks and the playlist tree. It covers rows,
  id lookups in order of first use, and the page layout (`pdbwrite.build_py_file`,
  `devicesql.build_py`).
- `tb_anlz_build`: the ANLZ0000.DAT and .EXT of a track, with beat grid, cues and the five
  waveforms (`anlz.build_py`).
- `tb_fold`, `tb_bands`: the mono folding and the waveform bands (`analysis`).

The Python versions stay as the reference and the fallback. They run without the DLL, with
`TB_PURE_PYTHON=1`, or when the C++ side refuses a value (a field that does not fit).

Both versions produce the same key. Exporting the same tracks with the built exe and with
`TB_PURE_PYTHON=1` gives byte-identical files. Only the `mtime` values in
`traktor_bridge_checksums.json` differ, because the two exports were written at different times.

The compiler is `g++` or `clang++` if present, then `TB_CXX`, then the zig that Nuitka
downloaded. The DLL is built with `-ffp-contract=off`, because a fused multiply-add would change
the last bit of the filters.

`python compile_core.py --native` builds only the DLL, next to the sources.

### DLL hardening

None of the hardening changes a result: an export with the hardened DLL is byte-identical to the pure Python one.

- Symbols and `.pdb` are stripped and unused code is dropped (`-s`, `--gc-sections`).
- The exports are renamed `q0` to `q5`. `hide.h` maps the readable names of the source, and
  `native.NAMES` those of the loader.
- The distinctive format constants are put back through a volatile read (`K32`).
- Section names, color names and path strings are stored xored and decoded when used (`HS`).
- Compiler commands add `-fstack-protector-strong` and `_FORTIFY_SOURCE=2`. On Windows they also
  set ASLR, DEP and high-entropy VA, on Linux RELRO, NOW and noexecstack.
- In the 3.5 release build, the PE header of `tbcore.dll` carries the ASLR, DEP and high-entropy VA
  flags. Its imports reference Windows and UCRT dependencies.

This only makes a static read slower. The layouts are documented in this file anyway.

Crinkler, UPX and the like were left out. They make executables, not loadable libraries, or
raise antivirus false positives.

### Loading the DLL

On Windows, `tbcore` is loaded from an absolute path with
`LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32`. Its dependencies must be next
to it or in System32.

The C ABI wrappers validate their input before calling the native code: one-dimensional finite
sample arrays, matching band lengths, normalized filters and integer ranges. The native output
size is limited to 1 GiB.

### Startup check

`compile_core.py` writes the SHA-256 of every native module of the staged package (the `.pyd`
files and `tbcore.dll`) into `traktor_bridge/_seal.py`. That file is packed in the executable,
and `build.py` fails if the built folder differs from it.

At startup, `integrity.check()` runs before any core module is imported. It compares the files
of `runtime/traktor_bridge/` with the seal. A file that is changed, missing or added beside them
stops the program with exit code 3. The message is a dialog in the window, or stderr with
`--export` and `--verify`. The findings go to `traktor_bridge.log`.

The launchers run this check before they import the compiled `app`. `integrity.py` is kept as
embedded Python in the executable archive.

The PyArmor runtime is one of the sealed files. If a byte of it changes, or a native file is
added or removed, the program stops with exit code 3. The installer packs the checked portable
folder as it is and adds nothing under `runtime/traktor_bridge/`, so an installed copy is
checked the same way as an unzipped one.

The installer also deletes the old `runtime` folder before it copies the new one
(`[InstallDelete]` in `installer/TraktorBridge.iss`). This is not optional. The check rejects any
native file it does not know, so a module left behind by an older version, for example a
`.pyd` that the new build no longer has, made the program refuse to start after an upgrade.
Settings and log sit next to the exe, outside `runtime`, and are kept.

The message lists up to six files, as `changed:`, `missing:` or `unexpected:` lines, so a bug
report says which ones. When every line is `unexpected:`, the message says what that almost
always means: an older copy left those files, because a new portable version was unzipped over
it. It tells the user to delete them from `runtime\traktor_bridge` and start again.

A run from the sources has no seal and is not checked. A frozen build with a missing, empty or
invalid seal does not start.

What the seal is, and what it is not:

- It stops a swapped or patched file in the unzipped folder.
- It covers the native modules under the package, not every Qt or FFmpeg dependency in the
  runtime.
- It is not Authenticode signing. Someone who rebuilds the executable with a new seal gets past
  it.

### Command line and runtime files

`multiprocessing.freeze_support()` and the `__main__` guard are required: the analysis processes
start the exe again.

Settings and log live next to the exe, the cache in `%LOCALAPPDATA%/TraktorBridge`.

```
TraktorBridge.exe --export COLLECTION OUTPUT [--format FORMAT] [--music FOLDER]
TraktorBridge.exe --verify OUTPUT
```

FORMAT is `CDJ/USB` (default), `Rekordbox XML`, `M3U` or `Traktor NML`. The report goes to
`traktor_bridge.log`, and the exit code is 0 when nothing failed.

`--verify` exits with 1 for errors, missing files or any difference, including Pioneer files
that the player may have modified. Exit code 0 requires an exact match.

The exe has no console, so use `start /wait` from a prompt.

---

### Layered validation and operational safeguards

This section lists the checks that protect imports, backups and USB preparation. I have not
measured their reliability against other DJ applications.

#### Local processing and privacy

The 3.5.1 application has no telemetry, usage analytics, library uploads or automatic log
submission. Audio decoding, BPM and waveform analysis, cue editing, backup and export all run
locally. No developer account or cloud service is required.

`urllib.parse` is used for local file-URI encoding and decoding, not for network requests. The
About links can open external sites in the user's browser.

Logs may contain paths and track names, so users should review them before sharing a support
report by hand.

Network or cloud-synced storage chosen by the user, and external antivirus tools, are outside
what the application transmits or controls.

#### Input

Collection size limits are applied before parsing.

NML, rekordbox XML and VirtualDJ files are read with `defusedxml.ElementTree`, which rejects
entities and external references. Standard escapes and a plain DOCTYPE are still accepted.

Project JSON is data. It is never deserialized into executable objects.

#### Audio checker

The checker runs in quick mode (headers) or full mode (full libsndfile decoding), in a spawned
process per file. The defaults are 120 s and 1024 MiB of monitored memory.

Full mode also caps channels at 32, sample rate at 768 kHz and duration at 24 h. A timeout, a
crash or a monitoring failure gives the result Not checked.

The separate process isolates a crash. It is not a sandbox, and it does not cover every
audio-read path of the application.

#### ClamAV

`find_clamav` only detects `clamscan`. The application does not run the antivirus, update its
signatures or quarantine anything. Users scan separately, with a current signature database.

A clean report cannot prove that a file is harmless. Signatures may recognize malicious content
in audio, but they do not guarantee detection of steganographic, encrypted or unknown payloads.

No MP3 steganography detector is implemented. Decodability and SHA-256 integrity are separate
properties.

#### Backup limits

Before `ZipFile` allocates anything, an EOCD/ZIP64 preflight bounds the central directory to
128 MiB and counts the actual entries.

- At most 100,000 entries, 1 TiB of expanded data, and a 100:1 ratio per entry.
- Only unencrypted stored or deflated entries are accepted.
- Metadata files have a 256 MiB cap each.

Before the staged folder is published, restore also rejects bad paths, symlinks, duplicates and
device names. It checks exact streamed sizes, the CRC and the audio SHA-256, and it keeps a 1 GiB
disk reserve. Cancellation or a failure removes the staging folder.

The SHA-256 sidecar checks integrity, not authenticity. Anyone who can change the ZIP can also
write a matching sidecar.

#### Pioneer generation

`export/cdj/validate.py` checks the PDB the exporter wrote: page alignment, table and page
identities, bounded acyclic chains and row offsets. For DAT and EXT it checks the headers and
sections, the required roles, the path, and the beat, cue and waveform counts.

`write_verified` validates the bytes, writes a temporary file, compares `sha256_drive` with the
intended digest, then replaces the destination. This read-back is mandatory, whatever the audio
copy verification option says.

An invalid ANLZ cache is recomputed.

Publication is per file. A whole-key export is not atomic.

#### Copy and later verification

The export manifest records SHA-256 for every file. **Verify the copy** is enabled by default,
and **Tools > Verify an export** rechecks a stored output later.

Windows tries uncached drive reads. Other platforms, or a drive without direct I/O, use normal
reads.

#### Lifecycle

Closing the main window is refused while Jobs are active or pending, while waveform threads or
queues are running, or while collection scans are running. This check comes before the
discard and exit prompts. Closing does not cancel the operation.

Writing jobs guard their own panels. Dialogs, transient menus and finished scan threads are
disposed. Explicit cancellation stays available where it is supported.

### Analysis and loading performance

These changes made loading and analysis faster without changing results.

- Folder loading lists each directory once, then reads the tags from the collected file lists.
  Natural order and hierarchy are kept.
- M3U and VirtualDJ relocation indexes the music root only on the first missing path, and caches
  the resolution within one load.
- Waveform requests deduplicate active decodes. The detailed cache conversion and the Python band
  reduction avoid unnecessary float and absolute-value copies.
- BPM refinement reuses scratch arrays across the same 162 candidates (121 coarse, then 41 fine).
- Metronome generation calculates only the active click samples and caches the negotiated format
  values. The 30 ms queue and 5 ms timer are unchanged.
- Replaying an already loaded track keeps its media source.

These are optimizations of the same code, not a changed musical model. The waveform arrays and
the tempo, first-beat and confidence output are meant to stay the same.

None of this says anything about hardware latency, or about accuracy on representative real music.

### Release checks and remaining evidence

The 3.5 release build was checked in these ways:

- `build.py` compares the built folder with the seal, and stops if a source file is left in the
  release.
- The packaged program starts, exports a CDJ/USB key from a small playlist and verifies it. An
  altered native module, an added one and a removed one each stop the program with exit code 3.
- The installer copies the same files as the portable folder, byte for byte, adds nothing
  under `runtime/traktor_bridge/`, and the installed copy passes the same startup check.
- An export with the built exe is byte-identical to a pure Python export.

What these checks do not show:

- They do not certify every native dependency, arbitrary malicious media, real-world tempo
  accuracy, storage hardware or every Pioneer model.
- Earlier checks on a CDJ-2000NXS2 do not cover each later change to the validation code.
- The metronome is not sample-locked to the audio output, and the checks above say nothing about
  acoustic device latency.

## 11. References

- Deep Symmetry, crate-digger and beat-link: rekordbox PDB and ANLZ formats, Pro DJ Link.
- openboxxx: a minimal CDJ export from Mixxx.
- Mixxx wiki: VirtualDJ database, Serato database and crates.
- Holzhaus/serato-tags: Serato Markers2 and BeatGrid.
- Pioneer DJ: rekordbox XML import and export.
