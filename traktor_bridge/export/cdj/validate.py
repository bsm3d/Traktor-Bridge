"""Structural checks for files produced by this exporter, not arbitrary rekordbox versions."""

import os
import struct

from ..manifest import sha256_bytes, sha256_drive, write_atomic
from .devicesql import HEAD, N_TABLES, PAGE, index_size


def anlz(data: bytes, expected_path: str | None = None, extension: str | None = None):
    if (len(data) < 28 or data[:4] != b"PMAI"
            or struct.unpack_from(">II", data, 4) != (28, len(data))):
        raise ValueError("Invalid ANLZ file header or length")
    position = 28
    sections = set()
    while position < len(data):
        if position + 12 > len(data):
            raise ValueError("Truncated ANLZ section header")
        kind = data[position:position + 4]
        header, size = struct.unpack_from(">II", data, position + 4)
        if not 12 <= header <= size or position + size > len(data):
            raise ValueError(f"Invalid ANLZ section length: {kind!r}")
        section = data[position:position + size]
        if kind == b"PPTH":
            if header != 16:
                raise ValueError("Invalid ANLZ path header")
            length = struct.unpack_from(">I", section, 12)[0]
            raw = section[header:]
            if length != len(raw) or length < 2 or length % 2 or raw[-2:] != b"\0\0":
                raise ValueError("Invalid ANLZ path payload")
            path = raw[:-2].decode("utf-16-be")
            if expected_path is not None and path != expected_path:
                raise ValueError("ANLZ path does not match its exported track")
        elif kind == b"PQTZ":
            if header != 24 or size - header != struct.unpack_from(">I", section, 20)[0] * 8:
                raise ValueError("Invalid ANLZ beat-grid count")
        elif kind in (b"PWAV", b"PWV2", b"PWV3", b"PWV4", b"PWV5"):
            if header < 20:
                raise ValueError("Invalid ANLZ waveform header")
            width, count = ((1, struct.unpack_from(">I", section, 12)[0])
                            if kind in (b"PWAV", b"PWV2")
                            else struct.unpack_from(">II", section, 12))
            expected_width = {b"PWAV": 1, b"PWV2": 1, b"PWV3": 1, b"PWV4": 6, b"PWV5": 2}[kind]
            if width != expected_width or size - header != width * count:
                raise ValueError("Invalid ANLZ waveform count or width")
        elif kind == b"PVBR" and (header != 16 or size != 1620):
            raise ValueError("Invalid ANLZ VBR payload")
        elif kind in (b"PCOB", b"PCO2"):
            if header != (24 if kind == b"PCOB" else 20):
                raise ValueError("Invalid ANLZ cue-list header")
            count = struct.unpack_from(">H", section, 18 if kind == b"PCOB" else 16)[0]
            cursor = header
            for _ in range(count):
                if cursor + 12 > size:
                    raise ValueError("Truncated ANLZ cue")
                cue_header, cue_size = struct.unpack_from(">II", section, cursor + 4)
                if (section[cursor:cursor + 4] != (b"PCPT" if kind == b"PCOB" else b"PCP2")
                        or not 12 <= cue_header <= cue_size or cursor + cue_size > size):
                    raise ValueError("Invalid ANLZ cue length")
                cursor += cue_size
            if cursor != size:
                raise ValueError("ANLZ cue count does not match payload")
        sections.add(kind)
        position += size
    if b"PPTH" not in sections:
        raise ValueError("ANLZ has no track path")
    required = ({b"PVBR", b"PQTZ", b"PWAV", b"PWV2", b"PCOB"} if extension == "DAT"
                else {b"PWV3", b"PWV4", b"PWV5", b"PCOB", b"PCO2"} if extension == "EXT" else set())
    if not required <= sections:
        raise ValueError(f"ANLZ {extension} is missing required sections")


def pdb(data: bytes):
    if len(data) < PAGE or len(data) % PAGE:
        raise ValueError("Invalid PDB page alignment")
    zero, page_size, count, next_unused, _, _, _ = struct.unpack_from("<7I", data)
    if zero or page_size != PAGE or count != N_TABLES or next_unused < len(data) // PAGE:
        raise ValueError("Invalid PDB header")
    assigned = set()
    for table in range(count):
        kind, _, first, last = struct.unpack_from("<4I", data, 28 + table * 16)
        if kind != table:
            raise ValueError("Invalid PDB table directory")
        page = first
        seen = set()
        while True:
            if page <= 0 or page >= len(data) // PAGE or page in seen or page in assigned:
                raise ValueError("Invalid or circular PDB page chain")
            seen.add(page)
            assigned.add(page)
            offset = page * PAGE
            _, index, page_kind, following = struct.unpack_from("<4I", data, offset)
            if index != page or page_kind != kind:
                raise ValueError("PDB page identity mismatch")
            flags = data[offset + 0x1b]
            if not flags & 0x40:
                rows = int.from_bytes(data[offset + 0x18:offset + 0x1b], "little") & 0x1fff
                free, used = struct.unpack_from("<HH", data, offset + 0x1c)
                if HEAD + used + index_size(rows) + free != PAGE:
                    raise ValueError("Invalid PDB row heap or index size")
                for group in range(0, rows, 16):
                    base = offset + PAGE - (group // 16) * 36
                    for row in range(min(16, rows - group)):
                        start = struct.unpack_from("<H", data, base - 6 - row * 2)[0]
                        if start >= used:
                            raise ValueError("PDB row offset is outside its heap")
            if page == last:
                break
            page = following


def write_verified(path: str, data: bytes, validator):
    validator(data)
    temporary = str(path) + ".verified"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        write_atomic(temporary, data)
        if sha256_drive(temporary) != sha256_bytes(data):
            raise OSError(f"Generated file read-back mismatch: {path}")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
        if os.path.exists(temporary + ".tmp"):
            os.unlink(temporary + ".tmp")
