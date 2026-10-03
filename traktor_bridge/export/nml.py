# Benoit Saint-Moulin
# Traktor Bridge : Traktor collection export (NML 19, read by Traktor Pro 3 and 4)

from __future__ import annotations

import os
import threading
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import PurePosixPath, PureWindowsPath

from .. import keys
from ..model import GRID, Node, Track, unique_tracks
from ..sources.nml import COLOR_TO_RB
from .common import clean, copy_tracks, start, where, write_xml
from .files import Report
from .manifest import Manifest

RB_TO_COLOR = {v: k for k, v in COLOR_TO_RB.items()}


def split_path(path: str) -> tuple[str, str, str]:
    """VOLUME, DIR, FILE the way Traktor stores them: 'C:', '/:Music/:House/:', 'x.mp3'."""
    if len(path) > 1 and path[1] == ":":
        p = PureWindowsPath(path)
        vol, parts = p.drive, p.parts[1:-1]
    else:
        p = PurePosixPath(path)
        parts = p.parts[1:-1]
        if len(parts) > 1 and parts[0] == "Volumes":
            vol, parts = parts[1], parts[2:]
        else:
            vol = "Macintosh HD"
    return vol, "".join(f"/:{d}" for d in parts) + "/:", p.name


def nml_date(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return ""
    return f"{d.year}/{d.month}/{d.day}"


def entry(t: Track, path: str) -> ET.Element:
    e = ET.Element("ENTRY", {"MODIFIED_DATE": nml_date(t.modified or date.today().isoformat()),
                             "MODIFIED_TIME": "0", "TITLE": clean(t.title), "ARTIST": clean(t.artist)})
    if t.audio_id:
        e.set("AUDIO_ID", t.audio_id)
    if t.locked:
        e.set("LOCK", "1")

    vol, d, f = split_path(path)
    ET.SubElement(e, "LOCATION", DIR=clean(d), FILE=clean(f), VOLUME=clean(vol))
    alb = {"TITLE": clean(t.album)}
    if t.track_no:
        alb["TRACK"] = str(t.track_no)
    ET.SubElement(e, "ALBUM", alb)
    ET.SubElement(e, "MODIFICATION_INFO", AUTHOR_TYPE="user")

    size = t.size or (os.path.getsize(path) if os.path.exists(path) else 0)
    info = {"BITRATE": t.bitrate * 1000, "GENRE": t.genre, "LABEL": t.label, "COMMENT": t.comment,
            "REMIXER": t.remixer, "PRODUCER": t.composer, "KEY": keys.name(t.key),
            "PLAYCOUNT": t.plays, "PLAYTIME": round(t.duration), "PLAYTIME_FLOAT": f"{t.duration:.6f}",
            "RANKING": min(5, t.rating) * 51, "IMPORT_DATE": nml_date(t.added),
            "LAST_PLAYED": nml_date(t.last_played), "FILESIZE": size // 1024,
            "RELEASE_DATE": f"{t.year}/1/1" if t.year else "", "COLOR": RB_TO_COLOR.get(t.color, "")}
    ET.SubElement(e, "INFO", {k: clean(v) for k, v in info.items() if v not in ("", 0)})

    if t.bpm > 0:
        ET.SubElement(e, "TEMPO", BPM=f"{t.bpm:.6f}", BPM_QUALITY="100.000000")
    if t.gain:
        ET.SubElement(e, "LOUDNESS", PEAK_DB="0.000000", PERCEIVED_DB=f"{t.gain:.6f}", ANALYZED_DB=f"{t.gain:.6f}")
    if t.key is not None:
        ET.SubElement(e, "MUSICAL_KEY", VALUE=str(t.key))

    cues = []
    if t.grid is not None:
        cues.append(("AutoGrid", GRID, t.grid, 0.0, 0, ""))
    cues += [(c.name, c.kind, c.start, c.length, c.hotcue, c.color) for c in t.cues]
    for i, (name, kind, st, ln, hot, col) in enumerate(cues):
        c = ET.SubElement(e, "CUE_V2", NAME=clean(name), DISPL_ORDER=str(i), TYPE=str(kind),
                          START=f"{st:.6f}", LEN=f"{ln:.6f}", REPEATS="-1", HOTCUE=str(hot))
        if col:
            c.set("COLOR", col)
    return e


def key_of(path: str) -> str:
    vol, d, f = split_path(path)
    return vol + d + f


def node(n: Node, paths: dict[str, str]) -> ET.Element:
    if n.is_folder:
        el = ET.Element("NODE", TYPE="FOLDER", NAME=clean(n.name))
        sub = ET.SubElement(el, "SUBNODES", COUNT=str(len(n.children)))
        for c in n.children:
            sub.append(node(c, paths))
        return el
    if n.kind == "smartlist":
        el = ET.Element("NODE", TYPE="SMARTLIST", NAME=clean(n.name))
        sl = ET.SubElement(el, "SMARTLIST", UUID=n.uuid)
        ET.SubElement(sl, "SEARCH_EXPRESSION", VERSION="1", QUERY=clean(n.query))
        return el
    el = ET.Element("NODE", TYPE="PLAYLIST", NAME=clean(n.name))
    ents = [paths[t.uid] for t in n.tracks if t.uid in paths]
    pl = ET.SubElement(el, "PLAYLIST", ENTRIES=str(len(ents)), TYPE="LIST", UUID=n.uuid)
    for p in ents:
        ent = ET.SubElement(pl, "ENTRY")
        ET.SubElement(ent, "PRIMARYKEY", TYPE="TRACK", KEY=clean(key_of(p)))
    return el


def export(nodes: list[Node], out: str, copy: bool = False, verify: bool = False,
           progress=None, cancel: threading.Event | None = None, man: Manifest | None = None) -> Report:
    cb = progress or (lambda pct, msg: None)
    os.makedirs(out, exist_ok=True)
    rep = start(nodes, os.path.join(out, "collection.nml"))
    moved = {}
    if copy:
        moved = copy_tracks(nodes, out, rep, verify, lambda i, n, info="": cb(80 * i // n, f"Copying {i}/{n} {info}".strip()), cancel, man)

    root = ET.Element("NML", VERSION="19")
    ET.SubElement(root, "HEAD", COMPANY="www.native-instruments.com", PROGRAM="Traktor")
    ET.SubElement(root, "MUSICFOLDERS")
    tracks = unique_tracks(nodes)
    col = ET.SubElement(root, "COLLECTION", ENTRIES=str(len(tracks)))
    paths = {}
    for t in tracks:
        p = where(t, moved)
        paths[t.uid] = p
        col.append(entry(t, p))

    pls = ET.SubElement(root, "PLAYLISTS")
    top = ET.SubElement(pls, "NODE", TYPE="FOLDER", NAME="$ROOT")
    sub = ET.SubElement(top, "SUBNODES", COUNT=str(len(nodes)))
    for n in nodes:
        sub.append(node(n, paths))

    write_xml(root, rep.path, '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>')
    if man:
        man.add(rep.path)
    cb(100, f"{len(tracks)} tracks written")
    return rep
