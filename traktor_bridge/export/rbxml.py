# Benoit Saint-Moulin
# Traktor Bridge : rekordbox XML export (File > Import in rekordbox)

from __future__ import annotations

import os
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

from .. import APP_NAME, AUTHOR, VERSION, keys
from ..model import CUE, FADE_IN, FADE_OUT, LOAD, LOOP, Node, Track, unique_tracks
from ..sources.rbxml import RB_COLORS
from .common import clean, copy_tracks, start, where, write_xml
from .files import Report
from .manifest import Manifest

# model cue kind -> POSITION_MARK Type
_TYPES = {CUE: 0, FADE_IN: 1, FADE_OUT: 2, LOAD: 3, LOOP: 4}

# rekordbox hot cue colours A..H as shown by default
HOT_RGB = [(40, 226, 20), (48, 90, 255), (255, 18, 123), (255, 127, 0),
           (48, 210, 255), (170, 114, 255), (224, 100, 27), (16, 177, 118)]

KINDS = {".mp3": "MP3 File", ".m4a": "M4A File", ".mp4": "M4A File", ".aac": "AAC File",
         ".flac": "FLAC File", ".wav": "WAV File", ".aif": "AIFF File", ".aiff": "AIFF File"}


def location(path: str) -> str:
    p = Path(path).as_posix()
    if not p.startswith("/"):
        p = "/" + p
    return "file://localhost" + quote(p, safe="/:")


def hex_rgb(s: str):
    s = s.lstrip("#")
    if len(s) == 8:          # Traktor ARGB
        s = s[2:]
    try:
        v = int(s, 16)
    except ValueError:
        return None
    return v >> 16 & 255, v >> 8 & 255, v & 255


def track_el(t: Track, tid: int, path: str) -> ET.Element:
    ext = os.path.splitext(path)[1].lower()
    a = {
        "TrackID": tid, "Name": t.title, "Artist": t.artist, "Composer": t.composer, "Album": t.album,
        "Grouping": "", "Genre": t.genre, "Kind": KINDS.get(ext, ext[1:].upper() + " File"),
        "Size": t.size or (os.path.getsize(path) if os.path.exists(path) else 0),
        "TotalTime": round(t.duration), "DiscNumber": t.disc_no, "TrackNumber": t.track_no,
        "Year": t.year or "", "AverageBpm": f"{t.bpm:.6f}", "DateAdded": t.added,
        "BitRate": t.bitrate, "SampleRate": t.samplerate, "Comments": t.comment,
        "PlayCount": t.plays, "Rating": min(5, t.rating) * 51, "Location": location(path),
        "Remixer": t.remixer, "Tonality": keys.name(t.key), "Label": t.label, "Mix": "",
    }
    if t.color:
        a["Colour"] = "0x" + RB_COLORS[t.color - 1]
    el = ET.Element("TRACK", {k: clean(v) for k, v in a.items()})

    if t.grid is not None:
        ET.SubElement(el, "TEMPO", Inizio=f"{t.grid / 1000:.6f}", Bpm=f"{t.bpm:.6f}",
                      Metro="4/4", Battito="1")

    for c in t.cues:
        if c.kind not in _TYPES:
            continue
        m = {"Name": clean(c.name), "Type": str(_TYPES[c.kind]), "Start": f"{c.start / 1000:.6f}",
             "Num": str(c.hotcue if 0 <= c.hotcue < 8 else -1)}
        if c.is_loop:
            m["End"] = f"{(c.start + c.length) / 1000:.6f}"
        if 0 <= c.hotcue < 8:
            rgb = hex_rgb(c.color) if c.color else None
            m["Red"], m["Green"], m["Blue"] = (str(v) for v in (rgb or HOT_RGB[c.hotcue]))
        ET.SubElement(el, "POSITION_MARK", m)
    return el


def node_el(n: Node, ids: dict[str, int]) -> ET.Element:
    if n.is_folder:
        el = ET.Element("NODE", Type="0", Name=clean(n.name), Count=str(len(n.children)))
        for c in n.children:
            el.append(node_el(c, ids))
        return el
    keys_ = [ids[t.uid] for t in n.tracks if t.uid in ids]
    el = ET.Element("NODE", Name=clean(n.name), Type="1", KeyType="0", Entries=str(len(keys_)))
    for k in keys_:
        ET.SubElement(el, "TRACK", Key=str(k))
    return el


def export(nodes: list[Node], out: str, copy: bool = False, verify: bool = False,
           progress=None, cancel: threading.Event | None = None, man: Manifest | None = None) -> Report:
    cb = progress or (lambda pct, msg: None)
    os.makedirs(out, exist_ok=True)
    rep = start(nodes, os.path.join(out, "rekordbox.xml"))
    moved = {}
    if copy:
        moved = copy_tracks(nodes, out, rep, verify, lambda i, n, info="": cb(80 * i // n, f"Copying {i}/{n} {info}".strip()), cancel, man)

    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    ET.SubElement(root, "PRODUCT", Name=APP_NAME, Version=VERSION, Company=AUTHOR)
    tracks = unique_tracks(nodes)
    col = ET.SubElement(root, "COLLECTION", Entries=str(len(tracks)))
    ids = {}
    for i, t in enumerate(tracks, 1):
        ids[t.uid] = i
        col.append(track_el(t, i, where(t, moved)))

    pls = ET.SubElement(root, "PLAYLISTS")
    top = ET.SubElement(pls, "NODE", Type="0", Name="ROOT", Count=str(len(nodes)))
    for n in nodes:
        top.append(node_el(n, ids))

    write_xml(root, rep.path, '<?xml version="1.0" encoding="UTF-8"?>')
    if man:
        man.add(rep.path)
    cb(100, f"{len(tracks)} tracks written")
    return rep
