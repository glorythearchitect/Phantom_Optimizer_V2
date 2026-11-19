"""
app/controllers/performance_controller.py
Performance tab controller.
Live monitor polls once per second via short-lived workers.
Benchmark tests lock the operation and pause polling.
GPU test cannot be cancelled per design.
"""

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

from core.threads import Worker, thread_pool
from performance import cpu_test, disk_test, mem_test, live_monitor


class PerformanceController(QObject):
    live_stats_ready    = pyqtSignal(dict)
    test_finished       = pyqtSignal(str, dict)
    gpu_preview_ready   = pyqtSignal(QImage)
    gpu_progress_changed = pyqtSignal(int, str)
    gpu_info_ready      = pyqtSignal(dict)
    operation_started   = pyqtSignal(str)
    operation_finished  = pyqtSignal(str)
    error_occurred      = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []
        self._busy = False
        self._current_op = ""
        self._live_worker_running = False

    def _run(self, op_name, fn, on_done, err_title="Performance",
             busy_lock=True, on_err=None):
        if busy_lock and self._busy:
            self.error_occurred.emit(
                "Performance Busy",
                f"Operation '{self._current_op}' is still running."
            )
            return

        if busy_lock:
            self._busy = True
            self._current_op = op_name
            self.operation_started.emit(op_name)

        w = Worker(fn)
        self._workers.append(w)

        def cleanup():
            try:
                self._workers.remove(w)
            except ValueError:
                pass

        def ok(r):
            cleanup()
            if busy_lock:
                self._busy = False
                self._current_op = ""
                self.operation_finished.emit(op_name)
            on_done(r)

        def err(msg):
            cleanup()
            if busy_lock:
                self._busy = False
                self._current_op = ""
                self.operation_finished.emit(op_name)
                self.error_occurred.emit(err_title, msg)
            if on_err is not None:
                try:
                    on_err(msg)
                except Exception:
                    pass

        w.signals.finished.connect(ok)
        w.signals.error.connect(err)
        thread_pool.start(w)

    # ---- live monitor ----

    def request_live_stats(self):
        """Called by UI timer. Skips if a live worker is already running."""
        if self._live_worker_running:
            return
        self._live_worker_running = True

        def work():
            return live_monitor.get_live_stats()

        def done(r):
            self._live_worker_running = False
            if r:
                self.live_stats_ready.emit(r)

        def err_handler(_msg):
            self._live_worker_running = False

        self._run("Live Stats", work, done, busy_lock=False, on_err=err_handler)

    # ---- CPU / Disk / Memory ----

    def run_cpu_benchmark(self):
        def work():
            return cpu_test.run_cpu_benchmark()
        def done(r):
            if r:
                self.test_finished.emit("CPU Test", r)
        self._run("CPU Test", work, done)

    def run_disk_test(self):
        def work():
            return disk_test.run_disk_speed_test(size_mb=256)
        def done(r):
            if r:
                self.test_finished.emit("Disk Test", r)
        self._run("Disk Test", work, done)

    def run_memory_test(self):
        def work():
            return mem_test.run_memory_check(size_mb=512)
        def done(r):
            if r:
                self.test_finished.emit("Memory Test", r)
        self._run("Memory Test", work, done)

    # ---- GPU ----
    def prepare_gpu_test(self):
        """Fetch GPU info in a worker thread. Emits gpu_info_ready when done
        (with an empty dict on any error, so the UI can always recover)."""
        def work():
            from performance.gpu_test import get_gpu_info_only
            return get_gpu_info_only()

        def done(r):
            self.gpu_info_ready.emit(r if isinstance(r, dict) else {})

        def err(_msg):
            self.gpu_info_ready.emit({})

        self._run("Prepare GPU Test", work, done, busy_lock=False, on_err=err)

    def run_gpu_test(self):
        """Run GPU Pulse on the GUI thread.

        QOffscreenSurface is GUI-thread-only. Creating it on a worker thread
        causes Qt to fall back to a QWindow-based surface that Windows binds
        to the integrated GPU (ignoring the process's 'High performance'
        preference). Running on the GUI thread with cooperative yields
        (QApplication.processEvents every N frames) keeps the UI responsive
        AND uses the correct adapter.
        """
        from performance import gpu_test as _gpu
        from PyQt6.QtWidgets import QApplication

        self.operation_started.emit("GPU Test")

        try:
            result = _gpu.run_gpu_benchmark(
                progress_cb=lambda pct, msg: self.gpu_progress_changed.emit(
                    int(pct), str(msg)
                ),
                preview_cb=lambda img: self.gpu_preview_ready.emit(img),
                yield_cb=lambda: QApplication.processEvents(),
            )
        except Exception as e:
            self.error_occurred.emit("GPU Test", f"Runtime error: {e}")
            self.operation_finished.emit("GPU Test")
            return

        self.operation_finished.emit("GPU Test")
        if result:
            self.test_finished.emit("GPU Test", result)