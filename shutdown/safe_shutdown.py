"""
shutdown/safe_shutdown.py
Native Windows shutdown/restart via the system command.
No process killing — Windows prompts open applications to close safely.
"""

import subprocess


def execute_shutdown(restart: bool = False, delay_s: int = 5) -> dict:
    action = "restart" if restart else "shutdown"
    try:
        delay = max(1, int(delay_s))
        flag = "/r" if restart else "/s"
        cmd = f'shutdown {flag} /t {delay} /c "Phantom Optimizer"'
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip() or "unknown error"
            return {
                "success": False,
                "detail": f"Windows {action} command failed: {err}",
                "action": action,
            }
        return {
            "success": True,
            "detail": f"Windows {action} scheduled in {delay} seconds.",
            "action": action,
        }
    except Exception as e:
        return {
            "success": False,
            "detail": f"Failed to schedule {action}: {e}",
            "action": action,
        }


def cancel_shutdown() -> dict:
    try:
        r = subprocess.run("shutdown /a", shell=True,
                           capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip() or "no pending shutdown"
            return {"success": False, "detail": f"Cancel failed: {err}"}
        return {"success": True, "detail": "Pending shutdown cancelled."}
    except Exception as e:
        return {"success": False, "detail": str(e)}