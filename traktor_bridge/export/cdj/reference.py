# Benoit Saint-Moulin
# Traktor Bridge : the player files a CDJ key holds next to the database, written by code

"""A key needs a few files besides the tracks: the player settings (MYSETTING, MYSETTING2,
DJMMYSETTING, DEVSETTING) and four export.pdb tables holding the browse menus and a short
history. Nothing of it is copied from a Pioneer file: the settings follow the layout the
open source projects pyrekordbox and rekordcrate document (header, one byte per setting,
CRC16), the tables follow the DeviceSQL row layout of devicesql.py, and every value is
written here with neutral defaults."""

from __future__ import annotations

import binascii
import os
import struct
import time
from functools import lru_cache

from ..manifest import write_atomic
from . import devicesql as ds

SETTINGS = ("MYSETTING.DAT", "MYSETTING2.DAT", "DJMMYSETTING.DAT", "DEVSETTING.DAT")

# export.pdb tables written here: browse columns, two menu tables, history
PAGES = {16: "columns", 17: "t17", 18: "t18", 19: "history"}


def names() -> list[str]:
    return list(SETTINGS) + [f"{n}.page" for n in PAGES.values()]


# ============================================================
# Settings files
# ============================================================

MAGIC_PLAYER = bytes.fromhex("7856341202000000")
MAGIC_MIXER = bytes.fromhex("785634120100000020000000")
MAGIC_DEV = bytes.fromhex("7856341201000000")

# byte position in the body (1 based, as in the format notes): value. Every setting is an
# enum counted from 0x80.
MYSETTING = {
    9: 0x81,   # on air display: on
    10: 0x83,  # LCD brightness: three
    11: 0x81,  # quantize: on
    12: 0x88,  # auto cue level: memory
    13: 0x80,  # language: english
    14: 0x01,
    15: 0x82,  # jog ring brightness: bright
    16: 0x81,  # jog ring indicator: on
    17: 0x81,  # slip flashing: on
    18: 0x01, 19: 0x01, 20: 0x01,
    21: 0x82,  # disc slot illumination: bright
    22: 0x80,  # eject lock: unlock
    23: 0x80,  # sync: off
    24: 0x80,  # play mode: continue
    25: 0x80,  # quantize beat value: one
    26: 0x81,  # hot cue auto load: on
    27: 0x81,  # hot cue colour: on
    30: 0x80,  # needle lock: unlock
    33: 0x80,  # time mode: elapsed
    34: 0x80,  # jog mode: cdj
    35: 0x81,  # auto cue: on
    36: 0x80,  # master tempo: off
    37: 0x81,  # tempo range: ten
    38: 0x80,  # phase meter: type 1
}
MYSETTING2 = {
    1: 0x81,   # vinyl speed adjust: touch
    2: 0x80,   # jog display mode: auto
    3: 0x83,   # pad / button brightness: three
    4: 0x83,   # jog LCD brightness: three
    5: 0x81,   # waveform divisions: phrase
    11: 0x80,  # waveform: waveform
    12: 0x81,
    13: 0x85,  # beat jump beat value: sixteen
}
DJMMYSETTING = {
    13: 0x81,  # channel fader curve: linear
    14: 0x82,  # cross fader curve: fast cut
    15: 0x80,  # headphones: post EQ
    16: 0x80,  # headphones: stereo
    17: 0x81,  # beat FX quantize: on
    18: 0x80,  # mic low cut: off
    19: 0x80,  # talk over mode: advanced
    20: 0x82,  # talk over level: minus 12 dB
    21: 0x80,  # MIDI channel: one
    22: 0x80,  # MIDI button type: toggle
    23: 0x85,  # display brightness: five
    24: 0x82,  # indicator brightness: three
    25: 0x81,  # channel fader curve: smooth
}


def setting_file(brand: str, version: str, body: bytes, whole: bool = False) -> bytes:
    """Header (96 bytes of strings), body, then CRC16 XMODEM and two zero bytes. The mixer
    file computes the CRC over everything before it, the others over the body."""
    head = struct.pack("<I32s32s32sI", 0x60, brand.encode(), b"rekordbox", version.encode(), len(body))
    raw = head + body
    crc = binascii.crc_hqx(raw if whole else body, 0)
    return raw + struct.pack("<HH", crc, 0)


def _body(magic: bytes, fields: dict[int, int], size: int) -> bytes:
    b = bytearray(size)
    b[:len(magic)] = magic
    for pos, v in fields.items():
        b[pos - 1] = v
    return bytes(b)


def _settings() -> dict[str, bytes]:
    return {
        "MYSETTING.DAT": setting_file("PIONEER", "0.001", _body(MAGIC_PLAYER, MYSETTING, 40)),
        "MYSETTING2.DAT": setting_file("PIONEER", "0.001", _body(b"", MYSETTING2, 40)),
        "DJMMYSETTING.DAT": setting_file("PioneerDJ", "1.000", _body(MAGIC_MIXER, DJMMYSETTING, 52), True),
        "DEVSETTING.DAT": setting_file("PIONEER DJ", "7.2.11", MAGIC_DEV + b"\x01" * 9 + bytes(15)),
    }


# ============================================================
# export.pdb tables
# ============================================================

# browse columns: (id, display code, name)
COLUMNS = [
    (1, 0x80, "GENRE"), (2, 0x81, "ARTIST"), (3, 0x82, "ALBUM"), (4, 0x83, "TRACK"), (5, 0x85, "BPM"),
    (6, 0x86, "RATING"), (7, 0x87, "YEAR"), (8, 0x88, "REMIXER"), (9, 0x89, "LABEL"),
    (10, 0x8A, "ORIGINAL ARTIST"), (11, 0x8B, "KEY"), (12, 0x8D, "CUE"), (13, 0x8E, "COLOR"),
    (14, 0x92, "TIME"), (15, 0x93, "BITRATE"), (16, 0x94, "FILE NAME"), (17, 0x84, "PLAYLIST"),
    (18, 0x98, "HOT CUE BANK"), (19, 0x95, "HISTORY"), (20, 0x91, "SEARCH"), (21, 0x96, "COMMENTS"),
    (22, 0x8C, "DATE ADDED"), (23, 0x97, "DJ PLAY COUNT"), (24, 0x90, "FOLDER"), (25, 0xA1, "DEFAULT"),
    (26, 0xA2, "ALPHABET"), (27, 0xAA, "MATCHING"),
]

# menu tables: rows of four u16
T17 = [
    (1, 1, 0x163, 0), (5, 6, 0x105, 0), (6, 7, 0x163, 0), (7, 8, 0x163, 0), (8, 9, 0x163, 0),
    (9, 10, 0x163, 0), (10, 11, 0x163, 0), (13, 15, 0x163, 0), (14, 19, 0x104, 0), (15, 20, 0x106, 0),
    (16, 21, 0x163, 0), (18, 23, 0x163, 0), (2, 2, 2, 1), (3, 3, 3, 2), (4, 4, 1, 3), (11, 12, 0x63, 4),
    (17, 5, 0x63, 5), (19, 22, 0x63, 6), (20, 18, 0x63, 7), (27, 26, 0x263, 8), (24, 17, 0x63, 9),
    (22, 27, 0x63, 10),
]
T18 = [
    (1, 6, 1, 0), (21, 7, 1, 0), (14, 8, 1, 0), (8, 9, 1, 0), (9, 10, 1, 0), (10, 11, 1, 0),
    (15, 13, 1, 0), (13, 15, 1, 0), (23, 16, 1, 0), (22, 17, 1, 0), (25, 0, 0x100, 0),
    (26, 1, 0x200, 0), (2, 2, 0x300, 0), (3, 3, 0x400, 0), (5, 4, 0x500, 0), (6, 5, 0x600, 0),
    (11, 12, 0x700, 0),
]
HISTORY_ROWS = 4
HISTORY_WRAP = bytes.fromhex("191e0b31303030") + b"\x03"


def _columns() -> list[bytes]:
    rows = []
    for ident, code, name in COLUMNS:
        raw = ("\ufffa" + name + "\ufffb").encode("utf-16-le")
        r = ds.Row(struct.pack("<HHBHB", ident, code, 0x90, len(raw) + 4, 0) + raw)
        rows.append(r.done())
    return rows


def _quads(table) -> list[bytes]:
    return [struct.pack("<4H", *t) for t in table]


def _history(day: str) -> list[bytes]:
    rows = []
    for i in range(HISTORY_ROWS):
        r = bytearray(40)
        struct.pack_into("<HHH", r, 0, 0x280, 0, i)
        s = ds.dstr(day) + HISTORY_WRAP
        r[12:12 + len(s)] = s
        rows.append(bytes(r))
    return rows


def _pages(day: str) -> dict[int, bytes]:
    out = {16: ds.data_page(0, 16, 0, 0, _columns(), False),
           17: ds.data_page(0, 17, 0, 0, _quads(T17), False),
           18: ds.data_page(0, 18, 0, 0, _quads(T18), False)}
    h = bytearray(ds.data_page(0, 19, 0, 0, _history(day), True))
    # a rekordbox history page counts its rows in two parts, and keeps two of the four masks
    h[0x18:0x1b] = bytes((4, 0x20, 0))
    struct.pack_into("<HH", h, 0x20, 2, 2)
    struct.pack_into("<HH", h, ds.PAGE - 4, 0x0008, 0x000C)
    out[19] = bytes(h)
    return out


# ============================================================
# Public
# ============================================================

@lru_cache(maxsize=1)
def files() -> dict[str, bytes]:
    day = time.strftime("%Y-%m-%d")
    f = _settings()
    for kind, pg in _pages(day).items():
        f[f"{PAGES[kind]}.page"] = pg
    return f


def pages() -> dict[int, bytes]:
    f = files()
    return {kind: f[f"{name}.page"] for kind, name in PAGES.items()}


def copy_settings(pioneer_dir: str):
    f = files()
    for n in SETTINGS:
        dst = os.path.join(pioneer_dir, n)
        if not os.path.exists(dst):
            write_atomic(dst, f[n])
