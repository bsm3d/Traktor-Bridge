# Benoit Saint-Moulin
# Traktor Bridge : rekordbox XML (DJ_PLAYLISTS) reader

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse

from .. import keys
from ..model import CUE, FADE_IN, FADE_OUT, LOAD, LOOP, Cue, Node, Track
from . import Progress, check_size, index_folder, num, relocate

# POSITION_MARK Type
_KINDS = {0: CUE, 1: FADE_IN, 2: FADE_OUT, 3: LOAD, 4: LOOP}

# the 8 rekordbox track colours as written in Colour="0x......"
RB_COLORS = ["FF007F", "FF0000", "FFA500", "FFFF00", "00FF00", "25FDE9", "0000FF", "660099"]


def url_to_path(loc: str) -> str:
    if not loc.startswith("file:"):
        return loc
    p = unquote(urlparse(loc).path)
    # file://localhost/C:/x gives /C:/x
    if len(p) > 2 and p[2] == ":":
        p = os.path.normpath(p[1:])
    return p


def rb_date(s: str) -> str:
    return s[:10] if len(s) >= 10 and s[4] == "-" else ""


def read_track(el: ET.Element) -> Track:
    g = el.get
    t = Track(title=g("Name", ""), artist=g("Artist", ""), album=g("Album", ""),
              genre=g("Genre", ""), label=g("Label", ""), comment=g("Comments", ""),
              remixer=g("Remixer", ""), composer=g("Composer", ""))
    t.path = url_to_path(g("Location", ""))
    t.size = int(num(g("Size")))
    t.bitrate = int(num(g("BitRate")))
    t.samplerate = int(num(g("SampleRate"), 44100))
    t.duration = num(g("TotalTime"))
    t.bpm = num(g("AverageBpm"))
    t.key = keys.parse(g("Tonality", ""))
    t.rating = int(num(g("Rating"))) // 51
    t.plays = int(num(g("PlayCount")))
    t.year = int(num(g("Year")))
    t.track_no = int(num(g("TrackNumber")))
    t.disc_no = int(num(g("DiscNumber")))
    t.added = rb_date(g("DateAdded", ""))
    col = g("Colour", "").upper().replace("0X", "")
    if col in RB_COLORS:
        t.color = RB_COLORS.index(col) + 1

    tempo = el.find("TEMPO")
    if tempo is not None:
        t.grid = num(tempo.get("Inizio")) * 1000

    for pm in el.findall("POSITION_MARK"):
        start = num(pm.get("Start")) * 1000
        end = pm.get("End")
        c = Cue(name=pm.get("Name", ""), kind=_KINDS.get(int(num(pm.get("Type"))), CUE),
                start=start, length=num(end) * 1000 - start if end else 0.0,
                hotcue=int(num(pm.get("Num"), -1)))
        r, gr, b = pm.get("Red"), pm.get("Green"), pm.get("Blue")
        if r is not None and gr is not None and b is not None:
            c.color = f"#{int(num(r)):02X}{int(num(gr)):02X}{int(num(b)):02X}"
        t.cues.append(c)
    return t


def read_nodes(parent: ET.Element, by_id: dict[str, Track], by_loc: dict[str, Track]) -> list[Node]:
    out = []
    for n in parent.findall("NODE"):
        name = n.get("Name", "")
        if n.get("Type") == "0":
            kids = read_nodes(n, by_id, by_loc)
            if kids:
                out.append(Node("folder", name, children=kids))
            continue
        # KeyType 1 means the playlist references tracks by Location instead of TrackID
        ref = by_loc if n.get("KeyType") == "1" else by_id
        node = Node("playlist", name)
        for tr in n.findall("TRACK"):
            t = ref.get(tr.get("Key", ""))
            if t is not None:
                node.tracks.append(t)
        if node.tracks:
            out.append(node)
    return out


def load(path: str, music_root: str = "", progress: Progress | None = None) -> list[Node]:
    cb = progress or (lambda pct, msg: None)
    check_size(path)
    root = ET.parse(path).getroot()
    found = index_folder(music_root) if music_root else {}

    by_id, by_loc = {}, {}
    col = root.find("COLLECTION")
    items = col.findall("TRACK") if col is not None else []
    for i, el in enumerate(items):
        if i % 500 == 0:
            cb(10 + 80 * i // max(1, len(items)), f"Reading {i}/{len(items)}")
        t = read_track(el)
        t.path = relocate(t.path, found)
        by_id[el.get("TrackID", "")] = t
        by_loc[el.get("Location", "")] = t

    top = root.find("PLAYLISTS/NODE")
    nodes = read_nodes(top, by_id, by_loc) if top is not None else []
    cb(100, f"{len(by_id)} tracks")
    return nodes
