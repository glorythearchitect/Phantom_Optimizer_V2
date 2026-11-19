"""
app/controllers/optimizer_controller.py
Mediates between the Optimizer UI and the backend optimizer modules.

Key fix: keeps a strong reference to every running Worker until it finishes.
Without this, PyQt garbage-collects the worker and the app crashes when the
background thread emits signals.
"""
import os

from PyQt6.QtCore import QObject, pyqtSignal

from core.threads import Worker, thread_pool
from core.paths import get_whitelist_path
from optimizer import killer, processes, whitelist, memory_tools


class OptimizerController(QObject):
    snapshot_ready      = pyqtSignal(dict)
    candidates_ready    = pyqtSignal(list)
    kill_finished       = pyqtSignal(list)
    memory_result_ready = pyqtSignal(dict)
    operation_started   = pyqtSignal(str)
    operation_finished  = pyqtSignal(str)
    error_occurred      = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._current_op = ""
        self._workers = []

    # ===============================
    # Worker lifecycle
    # ===============================

    def _run_worker(self, fn, on_done):
        w = Worker(fn)
        self._workers.append(w)

        def _cleanup():
            try:
                self._workers.remove(w)
            except ValueError:
                pass

        def _on_finished(result):
            _cleanup()
            on_done(result)

        def _on_error(msg):
            _cleanup()
            self._on_error(msg)

        w.signals.finished.connect(_on_finished)
        w.signals.error.connect(_on_error)
        thread_pool.start(w)

    # ===============================
    # Locking helpers
    # ===============================

    def _begin(self, op_name: str) -> bool:
        if self._busy:
            self.error_occurred.emit(
                "Optimizer Busy",
                f"Operation '{self._current_op}' is still running. "
                f"Please wait for it to finish."
            )
            return False
        self._busy = True
        self._current_op = op_name
        self.operation_started.emit(op_name)
        return True

    def _end(self):
        op = self._current_op
        self._busy = False
        self._current_op = ""
        self.operation_finished.emit(op)

    def _on_error(self, message: str):
        self._end()
        self.error_occurred.emit("Optimizer Error", message)

    # ===============================
    # Operations
    # ===============================

    def analyze(self, search_term: str = ""):
        if not self._begin("Analyze"):
            return
        wl = whitelist.load_whitelist()

        def work():
            snapshot = processes.list_processes(wl, search_term)
            all_procs = processes.list_all_processes(wl)
            candidates = killer.preview_candidates(wl)
            memory = memory_tools.get_memory_status()
            return {
                "snapshot": snapshot,
                "all_processes": all_procs,
                "candidates": candidates,
                "memory": memory,
            }

        def done(result):
            self._end()
            if result is None:
                return
            snap = result["snapshot"]
            self.snapshot_ready.emit({
                "apps": snap.get("apps", []),
                "background": snap.get("background", []),
                "memory": result["memory"],
                "all_processes": result["all_processes"],
            })
            self.candidates_ready.emit(
                [c.to_dict() for c in result["candidates"]]
            )

        self._run_worker(work, done)

    def refresh(self, search_term: str = ""):
        self.analyze(search_term)

    def kill_selected(self, pairs: list):
        if not pairs:
            self.error_occurred.emit("Kill Selected", "No processes selected.")
            return
        if not self._begin("Kill Selected"):
            return

        def work():
            return killer.kill_processes(pairs)

        def done(results):
            self._end()
            if results is None:
                return
            self.kill_finished.emit([r.to_dict() for r in results])

        self._run_worker(work, done)

    def auto_optimize(self):
        if not self._begin("Auto Optimize"):
            return
        wl = whitelist.load_whitelist()

        def work():
            return killer.auto_optimize(wl)

        def done(results):
            self._end()
            if results is None:
                return
            self.kill_finished.emit([r.to_dict() for r in results])

        self._run_worker(work, done)

    def preview_candidates(self) -> list:
        try:
            wl = whitelist.load_whitelist()
            return [c.to_dict() for c in killer.preview_candidates(wl)]
        except Exception as e:
            self.error_occurred.emit("Preview Candidates", str(e))
            return []

    def memory_optimize(self):
        if not self._begin("Memory Optimize"):
            return

        def work():
            return memory_tools.full_memory_optimize()

        def done(result):
            self._end()
            if result is None:
                return
            self.memory_result_ready.emit(result)

        self._run_worker(work, done)

    # ===============================
    # Whitelist
    # ===============================

    def open_whitelist_file(self) -> str:
        path = get_whitelist_path()
        try:
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write("# Add your safe process names below, one per line\n")
            os.startfile(path)
            return path
        except Exception as e:
            self.error_occurred.emit(
                "Whitelist",
                f"Could not open whitelist file:\n{e}"
            )
            return ""

    def reload_whitelist(self) -> set:
        return whitelist.load_whitelist()