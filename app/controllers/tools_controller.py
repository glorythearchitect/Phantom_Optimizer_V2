"""
app/controllers/tools_controller.py
Tools tab: Startup Manager, Cleaner, Event Logs, Network Usage (placeholder).
"""
from PyQt6.QtCore import QObject, pyqtSignal

from core.threads import Worker, thread_pool
from system import startup_manager, network
from maintenance import cleaner
from hardware import event_logs
import psutil

class ToolsController(QObject):
    content_ready      = pyqtSignal(str, dict)
    action_done        = pyqtSignal(str, bool, str)
    kill_finished      = pyqtSignal(list)      # list of KillResult.to_dict()
    event_logs_ready_for_export = pyqtSignal(list, str)  # logs, format   
    operation_started  = pyqtSignal(str)
    operation_finished = pyqtSignal(str)
    error_occurred     = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []
        self._busy = False
        self._current_op = ""

    def _run(self, op_name, fn, on_done, err_title="Tools"):
        if self._busy:
            self.error_occurred.emit("Tools Busy",
                                     f"Operation '{self._current_op}' is still running.")
            return
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
            self._busy = False
            self._current_op = ""
            self.operation_finished.emit(op_name)
            on_done(r)

        def err(msg):
            cleanup()
            self._busy = False
            self._current_op = ""
            self.operation_finished.emit(op_name)
            self.error_occurred.emit(err_title, msg)

        w.signals.finished.connect(ok)
        w.signals.error.connect(err)
        thread_pool.start(w)

    # ---------------- Startup Manager ----------------

    def load_startup(self):
        def work():
            rows = startup_manager.list_startup_apps()
            return {
                "kind": "table",
                "columns": ["Name", "Location", "Status", "Command"],
                "rows": [list(r) for r in rows],
            }
        self._run("Startup Load", work,
                  lambda r: self.content_ready.emit("Startup Manager", r or {}))

    def toggle_startup_batch(self, items, enable):
        """
        items: list of (name, location) tuples to enable/disable in one pass.
        """
        action = "Enable" if enable else "Disable"

        def work():
            ok_count = 0
            for name, loc in items:
                try:
                    fn = (startup_manager.enable_startup_item if enable
                          else startup_manager.disable_startup_item)
                    if fn(name, loc):
                        ok_count += 1
                except Exception:
                    pass
            return {
                "action": action,
                "ok_count": ok_count,
                "total": len(items),
            }

        def done(r):
            if r:
                msg = f"{r['action']}: {r['ok_count']}/{r['total']} succeeded."
                self.action_done.emit(r["action"],
                                      r["ok_count"] == r["total"], msg)

        self._run(f"{action} Startup", work, done)

    # ---------------- Cleaner ----------------

    def load_cleaner(self):
        def work():
            targets = cleaner.scan_cleanup_targets()
            return {
                "kind": "table",
                "columns": ["Category", "Size (MB)"],
                "rows": [[n, f"{s:.2f}"] for n, s in targets],
            }
        self._run("Cleaner Scan", work,
                  lambda r: self.content_ready.emit("Cleaner", r or {}))

    def execute_cleaner(self):
        def work():
            result = cleaner.perform_cleanup(dry_run=False)
            return {
                "kind": "table",
                "columns": ["Category", "Freed (MB)"],
                "rows": [[n, f"{s:.2f}"] for n, s in result.items()],
            }
        def done(r):
            if r:
                self.content_ready.emit("Cleaner", r)
                total = sum(float(row[1]) for row in r.get("rows", []))
                self.action_done.emit("Clean", True, f"Freed {total:.2f} MB total.")
        self._run("Cleaner Execute", work, done)

    # ---------------- Event Logs ----------------

    def load_event_logs(self):
        def work():
            logs = event_logs.get_recent_system_warnings(limit=50)
            return {
                "kind": "table",
                "columns": ["Time", "Source", "Message"],
                "rows": [list(r) for r in logs],
            }
        self._run("Event Logs Load", work,
                  lambda r: self.content_ready.emit("Event Logs", r or {}))

    def export_event_logs(self, fmt):
        """Fetch last 100 events and hand them to the UI for saving."""
        def work():
            logs = event_logs.get_recent_system_warnings(limit=100)
            return {"logs": logs, "format": fmt}

        def done(result):
            if result and result.get("logs"):
                self.event_logs_ready_for_export.emit(
                    result["logs"], result["format"]
                )
            else:
                self.error_occurred.emit(
                    "Event Logs Export",
                    "No event logs available to export."
                )

        self._run(f"Export Event Logs ({fmt.upper()})", work, done)

    # ---------------- Network Usage ----------------

    def load_network(self):
        def work():
            rows = network.list_network_processes()
            return {
                "kind": "checkable_table",
                "columns": ["Process", "PID", "Est", "Listen", "UDP", "Family", "Endpoints"],
                "rows": [
                    [
                        r["name"],
                        r["pid"] if r["pid"] is not None else "-",
                        r["tcp_est"],
                        r["tcp_listen"],
                        r["udp"],
                        r["family"],
                        r["endpoints"],
                    ]
                    for r in rows
                ],
                "checkable": [r["checkable"] for r in rows],
            }
        self._run("Network Load", work,
                  lambda r: self.content_ready.emit("Network Usage", r or {}))

    def kill_network_process(self, pairs):
        """
        Kill processes selected from the Network Usage table.
        Revalidates each PID still points at the intended process before terminating.
        Uses the same killer.kill_processes path as Optimizer for the same safety model.
        """
        if not pairs:
            self.error_occurred.emit("Network Usage", "No processes selected.")
            return

        def work():
            from optimizer import killer
            verified = []
            rejected = []
            for pid, expected_name in pairs:
                try:
                    proc = psutil.Process(pid)
                    actual = proc.name()
                    if actual.lower() == expected_name.lower():
                        verified.append((pid, expected_name))
                    else:
                        rejected.append((pid, expected_name, actual))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    rejected.append((pid, expected_name, None))
            results = killer.kill_processes(verified) if verified else []
            return {"results": results, "rejected": rejected}

        def done(data):
            if data is None:
                return
            from optimizer.killer import KillResult, KillStatus
            all_results = list(data["results"])
            for pid, name, actual in data["rejected"]:
                reason = (f"PID now points to '{actual}', not '{name}'"
                          if actual else "PID no longer exists")
                all_results.append(KillResult(pid, name, KillStatus.FAILED, reason))
            self.kill_finished.emit([r.to_dict() for r in all_results])

        self._run("Kill Selected", work, done, err_title="Network Usage")