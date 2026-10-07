# Benoit Saint-Moulin
# Traktor Bridge : user settings, stored as JSON next to the application

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

EXPORTS = ("CDJ/USB", "Rekordbox XML", "M3U", "Traktor NML")

DEFAULTS = {
    "source_path": "",
    "output_path": "",
    "music_root": "",
    "export_format": "CDJ/USB",
    "copy_music": True,
    "verify_copy": True,
    "key_format": "Open Key",
    "anlz_processes": 0,            # 0 = auto, up to 8
    "auto_load": True,
    "confirm_exit": False,
    "waveform_color": "RGB",
    "crossfade": 3,
    "volume": 70,
    "log_level": "INFO",
}


def app_dir() -> Path:
    # frozen build: next to the exe, source run: the project folder
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    d = Path(base) / "TraktorBridge"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG = app_dir() / "traktor_bridge.json"


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG, encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            cfg.update(saved)
        else:
            log.warning("settings are not a JSON object, defaults used")
    except FileNotFoundError:
        pass
    except (OSError, ValueError, RecursionError) as e:
        log.warning("settings unreadable, defaults used: %s", e)
    if cfg["export_format"] not in EXPORTS:
        cfg["export_format"] = "CDJ/USB"
    return cfg


def save(cfg: dict):
    tmp = CONFIG.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG)
    except OSError as e:
        log.error("cannot save settings: %s", e)


def default_collection() -> str:
    """Newest Traktor collection.nml in Documents/Native Instruments."""
    ni = Path.home() / "Documents" / "Native Instruments"
    found = sorted(ni.glob("Traktor*/collection.nml"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(found[0]) if found else ""
