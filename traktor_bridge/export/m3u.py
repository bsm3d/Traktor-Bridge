# Benoit Saint-Moulin
# Traktor Bridge : M3U8 export, one file per playlist, folders kept as folders

from __future__ import annotations

import os
import threading

from ..model import Node
from .common import copy_tracks, start, where
from .files import Planner, Report, safe_name
from .manifest import Manifest, sha256_bytes, write_atomic


def line(s: str) -> str:
    return s.replace("\r", " ").replace("\n", " ")


def write_list(n: Node, path: str, moved: dict[str, str], relative: bool, man: Manifest | None = None):
    base = os.path.dirname(path)
    out = ["#EXTM3U", f"#PLAYLIST:{line(n.name)}"]
    for t in n.tracks:
        p = where(t, moved)
        if not p:
            continue
        label = f"{t.artist} - {t.title}" if t.artist else t.title
        out.append(f"#EXTINF:{round(t.duration) or -1},{line(label)}")
        if relative:
            try:
                p = os.path.relpath(p, base)
            except ValueError:          # other drive
                pass
        out.append(p.replace("\\", "/") if relative else p)
    data = ("\n".join(out) + "\n").encode("utf-8")
    write_atomic(path, data)
    if man:
        man.add(path, sha256_bytes(data))


def walk(nodes: list[Node], folder: str, moved: dict[str, str], relative: bool, plan: Planner,
         man: Manifest | None = None) -> int:
    count = 0
    for n in nodes:
        if n.is_folder:
            count += walk(n.children, os.path.join(folder, safe_name(n.name)), moved, relative, plan, man)
            continue
        if not n.tracks:
            continue
        os.makedirs(folder, exist_ok=True)
        path = plan.claim(os.path.join(folder, safe_name(n.name) + ".m3u8"))
        write_list(n, path, moved, relative, man)
        count += 1
    return count


def export(nodes: list[Node], out: str, copy: bool = False, verify: bool = False,
           progress=None, cancel: threading.Event | None = None, man: Manifest | None = None) -> Report:
    cb = progress or (lambda pct, msg: None)
    os.makedirs(out, exist_ok=True)
    rep = start(nodes, out)
    moved = {}
    if copy:
        moved = copy_tracks(nodes, out, rep, verify, lambda i, n, info="": cb(90 * i // n, f"Copying {i}/{n} {info}".strip()), cancel, man)
    # relative paths only make sense when the audio travels with the playlists
    n = walk(nodes, os.path.join(out, "Playlists"), moved, copy, Planner(), man)
    cb(100, f"{n} playlists written")
    return rep
