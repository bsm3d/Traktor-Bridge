# Benoit Saint-Moulin
# Traktor Bridge : startup check of the compiled core

"""A release carries the core as .pyd files and tbcore.dll. compile_core.py writes their
SHA-256 into traktor_bridge/_seal.py, packed in the executable, and the program compares
them with the files on disk before it loads any of them. A file that changed, vanished or
was added beside them stops the program.

It keeps out a casual swap of a file in the unzipped folder, nothing more: whoever rebuilds
the executable can rebuild the seal."""

from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

EXTENSIONS = (".pyd", ".dll", ".so", ".dylib")

MESSAGE = ("Traktor Bridge found files that were changed or damaged, so it will not start.\n\n"
           "Download the program again from its release page and unzip it to a new folder.")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def scan(root: Path) -> dict[str, str]:
    """Every native module under root, by relative path."""
    return {p.relative_to(root).as_posix(): sha256(p)
            for p in sorted(root.rglob("*")) if p.is_file() and p.suffix.lower() in EXTENSIONS}


def problems(root: Path, expected: dict[str, str]) -> list[str]:
    """What differs between the files on disk and the seal, one line each."""
    found = scan(root)
    out = [f"missing: {rel}" for rel in expected if rel not in found]
    out += [f"changed: {rel}" for rel, digest in expected.items() if rel in found and found[rel] != digest]
    out += [f"unexpected: {rel}" for rel in found if rel not in expected]
    return out


def check() -> list[str]:
    """Empty when everything is as sealed, or when this is not a sealed build (a run from
    the sources has no seal and nothing to protect)."""
    if not getattr(sys, "frozen", False):
        return []
    try:
        from . import _seal
    except ImportError:
        log.warning("no seal in this build, files not checked")
        return []
    root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "traktor_bridge"
    return problems(root, _seal.HASHES)


def stop(found: list[str], quiet: bool = False) -> int:
    """Logs what was found and tells the user, without Qt (nothing has been loaded yet).
    quiet: command line use, a dialog would block a script, the message goes to stderr."""
    for line in found:
        log.error("integrity: %s", line)
    if quiet and sys.stderr is not None:
        print(MESSAGE, file=sys.stderr)
    elif sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, MESSAGE, "Traktor Bridge", 0x10)
    elif sys.stderr is not None:
        print(MESSAGE, file=sys.stderr)
    return 3
