# Benoit Saint-Moulin
# Traktor Bridge : ANLZ0000.DAT / .EXT writer (beat grid, cues, waveforms)

"""Section order and headers follow a rekordbox 6 export. Big endian everywhere.
PQT2, PSSI and the .2EX file are left out, they only matter to the CDJ-3000."""

from __future__ import annotations

import math
import struct

import numpy as np

from ...model import Cue, Track
from ...sources.rbxml import RB_COLORS
from ..rbxml import HOT_RGB
from . import native
from .analysis import Audio, Bands


def anlz_dir(usb_path: str, used: set[str] | None = None) -> str:
    """Folder rekordbox derives from the track path, the players look there first."""
    h = 0
    for c in usb_path:
        u = ord(c) & 0xFFFF
        h = ((h * 0x5BC9 + u) * 0x93B5 + u) & 0xFFFFFFFF
    for offset in range(200003):
        r = (h + offset) % 200003
        p = (r & 1) | (r >> 1 & 2) | (r >> 4 & 4) | (r >> 4 & 8) | (r >> 5 & 0x10) | (r >> 8 & 0x20) | (r >> 10 & 0x40)
        path = f"/PIONEER/USBANLZ/P{p:03X}/{r:08X}"
        if used is None:
            return path
        if path not in used:
            used.add(path)
            return path
    raise ValueError("Too many tracks: Pioneer analysis directory allocation is exhausted")


def tag(name: bytes, head: bytes, data: bytes = b"") -> bytes:
    return name + struct.pack(">II", 12 + len(head), 12 + len(head) + len(data)) + head + data


def pmai(sections: list[bytes]) -> bytes:
    body = b"".join(sections)
    return b"PMAI" + struct.pack(">IIIIII", 28, 28 + len(body), 1, 0x10000, 0x10000, 0) + body


# ============================================================
# Sections
# ============================================================

def ppth(usb_path: str) -> bytes:
    raw = usb_path.encode("utf-16-be") + b"\0\0"
    return tag(b"PPTH", struct.pack(">I", len(raw)), raw)


def pvbr(frames: int) -> bytes:
    # 400 byte offsets for VBR seeking, zero is fine, the player rebuilds them
    return tag(b"PVBR", struct.pack(">I", 0), bytes(1600) + struct.pack(">I", frames))


def beats(t: Track) -> list[tuple[int, int]]:
    if t.bpm <= 0 or t.grid is None or not t.duration:
        return []
    step = 60000 / t.bpm
    anchor = t.grid or 0.0
    back = math.floor(anchor / step)
    first = anchor - back * step
    out = []
    i = 0
    while first + i * step < t.duration * 1000:
        out.append((((i - back) % 4) + 1, round(first + i * step)))
        i += 1
    return out


def pqtz(t: Track) -> bytes:
    if t.grid is not None and t.bpm > 655.35:
        raise ValueError("CDJ beat grids support at most 655.35 BPM")
    tempo = round(t.bpm * 100)
    bs = beats(t)
    data = b"".join(struct.pack(">HHI", n, tempo, ms) for n, ms in bs)
    return tag(b"PQTZ", struct.pack(">III", 0, 0x80000, len(bs)), data)


def shade(b: Bands):
    """Height 0-31 and whiteness 0-7 per column, brighter when the highs dominate."""
    top = np.maximum(np.maximum(b.low, b.mid), b.high)
    ratio = np.divide(b.high, top, out=np.ones_like(top), where=top > 0.01)
    return np.rint(31 * top).astype(np.uint8), np.rint(7 * ratio).astype(np.uint8)


def mono(b: Bands) -> bytes:
    h, w = shade(b)
    return (w << 5 | h).astype(np.uint8).tobytes()


def pwav(b: Bands) -> bytes:
    return tag(b"PWAV", struct.pack(">II", len(b), 0x10000), mono(b))


def pwv2(b: Bands) -> bytes:
    top = np.maximum(np.maximum(b.low, b.mid), b.high)
    return tag(b"PWV2", struct.pack(">II", len(b), 0x10000), np.rint(15 * top).astype(np.uint8).tobytes())


def pwv3(b: Bands) -> bytes:
    return tag(b"PWV3", struct.pack(">IIHH", 1, len(b), 150, 0), mono(b))


def pwv5(b: Bands) -> bytes:
    top = np.maximum(np.maximum(b.low, b.mid), b.high)
    safe = np.where(top > 0.01, top, 1.0)
    on = top > 0.01
    r, g, bl = (np.where(on, np.rint(7 * v / safe), 0).astype(np.uint16) for v in (b.low, b.mid, b.high))
    word = r << 13 | g << 10 | bl << 7 | np.rint(31 * top).astype(np.uint16) << 2
    return tag(b"PWV5", struct.pack(">IIHH", 2, len(b), 150, 0x0305), word.astype(">u2").tobytes())


def pwv4(b: Bands) -> bytes:
    lo, mi, hi = (np.rint(127 * v).astype(np.uint8) for v in (b.low, b.mid, b.high))
    top = np.maximum(np.maximum(lo, mi), hi)
    # the players draw from bytes 3-5 (red, green, blue), 0-2 get the overall level
    cols = np.stack([top, top, top, lo, mi, hi], axis=1)
    return tag(b"PWV4", struct.pack(">III", 6, len(b), 0), cols.tobytes())


# ---- cues

def pcpt(c: Cue) -> bytes:
    loop = c.is_loop
    end = round(c.start + c.length) if loop else 0xFFFFFFFF
    return (b"PCPT" + struct.pack(">IIIIIHHBBHII", 28, 56, c.hotcue + 1 if c.hotcue >= 0 else 0, 0,
                                  0x10000, 0xFFFF, 0xFFFF, 2 if loop else 1, 0, 1000,
                                  round(max(0.0, c.start)), end) + bytes(16))


# The hot cue colours of the 4x4 palette grids, codes 1-62 (0 = the old default, green).
# A player shows the code, and ignores a hot cue colour it does not find here.
HOT_PALETTE = [
    0x305aff, 0x5073ff, 0x508cff, 0x50a0ff, 0x50b4ff, 0x50b0f2, 0x50aee8, 0x45acdb, 0x00e0ff,
    0x19daf0, 0x32d2e6, 0x21b4b9, 0x20aaa0, 0x1fa392, 0x19a08c, 0x14a584, 0x14aa7d, 0x10b176,
    0x30d26e, 0x37de5a, 0x3ceb50, 0x28e214, 0x7dc13d, 0x8cc832, 0x9bd723, 0xa5e116, 0xa5dc0a,
    0xaad208, 0xb4c805, 0xb4be04, 0xbab404, 0xc3af04, 0xe1aa00, 0xffa000, 0xff9600, 0xff8c00,
    0xff7500, 0xe0641b, 0xe0461e, 0xe0301e, 0xe02823, 0xe62828, 0xff376f, 0xff2d6f, 0xff127b,
    0xf51e8c, 0xeb2da0, 0xe637b4, 0xde44cf, 0xde448d, 0xe630b4, 0xe619dc, 0xe600ff, 0xdc00ff,
    0xcc00ff, 0xb432ff, 0xb93cff, 0xc542ff, 0xaa5aff, 0xaa72ff, 0x8272ff, 0x6473ff
]


def split_rgb(v: int) -> tuple[int, int, int]:
    return v >> 16 & 255, v >> 8 & 255, v & 255


def nearest(rgb: tuple[int, int, int], palette) -> int:
    return min(range(len(palette)), key=lambda i: sum((a - b) ** 2 for a, b in zip(rgb, split_rgb(palette[i]), strict=True)))


def hot_color(c: Cue) -> tuple[int, int]:
    """(palette code, 0xRRGGBB) of a hot cue: the colour read from the source (#RRGGBB) or the
    one of its slot, as the editor draws it, goes to the nearest palette colour."""
    rgb = HOT_RGB[c.hotcue % 8]
    col = c.color.lstrip("#")
    if len(col) in (6, 8):
        try:
            rgb = split_rgb(int(col[-6:], 16))
        except ValueError:
            pass
    near = nearest(rgb, HOT_PALETTE)
    return near + 1, HOT_PALETTE[near]


def cue_color(c: Cue) -> tuple[int, int]:
    """(rekordbox colour id, colour word) of a cue, (0, 0) for a memory cue. The word is
    0xRRGGBB with the hot cue palette code above it (bits 24-31), the native core splits it."""
    if c.hotcue < 0:
        return 0, 0
    code, rgb = hot_color(c)
    near = nearest(split_rgb(rgb), [int(h, 16) for h in RB_COLORS])
    return near + 1, code << 24 | rgb


def pcp2(c: Cue) -> bytes:
    loop = c.is_loop
    name = c.name.strip()
    com = name.encode("utf-16-be") + b"\0\0" if name else b""
    size = 0x2C + len(com) + 4
    cid, word = cue_color(c)
    code, rgb = word >> 24, word & 0xFFFFFF
    return (b"PCP2" + struct.pack(">IIIBBHII", 16, size, c.hotcue + 1 if c.hotcue >= 0 else 0,
                                  2 if loop else 1, 0, 1000, round(max(0.0, c.start)),
                                  round(c.start + c.length) if loop else 0)
            + bytes((cid,)) + bytes(7) + struct.pack(">HHI", 0, 0, len(com)) + com
            + bytes((code, rgb >> 16, rgb >> 8 & 255, rgb & 255)))


def cue_lists(t: Track, ext: bool) -> list[bytes]:
    out = []
    for kind, cues in ((1, t.hot_cues()[:8]), (0, t.memory_cues())):
        if ext:
            out.append(tag(b"PCO2", struct.pack(">IHH", kind, len(cues), 0), b"".join(map(pcp2, cues))))
        else:
            out.append(tag(b"PCOB", struct.pack(">IHHI", kind, 0, len(cues), 0xFFFFFFFF),
                           b"".join(map(pcpt, cues))))
    return out


# ============================================================
# Files
# ============================================================

def build(t: Track, usb_path: str, audio: Audio) -> tuple[bytes, bytes]:
    """The two files of a track. The native core writes them when it is there, build_py is
    the reference."""
    if t.grid is not None and t.bpm > 655.35:
        raise ValueError("CDJ beat grids support at most 655.35 BPM")
    if native.available():
        detail = audio.at(len(audio.fine[0]) if audio.ok else round(t.duration * 150))

        def cue(c: Cue):
            return c.hotcue, c.start, c.length, c.name.strip(), *cue_color(c)

        done = native.anlz_build(usb_path, t.bpm if t.grid is not None else 0.0,
                                 t.duration, t.grid or 0.0, detail.frames,
                                 [cue(c) for c in t.hot_cues()[:8]], [cue(c) for c in t.memory_cues()],
                                 [detail, audio.at(400), audio.at(100), audio.at(1200)])
        if done is not None:
            return done
    return build_py(t, usb_path, audio)


def build_py(t: Track, usb_path: str, audio: Audio) -> tuple[bytes, bytes]:
    detail = audio.at(len(audio.fine[0]) if audio.ok else round(t.duration * 150))
    dat = pmai([ppth(usb_path), pvbr(detail.frames), pqtz(t), pwav(audio.at(400)), pwv2(audio.at(100)),
                *cue_lists(t, False)])
    ext = pmai([ppth(usb_path), pwv3(detail), *cue_lists(t, False), *cue_lists(t, True),
                pwv5(detail), pwv4(audio.at(1200))])
    return dat, ext
