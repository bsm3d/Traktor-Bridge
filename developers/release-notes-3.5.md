# Traktor Bridge 3.5

## Playlist and cue editors

The playlist editor now has multi-selection, drag reordering, duplicate removal and Undo/Redo.
"Also in" shows which other loaded playlists contain a track. You can save a playlist, or
a selection, as M3U8 or NML.

Place hot cues with **A-H**, move them on the waveform, and edit memory cues and loops in the
timeline. **S** toggles snap. **Ctrl+Z / Ctrl+Y** undoes and redoes edits.
Waveforms zoom down to 500 ms and load detailed data when you need it.

**Detect grids** estimates a constant BPM and the first audible pulse, for one track or for
a selection in a playlist. In a batch, low-confidence results are skipped.
Always check the result with the waveform and the metronome. Detection does not find
every downbeat and does not handle variable tempo.

The preview metronome has its own volume and latency offset. It follows playback, seeks and
loops, and it is muted during crossfades. How well it lines up still depends on your audio device.

## Projects and metadata

**File > Save the project (Ctrl+S)** saves playlists, track order, metadata, cues, grids and
export settings as one JSON file. **File > Open project / collection (Ctrl+O)** opens
projects and supported DJ collections.

**ID Tag** edits metadata inside the project. **Write tags to audio...** is a separate action
that asks for confirmation. It works on a checked temporary copy and keeps a `.tb-tags.bak`
backup. Undo does not reverse an audio-file write.

## USB export

The FAT32 formatter writes an MBR partition on a removable USB, SD or MMC drive that you
select. It erases the drive and asks for confirmation first. After an export to removable
storage, the app offers to eject the drive safely.

Audio copy overlaps reading and writing. Audio already on the key is skipped. The analysis is
cached and runs on several cores. A cue change still updates the analysis files.

The generated `export.pdb` and ANLZ DAT/EXT files are checked, then read back with SHA-256
before they are published. This check stays on even when **Verify the copy** is off.
It protects each file, not the whole export as one transaction.

**Verify the copy** is on by default. Later, **Tools > Verify an export** compares the key
with its saved checksums. Windows tries uncached reads and falls back to ordinary reads.

A CDJ may update its database and analysis files. Verification lists the readable Pioneer
files that changed as modified, integrity unconfirmed. Changed audio or artwork, and missing
or unreadable files, are still problems.

The dialog shows counts by category and the file paths stay in the log. The command line
returns 1 for any difference. Checksums are never rebased automatically.

## Backup

**Tools > Backup** saves, verifies and restores ZIP backups.
A backup holds all loaded playlists, the edits you applied and the audio, with shared audio
stored once. Keep the ZIP and its `.zip.sha256` file together.

Restoration checks the archive and the audio hashes, writes into a new folder and offers to
open the project. If you cancel, the unfinished extraction is removed.

It rejects unsafe paths, encrypted entries and unsupported compression. The limits are
100,000 entries, 1 TiB of expanded data, a 128 MiB central directory, a 100:1 compression
ratio and a 1 GiB free-space reserve.

## Audio checks and privacy

**Tools > Verify audio files...** checks headers or decodes the full stream. It never modifies
audio. Each file runs in its own process with a time limit and a memory limit. Unsupported
decoding, crashes and exceeded limits are reported as **Not checked**, never as success.

ClamAV detection only tells you whether it is installed. Antivirus scans and signature updates
stay outside the program. Traktor Bridge has no MP3 steganography detector.

Everything is processed locally. No upload of audio, playlists, metadata or analysis, no
telemetry, no account, no automatic log sharing. The core workflows work offline.

## Fixes

- Colliding analysis paths no longer overwrite another track's DAT/EXT.
- Hot-cue colour changes invalidate the analysis cache.
- Duplicate removal keeps the first occurrence, including shared Track references.
- Playlist edits still mark the project unsaved after the main tree is rebuilt.
- Reload closes the old playlist editors, or waits for their running operations.
- Backup verification and restored-project loading start even if the worker finishes while
  the confirmation dialog is open.
- Overview and detailed waveforms use separate temporary cache files for each write.
- On Windows, a backup accepts unchanged audio after a tag write, despite legacy creation-time differences.
- Track durations no longer truncate after 99 minutes.
- Closed dialogs and transient menus are released. Waveform requests are not queued twice.

## Runtime and builds

Quit is blocked during writing, analysis and scans. Use the operation's **Cancel** button or
wait. Closing the main window does not cancel a running job.

XML readers reject declared entities and external references. The native wrappers check input
sizes, finite values and output bounds. On Windows, the native core looks for its
dependencies only in its own folder and in System32.

The packaged app checks the hashes of its native modules before it imports the core. A missing
or invalid seal refuses startup. This is not publisher signing and not a sandbox.

The two `__init__` files that carry code (readers and export entry points) go through PyArmor.
Its runtime sits inside the package, so the same seal checks it.

The portable build and the installer contain no Python, stub, C or C++ source files.
The installer packages the checked portable folder. A clean build installs the runtime
dependencies from `requirements.txt`.

BPM refinement, waveform processing, metronome generation and folder scanning reuse buffers or
skip repeated work. The results are the same as before.

## Validation

The release build was started and used to export a CDJ/USB key, which then verified. The
installer installs the same files as the portable folder, and the installed copy passes the
startup check. An altered, added or removed native module stops the program.

These checks do not prove compatibility with every CDJ, nor protection against every malicious
file. Test the exported key on your player before a gig.

Format details and implementation notes are in [DOCUMENTATION.md](DOCUMENTATION.md).
