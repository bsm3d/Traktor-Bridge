# Benoit Saint-Moulin
# Traktor Bridge : application start

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
from pathlib import Path

from . import APP_NAME, settings

USAGE = """TraktorBridge --export COLLECTION OUTPUT [--format FORMAT] [--music FOLDER]
TraktorBridge --verify OUTPUT

FORMAT: CDJ/USB (default), Rekordbox XML, M3U, Traktor NML. Everything in the
collection is exported, the report goes to traktor_bridge.log next to the program.
--verify reads an export back and compares it to the checksums written with it."""


def headless(argv: list[str]) -> int:
    from . import export, sources

    def opt(name, default=""):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default

    i = argv.index("--export")
    if len(argv) < i + 3:
        log_line(USAGE)
        return 2
    src, out = argv[i + 1], argv[i + 2]
    cfg = settings.load()
    fmt = opt("--format", "CDJ/USB")
    log = logging.getLogger("headless")
    log.info("export %s -> %s (%s)", src, out, fmt)
    try:
        nodes = sources.load(src, opt("--music", cfg["music_root"]))
        rep = export.run(fmt, nodes, out, cfg)
    except (ValueError, OSError) as e:
        # the windowed exe would show a crash box instead of the reason
        log_line(f"export failed: {e}")
        return 1
    except Exception as e:
        log.exception("export failed")
        log_line(f"export failed: {type(e).__name__}: {e}")
        return 1
    for m in rep.missing:
        log.warning("missing: %s", m)
    for e in rep.errors:
        log.error(e)
    log.info("%d tracks, %d missing, %d errors, %d cached", rep.tracks, len(rep.missing), len(rep.errors), rep.cached)
    return 1 if rep.errors else 0


def verify(argv: list[str]) -> int:
    from .export import manifest
    i = argv.index("--verify")
    if len(argv) < i + 2:
        log_line(USAGE)
        return 2
    chk = manifest.verify(argv[i + 1], allow_player_changes=True)
    for p in chk.damaged:
        log_line(f"damaged: {p}")
    for p in chk.missing:
        log_line(f"missing: {p}")
    for p in chk.modified:
        log_line(f"modified since export, integrity unconfirmed (possible player update): {p}")
    log_line(chk.summary())
    return 0 if chk.good else 1


def log_line(msg: str):
    logging.getLogger("headless").info(msg)
    if sys.stdout is not None:
        print(msg)


def main() -> int:
    # the ANLZ workers are processes, a frozen build re-enters here without this
    multiprocessing.freeze_support()

    # the Qt player's ffmpeg backend prints every probed file on the console
    os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg*=false")
    os.environ.setdefault("QT_FFMPEG_DEBUG", "0")

    # the compiled core is compared with its seal before anything of it is imported
    from . import integrity
    found = integrity.check()
    if found:
        logging.basicConfig(filename=str(settings.app_dir() / "traktor_bridge.log"), level=logging.ERROR)
        return integrity.stop(found, quiet="--export" in sys.argv or "--verify" in sys.argv)

    # the privileged half of formatting a drive: no window, no settings, no log file of its own
    if "--format-disk" in sys.argv:
        from . import drives
        return drives.helper_main(sys.argv)

    cfg = settings.load()
    root = logging.getLogger()
    root.setLevel(cfg["log_level"])
    fh = logging.FileHandler(settings.app_dir() / "traktor_bridge.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)

    if "--export" in sys.argv:
        return headless(sys.argv)
    if "--verify" in sys.argv:
        return verify(sys.argv)

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from .ui import theme
    from .ui.dialogs import LogBridge, LogWindow
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "ui" / "res" / "icon.png")))
    app.setStyleSheet(theme.STYLE)

    logwin = LogWindow()
    bridge = LogBridge()
    bridge.line.connect(logwin.add)
    root.addHandler(bridge)

    win = MainWindow(cfg, logwin)
    win.show()
    rc = app.exec()
    root.removeHandler(bridge)
    return rc
