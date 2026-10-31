"""Run blocking adb work off the Qt UI thread."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)

# Keep Python references alive until the task finishes; otherwise the signals
# object can be garbage collected and the callbacks silently never fire.
_running: set[Task] = set()


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as e:  # report every error to the UI
            log.debug("task failed\n%s", traceback.format_exc())
            try:
                self.signals.failed.emit(str(e) or e.__class__.__name__)
            except RuntimeError:
                pass  # receiver already deleted (dialog closed)
            return
        try:
            self.signals.done.emit(result)
        except RuntimeError:
            pass


def run_async(
    fn: Callable[[], Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> Task:
    """Run ``fn`` in the global thread pool; callbacks fire on the UI thread."""
    task = Task(fn)
    _running.add(task)
    if on_done:
        task.signals.done.connect(on_done)
    if on_error:
        task.signals.failed.connect(on_error)
    # Connected last so it runs after the user callbacks.
    task.signals.done.connect(lambda _=None: _running.discard(task))
    task.signals.failed.connect(lambda _=None: _running.discard(task))
    QThreadPool.globalInstance().start(task)
    return task
