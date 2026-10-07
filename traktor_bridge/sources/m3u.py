# Benoit Saint-Moulin
# Traktor Bridge : M3U / M3U8 playlist reader

from __future__ import annotations

import os

from ..model import Node, Track
from . import Progress, check_size, num, relocator
from .rbxml import url_to_path


def read_text(path: str) -> str:
    check_size(path, 64 << 20)           # 100 000 lines is about 10 MB
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # plain .m3u from older players is usually the Windows codepage
        return raw.decode("cp1252", errors="replace")


def load(path: str, music_root: str = "", progress: Progress | None = None) -> list[Node]:
    base = os.path.dirname(os.path.abspath(path))
    resolve = relocator(music_root)
    node = Node("playlist", os.path.splitext(os.path.basename(path))[0])

    info = None
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            dur, _, label = line[8:].partition(",")
            info = (max(0.0, num(dur)), label.strip())
            continue
        if line.startswith("#"):
            continue
        if "://" in line and not line.startswith("file:"):
            info = None
            continue

        p = url_to_path(line)
        if not os.path.isabs(p):
            p = os.path.normpath(os.path.join(base, p))
        t = Track(path=resolve(p))
        if info:
            t.duration = info[0]
            artist, sep, title = info[1].partition(" - ")
            t.artist, t.title = (artist, title) if sep else ("", info[1])
        if not t.title:
            t.title = os.path.splitext(os.path.basename(p))[0]
        node.tracks.append(t)
        info = None

    if progress:
        progress(100, f"{len(node.tracks)} tracks")
    return [node] if node.tracks else []
