"""Portable project backups, built and verified before replacing the destination."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .export.manifest import Cancelled, write_atomic
from .sources import index_folder, project, relocate

MAX_ENTRIES = 100_000
MAX_EXPANDED = 1 << 40
MAX_DIRECTORY = 128 << 20
MAX_RATIO = 100
DISK_RESERVE = 1 << 30


def _directory_limits(path: str):
    """Bound the central directory before ZipFile allocates its entry objects."""
    with open(path, "rb") as stream:
        size = os.fstat(stream.fileno()).st_size
        stream.seek(max(0, size - 65557))
        tail = stream.read(65557)
        end = tail.rfind(b"PK\x05\x06")
        if end < 0 or len(tail) - end < 22:
            raise ValueError("Invalid ZIP directory")
        _, disk, directory_disk, disk_count, count, directory_size, directory_offset, comment = struct.unpack(
            "<4s4H2LH", tail[end:end + 22])
        if end + 22 + comment != len(tail) or disk or directory_disk or disk_count != count:
            raise ValueError("Invalid or multi-volume ZIP directory")
        offset = size - len(tail) + end
        if count == 65535 or directory_size == 0xffffffff:
            if offset < 20:
                raise ValueError("Invalid ZIP64 directory")
            stream.seek(offset - 20)
            signature, disk, record_offset, disks = struct.unpack("<4sLQL", stream.read(20))
            if signature != b"PK\x06\x07" or disk or disks != 1 or record_offset > offset - 76:
                raise ValueError("Invalid ZIP64 locator")
            stream.seek(record_offset)
            record = stream.read(56)
            if len(record) != 56:
                raise ValueError("Invalid ZIP64 directory")
            signature, length, _, _, disk, directory_disk, disk_count, count, directory_size, directory_offset = (
                struct.unpack("<4sQ2H2L4Q", record))
            if (signature != b"PK\x06\x06" or not 44 <= length <= 1024 or disk
                    or directory_disk or disk_count != count):
                raise ValueError("Invalid ZIP64 directory")
        if count > MAX_ENTRIES or directory_size > MAX_DIRECTORY:
            raise ValueError("ZIP directory exceeds the backup entry or memory limit")
        if directory_offset + directory_size > offset:
            raise ValueError("Invalid ZIP directory bounds")
        stream.seek(directory_offset)
        consumed = actual_count = 0
        while consumed < directory_size:
            header = stream.read(46)
            if len(header) != 46 or header[:4] != b"PK\x01\x02":
                raise ValueError("Invalid ZIP directory entry")
            variable_size = sum(struct.unpack("<3H", header[28:34]))
            consumed += 46 + variable_size
            actual_count += 1
            if consumed > directory_size or actual_count > MAX_ENTRIES:
                raise ValueError("ZIP directory exceeds its size or entry limit")
            stream.seek(variable_size, os.SEEK_CUR)
        if actual_count != count:
            raise ValueError("ZIP directory entry count mismatch")


def _entry_limits(entries):
    if len(entries) > MAX_ENTRIES:
        raise ValueError("Too many backup entries")
    total = 0
    for entry in entries:
        if entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ValueError(f"Encrypted or unsupported ZIP entry: {entry.filename}")
        if entry.file_size > MAX_RATIO * max(1, entry.compress_size):
            raise ValueError(f"ZIP compression ratio exceeds {MAX_RATIO}:1: {entry.filename}")
        total += entry.file_size
        if total > MAX_EXPANDED:
            raise ValueError("Backup expanded size exceeds 1 TiB")
    return total


def verify(path: str, progress=None, cancel=None) -> str:
    """Verify the entire archive against its adjacent standard SHA-256 file."""
    source = Path(path)
    sidecar = Path(str(source) + ".sha256")
    if sidecar.stat().st_size > 4096:
        raise ValueError("The SHA-256 file is too large")
    line = sidecar.read_text(encoding="utf-8-sig").strip()
    match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
    if not match or match[2] != source.name:
        raise ValueError("The SHA-256 file must contain one checksum for this ZIP filename")
    digest = hashlib.sha256()
    size = source.stat().st_size
    done = 0
    with source.open("rb") as stream:
        while block := stream.read(4 << 20):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            digest.update(block)
            done += len(block)
            if progress:
                progress(min(100, done * 100 // max(1, size)), "Verifying archive SHA-256")
    if digest.hexdigest() != match[1].lower():
        raise ValueError("SHA-256 mismatch: the ZIP is damaged or its checksum belongs to another archive")
    return digest.hexdigest()


def restore(path: str, destination: str, progress=None, cancel=None) -> str:
    """Restore into a new folder only, after validating names, hashes and project paths."""
    target = Path(destination).absolute()
    if target.exists():
        raise FileExistsError("Choose a new restoration folder; existing folders are never overwritten")
    cb = progress or (lambda _pct, _message: None)

    def check():
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    initial = os.stat(path)
    _directory_limits(path)
    verify(path, lambda pct, msg: cb(pct // 4, msg), cancel)
    staging = Path(tempfile.mkdtemp(prefix=".tb-restore-", dir=target.parent))
    try:
        try:
            archive = zipfile.ZipFile(path)
        except NotImplementedError as e:        # a ZIP made by a version of the format Python does not read
            raise ValueError(f"{os.path.basename(path)} uses a ZIP version that cannot be read: {e}") from e
        with archive:
            entries = archive.infolist()
            total = _entry_limits(entries)
            names = set()
            for entry in entries:
                check()
                name = entry.filename
                parts = PurePosixPath(name).parts
                if (not parts or name.startswith("/") or "\\" in entry.orig_filename or
                        any(part in ("..", ".") or re.search(r'[<>:"|?*\x00-\x1f]', part)
                            or part.endswith((" ", "."))
                            or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
                            for part in parts) or
                        name.casefold() in names or entry.is_dir() or
                        stat.S_ISLNK(entry.external_attr >> 16)):
                    raise ValueError(f"Unsafe or duplicate ZIP entry: {name}")
                names.add(name.casefold())
                if name not in ("project.json", "manifest.json") and not (
                    len(parts) == 2 and parts[0] in ("Audio", "Playlists")
                ):
                    raise ValueError(f"Unexpected backup entry: {name}")
            for name in ("project.json", "manifest.json"):
                if name not in names:
                    raise ValueError(f"This is not a complete backup: {name} is missing from the ZIP")
                if archive.getinfo(name).file_size > 256 << 20:
                    raise ValueError(f"Backup metadata is too large: {name}")
            def metadata(name):
                chunks = []
                amount = 0
                with archive.open(name) as stream:
                    while block := stream.read(4 << 20):
                        check()
                        amount += len(block)
                        if amount > min(256 << 20, archive.getinfo(name).file_size):
                            raise ValueError(f"Backup metadata exceeds its size limit: {name}")
                        chunks.append(block)
                return json.loads(b"".join(chunks))

            doc = metadata("project.json")
            manifest = metadata("manifest.json")
            if (not isinstance(doc, dict) or not isinstance(manifest, dict)
                    or not isinstance(doc.get("settings"), dict)
                    or not isinstance(doc.get("tracks"), list)
                    or any(not isinstance(track, dict) for track in doc["tracks"])):
                raise ValueError("Invalid backup project or manifest structure")
            hashes = manifest.get("sha256")
            if not isinstance(hashes, dict) or any(
                not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in hashes.values()
            ):
                raise ValueError("Invalid backup audio checksums")
            audio = {entry.filename for entry in entries if entry.filename.startswith("Audio/")}
            if set(hashes) != audio or doc.get("format") != project.FORMAT:
                raise ValueError("The backup manifest or project is invalid")
            if any(track.get("path") not in audio for track in doc["tracks"]):
                raise ValueError("The project references audio outside the backup")
            doc["settings"].update(music_root="Audio", source_path="", output_path="")
            free = shutil.disk_usage(target.parent).free
            if free < total + DISK_RESERVE:
                raise OSError("Not enough free space to restore the backup")
            done = 0
            for entry in entries:
                check()
                output = staging.joinpath(*PurePosixPath(entry.filename).parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                written = 0
                with archive.open(entry) as src, output.open("xb") as dst:
                    while block := src.read(4 << 20):
                        check()
                        written += len(block)
                        if written > entry.file_size or done + len(block) > MAX_EXPANDED:
                            raise ValueError(f"ZIP entry exceeds its expanded size: {entry.filename}")
                        if shutil.disk_usage(staging).free < len(block) + DISK_RESERVE:
                            raise OSError("Restoration stopped to preserve 1 GiB of free disk space")
                        dst.write(block)
                        digest.update(block)
                        done += len(block)
                        cb(min(99, 25 + done * 74 // max(1, total)), f"Restoring {entry.filename}")
                if written != entry.file_size:
                    raise ValueError(f"ZIP entry size mismatch: {entry.filename}")
                if entry.filename in hashes and digest.hexdigest() != hashes[entry.filename]:
                    raise ValueError(f"Audio checksum mismatch: {entry.filename}")
            (staging / "project.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
            project.read(str(staging / "project.json"))
        current = os.stat(path)
        if (initial.st_size, initial.st_mtime_ns, initial.st_ino) != (
            current.st_size, current.st_mtime_ns, current.st_ino
        ):
            raise OSError("The ZIP changed during restoration")
        check()
        staging.rename(target)
        cb(100, "Backup restored")
        return str(target / "project.json")
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:100] or "Untitled"


def create(path: str, document: dict, progress=None, cancel=None) -> dict:
    """Archive a detached project.dump snapshot, all playlists and resolved audio."""
    doc = copy.deepcopy(document)
    target = Path(path).absolute()
    cb = progress or (lambda _pct, _message: None)

    def check():
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    check()
    cb(0, "Checking backup audio files")
    root = str(doc["settings"].get("music_root") or "")
    found = None
    files = {}
    missing = []
    for track in doc["tracks"]:
        check()
        original = track["path"]
        source = original
        if original and not os.path.isfile(original) and root and os.path.isdir(root):
            if found is None:
                found = index_folder(root)
            source = relocate(original, found)
        if not source or not os.path.isfile(source):
            missing.append(original or f"{track['artist']} - {track['title']} (no audio path)")
            continue
        source = os.path.abspath(source)
        if os.path.normcase(source) == os.path.normcase(str(target)):
            raise ValueError("The backup destination cannot replace a source audio file")
        identity = os.path.normcase(os.path.realpath(source))
        if identity not in files:
            stat = os.stat(source)
            stem, extension = os.path.splitext(os.path.basename(source))
            suffix = "." + safe_name(extension[1:]) if extension else ""
            entry = f"Audio/{len(files) + 1:06d}_{safe_name(stem)}{suffix}"
            files[identity] = (source, entry, stat)
        track["path"] = files[identity][1]
    if missing:
        raise FileNotFoundError(f"Backup not created: {len(missing)} missing audio file(s).\n"
                                + "\n".join(missing[:20]))

    doc["settings"].update(source_path="", music_root="Audio", output_path="")
    total = sum(stat.st_size for _source, _entry, stat in files.values())
    processed = 0
    hashes = {}
    fd, name = tempfile.mkstemp(prefix=".tb-backup-", suffix=".zip", dir=target.parent)
    temp = Path(name)
    os.close(fd)
    try:
        with zipfile.ZipFile(temp, "w", allowZip64=True) as archive:
            for source, entry, before in files.values():
                check()
                digest = hashlib.sha256()
                with open(source, "rb") as src, archive.open(entry, "w", force_zip64=True) as dst:
                    while block := src.read(4 << 20):
                        check()
                        dst.write(block)
                        digest.update(block)
                        processed += len(block)
                        cb(min(70, processed * 70 // max(1, total)), f"Backing up {os.path.basename(source)}")
                    after = os.fstat(src.fileno())
                current = os.stat(source)
                # Windows stat/fstat can expose different legacy ctime values after a tag-file replace.
                # Compare ctime between paths only there; size, mtime and inode still check the open handle.
                if (any((st.st_size, st.st_mtime_ns, st.st_ino) !=
                        (before.st_size, before.st_mtime_ns, before.st_ino) for st in (after, current))
                        or current.st_ctime_ns != before.st_ctime_ns
                        or (os.name != "nt" and after.st_ctime_ns != before.st_ctime_ns)):
                    raise OSError(f"Audio changed during backup: {source}. Try again after stopping edits.")
                hashes[entry] = digest.hexdigest()
            archive.writestr("project.json", json.dumps(doc, indent=1, ensure_ascii=False),
                             compress_type=zipfile.ZIP_DEFLATED)
            count = 0

            def playlists(nodes):
                nonlocal count
                for node in nodes:
                    check()
                    if node["kind"] == "folder":
                        playlists(node.get("children", []))
                    else:
                        count += 1
                        lines = ["#EXTM3U"]
                        for number in node.get("tracks", []):
                            track = doc["tracks"][number]
                            title = re.sub(r"[\r\n]", " ", f"{track['artist']} - {track['title']}")
                            lines.extend((f"#EXTINF:{round(track['duration'])},{title}",
                                          "../" + track["path"]))
                        archive.writestr(f"Playlists/{count:06d}_{safe_name(node['name'])}.m3u8",
                                         "\n".join(lines) + "\n", compress_type=zipfile.ZIP_DEFLATED)

            playlists(doc["tree"])
            archive.writestr("manifest.json", json.dumps({"sha256": hashes}, indent=1),
                             compress_type=zipfile.ZIP_DEFLATED)
        checked = 0
        with zipfile.ZipFile(temp) as archive:
            for entry in archive.infolist():
                check()
                digest = hashlib.sha256()
                with archive.open(entry) as src:
                    while block := src.read(4 << 20):
                        check()
                        digest.update(block)
                        checked += len(block)
                        cb(min(99, 70 + checked * 29 // max(1, total)), "Verifying ZIP backup")
                if entry.filename in hashes and digest.hexdigest() != hashes[entry.filename]:
                    raise OSError(f"Backup verification failed: {entry.filename}")
        check()
        with temp.open("r+b") as stream:
            os.fsync(stream.fileno())
        cb(99, "Computing archive SHA-256")
        digest = hashlib.sha256()
        with temp.open("rb") as stream:
            while block := stream.read(4 << 20):
                check()
                digest.update(block)
        checksum = digest.hexdigest()
        check()
        os.replace(temp, target)
        checksum_path = str(target) + ".sha256"
        try:
            write_atomic(checksum_path, f"{checksum} *{target.name}\n".encode())
        except OSError as e:
            raise OSError(f"The ZIP was created at {target}, but its SHA-256 file could not be saved: {e}") from e
        cb(100, "ZIP backup completed")
        return {"path": str(target), "audio": len(files), "playlists": count, "size": target.stat().st_size,
                "sha256": checksum, "checksum_path": checksum_path}
    finally:
        temp.unlink(missing_ok=True)
