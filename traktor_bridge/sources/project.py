# Benoit Saint-Moulin
# Traktor Bridge : a project is the work in the playlist editors saved as JSON

"""Ordered playlist trees, track metadata, cues, grids and export settings.
Tracks are stored once and referenced by number to preserve shared edits on reload."""

from __future__ import annotations

import json
import os
import time
from dataclasses import fields

from ..model import Cue, Node, Track
from . import Progress, check_size, index_folder, relocate, sane

FORMAT = "traktor-bridge-project"
VERSION = 1
MAX_DEPTH = 32

# the settings a project carries: where things are and how to export them
SETTING_KEYS = ("source_path", "music_root", "output_path", "export_format", "copy_music", "verify_copy",
                "key_format", "waveform_color", "crossfade")
PATH_KEYS = ("source_path", "music_root", "output_path")

TRACK_FIELDS = [f.name for f in fields(Track) if f.name != "cues"]
CUE_FIELDS = [f.name for f in fields(Cue)]
OPTIONAL = {"key": int, "grid": float}


def sniff(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return FORMAT.encode() in f.read(2048)
    except OSError:
        return False


# ============================================================
# Save
# ============================================================

def dump(nodes: list[Node], cfg: dict) -> dict:
    ids: dict[int, int] = {}
    tracks: list[dict] = []

    def track_id(t: Track) -> int:
        k = id(t)
        if k not in ids:
            ids[k] = len(tracks)
            d = {n: getattr(t, n) for n in TRACK_FIELDS}
            d["cues"] = [{n: getattr(c, n) for n in CUE_FIELDS} for c in t.cues]
            tracks.append(d)
        return ids[k]

    def node(n: Node) -> dict:
        d = {"kind": n.kind, "name": n.name, "uuid": n.uuid}
        if n.query:
            d["query"] = n.query
        if n.is_folder:
            d["children"] = [node(c) for c in n.children]
        else:
            d["tracks"] = [track_id(t) for t in n.tracks]
        return d

    tree = [node(n) for n in nodes]
    return {"format": FORMAT, "version": VERSION, "saved": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "settings": {k: cfg[k] for k in SETTING_KEYS if k in cfg}, "tracks": tracks, "tree": tree}


def save(path: str, nodes: list[Node], cfg: dict):
    from ..export.manifest import write_atomic
    text = json.dumps(dump(nodes, cfg), indent=1, ensure_ascii=False)
    write_atomic(path, text.encode("utf-8"))


# ============================================================
# Load
# ============================================================

def _coerce(value, default):
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, (int, float)):
        # JSON accepts NaN, Infinity and 1e999, and an integer of any length
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not sane(value):
            return default
        return type(default)(value)
    if isinstance(default, str):
        return value if isinstance(value, str) else default
    return default


def _list(value, what: str) -> list:
    """A list from the file, empty when missing. Anything else is a damaged project."""
    if isinstance(value, list):
        return value
    if value is not None:
        raise ValueError(f"{what} must be a list")
    return []


def _track(d: dict) -> Track:
    t = Track()
    for n in TRACK_FIELDS:
        if n not in d:
            continue
        v = d[n]
        if n in OPTIONAL:
            ok = isinstance(v, (int, float)) and not isinstance(v, bool) and sane(v)
            setattr(t, n, OPTIONAL[n](v) if ok else None)
        else:
            setattr(t, n, _coerce(v, getattr(t, n)))
    for c in _list(d.get("cues"), "the cues of a track"):
        if not isinstance(c, dict):
            continue
        cue = Cue()
        for n in CUE_FIELDS:
            if n in c:
                setattr(cue, n, _coerce(c[n], getattr(cue, n)))
        t.cues.append(cue)
    return t


def read(path: str, music_root: str = "", progress: Progress | None = None) -> tuple[list[Node], dict]:
    """The tree and the saved settings. Files that moved are looked up in music_root, or in
    the music folder of the project."""
    check_size(path, 256 << 20)
    try:
        with open(path, encoding="utf-8-sig") as f:
            doc = json.load(f)
    except (ValueError, RecursionError, UnicodeDecodeError) as e:
        raise ValueError(f"{os.path.basename(path)} is not a valid project: {e}") from e
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ValueError(f"{os.path.basename(path)} is not a Traktor Bridge project")
    if not isinstance(doc.get("version"), int) or doc["version"] > VERSION:
        raise ValueError("this project was saved by a newer Traktor Bridge")

    raw = doc.get("settings") if isinstance(doc.get("settings"), dict) else {}
    cfg = {k: raw[k] for k in SETTING_KEYS if k in raw and isinstance(raw[k], (str, int, float, bool))
           and (isinstance(raw[k], (str, bool)) or sane(raw[k]))}
    for name in PATH_KEYS:
        if not isinstance(cfg.get(name, ""), str):
            del cfg[name]
    bad = f"{os.path.basename(path)} is not a valid project"
    try:
        tracks = [_track(d) for d in _list(doc.get("tracks"), "tracks") if isinstance(d, dict)]
    except ValueError as e:
        raise ValueError(f"{bad}: {e}") from e

    base = os.path.dirname(os.path.abspath(path))
    for t in tracks:
        if t.path and not os.path.isabs(t.path):
            t.path = os.path.normpath(os.path.join(base, t.path))
    for name in PATH_KEYS:
        if cfg.get(name) and not os.path.isabs(cfg[name]):
            cfg[name] = os.path.normpath(os.path.join(base, cfg[name]))
    root = music_root or str(cfg.get("music_root") or "")
    if root and os.path.isdir(root) and any(t.path and not os.path.exists(t.path) for t in tracks):
        found = index_folder(root)
        for t in tracks:
            t.path = relocate(t.path, found)

    def node(d, depth: int) -> Node | None:
        if not isinstance(d, dict) or depth > MAX_DEPTH:
            return None
        kind = d.get("kind") if d.get("kind") in ("folder", "playlist", "smartlist") else "playlist"
        n = Node(kind, str(d.get("name") or "Untitled"), uuid=str(d.get("uuid") or ""), query=str(d.get("query") or ""))
        if kind == "folder":
            kids = _list(d.get("children"), "the children of a folder")
            n.children = [c for c in (node(x, depth + 1) for x in kids) if c]
        else:
            n.tracks = [tracks[i] for i in _list(d.get("tracks"), "the tracks of a playlist")
                        if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(tracks)]
        return n

    try:
        nodes = [n for n in (node(x, 0) for x in _list(doc.get("tree"), "tree")) if n]
    except ValueError as e:
        raise ValueError(f"{bad}: {e}") from e
    if progress:
        progress(100, "Project read")
    return nodes, cfg


def load(path: str, music_root: str = "", progress: Progress | None = None) -> list[Node]:
    return read(path, music_root, progress)[0]
