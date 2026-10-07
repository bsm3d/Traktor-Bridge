# Benoit Saint-Moulin
# Traktor Bridge : background jobs (loading a collection, exporting)

from __future__ import annotations

import logging
import threading
import traceback
from time import monotonic

from PySide6.QtCore import QThread, Signal

from ..export.files import Cancelled

log = logging.getLogger(__name__)


# Keep running threads alive even if their owning dialog closes.
# Qt aborts if a QThread is collected before it finishes.
_alive: set[Job] = set()


def has_active_jobs() -> bool:
    return bool(_alive)


def stop_all(ms: int = 5000) -> bool:
    """Asks every running job to stop and waits for them, at exit."""
    jobs = list(_alive)
    for j in jobs:
        j.stop.set()
    deadline = monotonic() + max(0, ms) / 1000
    stopped = True
    for j in jobs:
        remaining = max(0, int((deadline - monotonic()) * 1000))
        if j.wait(remaining):
            _alive.discard(j)
        else:
            stopped = False
    return stopped


class Job(QThread):
    """Runs fn(progress=..., cancel=...) away from the GUI, reports through signals."""

    progress = Signal(int, str)
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn, *args, **kw):
        super().__init__()
        self.fn, self.args, self.kw = fn, args, kw
        self.stop = threading.Event()

    def start(self, *args):
        _alive.add(self)
        self.finished.connect(self._over)
        super().start(*args)

    def _over(self):
        self.wait(2000)
        _alive.discard(self)

    def run(self):
        try:
            res = self.fn(*self.args, progress=self.progress.emit, cancel=self.stop, **self.kw)
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:  # noqa: BLE001 - a job boundary must report failures through its signal
            log.error("%s\n%s", e, traceback.format_exc())
            self.failed.emit(str(e))
        else:
            self.done.emit(res)
