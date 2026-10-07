# Benoit Saint-Moulin
# Traktor Bridge : source detection and loading

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone

from ..model import Node

Progress = Callable[[int, str], None]

# a collection of 100 000 tracks is a few hundred MB of XML, past 1 GB it is not a collection
MAX_FILE = 1 << 30


def check_size(path: str, limit: int = 0):
    """Refuses a file too big to be what its name says, before it is read into memory."""
    size = os.path.getsize(path)
    if size > (limit or MAX_FILE):
        raise ValueError(f"{os.path.basename(path)} is too large to be a collection ({size / 1e9:.1f} GB)")

AUDIO_EXT = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".mp4", ".aac", ".ogg", ".alac"}

KINDS = ("traktor", "rekordbox", "mixxx", "m3u", "virtualdj", "serato", "folder", "project")


def num(s, default: float = 0.0) -> float:
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def unix_date(s) -> str:
    try:
        return datetime.fromtimestamp(int(s), timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def index_folder(root: str) -> dict[str, list[str]]:
    """Every audio file under root, by lowercase filename."""
    out: dict[str, list[str]] = {}
    for d, _, files in os.walk(root):
        for f in files:
            if os.path.splitext(f)[1].lower() in AUDIO_EXT:
                out.setdefault(f.lower(), []).append(os.path.join(d, f))
    return out


def detect(path: str) -> str:
    if os.path.isdir(path):
        return "folder"
    ext = os.path.splitext(path)[1].lower()
    if os.path.basename(path).lower() == "database v2" or ext == ".crate":
        return "serato"
    if ext == ".vdjfolder":
        return "virtualdj"
    if ext == ".nml":
        return "traktor"
    if ext in (".m3u", ".m3u8"):
        return "m3u"
    if ext in (".sqlite", ".db"):
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                ok = con.execute("SELECT 1 FROM sqlite_master WHERE name='track_locations'").fetchone()
            finally:
                con.close()
            return "mixxx" if ok else ""
        except sqlite3.Error:
            return ""
    if ext == ".json":
        from . import project
        return "project" if project.sniff(path) else ""
    if ext == ".xml":
        with open(path, "rb") as f:
            head = f.read(4096)
        if b"<DJ_PLAYLISTS" in head:
            return "rekordbox"
        if b"<VirtualDJ_Database" in head:
            return "virtualdj"
        if b"<NML" in head:
            return "traktor"
    return ""


def load(path: str, music_root: str = "", progress: Progress | None = None) -> list[Node]:
    kind = detect(path)
    if kind == "traktor":
        from . import nml
        return nml.load(path, music_root, progress)
    if kind == "rekordbox":
        from . import rbxml
        return rbxml.load(path, music_root, progress)
    if kind == "mixxx":
        from . import mixxx
        return mixxx.load(path, music_root, progress)
    if kind == "m3u":
        from . import m3u
        return m3u.load(path, music_root, progress)
    if kind == "virtualdj":
        from . import vdj
        return vdj.load(path, music_root, progress)
    if kind == "serato":
        from . import serato
        return serato.load(path, music_root, progress)
    if kind == "project":
        from . import project
        return project.load(path, music_root, progress)
    if kind == "folder":
        from . import folder
        return folder.load(path, music_root, progress)
    raise ValueError(f"Unknown collection format: {os.path.basename(path)}")


def relocate(path: str, found: dict[str, list[str]]) -> str:
    if not found or os.path.exists(path):
        return path
    alt = found.get(os.path.basename(path).lower())
    return os.path.normpath(alt[0]) if alt else path


def relocator(music_root: str):
    """One lazy folder index and one existence lookup per distinct playlist path."""
    found = None
    resolved: dict[str, str] = {}

    def resolve(path: str) -> str:
        nonlocal found
        if not music_root or not path:
            return path
        if path not in resolved:
            if os.path.exists(path):
                resolved[path] = path
            else:
                if found is None:
                    found = index_folder(music_root)
                hits = found.get(os.path.basename(path).lower())
                resolved[path] = os.path.normpath(hits[0]) if hits else path
        return resolved[path]

    return resolve
