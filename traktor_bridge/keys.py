# Benoit Saint-Moulin
# Traktor Bridge : musical keys, one table for every notation

"""Traktor MUSICAL_KEY indices: 0-11 major from C, 12-23 minor from Cm.
Parsers and exporters share this table for all key notations."""

from __future__ import annotations

# index -> (rekordbox name, Open Key, Camelot)
# rekordbox writes flats (Dbm, Eb...) in the Keys table of export.pdb
_TABLE = [
    ("C", "1d", "8B"), ("Db", "8d", "3B"), ("D", "3d", "10B"), ("Eb", "10d", "5B"),
    ("E", "5d", "12B"), ("F", "12d", "7B"), ("Gb", "7d", "2B"), ("G", "2d", "9B"),
    ("Ab", "9d", "4B"), ("A", "4d", "11B"), ("Bb", "11d", "6B"), ("B", "6d", "1B"),
    ("Cm", "10m", "5A"), ("Dbm", "5m", "12A"), ("Dm", "12m", "7A"), ("Ebm", "7m", "2A"),
    ("Em", "2m", "9A"), ("Fm", "9m", "4A"), ("Gbm", "4m", "11A"), ("Gm", "11m", "6A"),
    ("Abm", "6m", "1A"), ("Am", "1m", "8A"), ("Bbm", "8m", "3A"), ("Bm", "3m", "10A"),
]

NOTATIONS = ("Classical", "Open Key", "Camelot")

_SHARPS = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}

_LOOKUP: dict[str, int] = {}
for _i, (_name, _ok, _cam) in enumerate(_TABLE):
    for _s in (_name, _ok, _cam):
        _LOOKUP[_s.lower()] = _i


def name(idx: int | None, notation: str = "Classical") -> str:
    if idx is None or not 0 <= idx < 24:
        return ""
    rb, ok, cam = _TABLE[idx]
    if notation == "Open Key":
        return ok
    if notation == "Camelot":
        return cam
    return rb


def parse(text: str) -> int | None:
    """Any notation back to the index: 'Am', 'A minor', 'F#m', '8A', '1m', 'Abmin'."""
    s = (text or "").strip().replace(" ", "")
    if not s:
        return None
    # '08A' as VirtualDJ and Mixed In Key write it
    low = s.lower().lstrip("0") or "0"
    if low in _LOOKUP:
        return _LOOKUP[low]
    for suffix in ("minor", "min"):
        if low.endswith(suffix):
            s = s[: -len(suffix)] + "m"
            break
    for suffix in ("major", "maj"):
        if s.lower().endswith(suffix):
            s = s[: -len(suffix)]
            break
    root = s[:2] if len(s) > 1 and s[1] in "#b" else s[:1]
    rest = s[len(root):]
    root = root[0].upper() + root[1:]
    root = _SHARPS.get(root, root)
    return _LOOKUP.get((root + rest).lower())


def from_traktor(value: str | int | None) -> int | None:
    try:
        idx = int(value)
    except (TypeError, ValueError):
        return None
    return idx if 0 <= idx < 24 else None
