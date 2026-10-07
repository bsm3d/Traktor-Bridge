# Benoit Saint-Moulin
# Traktor Bridge : DeviceSQL file layout (export.pdb pages, rows, strings)

"""Layout observed on a rekordbox 6 USB export, not from the public docs alone:
every table owns an index page (flags 0x64) followed by its data pages, the header
sequence is above every page sequence, and free_size is exact. The CDJ-2000NXS2
browses a file that breaks those rules and then locks up on the next screen."""

from __future__ import annotations

import struct

from . import native

PAGE = 4096
HEAD = 0x28
HEAP = PAGE - HEAD
N_TABLES = 20

# tables whose index page lists its data pages, their data pages carry flag 0x34
INDEXED = (0, 19)


# ============================================================
# Strings
# ============================================================

def dstr(s: str) -> bytes:
    if not s:
        return b"\x03"
    if s.isascii():
        raw = s.encode("ascii")
        if len(raw) <= 126:
            return bytes([((len(raw) + 1) << 1) | 1]) + raw
        return struct.pack("<BHB", 0x40, len(raw) + 4, 0) + raw
    raw = s.encode("utf-16-le")
    return struct.pack("<BHB", 0x90, len(raw) + 4, 0) + raw


def is_long(b: bytes) -> bool:
    return b[0] in (0x40, 0x90)


class Row:
    """A fixed part followed by strings. Long strings sit on a 4 byte boundary
    inside the row, rekordbox pads before them and the players expect it."""

    def __init__(self, fixed: bytes):
        self.buf = bytearray(fixed)

    def put(self, s: str) -> int:
        b = dstr(s)
        if is_long(b):
            while len(self.buf) % 4:
                self.buf.append(0)
        pos = len(self.buf)
        self.buf += b
        return pos

    def u8(self, off: int, v: int):
        self.buf[off] = v

    def u16(self, off: int, v: int):
        struct.pack_into("<H", self.buf, off, v)

    def done(self) -> bytes:
        while len(self.buf) % 4:
            self.buf.append(0)
        return bytes(self.buf)


# ============================================================
# Pages
# ============================================================

def index_size(n: int) -> int:
    """Bytes used at the page end by the row index: groups of 16 offsets plus
    two u16 masks, the last group only as long as it needs."""
    full, rest = divmod(n, 16)
    return full * 36 + (4 + 2 * rest if rest else 0)


def pack_rows(rows: list[bytes]) -> list[list[bytes]]:
    pages, cur, used = [], [], 0
    for r in rows:
        if len(r) + index_size(1) > HEAP:
            raise ValueError(f"row of {len(r)} bytes does not fit in a page")
        if cur and used + len(r) + index_size(len(cur) + 1) > HEAP:
            pages.append(cur)
            cur, used = [], 0
        cur.append(r)
        used += len(r)
    if cur:
        pages.append(cur)
    return pages


def data_page(idx: int, kind: int, nxt: int, seq: int, rows: list[bytes], shift: bool) -> bytes:
    buf = bytearray(PAGE)
    pos = 0
    offs = []
    for i, r in enumerate(rows):
        buf[HEAD + pos:HEAD + pos + len(r)] = r
        if shift:
            struct.pack_into("<H", buf, HEAD + pos + 2, i * 0x20)
        offs.append(pos)
        pos += len(r)

    n = len(rows)
    for g in range(0, n, 16):
        base = PAGE - (g // 16) * 36
        grp = offs[g:g + 16]
        mask = (1 << len(grp)) - 1
        # present rows, then rows touched by the last write, same thing for a fresh file
        struct.pack_into("<HH", buf, base - 4, mask, mask)
        for k, o in enumerate(grp):
            struct.pack_into("<H", buf, base - 6 - 2 * k, o)

    packed = n | (n << 13)
    flags = 0x34 if kind in INDEXED else 0x24
    struct.pack_into("<IIIIII", buf, 0, 0, idx, kind, nxt, seq, 0)
    buf[0x18:0x1b] = packed.to_bytes(3, "little")
    buf[0x1b] = flags
    struct.pack_into("<HHHHHH", buf, 0x1c, HEAP - pos - index_size(n), pos, n, 0, 0, 0)
    return bytes(buf)


# entry slots of an index page, between its 20 byte head and 20 byte tail
INDEX_SLOTS = (PAGE - HEAD - 40) // 4


def index_page(idx: int, kind: int, nxt: int, seq: int, entries: list[int]) -> bytes:
    # a big table has more data pages than slots, the players find them through
    # the page chain anyway, so the list stops when the page is full
    entries = entries[:INDEX_SLOTS]
    buf = bytearray(PAGE)
    struct.pack_into("<IIIII", buf, 0, 0, idx, kind, nxt, seq)
    buf[0x1b] = 0x64
    struct.pack_into("<HHHHHH", buf, 0x1c, 0, 0, 0x1FFF, 0x1FFF, INDEX_SLOTS, 1 if entries else 0)
    struct.pack_into("<IIIIHH", buf, HEAD, idx, nxt, 0x03FFFFFF, 0, len(entries), 0x1FFF)
    pos = HEAD + 20
    for e in entries:
        struct.pack_into("<I", buf, pos, e)
        pos += 4
    while pos < PAGE - 20:
        buf[pos:pos + 4] = b"\xf8\xff\xff\x1f"
        pos += 4
    return bytes(buf)


def patch_page(page: bytes, idx: int, nxt: int, seq: int) -> bytes:
    buf = bytearray(page)
    struct.pack_into("<I", buf, 0x04, idx)
    struct.pack_into("<II", buf, 0x0c, nxt, seq)
    return bytes(buf)


# ============================================================
# File
# ============================================================

def build(tables: dict[int, list[bytes]], static: dict[int, bytes], shifted: set[int]) -> bytes:
    """The whole file. The C++ core does it when it is there, build_py is the reference
    it is tested against and the fallback."""
    return native.pdb_build(tables, static, shifted) or build_py(tables, static, shifted)


def build_py(tables: dict[int, list[bytes]], static: dict[int, bytes], shifted: set[int]) -> bytes:
    """tables: kind -> rows, static: kind -> a finished data page generated by reference.py.
    Index page of table t at 1+2t, its first data page at 2+2t, overflow pages after."""
    data: dict[int, list] = {}
    for t in range(N_TABLES):
        if t in static:
            data[t] = [static[t]]
        elif tables.get(t):
            data[t] = pack_rows(tables[t])

    last = 2 * N_TABLES
    numbers: dict[int, list[int]] = {}
    for t, pages in data.items():
        nums = [2 + 2 * t]
        for _ in pages[1:]:
            last += 1
            nums.append(last)
        numbers[t] = nums

    nxt_free = last + 1
    empty_cand = {}
    for t in range(N_TABLES):
        if t in data:
            empty_cand[t] = nxt_free
            nxt_free += 1
        else:
            empty_cand[t] = 2 + 2 * t

    out = [bytes(PAGE)] * (last + 1)
    seq = 1
    for t in range(N_TABLES):
        for i, pg in enumerate(data.get(t, [])):
            seq += 1
            nums = numbers[t]
            follow = nums[i + 1] if i + 1 < len(nums) else empty_cand[t]
            if t in static:
                out[nums[i]] = patch_page(pg, nums[i], follow, seq)
            else:
                out[nums[i]] = data_page(nums[i], t, follow, seq, pg, t in shifted)

    for t in range(N_TABLES):
        entries = [n << 3 for n in numbers[t]] if t in INDEXED and t in data else []
        s = seq + 1 if entries else 1
        out[1 + 2 * t] = index_page(1 + 2 * t, t, 2 + 2 * t, s, entries)
    seq += 2

    head = bytearray(PAGE)
    struct.pack_into("<7I", head, 0, 0, PAGE, N_TABLES, nxt_free, 5, seq, 0)
    for t in range(N_TABLES):
        lastpg = numbers[t][-1] if t in data else 1 + 2 * t
        struct.pack_into("<4I", head, 28 + 16 * t, t, empty_cand[t], 1 + 2 * t, lastpg)
    out[0] = bytes(head)
    return b"".join(out)
