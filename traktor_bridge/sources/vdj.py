# Benoit Saint-Moulin
# Traktor Bridge : VirtualDJ reader (database.xml, playlists and .vdjfolder)

"""database.xml holds every track, its cues (Poi) and its analysis (Scan).
Playlists live next to it: Playlists/*.m3u and Folders/**/*.vdjfolder, the folder
tree on disk becomes the playlist tree. Scan Bpm is the time between two beats in
seconds, not beats per minute."""

from __future__ import annotations

import os

import defusedxml.ElementTree as ET

from .. import keys
from ..model import CUE, LOOP, Cue, Node, Track
from . import Progress, check_size, num, relocate, relocator, unix_date
from .m3u import read_text


def color(s: str) -> str:
    """Poi Color: '#rrggbb' or a decimal ARGB."""
    if not s:
        return ""
    if s.startswith("#"):
        return s[:7].upper()
    try:
        return "#%06X" % (int(s) & 0xFFFFFF)
    except ValueError:
        return ""


def read_song(el: ET.Element) -> Track:
    t = Track(path=el.get("FilePath", ""), size=int(num(el.get("FileSize"))))
    tg = el.find("Tags")
    if tg is not None:
        g = tg.get
        t.title, t.artist, t.album = g("Title", ""), g("Author", ""), g("Album", "")
        t.genre, t.label, t.composer = g("Genre", ""), g("Label", ""), g("Composer", "")
        t.remixer = g("Remix", "")
        t.track_no = int(num(g("TrackNumber")))
        t.year = int(num((g("Year") or "")[:4]))
        t.rating = min(5, int(num(g("Stars"))))
        if g("Key"):
            t.key = keys.parse(g("Key"))
    inf = el.find("Infos")
    if inf is not None:
        t.duration = num(inf.get("SongLength"))
        t.bitrate = int(num(inf.get("Bitrate")))
        t.plays = int(num(inf.get("PlayCount")))
        t.added = unix_date(inf.get("FirstSeen"))
        t.last_played = unix_date(inf.get("LastPlay"))
    com = el.find("Comment")
    if com is not None and com.text:
        t.comment = com.text.strip()

    sc = el.find("Scan")
    if sc is not None:
        spb = num(sc.get("Bpm"))
        t.bpm = 60 / spb if spb > 0 else 0.0
        if sc.get("Key"):
            t.key = keys.parse(sc.get("Key"))
        # fluid beatgrid (VirtualDJ 2026): the anchor moved from a Poi to Scan Phase
        if sc.get("Phase") is not None:
            t.grid = num(sc.get("Phase")) * 1000

    for p in el.findall("Poi"):
        kind = p.get("Type", "cue")
        pos = num(p.get("Pos")) * 1000
        if kind == "beatgrid":
            if t.grid is None:
                t.grid = pos
            continue
        if kind not in ("cue", "loop"):
            continue                        # automix, remix, action points
        n = int(num(p.get("Num"), 0))
        c = Cue(name=p.get("Name", ""), kind=CUE, start=pos, color=color(p.get("Color", "")),
                hotcue=n - 1 if 1 <= n <= 8 else -1)
        if kind == "loop":
            # Size is a length in beats, a saved loop without bpm has no usable length
            beats = num(p.get("Size"))
            if beats > 0 and t.bpm > 0:
                c.kind, c.length = LOOP, beats * 60000 / t.bpm
        t.cues.append(c)
    return t


def read_vdjfolder(path: str, by_path: dict[str, Track], found) -> list[Track]:
    try:
        check_size(path)
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return []
    out = []
    for s in root.iter("song"):
        p = s.get("path", "")
        t = by_path.get(os.path.normcase(p))
        if t is None:
            t = Track(path=found(p) if callable(found) else relocate(p, found),
                      title=s.get("title", ""), artist=s.get("artist", ""),
                      duration=num(s.get("songlength")), bpm=num(s.get("bpm")))
            by_path[os.path.normcase(p)] = t
        out.append(t)
    return out


def read_m3u(path: str, by_path: dict[str, Track], found) -> list[Track]:
    out = []
    base = os.path.dirname(path)
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line if os.path.isabs(line) else os.path.normpath(os.path.join(base, line))
        t = by_path.get(os.path.normcase(p))
        if t is None:
            t = Track(path=found(p) if callable(found) else relocate(p, found),
                      title=os.path.splitext(os.path.basename(p))[0])
            by_path[os.path.normcase(p)] = t
        out.append(t)
    return out


def read_dir(folder: str, by_path, found) -> list[Node]:
    out = []
    with os.scandir(folder) as scan:
        entries = sorted(scan, key=lambda entry: entry.name.lower())
    for entry in entries:
        name, full = entry.name, entry.path
        stem, ext = os.path.splitext(name)
        if entry.is_dir():
            kids = read_dir(full, by_path, found)
            if kids:
                out.append(Node("folder", name, children=kids))
        elif ext.lower() == ".vdjfolder":
            tl = read_vdjfolder(full, by_path, found)
            if tl:
                out.append(Node("playlist", stem, tracks=tl))
        elif ext.lower() in (".m3u", ".m3u8"):
            tl = read_m3u(full, by_path, found)
            if tl:
                out.append(Node("playlist", stem, tracks=tl))
    return out


def home_of(path: str) -> str:
    """The VirtualDJ folder whether the user picked database.xml or a playlist in it."""
    d = os.path.dirname(os.path.abspath(path))
    while d and not os.path.isfile(os.path.join(d, "database.xml")):
        up = os.path.dirname(d)
        if up == d:
            return os.path.dirname(os.path.abspath(path))
        d = up
    return d


def load(path: str, music_root: str = "", progress: Progress | None = None) -> list[Node]:
    cb = progress or (lambda pct, msg: None)
    home = home_of(path)
    found = relocator(music_root)

    by_path: dict[str, Track] = {}
    db = os.path.join(home, "database.xml")
    everything = []
    if os.path.isfile(db):
        cb(10, "Reading database.xml...")
        check_size(db)
        for el in ET.parse(db).getroot().iter("Song"):
            t = read_song(el)
            key = os.path.normcase(t.path)
            t.path = found(t.path)
            by_path[key] = t
            everything.append(t)

    # a single playlist picked: only that one
    if path.lower().endswith((".vdjfolder", ".m3u", ".m3u8")):
        reader = read_vdjfolder if path.lower().endswith(".vdjfolder") else read_m3u
        tl = reader(path, by_path, found)
        cb(100, f"{len(tl)} tracks")
        return [Node("playlist", os.path.splitext(os.path.basename(path))[0], tracks=tl)] if tl else []

    nodes = []
    for sub in ("Playlists", "Folders"):
        d = os.path.join(home, sub)
        if os.path.isdir(d):
            kids = read_dir(d, by_path, found)
            if kids:
                nodes.append(Node("folder", sub, children=kids))
    if everything:
        nodes.append(Node("playlist", "All tracks", tracks=everything))
    cb(100, f"{len(by_path)} tracks")
    return nodes
