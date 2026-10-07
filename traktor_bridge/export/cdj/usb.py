# Benoit Saint-Moulin
# Traktor Bridge : complete CDJ USB export (Contents, PIONEER, export.pdb, ANLZ, artwork)

from __future__ import annotations

import hashlib
import io
import logging
import os
import struct
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed

from ... import tags
from ...model import Node, Track, unique_tracks
from ...settings import cache_dir
from ..files import Cancelled, Planner, Report, copy_all, present, safe_name
from ..manifest import Manifest, sha256_bytes, write_atomic, write_direct
from . import anlz, pdbwrite, reference, validate

log = logging.getLogger(__name__)

# bump when the ANLZ writer changes, old cache entries are then ignored
ANLZ_VERSION = 7


def usb_path(t: Track, plan: Planner) -> str:
    # rekordbox cuts every level at 48 characters
    parts = [safe_name(t.artist or "Unknown Artist", 48), safe_name(t.album or "Unknown Album", 48),
             safe_name(os.path.basename(t.path), 48)]
    return "/" + plan.claim("Contents/" + "/".join(parts))


def cache_key(t: Track, usb: str) -> str:
    st = os.stat(t.path)
    cues = [(c.kind, c.start, c.length, c.hotcue, c.name, c.color) for c in t.cues]
    raw = repr((ANLZ_VERSION, st.st_size, int(st.st_mtime), usb, t.bpm, t.grid, t.duration, cues))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def whole(raw: bytes) -> bool:
    """A complete ANLZ file: PMAI tag and the length its header announces."""
    try:
        validate.anlz(raw)
    except (ValueError, UnicodeDecodeError, struct.error):
        return False
    return True


def cached(store, key: str, expected_path: str | None = None) -> tuple[bytes, bytes] | None:
    try:
        dat, ext = (store / f"{key}.DAT").read_bytes(), (store / f"{key}.EXT").read_bytes()
    except OSError:
        return None
    try:
        validate.anlz(dat, expected_path, "DAT")
        validate.anlz(ext, expected_path, "EXT")
    except (ValueError, UnicodeDecodeError, struct.error):
        log.warning("analysis cache %s damaged, analysed again", key)
    else:
        return dat, ext
    return None


def anlz_job(t: Track, usb: str) -> tuple[bytes, bytes]:
    from .analysis import Audio
    return anlz.build(t, usb, Audio(t.path))


# ============================================================
# Artwork
# ============================================================

# Reject oversized artwork before decoding its pixels.
MAX_PIXELS = 40_000_000


def write_artwork(items: list[pdbwrite.Item], root: str, man: Manifest | None = None) -> int:
    try:
        from PIL import Image
    except ImportError:
        log.info("Pillow missing, no artwork")
        return 0
    folder = os.path.join(root, "PIONEER", "Artwork", "00001")
    seen: dict[str, int] = {}
    for it in items:
        img = tags.artwork(it.track.path)
        if not img:
            continue
        h = hashlib.sha1(img).hexdigest()
        if h in seen:
            it.art = seen[h]
            continue
        try:
            pic = Image.open(io.BytesIO(img))
            if pic.width * pic.height > MAX_PIXELS:
                log.debug("artwork of %s: %sx%s too big", it.track.path, pic.width, pic.height)
                continue
            pic = pic.convert("RGB")
        except (OSError, ValueError) as e:
            log.debug("artwork of %s: %s", it.track.path, e)
            continue
        n = len(seen) + 1
        for size, name in ((80, f"a{n}.jpg"), (240, f"a{n}_m.jpg")):
            buf = io.BytesIO()
            pic.resize((size, size), Image.LANCZOS).save(buf, "JPEG", quality=90)
            put(os.path.join(folder, name), buf.getvalue(), man)
        seen[h] = it.art = n
    return len(seen)


# ============================================================
# Export
# ============================================================

def export(nodes: list[Node], root: str, verify: bool = False, processes: int = 0,
           progress=None, cancel: threading.Event | None = None, man: Manifest | None = None) -> Report:
    cb = progress or (lambda pct, msg: None)
    rep = Report(path=root)

    def check():
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    plan = Planner()
    items: list[pdbwrite.Item] = []
    for t in unique_tracks(nodes):
        if not present(t):
            rep.missing.append(t.path or t.title)
            continue
        tags.fill(t)
        items.append(pdbwrite.Item(t, len(items) + 1, usb_path(t, plan), "", 0))
    rep.tracks = len(items)
    if not items:
        return rep

    # ---- analysis cache
    store = cache_dir() / "anlz"
    store.mkdir(exist_ok=True)
    todo = []
    analysis_dirs: set[str] = set()
    for it in items:
        it.anlz = anlz.anlz_dir(it.path, analysis_dirs) + "/ANLZ0000.DAT"
        key = cache_key(it.track, it.path)
        hit = cached(store, key, it.path)
        if hit:
            put_anlz(root, it, *hit, man)
            rep.cached += 1
        else:
            todo.append((it, key))

    # ---- analysis and copy side by side: the analysis reads the source, not the copy
    total = 2 * len(items)
    state = {"copied": 0, "done": rep.cached, "info": ""}

    def tick():
        n = state["copied"] + state["done"]
        info = f" ({state['info']})" if state["info"] and state["copied"] < len(items) else ""
        cb(90 * n // total, f"Copied {state['copied']}/{len(items)}{info}, analysed {state['done']}/{len(items)}")

    def copied(i, n, info=""):
        state["copied"], state["info"] = i, info
        tick()

    jobs = [(it.track.path, os.path.join(root, it.path.lstrip("/"))) for it in items]
    # past 8 the workers fight over memory bandwidth and start up slower than they help
    auto = min(8, os.cpu_count() or 1)
    workers = max(1, min(processes or auto, len(todo) or 1))
    with ProcessPoolExecutor(workers) as pool:
        futs = {pool.submit(anlz_job, it.track, it.path): (it, key) for it, key in todo}
        try:
            rep.errors += copy_all(jobs, verify, cancel, copied, man)
            for f in as_completed(futs):
                check()
                it, key = futs[f]
                try:
                    dat, ext = f.result()
                except Exception as e:  # noqa: BLE001 - report any worker failure in the export result
                    rep.errors.append(f"{it.track.title}: analysis failed ({e})")
                    continue
                put_anlz(root, it, dat, ext, man)
                # EXT last: a cut between the two leaves no pair behind
                write_atomic(str(store / f"{key}.DAT"), dat)
                write_atomic(str(store / f"{key}.EXT"), ext)
                state["done"] += 1
                tick()
        except Cancelled:
            pool.shutdown(cancel_futures=True)
            raise
    for it, (_, dst) in zip(items, jobs, strict=True):
        it.size = os.path.getsize(dst) if os.path.exists(dst) else 0

    # ---- database
    cb(92, "Artwork...")
    write_artwork(items, root, man)
    cb(96, "Writing export.pdb...")
    dbdir = os.path.join(root, "PIONEER", "rekordbox")
    os.makedirs(dbdir, exist_ok=True)
    db = os.path.join(dbdir, "export.pdb")
    data = pdbwrite.write(items, nodes, db)
    reference.copy_settings(os.path.join(root, "PIONEER"))
    if man:
        man.add(db, sha256_bytes(data))
        for n in reference.SETTINGS:
            man.add(os.path.join(root, "PIONEER", n))
    cb(100, f"{len(items)} tracks exported")
    return rep


def put(path: str, data: bytes, man: Manifest | None):
    write_direct(path, data)
    if man:
        man.add(path, sha256_bytes(data))


def put_anlz(root: str, it: pdbwrite.Item, dat: bytes, ext: bytes, man: Manifest | None = None):
    base = os.path.join(root, it.anlz.lstrip("/"))
    validate.anlz(dat, it.path, "DAT")
    validate.anlz(ext, it.path, "EXT")
    for path, data, extension in ((base, dat, "DAT"), (base[:-4] + ".EXT", ext, "EXT")):
        check = lambda raw, extension=extension: validate.anlz(raw, it.path, extension)
        validate.write_verified(path, data, check)
        if man:
            man.add(path, sha256_bytes(data))
