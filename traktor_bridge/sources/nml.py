# Benoit Saint-Moulin
# Traktor Bridge : Traktor collection.nml reader (Traktor Pro 3 and 4)

from __future__ import annotations

import logging
import os
import re
import xml.etree.ElementTree as ET

from .. import keys
from ..model import CUE, GRID, LOOP, Cue, Node, Track
from . import Progress, check_size, index_folder, num, relocate

log = logging.getLogger(__name__)

# Traktor COLOR 1-7 -> rekordbox color id (1 pink ... 8 purple)
COLOR_TO_RB = {1: 2, 2: 3, 3: 4, 4: 5, 5: 7, 6: 8, 7: 1}


def read_tree(path: str) -> ET.Element:
    check_size(path)
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        # old collections sometimes carry control chars in tags, Traktor itself doesn't care
        txt = raw.decode("utf-8", errors="replace")
        txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", txt)
        return ET.fromstring(txt)


def nml_date(s: str) -> str:
    """'2026/9/28' -> '2026-09-28'."""
    parts = (s or "").split("/")
    if len(parts) != 3:
        return ""
    try:
        y, m, d = (int(p) for p in parts)
    except ValueError:
        return ""
    return f"{y:04d}-{m:02d}-{d:02d}"


def location_key(loc: ET.Element) -> str:
    """The PRIMARYKEY form Traktor uses to reference a track from a playlist."""
    return loc.get("VOLUME", "") + loc.get("DIR", "") + loc.get("FILE", "")


def location_path(loc: ET.Element) -> str:
    vol = loc.get("VOLUME", "")
    rel = loc.get("DIR", "").replace("/:", "/") + loc.get("FILE", "")
    if len(vol) == 2 and vol[1] == ":":
        return os.path.normpath(vol + rel)
    # macOS: VOLUME is the disk name, the boot disk is mounted on /
    ext = f"/Volumes/{vol}{rel}"
    return ext if os.path.exists(ext) else rel


# ============================================================
# Entries
# ============================================================

def read_entry(e: ET.Element) -> Track:
    t = Track(title=e.get("TITLE", ""), artist=e.get("ARTIST", ""))
    t.audio_id = e.get("AUDIO_ID", "")
    t.locked = e.get("LOCK") == "1"
    t.modified = nml_date(e.get("MODIFIED_DATE", ""))

    loc = e.find("LOCATION")
    if loc is not None:
        t.path = location_path(loc)

    alb = e.find("ALBUM")
    if alb is not None:
        t.album = alb.get("TITLE", "")
        t.track_no = int(num(alb.get("TRACK")))

    info = e.find("INFO")
    if info is not None:
        t.genre = info.get("GENRE", "")
        t.label = info.get("LABEL", "")
        t.comment = info.get("COMMENT", "")
        t.remixer = info.get("REMIXER", "") or e.get("REMIXER", "")
        t.composer = info.get("PRODUCER", "")
        t.bitrate = int(num(info.get("BITRATE"))) // 1000
        t.size = int(num(info.get("FILESIZE"))) * 1024    # Traktor stores KB
        t.duration = num(info.get("PLAYTIME_FLOAT")) or num(info.get("PLAYTIME"))
        t.rating = int(num(info.get("RANKING"))) // 51
        t.plays = int(num(info.get("PLAYCOUNT")))
        t.color = COLOR_TO_RB.get(int(num(info.get("COLOR"))), 0)
        t.added = nml_date(info.get("IMPORT_DATE", ""))
        t.last_played = nml_date(info.get("LAST_PLAYED", ""))
        t.year = int(num(info.get("RELEASE_DATE", "").split("/")[0]))
        if t.key is None and info.get("KEY"):
            t.key = keys.parse(info.get("KEY"))

    tempo = e.find("TEMPO")
    if tempo is not None:
        t.bpm = num(tempo.get("BPM"))

    mk = e.find("MUSICAL_KEY")
    if mk is not None:
        t.key = keys.from_traktor(mk.get("VALUE"))

    loud = e.find("LOUDNESS")
    if loud is not None:
        t.gain = num(loud.get("ANALYZED_DB"))

    for c in e.findall("CUE_V2"):
        cue = Cue(name=c.get("NAME", ""), kind=int(num(c.get("TYPE"))),
                  start=num(c.get("START")), length=num(c.get("LEN")),
                  hotcue=int(num(c.get("HOTCUE"), -1)), color=c.get("COLOR", ""))
        if cue.kind == GRID:
            if t.grid is None:
                t.grid = cue.start
            continue
        # AutoGrid and friends are not real cues, a LOOP without length is a plain cue
        if cue.kind == LOOP and cue.length <= 0:
            cue.kind = CUE
        t.cues.append(cue)
    return t


# ============================================================
# Playlists
# ============================================================

def read_nodes(parent: ET.Element, by_key: dict[str, Track]) -> list[Node]:
    out = []
    sub = parent.find("SUBNODES")
    for n in (sub if sub is not None else parent).findall("NODE"):
        kind, name = n.get("TYPE", ""), n.get("NAME", "")
        if kind == "FOLDER":
            kids = read_nodes(n, by_key)
            if kids:
                out.append(Node("folder", name, children=kids))
        elif kind == "PLAYLIST":
            pl = n.find("PLAYLIST")
            if pl is None:
                continue
            node = Node("playlist", name, uuid=pl.get("UUID", ""))
            for ent in pl.findall("ENTRY"):
                pk = ent.find("PRIMARYKEY")
                t = by_key.get(pk.get("KEY", "")) if pk is not None else None
                if t is not None:
                    node.tracks.append(t)
            if node.tracks:
                out.append(node)
        elif kind == "SMARTLIST":
            sl = n.find("SMARTLIST")
            if sl is None:
                continue
            q = sl.find("SEARCH_EXPRESSION")
            out.append(Node("smartlist", name, uuid=sl.get("UUID", ""),
                            query=q.get("QUERY", "") if q is not None else ""))
    return out


def load(path: str, music_root: str = "", progress: Progress | None = None) -> list[Node]:
    cb = progress or (lambda pct, msg: None)
    root = read_tree(path)
    log.info("NML version %s", root.get("VERSION", "?"))

    found = {}
    if music_root:
        cb(5, "Scanning music folder...")
        found = index_folder(music_root)

    col = root.find("COLLECTION")
    entries = col.findall("ENTRY") if col is not None else []
    by_key: dict[str, Track] = {}
    moved = 0
    for i, e in enumerate(entries):
        if i % 500 == 0:
            cb(10 + 80 * i // max(1, len(entries)), f"Reading {i}/{len(entries)}")
        loc = e.find("LOCATION")
        if loc is None:
            continue
        t = read_entry(e)
        # relocate only what is really gone, a same-named file elsewhere could be another mix
        p = relocate(t.path, found)
        if p != t.path:
            t.path = p
            moved += 1
        by_key[location_key(loc)] = t

    if moved:
        log.info("%d tracks relocated from %s", moved, music_root)

    top = root.find("PLAYLISTS")
    if top is None:
        return []
    rootnode = top.find("NODE")
    nodes = read_nodes(rootnode if rootnode is not None else top, by_key)
    cb(100, f"{len(by_key)} tracks")
    return nodes
