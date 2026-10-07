"""Explicit metadata writes: keep unrelated tags and audio, back up, then replace atomically."""

from __future__ import annotations

import math
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mutagen import MutagenError
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import COMM, ID3, Frames
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4FreeForm
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from . import keys
from .export.manifest import Cancelled

TEXT_FIELDS = ("title", "artist", "album", "album_artist", "genre", "label",
               "remixer", "composer", "comment")
NUMBER_FIELDS = ("year", "track_no", "disc_no")
FILE_FIELDS = (*TEXT_FIELDS, *NUMBER_FIELDS, "bpm", "key")
EXTENSIONS = (".mp3", ".wav", ".aif", ".aiff", ".flac", ".m4a", ".mp4", ".alac", ".ogg")

ID3_NAMES = {"title": "TIT2", "artist": "TPE1", "album": "TALB", "album_artist": "TPE2",
             "genre": "TCON", "label": "TPUB", "remixer": "TPE4", "composer": "TCOM",
             "year": "TDRC", "track_no": "TRCK", "disc_no": "TPOS", "bpm": "TBPM", "key": "TKEY"}
VORBIS_NAMES = {"title": "title", "artist": "artist", "album": "album", "album_artist": "albumartist",
                "genre": "genre", "label": "organization", "remixer": "remixer", "composer": "composer",
                "comment": "comment", "year": "date", "track_no": "tracknumber", "disc_no": "discnumber",
                "bpm": "bpm", "key": "initialkey"}
MP4_NAMES = {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb", "album_artist": "aART",
             "genre": "\xa9gen", "composer": "\xa9wrt", "comment": "\xa9cmt", "year": "\xa9day"}
MP4_CUSTOM = {field: f"----:com.apple.iTunes:{name}" for field, name in
              (("label", "LABEL"), ("remixer", "REMIXER"), ("bpm", "BPM"), ("key", "INITIALKEY"))}


@dataclass(frozen=True)
class WriteResult:
    path: str
    backup: str
    size: int


def validate(values: dict[str, str]):
    for field, value in values.items():
        if field not in FILE_FIELDS:
            raise ValueError(f"Unsupported audio tag: {field}")
        if not isinstance(value, str) or "\0" in value:
            raise ValueError(f"Invalid text in {field}")
        if field in NUMBER_FIELDS and value and (not value.isdecimal() or not 0 < int(value) <= 65535):
            raise ValueError(f"{field} must be a whole number from 1 to 65535, or empty")
        if field == "bpm" and value:
            try:
                bpm = float(value)
            except ValueError as e:
                raise ValueError("BPM must be a positive number, or empty") from e
            if not math.isfinite(bpm) or not 0 < bpm <= 1000:
                raise ValueError("BPM must be from 0 to 1000, or empty")
        if field == "key" and value and keys.parse(value) is None:
            raise ValueError("Invalid musical key")


def open_audio(path: str):
    ext = Path(path).suffix.lower()
    expected = {".mp3": MP3, ".wav": WAVE, ".aif": AIFF, ".aiff": AIFF, ".flac": FLAC,
                ".m4a": MP4, ".mp4": MP4, ".alac": MP4, ".ogg": OggVorbis}.get(ext)
    if expected is None:
        raise ValueError("Unsupported or damaged audio container; tags were not written")
    audio = expected(path)
    if audio.tags is None:
        audio.add_tags()
    if isinstance(audio.tags, ID3) and audio.tags.version[:2] == (2, 2):
        raise ValueError("ID3v2.2 files must be converted to ID3v2.3/2.4 before editing")
    return audio


def set_tags(audio, values: dict[str, str]):
    tag = audio if isinstance(audio, ID3) else audio.tags
    if isinstance(tag, ID3):
        for field, value in values.items():
            if field == "comment":
                # Only the regular comment; keep named/language-specific DJ frames.
                tag.delall("COMM::eng")
                if value:
                    tag.add(COMM(encoding=3, lang="eng", desc="", text=[value]))
            else:
                name = ID3_NAMES[field]
                tag.delall(name)
                if value:
                    tag.add(Frames[name](encoding=3, text=[value]))
    elif isinstance(audio, MP4):
        for field, value in values.items():
            if field in MP4_CUSTOM:
                aliases = ("initialkey", "key") if field == "key" else (field,)
                for old in list(tag):
                    if old.startswith("----:com.apple.iTunes:") and old.rsplit(":", 1)[-1].lower() in aliases:
                        del tag[old]
            if field == "genre":
                tag.pop("gnre", None)
            name = MP4_NAMES.get(field) or MP4_CUSTOM.get(field) or {
                "track_no": "trkn", "disc_no": "disk"}[field]
            total = tag.get(name, [(0, 0)])[0][1] if field in ("track_no", "disc_no") else 0
            tag.pop(name, None)
            if field == "bpm":
                tag.pop("tmpo", None)
                if value:
                    tag["tmpo"] = [round(float(value))]
            if not value:
                continue
            if field in MP4_CUSTOM:
                tag[name] = [MP4FreeForm(value.encode("utf-8"))]
            elif field in ("track_no", "disc_no"):
                tag[name] = [(int(value), total)]
            else:
                tag[name] = [value]
    else:
        for field, value in values.items():
            name = VORBIS_NAMES[field]
            alias = {"key": "key", "year": "year"}.get(field)
            if alias and alias in tag:
                del tag[alias]
            if name in tag:
                del tag[name]
            if value:
                tag[name] = [value]


def get_tags(audio, fields) -> dict[str, str]:
    tag = audio if isinstance(audio, ID3) else audio.tags
    out = {}
    for field in fields:
        if isinstance(tag, ID3):
            name = "COMM::eng" if field == "comment" else ID3_NAMES[field]
            frame = tag.get(name)
            value = str(frame.text[0]) if frame is not None and frame.text else ""
        elif isinstance(audio, MP4):
            name = MP4_NAMES.get(field) or MP4_CUSTOM.get(field) or {
                "track_no": "trkn", "disc_no": "disk"}[field]
            values = tag.get(name, [])
            value = values[0] if values else ""
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            elif isinstance(value, tuple):
                value = str(value[0])
        else:
            values = tag.get(VORBIS_NAMES[field], [])
            value = values[0] if values else ""
        out[field] = value
    return out


def fingerprint(path: Path):
    st = path.stat()
    return st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino


def write(path: str, values: dict[str, str], progress=None, cancel=None) -> WriteResult:
    """Validate on a copy, retain the first .tb-tags.bak, never mutate the source in place."""
    validate(values)
    source = Path(path)
    if source.suffix.lower() not in EXTENSIONS:
        raise ValueError("Writing tags is not supported for this audio format")
    if source.is_symlink() or not source.is_file():
        raise ValueError("Choose an existing regular audio file, not a symbolic link")
    source = source.absolute()
    if not source.stat().st_mode & stat.S_IWRITE:
        raise PermissionError("The source audio is read-only; tags were not written")
    initial = fingerprint(source)
    backup = source.with_name(source.name + ".tb-tags.bak")
    cb = progress or (lambda _pct, _msg: None)

    def check():
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if fingerprint(source) != initial:
            raise OSError("The source audio changed during tag writing; reload it and try again")

    fd, name = tempfile.mkstemp(prefix=".tb-tags-", suffix=source.suffix, dir=source.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as dst, source.open("rb") as src:
            copied = 0
            while block := src.read(4 << 20):
                check()
                dst.write(block)
                copied += len(block)
                cb(min(60, copied * 60 // max(1, initial[0])), "Preparing audio copy")
            dst.flush()
            os.fsync(dst.fileno())
        check()
        audio = open_audio(str(temp))
        set_tags(audio, values)
        if isinstance(audio.tags, ID3):
            audio.save(v2_version=3 if audio.tags.version[1] == 3 else 4)
        else:
            audio.save()
        readback = get_tags(open_audio(str(temp)), values)
        if readback != values:
            raise ValueError("Audio tags could not be verified; the original file was left unchanged")
        cb(75, "Tags verified; creating backup")
        check()
        created = False
        try:
            with backup.open("xb") as dst, source.open("rb") as src:
                created = True
                while block := src.read(4 << 20):
                    check()
                    dst.write(block)
                dst.flush()
                os.fsync(dst.fileno())
        except FileExistsError:
            if backup.is_symlink() or not backup.is_file():
                raise OSError("The backup path is not a regular file")
        except BaseException:
            if created:
                backup.unlink()
            raise
        check()
        with temp.open("r+b") as stream:
            os.fsync(stream.fileno())
        shutil.copymode(source, temp)
        check()
        os.replace(temp, source)
        cb(100, "Audio tags written")
        return WriteResult(str(source), str(backup), source.stat().st_size)
    except MutagenError as e:
        raise ValueError(f"Cannot write tags to this audio file: {e}") from e
    finally:
        if temp.exists():
            temp.chmod(stat.S_IREAD | stat.S_IWRITE)
            temp.unlink()
