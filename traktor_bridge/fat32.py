# Benoit Saint-Moulin
# Traktor Bridge : MBR + FAT32 writer for a whole drive (what the CDJ / XDJ players read)

"""Writes a blank MBR disk with one FAT32 partition on anything that takes sector writes:
a raw drive (\\\\.\\PhysicalDriveN, /dev/sdX) or an image file. No size limit of the
Windows formatter (32 GB), the 32 KB clusters Windows uses above that are the default.

Whatever was on the drive (GPT, APFS, HFS+, ext4, NTFS...) is wiped: the first and last
8 MiB are zeroed, and every sector of the FAT area is written, so no old signature survives."""

from __future__ import annotations

import os
import random
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass

MIB = 1 << 20
RESERVED = 32               # sectors before the first FAT, 6 + 3 used by the backup boot sector
FATS = 2
MIN_CLUSTERS = 65525        # below that a volume is FAT16 by definition
MAX_CLUSTERS = 0x0FFFFFF5
MAX_SECTORS = 0xFFFFFFFF    # an MBR partition is 32 bit
WIPE = 8 * MIB
CHUNK = 4 * MIB
LABEL_BAD = set('*?.,;:/\\|+=<>[]"')

# code at 0x5A of the boot sector: prints the message through the BIOS, then halts
_MSG = b"\r\nThis is not a bootable disk.\r\n\x00"
_CODE = bytes([0xFA, 0x31, 0xC0, 0x8E, 0xD0, 0xBC, 0x00, 0x7C, 0xFB, 0x8E, 0xD8,
               0xBE, 0x79, 0x7C,                                     # mov si, message
               0xAC, 0x08, 0xC0, 0x74, 0x09, 0xB4, 0x0E, 0xBB, 0x07, 0x00, 0xCD, 0x10, 0xEB, 0xF2,
               0xF4, 0xEB, 0xFD]) + _MSG

Progress = Callable[[int, str], None]


def clean_label(label: str) -> str:
    """Upper case, no character FAT refuses, 11 characters at most."""
    out = "".join("_" if c in LABEL_BAD or ord(c) < 32 or ord(c) > 126 else c for c in label.upper())
    return out.strip()[:11]


def cluster_bytes(size: int) -> int:
    """The default of Windows for FAT32: 4 KB up to 8 GB, then 8, 16 and 32 KB."""
    gib = size / (1 << 30)
    for limit, c in ((8, 4096), (16, 8192), (32, 16384)):
        if gib <= limit:
            return c
    return 32768


@dataclass
class Layout:
    bps: int            # bytes per sector
    spc: int            # sectors per cluster
    start: int          # first sector of the partition on the disk
    total: int          # sectors of the partition
    reserved: int
    fat: int            # sectors of one FAT
    clusters: int
    volid: int
    label: str

    @property
    def data(self) -> int:
        return self.reserved + FATS * self.fat

    @property
    def cluster_size(self) -> int:
        return self.spc * self.bps


def layout(size: int, bps: int = 512, label: str = "", cluster: int = 0, volid: int | None = None) -> Layout:
    """The geometry for a drive of size bytes. The data area starts on a cluster boundary
    and the partition on 1 MiB, so flash pages and clusters line up."""
    start = MIB // bps
    total = min(size // bps - start, MAX_SECTORS - start)
    if total <= 0:
        raise ValueError("The drive is too small")
    spc = max(1, (cluster or cluster_bytes(size)) // bps)
    while spc >= 1:
        fat = 1
        while True:
            reserved = RESERVED + (-(RESERVED + FATS * fat)) % spc
            clusters = (total - reserved - FATS * fat) // spc
            need = -(-(clusters + 2) * 4 // bps)
            if need <= fat:
                break
            fat = need
        if clusters > MAX_CLUSTERS:
            if spc >= 128:
                raise ValueError("The drive is too big for FAT32")
            spc *= 2
            continue
        if clusters >= MIN_CLUSTERS:
            return Layout(bps, spc, start, total, reserved, fat, clusters,
                          random.getrandbits(32) if volid is None else volid, clean_label(label))
        spc //= 2
    raise ValueError("The drive is too small for FAT32 (about 34 MB at least)")


def dos_stamp(t: float | None = None) -> tuple[int, int]:
    n = time.localtime(t)
    return (((max(n.tm_year, 1980) - 1980) << 9) | (n.tm_mon << 5) | n.tm_mday,
            (n.tm_hour << 11) | (n.tm_min << 5) | (n.tm_sec // 2))


def boot_sector(L: Layout) -> bytes:
    b = bytearray(L.bps)
    b[0:3] = b"\xEB\x58\x90"
    b[3:11] = b"MSDOS5.0"
    # bytes/sector, sectors/cluster, reserved, FATs, root entries, sectors16, media, FAT16 size,
    # sectors/track, heads, hidden sectors (before the partition), sectors32
    struct.pack_into("<HBHBHHBHHHLL", b, 11, L.bps, L.spc, L.reserved, FATS, 0, 0, 0xF8, 0, 63, 255, L.start, L.total)
    # FAT size, flags, version, root cluster, FSInfo, backup boot, 12 reserved, drive, 0, signature, id, label, type
    struct.pack_into("<LHHLHH12sBBBL11s8s", b, 36, L.fat, 0, 0, 2, 1, 6, b"", 0x80, 0, 0x29, L.volid,
                     (L.label or "NO NAME").ljust(11).encode("ascii"), b"FAT32   ")
    b[0x5A:0x5A + len(_CODE)] = _CODE
    b[510:512] = b"\x55\xAA"
    return bytes(b)


def fsinfo(L: Layout) -> bytes:
    b = bytearray(L.bps)
    struct.pack_into("<L", b, 0, 0x41615252)
    struct.pack_into("<LLL", b, 484, 0x61417272, L.clusters - 1, 3)      # the root directory has cluster 2
    b[508:512] = b"\x00\x00\x55\xAA"
    return bytes(b)


def tail_sector(L: Layout) -> bytes:
    b = bytearray(L.bps)
    b[508:512] = b"\x00\x00\x55\xAA"
    return bytes(b)


def mbr(L: Layout) -> bytes:
    b = bytearray(L.bps)
    struct.pack_into("<L", b, 440, random.getrandbits(32))

    def chs(lba: int) -> bytes:
        c, r = divmod(lba, 255 * 63)
        if c > 1023:
            return b"\xFE\xFF\xFF"
        h, s = divmod(r, 63)
        return bytes([h, ((c >> 2) & 0xC0) | (s + 1), c & 0xFF])

    # not active, type 0x0C (FAT32 with LBA)
    b[446:462] = b"\x00" + chs(L.start) + b"\x0C" + chs(L.start + L.total - 1) + struct.pack("<LL", L.start, L.total)
    b[510:512] = b"\x55\xAA"
    return bytes(b)


def root_entry(L: Layout) -> bytes:
    """The volume label entry of the root directory, the way Windows writes it."""
    if not L.label:
        return b""
    d, t = dos_stamp()
    return struct.pack("<11sBBBHHHHHHHL", L.label.ljust(11).encode("ascii"), 0x08, 0, 0, t, d, d, 0, t, d, 0, 0)


class RawDevice:
    """Sector writes on a raw drive or an image. Offsets and lengths are sector multiples,
    Windows refuses anything else on a physical drive."""

    def __init__(self, path: str, size: int = 0):
        self.f = open(path, "r+b", buffering=0)  # noqa: SIM115
        self.size = size

    def write(self, offset: int, data: bytes):
        self.f.seek(offset)
        n = self.f.write(data)
        if n != len(data):
            raise OSError(f"Short write at {offset}: {n} of {len(data)} bytes")

    def read(self, offset: int, n: int) -> bytes:
        self.f.seek(offset)
        return self.f.read(n)

    def flush(self):
        try:
            os.fsync(self.f.fileno())
        except OSError:
            pass

    def close(self):
        self.f.close()


def format_disk(dev, size: int, bps: int = 512, label: str = "", cluster: int = 0,
                progress: Progress | None = None) -> Layout:
    """Wipes the drive of size bytes and writes the partition table and the FAT32 file system.
    The partition table comes last: a drive interrupted before is blank, never half formatted."""
    cb = progress or (lambda pct, msg: None)
    L = layout(size, bps, label, cluster)
    sec = L.bps
    wipe = min(WIPE, size // 2) // sec * sec
    fats = FATS * L.fat * sec
    todo = 2 * wipe + fats + L.reserved * sec
    done = 0
    zero = bytes(min(CHUNK, max(wipe, fats, sec)))

    def blank(offset: int, length: int, what: str):
        nonlocal done
        end = offset + length
        while offset < end:
            n = min(len(zero), end - offset)
            dev.write(offset, zero[:n])
            offset += n
            done += n
            cb(min(95, 100 * done // todo), what)

    blank(0, wipe, "Erasing the start of the drive")
    blank(size // sec * sec - wipe, wipe, "Erasing the end of the drive")
    base = L.start * sec
    blank(base, L.reserved * sec, "Writing the boot area")
    for at, data in ((0, boot_sector(L)), (1, fsinfo(L)), (2, tail_sector(L)),
                     (6, boot_sector(L)), (7, fsinfo(L)), (8, tail_sector(L))):
        dev.write(base + at * sec, data)
    for i in range(FATS):
        blank(base + (L.reserved + i * L.fat) * sec, L.fat * sec, "Writing the file allocation tables")
    # media, end of chain, and the root directory cluster closed
    entries = struct.pack("<LLL", 0x0FFFFFF8, 0x0FFFFFFF, 0x0FFFFFFF).ljust(sec, b"\x00")
    for i in range(FATS):
        dev.write(base + (L.reserved + i * L.fat) * sec, entries)
    root = bytearray(L.cluster_size)
    if L.label:
        root[:32] = root_entry(L)
    dev.write(base + L.data * sec, bytes(root))
    cb(97, "Writing the partition table")
    table = mbr(L)
    dev.write(0, table)
    dev.flush()
    if dev.read(0, sec) != table or dev.read(base, sec) != boot_sector(L):
        raise OSError("The drive does not hold what was written")
    cb(100, "Formatted")
    return L
