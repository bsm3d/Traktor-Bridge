# Benoit Saint-Moulin
# Traktor Bridge : audio copies shared by every export

from __future__ import annotations

import contextlib
import hashlib
import os
import queue
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..model import Track
from .manifest import Cancelled, Manifest, sha256_file

# copy block: big writes are more sequential for a flash controller and cost fewer system calls
COPY_BLOCK = 4 << 20
# blocks read ahead of the writer on a removable drive
QUEUE = 8

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class Report:
    tracks: int = 0
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cached: int = 0
    path: str = ""
    manifest: str = ""
    verified: int = 0       # files read back from the drive and found identical
    verified_size: int = 0


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


def _todo(jobs) -> int:
    n = 0
    for s, d in jobs:
        try:
            size = os.path.getsize(s)
            if not (os.path.exists(d) and os.path.getsize(d) == size):
                n += size
        except OSError:
            pass
    return n


def _already(src: str, dst: str, size: int, verify: bool) -> tuple[bool, str | None]:
    """(True, sha) when dst is already a good copy. The sha is None when it was trusted
    without reading, the manifest then keeps what it knows."""
    # same size already there: a previous export of the same file. Trusted as is,
    # unless verifying, then it has to match the source byte for byte
    if os.path.exists(dst) and os.path.getsize(dst) == size:
        if not verify:
            return True, None
        # the drive is read for real, the time stamp alone misses a damaged block
        sha = sha256_file(dst)
        if sha256_file(src) == sha:
            return True, sha
    return False, None


def copy_one(src: str, dst: str, verify: bool, man: Manifest | None = None) -> int:
    """Bytes actually written, 0 when the file was already there. The copy is hashed
    on the way for the manifest, no second read."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    size = os.path.getsize(src)
    hit, sha = _already(src, dst, size, verify)
    if hit:
        if man:
            man.add(dst, man.known(dst) if sha is None else sha)
        return 0
    tmp = dst + ".part"
    h = hashlib.sha256()
    try:
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            while True:
                b = fi.read(COPY_BLOCK)
                if not b:
                    break
                h.update(b)
                fo.write(b)
        os.replace(tmp, dst)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise
    if man:
        man.add(dst, h.hexdigest())
    return size


def _read_ahead(jobs, verify: bool, q: queue.Queue, stop: threading.Event):
    """Reads the sources in order, ahead of the writer, into a bounded queue. The
    source drive and the key are busy at the same time instead of taking turns."""
    def put(item) -> bool:
        while not stop.is_set():
            try:
                q.put(item, timeout=0.2)
                return True
            except queue.Full:
                pass
        return False

    for i, (src, dst) in enumerate(jobs):
        try:
            size = os.path.getsize(src)
            hit, sha = _already(src, dst, size, verify)
            if hit:
                if not put((i, "skip", sha)):
                    return
                continue
            with open(src, "rb") as fi:
                if not put((i, "start", size)):
                    return
                while True:
                    b = fi.read(COPY_BLOCK)
                    if not b:
                        break
                    if not put((i, "data", b)):
                        return
            if not put((i, "end", None)):
                return
        except OSError as e:
            if not put((i, "err", e)):
                return


def copy_pipelined(jobs: list[tuple[str, str]], verify: bool, cancel: threading.Event | None = None,
                   progress=None, man: Manifest | None = None) -> list[str]:
    """One writer fed by a reader thread: for a removable drive, where parallel writes
    do not help but waiting for each read before writing does."""
    errors, written = [], 0
    todo = _todo(jobs)
    q: queue.Queue = queue.Queue(maxsize=QUEUE)
    stop = threading.Event()
    reader = threading.Thread(target=_read_ahead, args=(jobs, verify, q, stop), daemon=True)
    t0 = time.monotonic()
    reader.start()

    fo, h, tmp, failed, size = None, None, "", None, 0

    def drop():
        nonlocal fo
        if fo is not None:
            fo.close()
            fo = None
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass

    try:
        done = 0
        while done < len(jobs):
            try:
                i, kind, payload = q.get(timeout=0.5)
            except queue.Empty:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                if not reader.is_alive():
                    raise RuntimeError("read-ahead thread stopped")
                continue
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            src, dst = jobs[i]
            finished = True
            if kind == "skip":
                if man:
                    man.add(dst, man.known(dst) if payload is None else payload)
            elif kind == "start":
                finished = False
                size, failed, h, tmp = payload, None, hashlib.sha256(), dst + ".part"
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    fo = open(tmp, "wb")  # noqa: SIM115, kept open across the data items
                except OSError as e:
                    failed, tmp = e, ""
            elif kind == "data":
                finished = False
                if failed is None:
                    try:
                        h.update(payload)
                        fo.write(payload)
                    except OSError as e:
                        failed = e
                        drop()
            elif kind == "end":
                if failed is None:
                    try:
                        fo.close()
                        fo = None
                        os.replace(tmp, dst)
                        written += size
                        if man:
                            man.add(dst, h.hexdigest())
                    except OSError as e:
                        failed = e
                        drop()
                tmp = ""
            else:
                failed = payload
                drop()
                tmp = ""
            if finished:
                if failed is not None:
                    errors.append(f"{os.path.basename(src)}: {failed}")
                    failed = None
                done += 1
                if progress:
                    progress(done, len(jobs), eta(written, todo, t0))
    except BaseException:
        drop()
        raise
    finally:
        stop.set()
        reader.join(timeout=5)
    return errors


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
    if jobs and removable(jobs[0][1]):
        return copy_pipelined(jobs, verify, cancel, progress, man)
    errors, done, written = [], 0, 0
    todo = _todo(jobs)
    workers = 4
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
