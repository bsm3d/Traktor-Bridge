# Benoit Saint-Moulin
# Traktor Bridge : export.pdb reader, used by the validator and the oracle tests

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .devicesql import HEAD, PAGE


@dataclass
class Page:
    idx: int
    kind: int
    nxt: int
    seq: int
    flags: int
    free: int
    used: int
    rows: list[bytes] = field(default_factory=list)     # live rows only


@dataclass
class Pdb:
    next_unused: int
    seq: int
    tables: dict[int, tuple[int, int, int]]             # kind -> (empty_candidate, first, last)
    pages: dict[int, list[Page]]                        # kind -> data pages in chain order


def dstr(buf: bytes, off: int) -> str:
    f = buf[off]
    if f & 1:
        n = (f >> 1) - 1
        return buf[off + 1:off + 1 + n].decode("ascii", "replace")
    size = struct.unpack_from("<H", buf, off + 1)[0]
    raw = buf[off + 4:off + size]
    return raw.decode("utf-16-le" if f == 0x90 else "ascii", "replace")


def read_page(data: bytes, idx: int) -> Page:
    b = data[idx * PAGE:(idx + 1) * PAGE]
    _, pidx, kind, nxt, seq = struct.unpack_from("<5I", b, 0)
    packed = int.from_bytes(b[0x18:0x1b], "little")
    free, used = struct.unpack_from("<HH", b, 0x1c)
    pg = Page(pidx, kind, nxt, seq, b[0x1b], free, used)
    if b[0x1b] & 0x40:
        return pg

    n = packed & 0x1FFF
    offs = []
    for g in range(0, n, 16):
        base = PAGE - (g // 16) * 36
        present = struct.unpack_from("<H", b, base - 4)[0]
        for k in range(min(16, n - g)):
            o = struct.unpack_from("<H", b, base - 6 - 2 * k)[0]
            offs.append((o, bool(present >> k & 1)))
    ends = sorted({o for o, _ in offs} | {used})
    for o, live in offs:
        if live:
            end = next((e for e in ends if e > o), used)
            pg.rows.append(b[HEAD + o:HEAD + end])
    return pg


def read(data: bytes) -> Pdb:
    _, _, ntab, next_unused, _, seq, _ = struct.unpack_from("<7I", data, 0)
    tables, pages = {}, {}
    for i in range(ntab):
        kind, ec, first, last = struct.unpack_from("<4I", data, 28 + 16 * i)
        tables[kind] = (ec, first, last)
        chain = []
        p, seen = first, set()
        # a damaged file can point back to a page already read, never loop on it
        while p * PAGE < len(data) and p not in seen:
            seen.add(p)
            pg = read_page(data, p)
            if not pg.flags & 0x40:
                chain.append(pg)
            if p == last:
                break
            p = pg.nxt
        pages[kind] = chain
    return Pdb(next_unused, seq, tables, pages)


def rows(pdb: Pdb, kind: int) -> list[bytes]:
    return [r for pg in pdb.pages.get(kind, []) for r in pg.rows]


def track_strings(row: bytes) -> list[str]:
    return [dstr(row, o) for o in struct.unpack_from("<21H", row, 0x5e)]
