# Benoit Saint-Moulin
# Traktor Bridge : Mixxx library (mixxxdb.sqlite) reader

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..model import CUE, LOAD, LOOP, Cue, Node, Track
from . import Progress, index_folder, relocate

# Mixxx cue types: 1 hotcue, 2 main cue, 4 loop, 5 jump, 6 intro, 7 outro
# 0 invalid, 3 beat and 8 audible are internal markers
_KEEP = {1, 2, 4, 5, 6, 7}

_TRACKS = """
SELECT l.id, l.artist, l.title, l.album, l.year, l.genre, l.comment, l.composer,
       l.bpm, l.duration, l.rating, l.timesplayed, l.datetime_added, l.bitrate,
       l.samplerate, l.key_id, l.tracknumber, tl.location, tl.filesize
FROM library l JOIN track_locations tl ON l.location = tl.id
WHERE l.mixxx_deleted = 0 AND tl.fs_deleted = 0
"""


def read_track(r: sqlite3.Row) -> Track:
    t = Track(title=r["title"] or "", artist=r["artist"] or "", album=r["album"] or "",
              genre=r["genre"] or "", comment=r["comment"] or "", composer=r["composer"] or "")
    t.path = r["location"] or ""
    t.size = r["filesize"] or 0
    t.bpm = r["bpm"] or 0.0
    t.duration = r["duration"] or 0.0
    t.bitrate = r["bitrate"] or 0
    t.samplerate = r["samplerate"] or 44100
    t.rating = r["rating"] or 0
    t.plays = r["timesplayed"] or 0
    t.added = (r["datetime_added"] or "")[:10]
    # ChromaticKey: 1-12 C..B major, 13-24 Cm..Bm, same order as Traktor
    kid = r["key_id"] or 0
    t.key = kid - 1 if 1 <= kid <= 24 else None
    try:
        t.year = int(str(r["year"] or "")[:4])
    except ValueError:
        pass
    try:
        t.track_no = int(str(r["tracknumber"] or "").split("/")[0])
    except ValueError:
        pass
    return t


def read_cues(con: sqlite3.Connection, tracks: dict[int, Track]):
    for r in con.execute("SELECT track_id, type, position, length, hotcue, label FROM cues"):
        t = tracks.get(r["track_id"])
        if t is None or r["type"] not in _KEEP:
            continue
        # positions are interleaved stereo samples at the file rate
        per_ms = 2 * t.samplerate / 1000
        start = (r["position"] or 0) / per_ms
        length = (r["length"] or 0) / per_ms if r["type"] == 4 else 0.0
        kind = LOOP if length > 0 else LOAD if r["type"] == 2 else CUE
        hot = r["hotcue"] if r["hotcue"] is not None and r["hotcue"] >= 0 else -1
        t.cues.append(Cue(name=r["label"] or "", kind=kind, start=start, length=length, hotcue=hot))


def read_list(con, sql: str, lid: int, tracks: dict[int, Track]) -> list[Track]:
    return [tracks[r[0]] for r in con.execute(sql, (lid,)) if r[0] in tracks]


def load(path: str, music_root: str = "", progress: Progress | None = None) -> list[Node]:
    cb = progress or (lambda pct, msg: None)
    con = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        found = index_folder(music_root) if music_root else {}
        cb(10, "Reading library...")
        tracks = {}
        for r in con.execute(_TRACKS):
            t = read_track(r)
            t.path = relocate(t.path, found)
            tracks[r["id"]] = t
        read_cues(con, tracks)

        out = []
        # hidden 0 = user playlists, the others are Auto DJ and the history
        for r in con.execute("SELECT id, name FROM Playlists WHERE hidden = 0 ORDER BY position"):
            tl = read_list(con, "SELECT track_id FROM PlaylistTracks WHERE playlist_id = ? ORDER BY position",
                           r["id"], tracks)
            if tl:
                out.append(Node("playlist", r["name"], tracks=tl))

        crates = []
        for r in con.execute("SELECT id, name FROM crates WHERE show = 1 ORDER BY name"):
            tl = read_list(con, "SELECT track_id FROM crate_tracks WHERE crate_id = ? ORDER BY track_id",
                           r["id"], tracks)
            if tl:
                crates.append(Node("playlist", r["name"], tracks=tl))
        if crates:
            out.append(Node("folder", "Crates", children=crates))
    finally:
        con.close()
    cb(100, f"{len(tracks)} tracks")
    return out
