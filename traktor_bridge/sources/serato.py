# Benoit Saint-Moulin
# Traktor Bridge : Serato DJ reader (database V2, crates, cues in the audio files)

"""The library is _Serato_/database V2, crates are _Serato_/Subcrates/*.crate
('Parent%%Child.crate' for nesting). Both are the same record format: 4 char tag,
u32 big endian length, payload; 'o' tags nest, 't' and 'p' are UTF-16BE text,
paths are relative to the root of the drive holding _Serato_.

Cues, loops and the beatgrid are not in the library but in each audio file:
GEOB 'Serato Markers2' / 'Serato BeatGrid' (mp3, aiff, wav), base64 vorbis
comments SERATO_MARKERS_V2 / SERATO_BEATGRID (flac). MP4 tags are not read yet."""

from __future__ import annotations

import base64
import os
import struct

from .. import keys, tags
from ..model import CUE, LOOP, Cue, Node, Track
from . import Progress, check_size, index_folder, num, relocate, unix_date

# ============================================================
# Records
# ============================================================

def records(buf: bytes):
    p = 0
    while p + 8 <= len(buf):
        tag = buf[p:p + 4].decode("latin-1")
        n = struct.unpack_from(">I", buf, p + 4)[0]
        yield tag, buf[p + 8:p + 8 + n]
        p += 8 + n


def text(b: bytes) -> str:
    return b.decode("utf-16-be", "replace").rstrip("\0")


def fields(buf: bytes) -> dict:
    out = {}
    for tag, val in records(buf):
        if tag[0] in "tp":
            out[tag] = text(val)
        elif tag[0] in "us" and len(val) == 4:
            out[tag] = struct.unpack(">I" if tag[0] == "u" else ">i", val)[0]
        elif tag[0] == "b" and val:
            out[tag] = val[0]
    return out


def drive_root(serato: str) -> str:
    """Paths are relative to the drive holding _Serato_: C:\\ for the one in Music,
    E:\\ for a key, / or /Volumes/Name on a Mac."""
    drive = os.path.splitdrive(serato)[0]
    if drive:
        return drive + os.sep
    parts = serato.split("/")
    if len(parts) > 2 and parts[1] == "Volumes":
        return "/".join(parts[:3]) + "/"
    return "/"


def length(s: str) -> float:
    """tlen '05:23.42' or '323.4' in seconds."""
    if ":" in s:
        m, _, sec = s.partition(":")
        return num(m) * 60 + num(sec)
    return num(s)


def read_track(f: dict, root: str) -> Track:
    t = Track(title=f.get("tsng", ""), artist=f.get("tart", ""), album=f.get("talb", ""),
              genre=f.get("tgen", ""), comment=f.get("tcom", ""), label=f.get("tlbl", ""),
              remixer=f.get("trmx", ""), composer=f.get("tcmp", ""))
    t.path = os.path.normpath(os.path.join(root, f.get("pfil", "")))
    t.bpm = num(f.get("tbpm"))
    t.key = keys.parse(f.get("tkey", ""))
    t.duration = length(f.get("tlen", ""))
    t.bitrate = int(num(f.get("tbit", "").lower().replace("kbps", "")))
    sr = f.get("tsmp", "").lower().replace("k", "")
    t.samplerate = int(num(sr) * 1000) if num(sr) else 44100
    t.year = int(num(f.get("ttyr", "")[:4]))
    if f.get("uadd"):
        t.added = unix_date(f["uadd"])
    return t


# ============================================================
# Tags inside the audio files
# ============================================================

def geob_payload(raw: bytes | None) -> bytes | None:
    """Base64 body of a Serato GEOB object (after its 2 byte version)."""
    if not raw or len(raw) < 3:
        return None
    b64 = raw[2:].split(b"\0")[0].replace(b"\n", b"")
    if len(b64) % 4 == 1:
        b64 += b"A=="
    b64 += b"=" * (-len(b64) % 4)
    try:
        return base64.b64decode(b64)
    except ValueError:
        return None


def flac_object(comments: dict, key: str, desc: str) -> bytes | None:
    """FLAC keeps the whole GEOB (mime, name, description, data) base64 encoded."""
    v = comments.get(key)
    if not v:
        return None
    v = v.replace("\n", "")
    try:
        raw = base64.b64decode(v + "=" * (-len(v) % 4))
    except ValueError:
        return None
    mark = desc.encode("latin-1") + b"\0"
    i = raw.find(mark)
    return raw[i + len(mark):] if i >= 0 else None


def markers(data: bytes) -> list[Cue]:
    """Decoded Serato Markers2: 01 01 then (name NUL, u32 length, payload)."""
    out = []
    p = 2
    while p < len(data):
        end = data.find(b"\0", p)
        if end <= p:
            break
        name = data[p:end].decode("latin-1")
        n = struct.unpack_from(">I", data, end + 1)[0]
        body = data[end + 5:end + 5 + n]
        p = end + 5 + n
        if name == "CUE" and len(body) >= 12:
            idx, pos = body[1], struct.unpack_from(">I", body, 2)[0]
            r, g, b = body[7:10]
            label = body[12:].split(b"\0")[0].decode("utf-8", "replace")
            out.append(Cue(label, CUE, float(pos), hotcue=idx if idx < 8 else -1, color=f"#{r:02X}{g:02X}{b:02X}"))
        elif name == "LOOP" and len(body) >= 20:
            start, stop = struct.unpack_from(">II", body, 2)
            label = body[20:].split(b"\0")[0].decode("utf-8", "replace")
            if stop > start:
                # Serato loops have their own 8 slots, the cue pads keep A-H
                out.append(Cue(label, LOOP, float(start), float(stop - start)))
    return out


def beatgrid(data: bytes) -> tuple[float | None, float]:
    """(first beat ms, bpm of the last marker) from Serato BeatGrid."""
    if len(data) < 6:
        return None, 0.0
    count = struct.unpack_from(">I", data, 2)[0]
    if count == 0 or len(data) < 6 + 8 * count:
        return None, 0.0
    first = struct.unpack_from(">f", data, 6)[0]
    bpm = struct.unpack_from(">f", data, 6 + 8 * (count - 1) + 4)[0]
    return first * 1000, bpm


def read_tags(t: Track):
    if t.path.lower().endswith(".flac"):
        com = tags.comments(t.path)
        mk = flac_object(com, "SERATO_MARKERS_V2", "Serato Markers2")
        bg = flac_object(com, "SERATO_BEATGRID", "Serato BeatGrid")
    else:
        mk = tags.geob(t.path, "Serato Markers2")
        bg = tags.geob(t.path, "Serato BeatGrid")
    data = geob_payload(mk)
    if data:
        t.cues = markers(data)
    if bg:
        anchor, bpm = beatgrid(bg)
        if anchor is not None:
            t.grid = max(0.0, anchor)
        if bpm and not t.bpm:
            t.bpm = bpm


# ============================================================
# Load
# ============================================================

def serato_dir(path: str) -> str:
    d = os.path.dirname(os.path.abspath(path))
    return os.path.dirname(d) if os.path.basename(d).lower() == "subcrates" else d


def read_crate(path: str, root: str, by_path: dict[str, Track], found) -> list[Track]:
    check_size(path)
    with open(path, "rb") as f:
        buf = f.read()
    out = []
    for tag, val in records(buf):
        if tag != "otrk":
            continue
        rel = fields(val).get("ptrk", "")
        if not rel:
            continue
        full = os.path.normpath(os.path.join(root, rel))
        t = by_path.get(os.path.normcase(full))
        if t is None:
            t = Track(path=relocate(full, found), title=os.path.splitext(os.path.basename(full))[0])
            by_path[os.path.normcase(full)] = t
        out.append(t)
    return out


def crate_tree(files: list[str], root: str, by_path, found) -> list[Node]:
    """'House%%Deep.crate' is the crate Deep inside House."""
    top: list[Node] = []
    folders: dict[tuple, Node] = {}
    for f in sorted(files, key=str.lower):
        parts = os.path.splitext(os.path.basename(f))[0].split("%%")
        tl = read_crate(f, root, by_path, found)
        if not tl:
            continue
        level = top
        for i in range(len(parts) - 1):
            key = tuple(parts[:i + 1])
            if key not in folders:
                folders[key] = Node("folder", parts[i])
                level.append(folders[key])
            level = folders[key].children
        level.append(Node("playlist", parts[-1], tracks=tl))
    return top


def load(path: str, music_root: str = "", progress: Progress | None = None) -> list[Node]:
    cb = progress or (lambda pct, msg: None)
    home = serato_dir(path)
    root = drive_root(home)
    found = index_folder(music_root) if music_root else {}

    by_path: dict[str, Track] = {}
    db = os.path.join(home, "database V2")
    if os.path.isfile(db):
        cb(10, "Reading database V2...")
        check_size(db)
        with open(db, "rb") as f:
            buf = f.read()
        for tag, val in records(buf):
            if tag == "otrk":
                fl = fields(val)
                if fl.get("pfil"):
                    t = read_track(fl, root)
                    by_path[os.path.normcase(t.path)] = t

    if path.lower().endswith(".crate"):
        crates = [path]
    else:
        sub = os.path.join(home, "Subcrates")
        crates = [os.path.join(sub, f) for f in os.listdir(sub) if f.lower().endswith(".crate")] \
            if os.path.isdir(sub) else []
    nodes = crate_tree(crates, root, by_path, found)
    if not path.lower().endswith(".crate") and by_path:
        nodes.append(Node("playlist", "All tracks", tracks=list(by_path.values())))

    # cues live in the files, only read the ones that will be shown
    used = {id(t): t for n in nodes for t in walk(n)}
    for i, t in enumerate(used.values()):
        if i % 50 == 0:
            cb(40 + 55 * i // max(1, len(used)), f"Reading cues {i}/{len(used)}")
        t.path = relocate(t.path, found)
        if os.path.isfile(t.path):
            read_tags(t)
    cb(100, f"{len(used)} tracks")
    return nodes


def walk(n: Node):
    if n.is_folder:
        for c in n.children:
            yield from walk(c)
    else:
        yield from n.tracks
