# Benoit Saint-Moulin
# Traktor Bridge : a folder of music read as it is, no collection needed

"""Audio folders become playlists; parent folders keep their hierarchy.
Tags supply metadata. There is no beat grid until one is detected or set in the
cue editor, and a CDJ export leaves the beat entries out until then."""

from __future__ import annotations

import logging
import os
import re

from .. import keys, tags
from ..model import Node, Track
from . import AUDIO_EXT, Progress, num

BPM_RANGE = (40.0, 300.0)
log = logging.getLogger(__name__)


def natural(name: str):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def make_track(path: str) -> Track:
    t = Track(path=path)
    try:
        t.size = os.path.getsize(path)
    except OSError:
        pass
    raw = tags.basic(path)
    t.title = raw.get("title") or os.path.splitext(os.path.basename(path))[0]
    t.artist = raw.get("artist", "")
    t.album = raw.get("album", "")
    t.album_artist = raw.get("album_artist", "")
    t.label = raw.get("label", "")
    t.remixer = raw.get("remixer", "")
    t.composer = raw.get("composer", "")
    t.genre = re.sub(r"^\(\d+\)", "", raw.get("genre", "")).strip()
    t.comment = raw.get("comment", "")
    t.year = int(num(raw.get("year", "")[:4]))
    t.track_no = int(num(raw.get("track_no", "").split("/")[0]))
    t.disc_no = int(num(raw.get("disc_no", "").split("/")[0]))
    bpm = num(raw.get("bpm", ""))
    if BPM_RANGE[0] <= bpm <= BPM_RANGE[1]:
        t.bpm = bpm
    t.key = keys.parse(raw.get("key", ""))
    tags.fill(t)
    return t


def tracks_from(paths: list[str]) -> list[Track]:
    """Tracks of dropped or picked paths: audio files as they are, folders walked in natural order."""
    out = []
    for p in paths:
        if os.path.isdir(p):
            for d, dirs, files in os.walk(p):
                dirs.sort(key=natural)
                audio = (n for n in files if os.path.splitext(n)[1].lower() in AUDIO_EXT)
                out.extend(make_track(os.path.join(d, n)) for n in sorted(audio, key=natural))
        elif os.path.splitext(p)[1].lower() in AUDIO_EXT and os.path.isfile(p):
            out.append(make_track(p))
    return out


def count_audio(root: str) -> int:
    return sum(1 for _, _, files in os.walk(root) for f in files if os.path.splitext(f)[1].lower() in AUDIO_EXT)


def load(path: str, music_root: str = "", progress: Progress | None = None) -> list[Node]:
    path = os.path.abspath(path)
    pending: list[tuple[Node, list[str]]] = []
    total = directories = 0

    def collect(d: str) -> Node | None:
        nonlocal total, directories
        directories += 1
        if progress and (directories == 1 or directories % 100 == 0):
            progress(0, f"Scanning folders: {directories}")
        files, subs = [], []
        try:
            with os.scandir(d) as scan:
                entries = sorted(scan, key=lambda e: natural(e.name))
        except OSError as error:
            log.warning("Cannot scan audio folder %s: %s", d, error)
            return None
        for e in entries:
            if e.is_symlink():
                continue                      # a link back up would loop
            if e.is_dir():
                sub = collect(e.path)
                if sub is not None:
                    subs.append(sub)
            elif os.path.splitext(e.name)[1].lower() in AUDIO_EXT:
                files.append(e.path)
        name = os.path.basename(d) or d
        playlist = None
        if files:
            playlist = Node("playlist", name)
            total += len(files)
            pending.append((playlist, files))
        if not subs:
            return playlist
        return Node("folder", name, children=([playlist] if playlist else []) + subs)

    root = collect(path)
    done = 0
    for playlist, files in pending:
        for file in files:
            playlist.tracks.append(make_track(file))
            done += 1
            if progress and done % 25 == 0:
                progress(min(99, 100 * done // max(1, total)), f"Reading tags {done}/{total}")
    if progress:
        progress(100, f"{done} tracks")
    return [root] if root is not None else []
