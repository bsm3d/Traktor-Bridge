# Benoit Saint-Moulin
# Traktor Bridge : what the file exports share (audio copy, XML output)

from __future__ import annotations

import os
import re
import threading
import xml.etree.ElementTree as ET

from ..model import Node, Track, unique_tracks
from .files import Planner, Report, copy_all, present, safe_name
from .manifest import Manifest

_XML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean(s) -> str:
    """ElementTree writes control chars as is, then nothing can read the file back."""
    return _XML_BAD.sub("", str(s))


def write_xml(root: ET.Element, path: str, decl: str):
    ET.indent(root, "  ")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(decl + "\n")
        f.write(ET.tostring(root, encoding="unicode"))
        f.write("\n")
    os.replace(tmp, path)


def start(nodes: list[Node], path: str) -> Report:
    tracks = unique_tracks(nodes)
    return Report(tracks=len(tracks), path=path,
                  missing=[t.path or t.title for t in tracks if not present(t)])


def copy_tracks(nodes: list[Node], out: str, rep: Report, verify: bool, progress=None,
                cancel: threading.Event | None = None, man: Manifest | None = None) -> dict[str, str]:
    """Audio copied under out/Contents/Artist/Album, returns uid -> new path."""
    plan = Planner()
    moved, jobs = {}, []
    for t in unique_tracks(nodes):
        if not present(t):
            continue
        rel = plan.claim(os.path.join("Contents", safe_name(t.artist or "Unknown Artist"),
                                      safe_name(t.album or "Unknown Album"),
                                      safe_name(os.path.basename(t.path))))
        dst = os.path.join(out, rel)
        moved[t.uid] = dst
        jobs.append((t.path, dst))
    rep.errors += copy_all(jobs, verify, cancel, progress, man)
    return moved


def where(t: Track, moved: dict[str, str]) -> str:
    return moved.get(t.uid, t.path)
