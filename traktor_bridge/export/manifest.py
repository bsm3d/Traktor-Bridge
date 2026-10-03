# Benoit Saint-Moulin
# Traktor Bridge : checksums of every file an export writes, and their verification

"""The manifest sits at the root of the export and lists each file with its size,
modification time and SHA-256. The audio is hashed while it is copied, the other files
from the bytes written, so building it costs no extra read. A later export reuses the
entries of files left untouched (same size, same time), and the verification reads
everything back from the drive and compares."""

from __future__ import annotations

import hashlib
import json
import os
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_atomic(path: str, data: bytes):
    """Whole file or nothing, a power cut or a pulled key leaves the old one."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


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

    @property
    def good(self) -> bool:
        return not self.error and not self.damaged and not self.missing

    def summary(self) -> str:
        if self.error:
            return self.error
        s = f"{self.ok} of {self.total} files intact ({self.size / 1e9:.2f} GB read)"
        if self.damaged:
            s += f", {len(self.damaged)} damaged"
        if self.missing:
            s += f", {len(self.missing)} missing"
        return s


def verify(base: str, progress=None, cancel: threading.Event | None = None) -> Check:
    """Reads back every listed file. progress(pct, msg)."""
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
        p = os.path.join(base, *rel.split("/"))
        if not os.path.isfile(p):
            res.missing.append(rel)
            continue
        if os.path.getsize(p) != e["size"] or sha256_file(p, cancel) != e["sha256"]:
            res.damaged.append(rel)
        else:
            res.ok += 1
        done += e["size"]
        res.size = done
        dt = time.monotonic() - t0
        rate = f", {done / dt / 1e6:.0f} MB/s" if dt > 1 else ""
        cb(100 * done // max(1, todo), f"Verifying {i + 1}/{res.total}{rate}")
    return res
