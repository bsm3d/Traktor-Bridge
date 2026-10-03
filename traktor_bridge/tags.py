# Benoit Saint-Moulin
# Traktor Bridge : what the collection doesn't say, read from the audio file itself

"""No tag library needed: embedded pictures and the GEOB objects other DJ software
hides in the files are pulled straight from the ID3v2, FLAC and MP4 containers,
stream info comes from soundfile when it is installed."""

from __future__ import annotations

import logging
import os
import struct

from .model import Track

# a cover or a Serato object is a few MB, a size field far past that is a damaged or hostile file
MAX_TAG = 64 << 20

log = logging.getLogger(__name__)

try:
    import soundfile
except ImportError:
    soundfile = None


def fill(t: Track):
    """Duration and sample rate when the source had none (M3U, some XML)."""
    if soundfile is None or (t.duration and t.samplerate):
        return
    try:
        i = soundfile.info(t.path)
    except Exception as e:
        log.debug("soundfile %s: %s", t.path, e)
        return
    t.duration = t.duration or i.duration
    t.samplerate = i.samplerate or t.samplerate
    if not t.bitrate and i.duration:
        t.bitrate = round(os.path.getsize(t.path) * 8 / i.duration / 1000)


# ============================================================
# ID3 (mp3, and the ID3 chunk of aiff / wav)
# ============================================================

def syncsafe(b: bytes) -> int:
    return b[0] << 21 | b[1] << 14 | b[2] << 7 | b[3]


def skip_text(buf: bytes, pos: int, enc: int) -> int:
    """Past a NUL terminated string, 2 byte NUL for the UTF-16 encodings."""
    if enc in (1, 2):
        while pos + 1 < len(buf) and buf[pos:pos + 2] != b"\0\0":
            pos += 2
        return pos + 2
    end = buf.find(b"\0", pos)
    return (end if end >= 0 else len(buf)) + 1


def id3_block(f) -> bytes | None:
    """The whole ID3v2 tag: at the start of an mp3, in the 'ID3 ' chunk of an aiff
    or the 'id3 ' chunk of a wav, where the first reader never looked."""
    head = f.read(12)
    if head[:3] == b"ID3":
        n = 10 + syncsafe(head[6:10])
        if n > MAX_TAG:
            return None
        f.seek(0)
        return f.read(n)
    riff = head[:4] == b"RIFF"
    if not (head[:4] == b"FORM" or riff):
        return None
    pos = 12
    while True:
        f.seek(pos)
        ch = f.read(8)
        if len(ch) < 8:
            return None
        size = struct.unpack("<I" if riff else ">I", ch[4:])[0]
        if ch[:4].lower() == b"id3 ":
            return f.read(size) if size <= MAX_TAG else None
        pos += 8 + size + (size & 1)


def id3_frames(tag: bytes):
    """(frame id, body) for every frame of an ID3v2 tag."""
    ver, flags = tag[3], tag[5]
    buf = tag[10:10 + syncsafe(tag[6:10])]
    if flags & 0x80 and ver < 4:
        buf = buf.replace(b"\xff\x00", b"\xff")
    pos = 0
    if flags & 0x40:                        # extended header
        pos = syncsafe(buf[:4]) if ver == 4 else 4 + struct.unpack(">I", buf[:4])[0]
    while pos + 10 <= len(buf):
        if ver == 2:
            fid, size, hl = buf[pos:pos + 3], int.from_bytes(buf[pos + 3:pos + 6], "big"), 6
        else:
            fid, hl = buf[pos:pos + 4], 10
            size = syncsafe(buf[pos + 4:pos + 8]) if ver == 4 else struct.unpack(">I", buf[pos + 4:pos + 8])[0]
        if not fid.strip(b"\0") or size <= 0:
            break
        body = buf[pos + hl:pos + hl + size]
        if ver == 4 and buf[pos + 9] & 0x01:
            body = body[4:]                 # data length indicator
        pos += hl + size
        yield fid, body


def id3_picture(tag: bytes) -> bytes | None:
    pics = []
    for fid, body in id3_frames(tag):
        if fid not in (b"APIC", b"PIC"):
            continue
        enc = body[0]
        p = 4 if fid == b"PIC" else body.find(b"\0", 1) + 1
        kind = body[p]
        p = skip_text(body, p + 1, enc)
        pics.append((kind, body[p:]))
    front = [d for k, d in pics if k == 3]
    return (front or [d for _, d in pics] or [None])[0]


def id3_geob(tag: bytes, desc: str) -> bytes | None:
    """GEOB frame by its description ('Serato Markers2'...), the object data only."""
    for fid, body in id3_frames(tag):
        if fid != b"GEOB":
            continue
        enc = body[0]
        p = body.find(b"\0", 1) + 1         # mime, always latin-1
        p = skip_text(body, p, enc)         # file name
        end = skip_text(body, p, enc)       # description
        text = body[p:end].decode("utf-16" if enc in (1, 2) else "latin-1", "replace").rstrip("\0")
        if text == desc:
            return body[end:]
    return None


# ============================================================
# FLAC
# ============================================================

def flac_blocks(f):
    if f.read(4) != b"fLaC":
        return
    while True:
        h = f.read(4)
        if len(h) < 4:
            return
        last, kind, size = h[0] & 0x80, h[0] & 0x7F, int.from_bytes(h[1:4], "big")
        yield kind, f.read(size)
        if last:
            return


def flac_picture(f) -> bytes | None:
    pics = []
    for kind, data in flac_blocks(f):
        if kind == 6:
            ptype, mlen = struct.unpack_from(">II", data, 0)
            p = 8 + mlen
            dlen = struct.unpack_from(">I", data, p)[0]
            p += 4 + dlen + 16
            n = struct.unpack_from(">I", data, p)[0]
            pics.append((ptype, data[p + 4:p + 4 + n]))
    front = [d for k, d in pics if k == 3]
    return (front or [d for _, d in pics] or [None])[0]


def flac_comments(f) -> dict[str, str]:
    """Vorbis comments, keys upper case."""
    out = {}
    for kind, data in flac_blocks(f):
        if kind != 4:
            continue
        p = 4 + struct.unpack_from("<I", data, 0)[0]
        count = struct.unpack_from("<I", data, p)[0]
        p += 4
        # every comment takes at least its 4 length bytes, a bigger count is a lie
        for _ in range(min(count, (len(data) - p) // 4)):
            ln = struct.unpack_from("<I", data, p)[0]
            k, _, v = data[p + 4:p + 4 + ln].decode("utf-8", "replace").partition("=")
            out[k.upper()] = v
            p += 4 + ln
    return out


# ============================================================
# MP4
# ============================================================

def mp4_moov(f) -> bytes | None:
    """The moov atom only, an m4a can weigh hundreds of MB."""
    f.seek(0, 2)
    end, p = f.tell(), 0
    while p + 8 <= end:
        f.seek(p)
        head = f.read(16)
        size, name = struct.unpack_from(">I4s", head, 0)
        hl = 8
        if size == 1 and len(head) == 16:
            size, hl = struct.unpack_from(">Q", head, 8)[0], 16
        elif size == 0:
            size = end - p
        if size < hl:
            return None
        if name == b"moov":
            if size - hl > MAX_TAG:
                return None
            f.seek(p + hl)
            return f.read(size - hl)
        p += size
    return None


def mp4_atoms(data: bytes, start: int, end: int):
    p = start
    while p + 8 <= end:
        size, name = struct.unpack_from(">I4s", data, p)
        hl = 8
        if size == 1:
            size, hl = struct.unpack_from(">Q", data, p + 8)[0], 16
        elif size == 0:
            size = end - p
        if size < hl:
            return
        yield name, p + hl, min(p + size, end)
        p += size


def mp4_find(data: bytes, path: list[bytes], start: int, end: int):
    for name, a, b in mp4_atoms(data, start, end):
        if name == path[0]:
            if len(path) == 1:
                return a, b
            # meta carries 4 bytes of version and flags before its children
            return mp4_find(data, path[1:], a + 4 if name == b"meta" else a, b)
    return None


def mp4_picture(f) -> bytes | None:
    """moov/udta/meta/ilst/covr/data, walked atom by atom."""
    data = mp4_moov(f)
    if data is None:
        return None
    hit = mp4_find(data, [b"udta", b"meta", b"ilst", b"covr", b"data"], 0, len(data))
    return data[hit[0] + 8:hit[1]] if hit else None


MP4_TEXT = {b"\xa9nam": "title", b"\xa9ART": "artist", b"\xa9alb": "album", b"\xa9gen": "genre",
            b"\xa9day": "year", b"\xa9cmt": "comment", b"aART": "album_artist"}


def mp4_tags(f) -> dict[str, str]:
    """Text items of moov/udta/meta/ilst, tempo, track number and the Mixed In Key key."""
    data = mp4_moov(f)
    hit = mp4_find(data, [b"udta", b"meta", b"ilst"], 0, len(data)) if data else None
    out: dict[str, str] = {}
    if not hit:
        return out
    for name, a, b in mp4_atoms(data, hit[0], hit[1]):
        d = mp4_find(data, [b"data"], a, b)
        if d is None or d[1] - d[0] < 8:
            continue
        val = data[d[0] + 8:d[1]]
        if name in MP4_TEXT:
            out[MP4_TEXT[name]] = val.decode("utf-8", "replace")
        elif name == b"tmpo" and len(val) >= 2:
            out["bpm"] = str(struct.unpack_from(">H", val)[0])
        elif name == b"trkn" and len(val) >= 4:
            out["track_no"] = str(struct.unpack_from(">H", val, 2)[0])
        elif name == b"----":
            label = mp4_find(data, [b"name"], a, b)
            if label and data[label[0] + 4:label[1]].decode("utf-8", "replace").lower() in ("initialkey", "key"):
                out["key"] = val.decode("utf-8", "replace")
    return out


# ============================================================
# Entry points
# ============================================================

MP4 = (".m4a", ".mp4", ".aac", ".alac")


def artwork(path: str) -> bytes | None:
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as f:
            if ext == ".flac":
                return flac_picture(f)
            if ext in MP4:
                return mp4_picture(f)
            tag = id3_block(f)
            return id3_picture(tag) if tag else None
    except (OSError, IndexError, struct.error) as e:
        log.debug("artwork %s: %s", path, e)
        return None


def geob(path: str, desc: str) -> bytes | None:
    """An ID3 GEOB object (mp3, aiff, wav), None elsewhere or when absent."""
    if os.path.splitext(path)[1].lower() in MP4 + (".flac", ".ogg"):
        return None
    try:
        with open(path, "rb") as f:
            tag = id3_block(f)
            return id3_geob(tag, desc) if tag else None
    except (OSError, IndexError, struct.error) as e:
        log.debug("geob %s: %s", path, e)
        return None


def comments(path: str) -> dict[str, str]:
    """Vorbis comments of a FLAC, empty elsewhere."""
    if os.path.splitext(path)[1].lower() != ".flac":
        return {}
    try:
        with open(path, "rb") as f:
            return flac_comments(f)
    except (OSError, IndexError, struct.error) as e:
        log.debug("comments %s: %s", path, e)
        return {}


# ============================================================
# Basic tags, for a folder of music with no collection
# ============================================================

ID3_TEXT = {b"TIT2": "title", b"TPE1": "artist", b"TALB": "album", b"TCON": "genre", b"TBPM": "bpm",
            b"TKEY": "key", b"TDRC": "year", b"TYER": "year", b"TRCK": "track_no", b"TPE2": "album_artist",
            b"TT2": "title", b"TP1": "artist", b"TAL": "album", b"TCO": "genre", b"TBP": "bpm",
            b"TKE": "key", b"TYE": "year", b"TRK": "track_no", b"TP2": "album_artist"}
VORBIS = {"TITLE": "title", "ARTIST": "artist", "ALBUM": "album", "GENRE": "genre", "BPM": "bpm",
          "INITIALKEY": "key", "KEY": "key", "DATE": "year", "YEAR": "year", "TRACKNUMBER": "track_no",
          "ALBUMARTIST": "album_artist", "COMMENT": "comment"}


def id3_text(body: bytes, skip: int = 0) -> str:
    enc = body[0] if body else 0
    raw = body[1 + skip:]
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(enc, "latin-1")
    return raw.decode(codec, "replace").split("\0")[0].strip()


def id3_tags(tag: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for fid, body in id3_frames(tag):
        if fid in ID3_TEXT:
            out.setdefault(ID3_TEXT[fid], id3_text(body))
        elif fid in (b"COMM", b"COM") and len(body) > 4 and "comment" not in out:
            p = skip_text(body, 4, body[0])         # past the language and the short description
            enc = body[0]
            out["comment"] = body[p:].decode({0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}
                                             .get(enc, "latin-1"), "replace").split("\0")[0].strip()
    return out


def basic(path: str) -> dict[str, str]:
    """title, artist, album, album_artist, genre, year, comment, track_no, bpm and key as
    written in the file, only the ones that are there. Empty when the file can't be read."""
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as f:
            if ext == ".flac":
                return {VORBIS[k]: v for k, v in flac_comments(f).items() if k in VORBIS and v}
            if ext in MP4:
                return {k: v for k, v in mp4_tags(f).items() if v}
            tag = id3_block(f)
            return {k: v for k, v in id3_tags(tag).items() if v} if tag else {}
    except (OSError, IndexError, struct.error, ValueError) as e:
        log.debug("basic tags %s: %s", path, e)
        return {}
