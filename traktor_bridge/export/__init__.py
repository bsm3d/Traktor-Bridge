# Benoit Saint-Moulin
# Traktor Bridge : one entry for every export format

from __future__ import annotations

import os

from ..model import Node
from . import manifest
from .files import Report


def run(fmt: str, nodes: list[Node], out: str, cfg: dict, progress=None, cancel=None) -> Report:
    """Export, then the checksums of everything written. With verify_copy the whole
    export is read back from the drive and compared to them."""
    os.makedirs(out, exist_ok=True)
    man = manifest.Manifest(out)
    if fmt == "CDJ/USB":
        from .cdj import usb
        rep = usb.export(nodes, out, cfg["verify_copy"], cfg["anlz_processes"], progress, cancel, man)
    else:
        from . import m3u, nml, rbxml
        mod = {"Rekordbox XML": rbxml, "M3U": m3u, "Traktor NML": nml}[fmt]
        rep = mod.export(nodes, out, cfg["copy_music"], cfg["verify_copy"], progress, cancel, man)
    rep.manifest = man.save()
    if cfg["verify_copy"]:
        chk = manifest.verify(out, progress, cancel)
        rep.verified, rep.verified_size = chk.ok, chk.size
        rep.errors += [f"{p}: differs from what was written" for p in chk.damaged]
        rep.errors += [f"{p}: missing after the export" for p in chk.missing]
        if chk.error:
            rep.errors.append(chk.error)
    return rep
