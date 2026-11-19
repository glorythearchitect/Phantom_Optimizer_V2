"""
app/controllers/home_controller.py
Home tab: fetches user/device/CPU/GPU/Windows name.
"""
from PyQt6.QtCore import QObject, pyqtSignal

from core.threads import Worker, thread_pool
from system.home_info import get_home_info


class HomeController(QObject):
    info_ready       = pyqtSignal(dict)
    operation_started = pyqtSignal(str)
    operation_finished = pyqtSignal(str)
    error_occurred   = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []
        self._busy = False

    def _run(self, fn, on_done):
        w = Worker(fn)
        self._workers.append(w)

        def cleanup():
            try: self._workers.remove(w)
            except ValueError: pass

        def ok(r):
            cleanup()
            self._busy = False
            self.operation_finished.emit("Home Load")
            on_done(r)

        def err(msg):
            cleanup()
            self._busy = False
            self.operation_finished.emit("Home Load")
            self.error_occurred.emit("Home", msg)

        w.signals.finished.connect(ok)
        w.signals.error.connect(err)
        thread_pool.start(w)

    def load(self):
        if self._busy:
            return
        self._busy = True
        self.operation_started.emit("Home Load")
        self._run(get_home_info, lambda r: self.info_ready.emit(r or {}))