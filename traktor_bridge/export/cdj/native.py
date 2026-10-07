# Benoit Saint-Moulin
# Traktor Bridge : loader of the native core (tbcore), None of it is needed to run

"""The page layout of export.pdb and the waveform bands exist twice: in Python
(devicesql.py, analysis.py), the reference, and in C++ (core/tbcore.cpp), what a
release uses. Every function here returns None when the library is absent or
TB_PURE_PYTHON is set, and the caller falls back to the Python version."""

from __future__ import annotations

import ctypes
import logging
import math
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

NAME = "tbcore.dll" if sys.platform == "win32" else "libtbcore.dylib" if sys.platform == "darwin" else "libtbcore.so"
VERSION = 2
MAX_OUTPUT = 1 << 30
N_TABLES = 20
PAGE = 4096


u32 = ctypes.c_uint32

# the library exports neutral names, the code keeps the readable ones
NAMES = {"tb_version": "q0", "tb_pdb_build": "q1", "tb_pdb_write": "q2", "tb_anlz_build": "q3",
         "tb_fold": "q4", "tb_bands": "q5"}


class Named:
    def __init__(self, dll):
        self.dll = dll

    def __getattr__(self, name: str):
        return getattr(self.dll, NAMES[name])


class TbTrack(ctypes.Structure):
    _fields_ = [(n, u32) for n in ("id", "art", "size", "samplerate", "bitrate", "track_no", "disc_no",
                                   "plays", "year", "color", "rating", "ftype")] + \
               [("bpm", ctypes.c_double), ("duration", ctypes.c_double), ("off", u32 * 14), ("len", u32 * 14)]


class TbNode(ctypes.Structure):
    _fields_ = [(n, u32) for n in ("parent", "sort", "id", "folder", "off", "len")]


class TbEntry(ctypes.Structure):
    _fields_ = [(n, u32) for n in ("pos", "tid", "me")]


class TbWave(ctypes.Structure):
    _fields_ = [("low", ctypes.c_void_p), ("mid", ctypes.c_void_p), ("high", ctypes.c_void_p), ("n", ctypes.c_int64)]


class TbCue(ctypes.Structure):
    _fields_ = [("hotcue", ctypes.c_int32), ("start", ctypes.c_double), ("length", ctypes.c_double),
                ("name_off", u32), ("name_len", u32),
                ("color_id", u32), ("rgb", u32)]


def load():
    if os.environ.get("TB_PURE_PYTHON"):
        return None
    path = Path(__file__).resolve().with_name(NAME)
    if not path.is_file():
        return None
    try:
        # Restrict dependency lookup to the DLL's directory and Windows system DLLs.
        lib = Named(ctypes.CDLL(str(path), winmode=0x00000100 | 0x00000800)
                    if sys.platform == "win32" else ctypes.CDLL(str(path)))
        lib.tb_version.argtypes = []
        lib.tb_version.restype = ctypes.c_int32
        if lib.tb_version() != VERSION:
            raise OSError(f"version {lib.tb_version()}, {VERSION} expected")
        log.info("native core loaded: %s", path.name)
        u8p, u32p = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint32)
        lib.tb_pdb_build.restype = ctypes.c_int64
        lib.tb_pdb_build.argtypes = [ctypes.POINTER(u8p), ctypes.POINTER(u32p), u32p, ctypes.POINTER(u8p),
                                     u8p, ctypes.c_void_p, ctypes.c_int64]
        lib.tb_pdb_write.restype = ctypes.c_int64
        lib.tb_pdb_write.argtypes = [ctypes.POINTER(TbTrack), u32, ctypes.c_void_p, ctypes.c_char_p, u32,
                                     ctypes.POINTER(TbNode), u32, ctypes.POINTER(TbEntry), u32,
                                     ctypes.POINTER(u8p), ctypes.c_void_p, ctypes.c_int64]
        lib.tb_anlz_build.restype = ctypes.c_int32
        lib.tb_anlz_build.argtypes = [ctypes.c_char_p, u32, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                                      u32, ctypes.POINTER(TbCue), u32, ctypes.POINTER(TbCue), u32,
                                      ctypes.c_void_p] + [ctypes.POINTER(TbWave)] * 4 + \
                                     [ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64,
                                      ctypes.POINTER(ctypes.c_int64)]
        lib.tb_fold.restype = ctypes.c_int64
        lib.tb_fold.argtypes = [ctypes.c_void_p, ctypes.c_int64, ctypes.c_int32, ctypes.c_void_p]
        lib.tb_bands.restype = ctypes.c_int32
        lib.tb_bands.argtypes = [ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_int64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        return lib
    except (OSError, AttributeError) as e:      # AttributeError: a build with other export names
        log.warning("native core not loaded, Python used: %s", e)
        return None


LIB = load()


def available() -> bool:
    return LIB is not None


def _output_size(size: int) -> int:
    if not 0 < size <= MAX_OUTPUT:
        raise ValueError(f"Native output size is invalid or exceeds 1 GiB: {size}")
    return size


def _samples(y):
    import numpy as np
    array = np.ascontiguousarray(y, dtype=np.float32)
    if array.ndim != 1 or not np.isfinite(array).all():
        raise ValueError("Native audio input must be a finite one-dimensional array")
    return array


def pdb_build(tables: dict[int, list[bytes]], static: dict[int, bytes], shifted: set[int]) -> bytes | None:
    """The export.pdb file, same as devicesql.build."""
    if LIB is None:
        return None
    for page in static.values():
        if len(page) != PAGE:
            raise ValueError("a static page is not 4096 bytes")
    u8p, u32p = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint32)
    keep = []                                           # buffers must outlive the call
    rows = (u8p * N_TABLES)()
    lens = (u32p * N_TABLES)()
    counts = (ctypes.c_uint32 * N_TABLES)()
    stat = (u8p * N_TABLES)()
    flags = (ctypes.c_uint8 * N_TABLES)()
    for t in range(N_TABLES):
        if t in static:
            buf = ctypes.create_string_buffer(static[t], PAGE)
            keep.append(buf)
            stat[t] = ctypes.cast(buf, u8p)
        elif tables.get(t):
            blob = ctypes.create_string_buffer(b"".join(tables[t]), sum(len(r) for r in tables[t]) or 1)
            ln = (ctypes.c_uint32 * len(tables[t]))(*[len(r) for r in tables[t]])
            keep += [blob, ln]
            rows[t] = ctypes.cast(blob, u8p)
            lens[t] = ctypes.cast(ln, u32p)
            counts[t] = len(tables[t])
        flags[t] = 1 if t in shifted else 0
    size = LIB.tb_pdb_build(rows, lens, counts, stat, flags, None, 0)
    if size == 0:
        raise ValueError("a row does not fit in a page")
    out = ctypes.create_string_buffer(_output_size(size))
    if LIB.tb_pdb_build(rows, lens, counts, stat, flags, out, size) != size:
        raise RuntimeError("native pdb build changed its size")
    return out.raw


def fold(y, w: int):
    """Mean of w consecutive samples, float32 in, float32 out. None without the library."""
    if LIB is None:
        return None
    import numpy as np
    if not isinstance(w, int) or isinstance(w, bool) or not 0 < w <= 0x7fffffff:
        raise ValueError("Native fold width must be a positive int32")
    y = _samples(y)
    out = np.empty(len(y) // w, dtype=np.float32)
    n = LIB.tb_fold(y.ctypes.data, len(y), w, out.ctypes.data)
    if n != len(out):
        raise RuntimeError("Native fold returned an unexpected sample count")
    return out[:n]


def bands(y, lo_sos, hi_sos, cols: int):
    """Three float32 arrays of cols peaks, normalised, or None without the library.
    Zeros when the signal has fewer samples than columns."""
    if LIB is None:
        return None
    import numpy as np
    if not isinstance(cols, int) or isinstance(cols, bool) or not 0 <= cols <= MAX_OUTPUT // 12:
        raise ValueError("Native waveform column count is invalid or too large")
    y = _samples(y)
    lo = np.ascontiguousarray(lo_sos, dtype=np.float64).reshape(-1)
    hi = np.ascontiguousarray(hi_sos, dtype=np.float64).reshape(-1)
    if lo.size != 6 or hi.size != 6:
        return None                                     # only second order, one section
    if not np.isfinite(lo).all() or not np.isfinite(hi).all() or lo[3] != 1 or hi[3] != 1:
        raise ValueError("Native filters must be finite with normalized a0")
    out = [np.zeros(cols, dtype=np.float32) for _ in range(3)]
    if len(y) >= cols > 0:
        status = LIB.tb_bands(y.ctypes.data, len(y), lo.ctypes.data, hi.ctypes.data, cols,
                              out[0].ctypes.data, out[1].ctypes.data, out[2].ctypes.data)
        if status != 1:
            raise RuntimeError(f"Native waveform calculation failed: {status}")
    return out


def _u32(v) -> int:
    v = int(v)
    if not 0 <= v <= 0xFFFFFFFF:
        raise ValueError(f"{v} does not fit in an export.pdb field")
    return v


def _blob(strings: list[str]):
    raw = [s.encode("utf-8") for s in strings]
    spans, pos = [], 0
    for r in raw:
        spans.append((_u32(pos), _u32(len(r))))
        pos += len(r)
        _u32(pos)
    return ctypes.create_string_buffer(b"".join(raw), pos + 1), spans


def pdb_write(tracks: list, nodes: list, entries: list, today: str, static: dict[int, bytes]) -> bytes | None:
    """The whole export.pdb, same as pdbwrite.build_py_file builds it.
    tracks: (id, art, size, samplerate, bitrate, track_no, disc_no, plays, year, color, rating,
    filetype, bpm, duration, [14 strings]); nodes: (parent, sort, id, folder, name);
    entries: (pos, track id, playlist id). None when the library is absent or cannot write it."""
    if LIB is None:
        return None
    if any(len(track) != 15 or len(track[14]) != 14 for track in tracks):
        raise ValueError("Native tracks require exactly 14 metadata strings")
    for count in (len(tracks), len(nodes), len(entries)):
        _u32(count)
    for page in static.values():
        if len(page) != PAGE:
            raise ValueError("a static page is not 4096 bytes")
    strings = [x for t in tracks for x in t[14]] + [n[4] for n in nodes]
    blob, spans = _blob(strings)
    arr = (TbTrack * max(1, len(tracks)))()
    for i, t in enumerate(tracks):
        c = arr[i]
        (c.id, c.art, c.size, c.samplerate, c.bitrate, c.track_no, c.disc_no, c.plays, c.year, c.color,
         c.rating, c.ftype) = (_u32(v) for v in t[:12])
        c.bpm, c.duration = float(t[12]), float(t[13])
        if not math.isfinite(c.bpm) or not math.isfinite(c.duration):
            raise ValueError("Native track timing must be finite")
        for k in range(14):
            c.off[k], c.len[k] = spans[i * 14 + k]
    base = len(tracks) * 14
    narr = (TbNode * max(1, len(nodes)))()
    for i, n in enumerate(nodes):
        c = narr[i]
        c.parent, c.sort, c.id, c.folder = (_u32(v) for v in n[:4])
        c.off, c.len = spans[base + i]
    earr = (TbEntry * max(1, len(entries)))()
    for i, e in enumerate(entries):
        earr[i].pos, earr[i].tid, earr[i].me = (_u32(v) for v in e)
    u8p = ctypes.POINTER(ctypes.c_uint8)
    stat = (u8p * N_TABLES)()
    keep = []
    for t, page in static.items():
        buf = ctypes.create_string_buffer(page, PAGE)
        keep.append(buf)
        stat[t] = ctypes.cast(buf, u8p)
    day = today.encode("utf-8")
    args = (arr, len(tracks), blob, day, len(day), narr, len(nodes), earr, len(entries), stat)
    size = LIB.tb_pdb_write(*args, None, 0)
    if size == 0:
        raise ValueError("a row does not fit in a page")
    if size < 0:
        return None
    out = ctypes.create_string_buffer(_output_size(size))
    if LIB.tb_pdb_write(*args, out, size) != size:
        raise RuntimeError("native pdb write changed its size")
    return out.raw


def anlz_build(path: str, bpm: float, duration: float, anchor: float, frames: int, hot: list, mem: list,
               waves: list) -> tuple[bytes, bytes] | None:
    """ANLZ0000.DAT and .EXT of one track. hot / mem: (hotcue, start, length, stripped name, colour id, rgb);
    waves: the detail, 400, 100 and 1200 column Bands. None without the library."""
    if LIB is None:
        return None
    if len(waves) != 4:
        raise ValueError("Native ANLZ requires exactly four waveforms")
    if not all(math.isfinite(value) for value in (bpm, duration, anchor)):
        raise ValueError("Native ANLZ timing must be finite")
    raw = path.encode("utf-8")
    for count in (len(raw), len(hot), len(mem)):
        _u32(count)
    blob, spans = _blob([c[3] for c in hot + mem])

    def cues(lst, first):
        arr = (TbCue * max(1, len(lst)))()
        for i, c in enumerate(lst):
            arr[i].hotcue, arr[i].start, arr[i].length = int(c[0]), float(c[1]), float(c[2])
            if (not -0x80000000 <= int(c[0]) <= 0x7fffffff
                    or not math.isfinite(arr[i].start) or not math.isfinite(arr[i].length)):
                raise ValueError("Native cue values are out of range")
            arr[i].name_off, arr[i].name_len = spans[first + i]
            arr[i].color_id, arr[i].rgb = _u32(c[4]), _u32(c[5])
        return arr

    harr, marr = cues(hot, 0), cues(mem, len(hot))
    keep, tw = [], []
    for b in waves:
        low, mid, high = (_samples(v) for v in (b.low, b.mid, b.high))
        if len(low) != len(mid) or len(low) != len(high):
            raise ValueError("Native waveform bands must have matching lengths")
        keep += [low, mid, high]
        tw.append(TbWave(low.ctypes.data, mid.ctypes.data, high.ctypes.data, len(low)))
    sizes = (ctypes.c_int64 * 2)()
    args = (raw, len(raw), float(bpm), float(duration), float(anchor), _u32(frames), harr, len(hot), marr,
            len(mem), blob, *[ctypes.byref(w) for w in tw])
    if LIB.tb_anlz_build(*args, None, 0, None, 0, sizes) != 0:
        return None
    dat, ext = (ctypes.create_string_buffer(_output_size(size)) for size in sizes)
    if LIB.tb_anlz_build(*args, dat, sizes[0], ext, sizes[1], sizes) != 0:
        return None
    return dat.raw, ext.raw
