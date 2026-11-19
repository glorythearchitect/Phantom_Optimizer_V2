"""
app/controllers/hardware_controller.py
Hardware Info tab: dispatches per-category content into Holo.
Read-only. One operation at a time.
"""
from PyQt6.QtCore import QObject, pyqtSignal

from core.threads import Worker, thread_pool
from hardware import summary


CATEGORIES = ["CPU", "GPU", "MEMORY", "DISKS", "DRIVERS", "SENSORS"]


def _dispatch(category: str) -> dict:
    """
    Returns {"kind": "text", "payload": <str>}
    Event Logs are deferred to Tools/System.
    """
    cat = category.upper()
    if cat == "CPU":     return {"kind": "text", "payload": summary.get_cpu_info()}
    if cat == "GPU":     return {"kind": "text", "payload": summary.get_gpu_info()}
    if cat == "MEMORY":  return {"kind": "text", "payload": summary.get_memory_info()}
    if cat == "DISKS":   return {"kind": "text", "payload": summary.get_disks_info()}
    if cat == "DRIVERS": return {"kind": "text", "payload": summary.get_drivers_info()}
    if cat == "SENSORS": return {"kind": "text", "payload": summary.get_sensors_info()}
    return {"kind": "text", "payload": f"Unknown category: {category}"}


class HardwareController(QObject):
    category_ready     = pyqtSignal(str, dict)
    operation_started  = pyqtSignal(str)
    operation_finished = pyqtSignal(str)
    error_occurred     = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []
        self._busy = False
        self._current_category = ""

    def _run(self, fn, on_done):
        w = Worker(fn)
        self._workers.append(w)

        def cleanup():
            try:
                self._workers.remove(w)
            except ValueError:
                pass

        def ok(r):
            cleanup()
            self._busy = False
            self.operation_finished.emit(self._current_category)
            on_done(r)

        def err(msg):
            cleanup()
            self._busy = False
            self.operation_finished.emit(self._current_category)
            self.error_occurred.emit("Hardware Info", msg)

        w.signals.finished.connect(ok)
        w.signals.error.connect(err)
        thread_pool.start(w)

    def load_category(self, category: str):
        if self._busy:
            return
        self._busy = True
        self._current_category = category
        self.operation_started.emit(category)
        self._run(
            lambda: _dispatch(category),
            lambda r: self.category_ready.emit(
                category, r or {"kind": "text", "payload": "No data."}
            ),
        )