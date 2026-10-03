# Benoit Saint-Moulin
# Traktor Bridge : audio copies shared by every export

from __future__ import annotations

import hashlib
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..model import Track
from .manifest import BLOCK, Cancelled, Manifest, sha256_file

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class Report:
    tracks: int = 0
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cached: int = 0
    path: str = ""
    manifest: str = ""


def safe_name(s: str, limit: int = 0) -> str:
    """FAT32 friendly name, keeps the accents like rekordbox does."""
    s = _BAD.sub("_", s).strip().rstrip(". ")
    if limit and len(s) > limit:
        stem, ext = os.path.splitext(s)
        s = stem[:max(1, limit - len(ext))].rstrip(". ") + ext
    return s or "_"


class Planner:
    """Hands out destination names, never twice the same (case insensitive, FAT)."""

    def __init__(self):
        self.taken: set[str] = set()

    def claim(self, rel: str) -> str:
        stem, ext = os.path.splitext(rel)
        cand, n = rel, 1
        while cand.lower() in self.taken:
            n += 1
            cand = f"{stem} ({n}){ext}"
        self.taken.add(cand.lower())
        return cand


def removable(path: str) -> bool:
    """USB key or card: one copy at a time is faster there, parallel writes fragment
    the FAT and the flash controller serialises them anyway."""
    if sys.platform != "win32":
        return False
    import ctypes
    root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    return ctypes.windll.kernel32.GetDriveTypeW(root) == 2


def copy_one(src: str, dst: str, verify: bool, man: Manifest | None = None) -> int:
    """Bytes actually written, 0 when the file was already there. The copy is hashed
    on the way for the manifest, no second read."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    size = os.path.getsize(src)
    # same size already there: a previous export of the same file. Trusted as is,
    # unless verifying, then it has to match the source byte for byte
    if os.path.exists(dst) and os.path.getsize(dst) == size:
        if not verify:
            if man:
                man.add(dst, man.known(dst))
            return 0
        # the drive is read for real, the time stamp alone misses a damaged block
        sha = sha256_file(dst)
        if sha256_file(src) == sha:
            if man:
                man.add(dst, sha)
            return 0
    tmp = dst + ".part"
    h = hashlib.sha256()
    with open(src, "rb") as fi, open(tmp, "wb") as fo:
        while True:
            b = fi.read(BLOCK)
            if not b:
                break
            h.update(b)
            fo.write(b)
    os.replace(tmp, dst)
    if man:
        man.add(dst, h.hexdigest())
    return size


def eta(done: int, total: int, t0: float) -> str:
    dt = time.monotonic() - t0
    if done <= 0 or dt < 1:
        return ""
    rate = done / dt
    left = (total - done) / rate
    return f"{rate / 1e6:.1f} MB/s, {int(left // 60)}:{int(left % 60):02d} left"


def copy_all(jobs: list[tuple[str, str]], verify: bool, cancel: threading.Event | None = None,
             progress=None, man: Manifest | None = None) -> list[str]:
    """jobs: (src, dst). progress(i, n, info) with the speed and time left.
    Returns the errors, one line each."""
    errors, done, written = [], 0, 0
    todo = sum(os.path.getsize(s) for s, d in jobs
               if not (os.path.exists(d) and os.path.getsize(d) == os.path.getsize(s)))
    workers = 1 if jobs and removable(jobs[0][1]) else 4
    t0 = time.monotonic()
    with ThreadPoolExecutor(workers) as pool:
        futs = {pool.submit(copy_one, s, d, verify, man): (s, d) for s, d in jobs}
        for f, (s, _) in futs.items():
            if cancel is not None and cancel.is_set():
                pool.shutdown(cancel_futures=True)
                raise Cancelled()
            try:
                written += f.result()
            except OSError as e:
                errors.append(f"{os.path.basename(s)}: {e}")
            done += 1
            if progress:
                progress(done, len(jobs), eta(written, todo, t0))
    return errors


def present(t: Track) -> bool:
    return bool(t.path) and os.path.isfile(t.path)
