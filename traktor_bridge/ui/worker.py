# Benoit Saint-Moulin
# Traktor Bridge : background jobs (loading a collection, exporting)

from __future__ import annotations

import logging
import threading
import traceback

from PySide6.QtCore import QThread, Signal

from ..export.files import Cancelled

log = logging.getLogger(__name__)


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

    def run(self):
        try:
            res = self.fn(*self.args, progress=self.progress.emit, cancel=self.stop, **self.kw)
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:
            log.error("%s\n%s", e, traceback.format_exc())
            self.failed.emit(str(e))
        else:
            self.done.emit(res)
