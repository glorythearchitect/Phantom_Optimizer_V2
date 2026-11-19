"""
core/threads.py
Generic worker thread utilities for Phantom Optimizer V2 (PyQt6).

Signals:
    started  -> emitted when the worker begins running
    finished -> emitted with the result (or None if cancelled)
    error    -> emitted with the exception message
"""
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class WorkerSignals(QObject):
    started = pyqtSignal()
    finished = pyqtSignal(object)
    error = pyqtSignal(str)


class Worker(QRunnable):
    """
    Runs a blocking function off the UI thread.

    Cancellation:
        Pass a `threading.Event` as `cancel_flag`. The backend function must
        check the flag periodically to honor cancellation. If the flag is set
        before completion, the result is discarded and `finished(None)` fires.
    """
    def __init__(self, fn, *args, cancel_flag=None, **kwargs):
        super().__init__()
        # Prevent Qt from deleting the C++ object while signals may still fire.
        self.setAutoDelete(False)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.cancel_flag = cancel_flag
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.started.emit()

            if self.cancel_flag is not None and self.cancel_flag.is_set():
                self.signals.finished.emit(None)
                return

            result = self.fn(*self.args, **self.kwargs)

            if self.cancel_flag is not None and self.cancel_flag.is_set():
                # Cancelled while running; drop result silently.
                self.signals.finished.emit(None)
                return

            try:
                self.signals.finished.emit(result)
            except RuntimeError:
                pass
        except Exception as e:
            try:
                self.signals.error.emit(str(e))
            except RuntimeError:
                pass


thread_pool = QThreadPool.globalInstance()