# Benoit Saint-Moulin
# Traktor Bridge : waveform overview for the player and the timeline, cached on disk

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict

from PySide6.QtCore import QObject, QThread, Signal

from ..settings import cache_dir

COLS = 1200
# waves kept in memory (about 170 KB each as tuples) and tracks decoded ahead
KEEP = 48
AHEAD = 64

# (low, mid, high) 0..1 per column
Wave = list[tuple[float, float, float]]


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


def compute(path: str) -> Wave:
    import numpy as np

    from ..export.cdj.analysis import Audio
    b = Audio(path).at(COLS)
    wave = list(zip(b.low.tolist(), b.mid.tolist(), b.high.tolist(), strict=True))
    if b.low.any() or b.mid.any() or b.high.any():
        f = cache_file(path)
        tmp = f.with_suffix(".tmp")
        tmp.write_bytes(np.rint(np.stack([b.low, b.mid, b.high], axis=1) * 255).astype(np.uint8).tobytes())
        os.replace(tmp, f)
    return wave


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
                self.ready.emit(p, None)


class Loader(QObject):
    """One decoding thread at a time, requests queue up, the newest first."""

    ready = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.queue: list[str] = []
        self.th: _Thread | None = None
        self.mem: OrderedDict[str, Wave] = OrderedDict()

    def keep(self, path: str, wave: Wave):
        self.mem[path] = wave
        self.mem.move_to_end(path)
        while len(self.mem) > KEEP:
            self.mem.popitem(last=False)

    def get(self, path: str) -> Wave | None:
        if path in self.mem:
            self.mem.move_to_end(path)
            return self.mem[path]
        w = load(path)
        if w:
            self.keep(path, w)
            return w
        if path in self.queue:
            self.queue.remove(path)
        self.queue.insert(0, path)
        self.pump()
        return None

    def prefetch(self, paths: list[str]):
        """Decodes the first tracks of a playlist to the disk cache, the others
        come when they are selected, a 5000 track playlist would keep a core busy for hours."""
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

    def stop(self):
        self.queue.clear()
        if self.th is not None:
            self.th.halt = True
            self.th.wait()
