"""
app/controllers/scan_controller.py
Scan tab controller. True progress, real cancellation.
"""

import threading

from PyQt6.QtCore import QObject, pyqtSignal

from core.threads import Worker, thread_pool
from system import scan_engine


class ScanController(QObject):
    progress_changed   = pyqtSignal(int, str)   # pct, message
    scan_finished      = pyqtSignal(str, dict)  # scan_type, result
    scan_cancelled     = pyqtSignal(str)        # scan_type
    operation_started  = pyqtSignal(str)
    operation_finished = pyqtSignal(str)
    error_occurred     = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []
        self._busy = False
        self._current_op = ""
        self._cancel_event = None

    def start_scan(self, scan_type: str):
        if self._busy:
            self.error_occurred.emit(
                "Scan Busy",
                f"Operation '{self._current_op}' is still running."
            )
            return

        cancel = threading.Event()
        self._cancel_event = cancel
        self._busy = True
        self._current_op = scan_type
        self.operation_started.emit(scan_type)

        def progress_emit(pct, msg):
            try:
                self.progress_changed.emit(int(pct), str(msg))
            except Exception:
                pass

        def work():
            if scan_type == "full":
                return scan_engine.scan_full(progress_emit, cancel)
            if scan_type == "phantom":
                return scan_engine.scan_phantom(progress_emit, cancel)
            if scan_type == "software":
                return scan_engine.scan_software(progress_emit, cancel)
            if scan_type == "hardware":
                return scan_engine.scan_hardware(progress_emit, cancel)
            return None

        w = Worker(work, cancel_flag=cancel)
        self._workers.append(w)

        def cleanup():
            try:
                self._workers.remove(w)
            except ValueError:
                pass

        def on_done(result):
            cleanup()
            op = self._current_op
            self._busy = False
            self._current_op = ""
            self._cancel_event = None
            self.operation_finished.emit(op)
            if result is None:
                self.scan_cancelled.emit(op)
            else:
                self.scan_finished.emit(op, result)

        def on_err(msg):
            cleanup()
            op = self._current_op
            self._busy = False
            self._current_op = ""
            self._cancel_event = None
            self.operation_finished.emit(op)
            self.error_occurred.emit("Scan Error", msg)

        w.signals.finished.connect(on_done)
        w.signals.error.connect(on_err)
        thread_pool.start(w)

    def cancel_scan(self):
        if self._cancel_event is not None:
            self._cancel_event.set()