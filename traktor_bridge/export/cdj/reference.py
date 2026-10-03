# Benoit Saint-Moulin
# Traktor Bridge : player files taken from the user's own rekordbox export

"""A key needs a few files only rekordbox writes: the player settings (MYSETTING,
MYSETTING2, DJMMYSETTING, DEVSETTING) and four export.pdb pages holding the player
menus and an empty history. Traktor Bridge does not ship them. Each user points once to a
key or folder exported by their own rekordbox, and they are copied from there."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ...settings import cache_dir
from ..manifest import write_atomic
from .devicesql import PAGE
from .pdbread import read

SETTINGS = ("MYSETTING.DAT", "MYSETTING2.DAT", "DJMMYSETTING.DAT", "DEVSETTING.DAT")

# export.pdb tables copied as they are: columns, the two menu tables, history
PAGES = {16: "columns", 17: "t17", 18: "t18", 19: "history"}


class MissingReference(Exception):
    pass


# the files of the author's own rekordbox, shipped in the personal build only (rbref/ is left
# out of the public release, see traktor_bridge.spec)
BUNDLED = Path(__file__).resolve().with_name("rbref")


def _complete(d: Path) -> bool:
    return all((d / n).is_file() for n in SETTINGS) and all((d / f"{p}.page").is_file() for p in PAGES.values())


def _cache() -> Path:
    return cache_dir() / "rekordbox_reference"


def folder() -> Path:
    """The user's imported reference, else the bundled one when there is one."""
    d = _cache()
    if not _complete(d) and _complete(BUNDLED):
        return BUNDLED
    return d


def ready() -> bool:
    return _complete(folder())


def find_pioneer(path: str) -> Path | None:
    """The PIONEER folder, whether the user picked the key, PIONEER or rekordbox."""
    p = Path(path)
    for cand in (p / "PIONEER", p, p.parent, p.parent.parent):
        if (cand / "rekordbox" / "export.pdb").is_file():
            return cand
    return None


def import_from(path: str) -> list[str]:
    """Copy the reference files from a rekordbox export. Returns what was found missing."""
    pio = find_pioneer(path)
    if pio is None:
        raise MissingReference(f"no PIONEER/rekordbox/export.pdb under {path}")
    data = (pio / "rekordbox" / "export.pdb").read_bytes()
    pdb = read(data)

    missing = []
    pages = {}
    for kind, name in PAGES.items():
        chain = pdb.pages.get(kind) or []
        if not chain:
            missing.append(f"export.pdb table {kind}")
            continue
        i = chain[0].idx
        pages[name] = data[i * PAGE:(i + 1) * PAGE]
    for n in SETTINGS:
        if not (pio / n).is_file() or os.path.getsize(pio / n) == 0:
            missing.append(n)
    if missing:
        raise MissingReference("incomplete rekordbox export, missing: " + ", ".join(missing))

    d = _cache()
    d.mkdir(parents=True, exist_ok=True)
    for name, raw in pages.items():
        write_atomic(str(d / f"{name}.page"), raw)
    for n in SETTINGS:
        shutil.copyfile(pio / n, d / n)
    return []


def pages() -> dict[int, bytes]:
    if not ready():
        raise MissingReference("no rekordbox reference imported yet")
    d = folder()
    return {kind: (d / f"{name}.page").read_bytes() for kind, name in PAGES.items()}


def copy_settings(pioneer_dir: str):
    d = folder()
    for n in SETTINGS:
        dst = os.path.join(pioneer_dir, n)
        if not os.path.exists(dst):
            shutil.copyfile(d / n, dst)
