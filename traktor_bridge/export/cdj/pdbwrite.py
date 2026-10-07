# Benoit Saint-Moulin
# Traktor Bridge : export.pdb tables (tracks, lookups, playlists)

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from datetime import datetime

from ... import keys
from ...model import Node, Track
from . import native
from .devicesql import Row, build_py

(TRACKS, GENRES, ARTISTS, ALBUMS, LABELS, KEYS, COLORS, PL_TREE, PL_ENTRIES) = range(9)
ARTWORK, COLUMNS, T17, T18, HISTORY = 13, 16, 17, 18, 19

COLOR_NAMES = ["Pink", "Red", "Orange", "Yellow", "Green", "Aqua", "Blue", "Purple"]

FILE_TYPES = {".mp3": 1, ".m4a": 4, ".mp4": 4, ".aac": 4, ".flac": 5, ".wav": 11, ".aif": 12, ".aiff": 12}



@dataclass(slots=True)
class Item:
    """A track as it lands on the key."""
    track: Track
    id: int
    path: str           # /Contents/..., as the player sees it
    anlz: str           # /PIONEER/USBANLZ/P.../ANLZ0000.DAT
    size: int
    art: int = 0


class Lookup:
    """Name -> id in order of first use, the way rekordbox numbers them."""

    def __init__(self):
        self.ids: dict = {}

    def get(self, key) -> int:
        if key in (None, ""):
            return 0
        if key not in self.ids:
            self.ids[key] = len(self.ids) + 1
        return self.ids[key]


# ============================================================
# Rows
# ============================================================

def track_row(it: Item, today: str, artist: int, album: int, genre: int, label: int,
              remixer: int, composer: int, key: int) -> bytes:
    t = it.track
    ext = os.path.splitext(it.path)[1].lower()
    r = Row(bytes(0x88))
    struct.pack_into("<HHIIIIII", r.buf, 0x00, 0x24, 0, 0x000C0700, t.samplerate or 44100,
                     composer, it.size, 0, 0xC25930BF)
    struct.pack_into("<IIIIII", r.buf, 0x1c, it.art, key, 0, label, remixer, t.bitrate)
    struct.pack_into("<IIIIII", r.buf, 0x34, t.track_no, round(t.bpm * 100), genre, album, artist, it.id)
    struct.pack_into("<HHHHHH", r.buf, 0x4c, t.disc_no, t.plays, t.year, 16, round(t.duration), 41)
    struct.pack_into("<BBHH", r.buf, 0x58, t.color, min(5, t.rating), FILE_TYPES.get(ext, 1), 3)

    strs = ["", "", "2", "2", "", "", "ON", "ON", "", "", t.added or today, "", "", "",
            it.anlz, today, t.comment, t.title, "", os.path.basename(it.path), it.path]
    for i, s in enumerate(strs):
        r.u16(0x5e + 2 * i, r.put(s))
    return r.done()


def id_name(i: int, name: str) -> bytes:
    r = Row(struct.pack("<I", i))
    r.put(name)
    return r.done()


def artist_row(i: int, name: str) -> bytes:
    r = Row(struct.pack("<HHIBB", 0x60, 0, i, 3, 0))
    r.u8(9, r.put(name))
    return r.done()


def album_row(i: int, name: str, artist: int) -> bytes:
    r = Row(struct.pack("<HHIIIIBB", 0x80, 0, 0, artist, i, 0, 3, 0))
    r.u8(21, r.put(name))
    return r.done()


def key_row(i: int, name: str) -> bytes:
    r = Row(struct.pack("<II", i, i))
    r.put(name)
    return r.done()


def color_row(i: int, name: str) -> bytes:
    r = Row(struct.pack("<IBHB", 0, i, i, 0))
    r.put(name)
    return r.done()


def tree_row(parent: int, sort: int, i: int, folder: bool, name: str) -> bytes:
    r = Row(struct.pack("<IIIII", parent, 0, sort, i, int(folder)))
    r.put(name)
    return r.done()


# ============================================================
# Playlists
# ============================================================

def walk_tree(nodes: list[Node], parent: int, ids: dict[str, int], rows: list, entries: list, nid: list):
    for sort, n in enumerate(nodes):
        nid[0] += 1
        me = nid[0]
        rows.append(tree_row(parent, sort, me, n.is_folder, n.name))
        if n.is_folder:
            walk_tree(n.children, me, ids, rows, entries, nid)
            continue
        pos = 0
        for t in n.tracks:
            tid = ids.get(t.uid)
            if tid:
                pos += 1
                entries.append(struct.pack("<III", pos, tid, me))


def flat_inputs(items: list[Item], nodes: list[Node]):
    """The same data as build_py_file reads, as plain numbers and strings for the native core."""
    tracks = []
    for it in items:
        t = it.track
        ext = os.path.splitext(it.path)[1].lower()
        tracks.append((it.id, it.art, it.size, t.samplerate or 44100, t.bitrate, t.track_no, t.disc_no, t.plays,
                       t.year, t.color, t.rating, FILE_TYPES.get(ext, 1), t.bpm, t.duration,
                       [t.title, t.artist, t.album_artist, t.album, t.genre, t.label, t.remixer, t.composer,
                        t.comment, keys.name(t.key), t.added, it.path, it.anlz, os.path.basename(it.path)]))
    ids = {it.track.uid: it.id for it in items}
    tree, ents = [], []

    def walk(level: list[Node], parent: int, nid: list):
        for sort, n in enumerate(level):
            nid[0] += 1
            me = nid[0]
            tree.append((parent, sort, me, int(n.is_folder), n.name))
            if n.is_folder:
                walk(n.children, me, nid)
                continue
            pos = 0
            for t in n.tracks:
                tid = ids.get(t.uid)
                if tid:
                    pos += 1
                    ents.append((pos, tid, me))
    walk(nodes, 0, [0])
    return tracks, tree, ents


def write(items: list[Item], nodes: list[Node], path: str | os.PathLike, today: str = "",
          static: dict[int, bytes] | None = None):
    """export.pdb. The native core builds it when it is there, build_py_file is the reference."""
    today = today or datetime.now().astimezone().date().isoformat()
    # player menus and an empty history, the same in every rekordbox export
    if static is None:
        from . import reference
        static = reference.pages()
    data = None
    if native.available():
        tracks, tree, ents = flat_inputs(items, nodes)
        data = native.pdb_write(tracks, tree, ents, today, static)
    if data is None:
        data = build_py_file(items, nodes, today, static)
    from .validate import pdb, write_verified
    write_verified(str(path), data, pdb)


def build_py_file(items: list[Item], nodes: list[Node], today: str, static: dict[int, bytes]) -> bytes:
    artists, albums, genres, labels, used_keys = Lookup(), Lookup(), Lookup(), Lookup(), Lookup()

    track_rows = []
    for it in items:
        t = it.track
        a = artists.get(t.artist)
        aa = artists.get(t.album_artist) or a
        track_rows.append(track_row(
            it, today, a, albums.get((t.album, aa) if t.album else None), genres.get(t.genre),
            labels.get(t.label), artists.get(t.remixer), artists.get(t.composer),
            used_keys.get(keys.name(t.key))))

    tables = {
        TRACKS: track_rows,
        GENRES: [id_name(i, n) for n, i in genres.ids.items()],
        ARTISTS: [artist_row(i, n) for n, i in artists.ids.items()],
        ALBUMS: [album_row(i, n, a) for (n, a), i in albums.ids.items()],
        LABELS: [id_name(i, n) for n, i in labels.ids.items()],
        KEYS: [key_row(i, n) for n, i in used_keys.ids.items()],
        COLORS: [color_row(i + 1, n) for i, n in enumerate(COLOR_NAMES)],
        ARTWORK: [id_name(a, f"/PIONEER/Artwork/00001/a{a}.jpg")
                  for a in sorted({it.art for it in items if it.art})],
    }

    ids = {it.track.uid: it.id for it in items}
    tree, ents = [], []
    walk_tree(nodes, 0, ids, tree, ents, [0])
    tables[PL_TREE] = tree
    tables[PL_ENTRIES] = ents

    return build_py(tables, static, {TRACKS, ARTISTS, ALBUMS})
