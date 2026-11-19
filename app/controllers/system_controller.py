"""
app/controllers/system_controller.py
System tab: Power, Privacy, Windows Update, Admin status, Safe Mode, Shutdown.
"""
from PyQt6.QtCore import QObject, pyqtSignal

from core.threads import Worker, thread_pool
from system import power, privacy, windows_update, admin
from shutdown import safe_shutdown


class SystemController(QObject):
    content_ready      = pyqtSignal(str, dict)
    action_done        = pyqtSignal(str, bool, str)
    operation_started  = pyqtSignal(str)
    operation_finished = pyqtSignal(str)
    error_occurred     = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []
        self._busy = False
        self._current_op = ""

    def _run(self, op_name, fn, on_done, err_title="System"):
        if self._busy:
            self.error_occurred.emit("System Busy",
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

    # ---------------- Power ----------------

    def load_power(self):
        def work():
            plans = power.list_power_plans()
            return {
                "kind": "table",
                "columns": ["Plan Name", "GUID", "Active"],
                "rows": [[name, guid, "Yes" if active else ""]
                         for guid, name, active in plans],
            }
        self._run("Power Load", work,
                  lambda r: self.content_ready.emit("Power", r or {}))

    def set_power_plan(self, name_or_guid):
        def work():
            return {"action": "Set Power Plan",
                    "success": power.set_power_plan(name_or_guid)}
        def done(r):
            if r:
                msg = "Plan activated." if r["success"] else "Failed to switch plan."
                self.action_done.emit(r["action"], r["success"], msg)
        self._run("Set Power Plan", work, done)

    def auto_switch_power(self):
        def work():
            return {"action": "Auto Switch",
                    "result": power.auto_switch_power_plan()}
        def done(r):
            if r:
                self.action_done.emit("Auto Switch", True,
                                      f"Switched to: {r.get('result', '?')}")
        self._run("Auto Switch", work, done)

    # ---------------- Privacy ----------------

    def load_privacy(self):
        def work():
            status = privacy.get_privacy_status()
            return {
                "kind": "text",
                "payload": privacy.format_privacy_status(status),
            }
        self._run("Privacy Load", work,
                  lambda r: self.content_ready.emit("Privacy", r or {}))

    def set_privacy_all(self, enable):
        def work():
            result = privacy.toggle_all_privacy(enable)
            ok_count = sum(1 for v in result.values() if v)
            return {"action": "Privacy All",
                    "success": ok_count == len(result),
                    "count": ok_count,
                    "total": len(result)}
        def done(r):
            if r:
                self.action_done.emit(
                    r["action"], r["success"],
                    f"Applied to {r['count']}/{r['total']} items."
                )
        self._run("Privacy All", work, done)

    # ---------------- Windows Update ----------------

    def load_update(self):
        def work():
            status = windows_update.get_update_status()
            return {
                "kind": "text",
                "payload": windows_update.format_update_status(status),
            }
        self._run("Update Load", work,
                  lambda r: self.content_ready.emit("Windows Update", r or {}))

    def pause_updates(self, days=7):
        def work():
            return {"action": "Pause Updates",
                    "success": windows_update.pause_updates(days),
                    "days": days}
        def done(r):
            if r:
                msg = (f"Updates paused for {r['days']} days." if r["success"]
                       else "Failed to pause updates.")
                self.action_done.emit(r["action"], r["success"], msg)
        self._run("Pause Updates", work, done)

    # ---------------- Admin status ----------------

    def load_admin(self):
        def work():
            s = admin.get_admin_status()
            return {
                "kind": "text",
                "payload": f"Administrator: {'YES' if s['is_admin'] else 'NO'}\n\n"
                           f"{s['message']}",
            }
        self._run("Admin Load", work,
                  lambda r: self.content_ready.emit("Admin", r or {}))

    # ---------------- Safe Mode ----------------

    def load_safe_mode(self):
        def work():
            return {
                "kind": "text",
                "payload": "Safe Mode\n\n"
                           "Enter Safe Mode: configures the system to boot into\n"
                           "Safe Mode on the next restart and restarts immediately.\n\n"
                           "Exit Safe Mode: removes the Safe Mode boot flag and\n"
                           "restarts normally.\n\n"
                           "Both actions close all applications.",
            }
        self._run("Safe Mode Load", work,
                  lambda r: self.content_ready.emit("Safe Mode", r or {}))

    def enter_safe_mode(self):
        def work():
            return {"action": "Enter Safe Mode", **admin.restart_safe_mode()}
        def done(r):
            if r:
                self.action_done.emit(r["action"], r.get("success", False),
                                      r.get("detail", ""))
        self._run("Enter Safe Mode", work, done)

    def exit_safe_mode(self):
        def work():
            return {"action": "Exit Safe Mode", **admin.exit_safe_mode()}
        def done(r):
            if r:
                self.action_done.emit(r["action"], r.get("success", False),
                                      r.get("detail", ""))
        self._run("Exit Safe Mode", work, done)

    # ---------------- Safe Shutdown ----------------

    def load_shutdown(self):
        def work():
            return {
                "kind": "text",
                "payload": "System Shutdown\n\n"
                           "Windows will prompt open applications to close\n"
                           "and then shut down. Unsaved work may be lost.\n\n"
                           "A 5-second delay is applied so you can cancel via\n"
                           "the standard Windows prompt.",
            }
        self._run("Shutdown Load", work,
                  lambda r: self.content_ready.emit("Shutdown", r or {}))

    def execute_shutdown(self, restart=False):
        def work():
            return safe_shutdown.execute_shutdown(restart=restart)
        def done(r):
            if r:
                self.action_done.emit(r.get("action", "Shutdown"),
                                      r.get("success", False),
                                      r.get("detail", ""))
        self._run("Shutdown" if not restart else "Restart", work, done)