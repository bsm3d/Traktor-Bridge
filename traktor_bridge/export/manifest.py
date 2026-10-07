# Benoit Saint-Moulin
# Traktor Bridge : checksums of every file an export writes, and their verification

"""Export manifest: paths, sizes, modification times and SHA-256.
Hashes are collected during writes and reused for unchanged files. Verification
reads the drive back rather than trusting those cached entries."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field

from .. import APP_NAME, VERSION

NAME = "traktor_bridge_checksums.json"
FORMAT = 1
BLOCK = 1 << 20
MAX_MANIFEST = 256 << 20          # 1 million files is about 150 MB of JSON


class Cancelled(Exception):
    pass


def sha256_file(path: str, cancel: threading.Event | None = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            b = f.read(BLOCK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _direct_blocks(path: str):
    """Windows: the file read around the system cache, so the bytes come from the drive
    and not from what was just written. Sector aligned buffer, as that mode requires."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                              wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    k.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                           ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    # read, share all, open existing, no buffering + sequential scan
    h = k.CreateFileW(os.path.abspath(path), 0x80000000, 7, None, 3, 0x28000000, None)
    if h in (None, ctypes.c_void_p(-1).value):
        raise OSError(ctypes.get_last_error(), "cannot open uncached")
    try:
        raw = ctypes.create_string_buffer(BLOCK + 4096)
        addr = ctypes.addressof(raw)
        off = -addr % 4096
        view = memoryview(raw)[off:off + BLOCK]
        n = wintypes.DWORD()
        while True:
            if not k.ReadFile(h, addr + off, BLOCK, ctypes.byref(n), None):
                raise OSError(ctypes.get_last_error(), "read error")
            if n.value == 0:
                return
            yield view[:n.value]
    finally:
        k.CloseHandle(h)


def sha256_drive(path: str, cancel: threading.Event | None = None) -> str:
    """SHA-256 of what the drive holds, not of the system cache. Falls back to a normal
    read where that is not possible; a read error that happens halfway is raised."""
    if sys.platform == "win32":
        h = hashlib.sha256()
        try:
            for b in _direct_blocks(path):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                h.update(b)
            return h.hexdigest()
        except OSError as e:
            if "uncached" not in str(e):
                raise
    return sha256_file(path, cancel)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_atomic(path: str, data: bytes):
    """Whole file or nothing, a power cut or a pulled key leaves the old one."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def write_direct(path: str, data: bytes):
    """Straight into the final name, parents created on demand. A rename costs a directory
    entry removed and another created, for a small file on FAT that is most of the work.
    Only for files an export rewrites in full anyway, a cut leaves one to write again."""
    def dump():
        with open(path, "wb") as f:
            f.write(data)

    try:
        try:
            dump()
        except FileNotFoundError:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            dump()
    except BaseException:
        try:
            os.remove(path)
        except OSError:
            pass
        raise

def safe_rel(rel) -> bool:
    """A path inside the drive: no drive letter, no absolute path, no '..'."""
    return (isinstance(rel, str) and bool(rel) and ":" not in rel and "\\" not in rel
            and not any(part in ("", ".", "..") for part in rel.split("/")))


def seal(files: dict) -> str:
    """Checksum of the list itself, a manifest edited or cut short is refused."""
    return sha256_bytes(json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def same_stat(entry: dict, st: os.stat_result) -> bool:
    # FAT keeps times to 2 seconds
    return entry.get("size") == st.st_size and abs(entry.get("mtime", 0) - int(st.st_mtime)) <= 2


# ============================================================
# Reading
# ============================================================

def read(base: str) -> dict:
    """Whole manifest, {} when absent, ValueError when damaged."""
    p = os.path.join(base, NAME)
    if not os.path.isfile(p):
        return {}
    if os.path.getsize(p) > MAX_MANIFEST:
        raise ValueError(f"{NAME} is damaged (too large)")
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except RecursionError:
        raise ValueError(f"{NAME} is damaged") from None
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict) or data.get("seal") != seal(files):
        raise ValueError(f"{NAME} is damaged")
    # the seal only proves the list was not cut or edited by accident: the content is still checked
    for rel, e in files.items():
        if not safe_rel(rel) or not isinstance(e, dict) or type(e.get("size")) is not int                 or not isinstance(e.get("sha256"), str):
            raise ValueError(f"{NAME} is damaged (entry {rel!r})")
    return data


# ============================================================
# Writing
# ============================================================

class Manifest:
    """Filled by an export, saved at its end. The previous one is read and then
    removed at the start, a cancelled export must not leave an outdated list behind."""

    def __init__(self, base: str):
        self.base = base
        self.files: dict[str, dict] = {}
        self.lock = threading.Lock()
        try:
            self.old = read(base).get("files", {})
        except (OSError, ValueError):
            self.old = {}
        try:
            os.remove(os.path.join(base, NAME))
        except OSError:
            pass

    def rel(self, path: str) -> str:
        return os.path.relpath(path, self.base).replace("\\", "/")

    def known(self, path: str) -> str:
        """Hash of a file already on the drive, from the previous manifest when the
        file did not change since, '' when it has to be read."""
        e = self.old.get(self.rel(path))
        try:
            return e["sha256"] if e and same_stat(e, os.stat(path)) else ""
        except OSError:
            return ""

    def add(self, path: str, sha: str = ""):
        st = os.stat(path)
        sha = sha or self.known(path) or sha256_file(path)
        with self.lock:
            self.files[self.rel(path)] = {"size": st.st_size, "mtime": int(st.st_mtime), "sha256": sha}

    def save(self) -> str:
        files = dict(sorted(self.files.items()))
        data = {"format": FORMAT, "program": f"{APP_NAME} {VERSION}",
                "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "algorithm": "sha256",
                "files": files, "seal": seal(files)}
        path = os.path.join(self.base, NAME)
        write_atomic(path, json.dumps(data, indent=1, ensure_ascii=False).encode("utf-8"))
        return path


# ============================================================
# Verification
# ============================================================

@dataclass
class Check:
    base: str = ""
    created: str = ""
    total: int = 0
    ok: int = 0
    size: int = 0
    damaged: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    error: str = ""
    modified: list[str] = field(default_factory=list)
    category_totals: dict[str, int] = field(default_factory=dict)
    category_ok: dict[str, int] = field(default_factory=dict)

    @property
    def good(self) -> bool:
        return not self.error and not self.damaged and not self.missing and not self.modified

    def summary(self) -> str:
        if self.error:
            return self.error
        s = f"{self.ok} of {self.total} files intact ({self.size / 1e9:.2f} GB read)"
        if self.damaged:
            s += f", {len(self.damaged)} damaged"
        if self.missing:
            s += f", {len(self.missing)} missing"
        if self.modified:
            s += f", {len(self.modified)} Pioneer files modified since export (integrity unconfirmed)"
        return s

    def report(self) -> str:
        if self.error:
            return self.error
        lines = []
        for category in ("Audio", "Artwork", "Pioneer database / analysis", "Other files"):
            total = self.category_totals.get(category, 0)
            if total:
                lines.append(f"{category}: {self.category_ok.get(category, 0)} / {total} verified, checksums match.")
        if self.modified:
            lines.append(f"Pioneer files: {len(self.modified)} modified since export.")
            lines.append("If the key was used on a CDJ, updates to its database and analysis files are normal; "
                         "changed files are not checksum-validated.")
        if self.damaged or self.missing:
            lines.append(f"Problems: {len(self.damaged)} different or unreadable, {len(self.missing)} missing. "
                         "See the log (Ctrl+L) for file details.")
        return "\n\n".join(lines) if lines else self.summary()


def file_category(rel: str) -> str:
    from ..sources import AUDIO_EXT

    parts = rel.casefold().split("/")
    if os.path.splitext(parts[-1])[1] in AUDIO_EXT:
        return "Audio"
    if parts[:2] == ["pioneer", "artwork"]:
        return "Artwork"
    if player_mutable(rel):
        return "Pioneer database / analysis"
    return "Other files"


def player_mutable(rel: str) -> bool:
    """Only known player-written database and analysis locations."""
    parts = rel.casefold().split("/")
    return (parts == ["pioneer", "rekordbox", "export.pdb"]
            or (len(parts) >= 4 and parts[:2] == ["pioneer", "usbanlz"]
                and parts[-1] in ("anlz0000.dat", "anlz0000.ext", "anlz0000.2ex")))


def verify(base: str, progress=None, cancel: threading.Event | None = None,
           *, allow_player_changes: bool = False) -> Check:
    """Read every listed file; standalone checks can distinguish possible player changes.

    A changed Pioneer file is not certified healthy: its checksum cannot establish who
    changed it. Immediate export verification remains strict.
    """
    cb = progress or (lambda pct, msg: None)
    res = Check(base=base)
    try:
        data = read(base)
    except (OSError, ValueError) as e:
        res.error = f"Cannot read the checksums: {e}"
        return res
    if not data:
        res.error = f"No {NAME} in {base}, export again to create it."
        return res
    res.created = data.get("created", "")
    files = data["files"]
    res.total = len(files)
    todo = sum(e["size"] for e in files.values())
    done, t0 = 0, time.monotonic()
    for i, (rel, e) in enumerate(files.items()):
        category = file_category(rel)
        res.category_totals[category] = res.category_totals.get(category, 0) + 1
        p = os.path.join(base, *rel.split("/"))
        if not os.path.isfile(p):
            res.missing.append(rel)
            continue
        try:
            size = os.path.getsize(p)
            digest = sha256_drive(p, cancel)
            bad = size != e["size"] or digest != e["sha256"]
        except OSError:
            res.damaged.append(rel)
        else:
            if bad:
                if allow_player_changes and player_mutable(rel):
                    res.modified.append(rel)
                else:
                    res.damaged.append(rel)
            else:
                res.ok += 1
                res.category_ok[category] = res.category_ok.get(category, 0) + 1
        done += e["size"]
        res.size = done
        dt = time.monotonic() - t0
        rate = f", {done / dt / 1e6:.0f} MB/s" if dt > 1 else ""
        cb(100 * done // max(1, todo), f"Verifying {i + 1}/{res.total}{rate}")
    return res
