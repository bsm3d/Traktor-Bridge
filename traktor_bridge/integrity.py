# Benoit Saint-Moulin
# Traktor Bridge : startup check of the compiled core

"""A release carries the core as .pyd files and tbcore.dll. compile_core.py writes their
SHA-256 into traktor_bridge/_seal.py, packed in the executable, and the program compares
them with the files on disk before it loads any of them. A file that changed, vanished or
was added beside them stops the program.
The checker stays in the executable's Python archive, not an unverified extension DLL.

It keeps out a casual swap of a file in the unzipped folder, nothing more: whoever rebuilds
the executable can rebuild the seal."""

from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

EXTENSIONS = (".pyd", ".dll", ".so", ".dylib")

HEAD = "Traktor Bridge found files that were changed or damaged, so it will not start."

MESSAGE = (HEAD + "\n\n"
           "Run the installer again, or download the portable version again and unzip it to a new "
           "folder. Do not unzip over an older copy.")

# Only unexpected files: most likely an older copy left them when a new version was unzipped over it
STALE = (HEAD + "\n\n{details}\n\n"
         "These files do not belong to this version. An older copy probably left them. Delete them "
         "from the runtime\\traktor_bridge folder next to TraktorBridge.exe, then start the program again.\n\n"
         "To avoid this, unzip a new version into a new folder, or use the installer.")


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
        return ["missing integrity seal in frozen build"]
    if (not isinstance(getattr(_seal, "HASHES", None), dict) or not _seal.HASHES
            or any(not isinstance(rel, str) or not isinstance(digest, str)
                   or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                   for rel, digest in _seal.HASHES.items())):
        return ["invalid integrity seal in frozen build"]
    root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "traktor_bridge"
    return problems(root, _seal.HASHES)


def details(found: list[str], limit: int = 6) -> str:
    """The files at fault, a few lines, so that a bug report says which ones."""
    lines = found[:limit]
    if len(found) > limit:
        lines.append(f"... and {len(found) - limit} more")
    return "\n".join(lines)


def stop(found: list[str], quiet: bool = False) -> int:
    """Logs what was found and tells the user, without Qt (nothing has been loaded yet).
    quiet: command line use, a dialog would block a script, the message goes to stderr."""
    for line in found:
        log.error("integrity: %s", line)
    if found and all(line.startswith("unexpected:") for line in found):
        text = STALE.format(details=details(found))
    else:
        text = MESSAGE + "\n\n" + details(found)
    if quiet and sys.stderr is not None:
        print(text, file=sys.stderr)
    elif sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Traktor Bridge", 0x10)
    elif sys.stderr is not None:
        print(text, file=sys.stderr)
    return 3
