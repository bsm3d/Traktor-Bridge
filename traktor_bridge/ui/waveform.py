# Benoit Saint-Moulin
# Traktor Bridge : waveform overview for the player and the timeline, cached on disk

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from collections import OrderedDict
from time import monotonic

from PySide6.QtCore import QObject, QThread, Signal

from ..settings import cache_dir

COLS = 1200
# waves kept in memory (about 170 KB each as tuples) and tracks decoded ahead
KEEP = 48
AHEAD = 64
# the zoomed view: columns per second, computed when the user first zooms in on a track
HI_PER_SEC = 1000
KEEP_HI = 4

# (low, mid, high) 0..1 per column
Wave = list[tuple[float, float, float]]
log = logging.getLogger(__name__)


def key(path: str) -> str:
    st = os.stat(path)
    raw = f"{os.path.normcase(os.path.abspath(path))}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def cache_file(path: str):
    d = cache_dir() / "wave"
    d.mkdir(exist_ok=True)
    return d / (key(path) + ".bin")


def load(path: str) -> Wave | None:
    try:
        raw = cache_file(path).read_bytes()
    except OSError:
        return None
    if len(raw) != COLS * 3:
        return None
    return [(raw[i] / 255, raw[i + 1] / 255, raw[i + 2] / 255) for i in range(0, len(raw), 3)]


def write_cache(path, raw: bytes):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp",
                                     delete=False) as stream:
        tmp = stream.name
        try:
            stream.write(raw)
        except BaseException:
            stream.close()
            os.unlink(tmp)
            raise
    try:
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def compute(path: str) -> Wave:
    import numpy as np

    from ..export.cdj.analysis import Audio
    b = Audio(path).at(COLS)
    wave = list(zip(b.low.tolist(), b.mid.tolist(), b.high.tolist(), strict=True))
    if b.low.any() or b.mid.any() or b.high.any():
        f = cache_file(path)
        write_cache(f, np.rint(np.stack([b.low, b.mid, b.high], axis=1) * 255).astype(np.uint8).tobytes())
    return wave


def hi_file(path: str):
    d = cache_dir() / "wave"
    d.mkdir(exist_ok=True)
    return d / (key(path) + f".hi{HI_PER_SEC}")


def load_hi(path: str):
    """(n, 3) float array 0..1, None when not computed yet."""
    import numpy as np
    try:
        raw = hi_file(path).read_bytes()
    except OSError:
        return None
    if len(raw) % 3 or len(raw) < COLS * 3:
        return None
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.float32)
    arr /= 255
    return arr


def compute_hi(path: str):
    import numpy as np

    from ..export.cdj.analysis import Audio
    a = Audio(path, detail=HI_PER_SEC)
    b = a.at(max(COLS, round(a.seconds * HI_PER_SEC)))
    arr = np.stack([b.low, b.mid, b.high], axis=1).astype(np.float32)
    if arr.any():
        f = hi_file(path)
        write_cache(f, np.rint(arr * 255).astype(np.uint8).tobytes())
    return arr


class _HiThread(QThread):
    ready = Signal(str, object)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            h = load_hi(self.path)
            self.ready.emit(self.path, h if h is not None else compute_hi(self.path))
        except Exception:
            log.warning("cannot load detailed waveform for %s", self.path, exc_info=True)
            self.ready.emit(self.path, None)


class _Thread(QThread):
    ready = Signal(str, object)

    def __init__(self, paths: list[str]):
        super().__init__()
        self.paths = paths
        self.halt = False

    def run(self):
        for p in self.paths:
            if self.halt:
                return
            try:
                self.ready.emit(p, load(p) or compute(p))
            except Exception:
                log.warning("cannot load waveform for %s", p, exc_info=True)
                self.ready.emit(p, None)


class Loader(QObject):
    """One decoding thread at a time, requests queue up, the newest first."""

    ready = Signal(str, object)
    hi_ready = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.queue: list[str] = []
        self.th: _Thread | None = None
        self.mem: OrderedDict[str, Wave] = OrderedDict()
        self.hi: OrderedDict = OrderedDict()
        self.hi_queue: list[str] = []
        self.hi_th: _HiThread | None = None

    def keep(self, path: str, wave: Wave):
        self.mem[path] = wave
        self.mem.move_to_end(path)
        while len(self.mem) > KEEP:
            self.mem.popitem(last=False)

    def get(self, path: str) -> Wave | None:
        if path in self.mem:
            self.mem.move_to_end(path)
            return self.mem[path]
        if self.th is not None and path in self.th.paths:
            return None
        w = load(path)
        if w:
            self.keep(path, w)
            return w
        if path in self.queue:
            self.queue.remove(path)
        self.queue.insert(0, path)
        self.pump()
        return None

    def get_hi(self, path: str):
        """The detailed wave now when it is there, else None and hi_ready comes later."""
        if path in self.hi:
            self.hi.move_to_end(path)
            return self.hi[path]
        if self.hi_th is not None and path == self.hi_th.path:
            return None
        h = load_hi(path)
        if h is not None:
            self.keep_hi(path, h)
            return h
        if path in self.hi_queue:
            self.hi_queue.remove(path)
        self.hi_queue.insert(0, path)
        self.pump_hi()
        return None

    def keep_hi(self, path: str, arr):
        self.hi[path] = arr
        self.hi.move_to_end(path)
        while len(self.hi) > KEEP_HI:
            self.hi.popitem(last=False)

    def pump_hi(self):
        if self.hi_th is not None or not self.hi_queue:
            return
        self.hi_th = _HiThread(self.hi_queue.pop(0))
        self.hi_th.ready.connect(self.hi_got)
        self.hi_th.finished.connect(self.hi_next)
        self.hi_th.start()

    def hi_got(self, path: str, arr):
        if arr is not None:
            self.keep_hi(path, arr)
        self.hi_ready.emit(path, arr)

    def hi_next(self):
        self.hi_th.deleteLater()
        self.hi_th = None
        self.pump_hi()

    def prefetch(self, paths: list[str]):
        """Warm the disk cache for the first tracks; decode the rest on selection."""
        for p in paths[:AHEAD]:
            if p not in self.mem and p not in self.queue and not cache_file(p).exists():
                self.queue.append(p)
        self.pump()

    def pump(self):
        if self.th is not None or not self.queue:
            return
        p = self.queue.pop(0)
        self.th = _Thread([p])
        self.th.ready.connect(self.got)
        self.th.finished.connect(self.next)
        self.th.start()

    def got(self, path: str, wave):
        if wave:
            self.keep(path, wave)
        self.ready.emit(path, wave)

    def next(self):
        self.th.deleteLater()
        self.th = None
        self.pump()

    def stop(self, ms: int = 5000) -> bool:
        self.queue.clear()
        self.hi_queue.clear()
        deadline = monotonic() + max(0, ms) / 1000
        stopped = True
        if self.th is not None:
            self.th.halt = True
        for thread in (self.th, self.hi_th):
            if thread is not None:
                remaining = max(0, int((deadline - monotonic()) * 1000))
                if not thread.wait(remaining):
                    stopped = False
        return stopped
