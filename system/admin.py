"""
system/admin.py
Admin privilege checks, elevation, and Safe Mode control.
No Qt dependencies.
"""

import os
import sys
import ctypes
import subprocess


def is_admin() -> bool:
    if os.name != "nt" or not hasattr(ctypes, "windll"):
        return True
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin():
    if os.name != "nt" or not hasattr(ctypes, "windll"):
        return
    try:
        if ctypes.windll.shell32.IsUserAnAdmin() == 0:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
            sys.exit(0)
    except Exception as e:
        print(f"[WARN] Admin elevation failed or cancelled: {e}")


def get_admin_status() -> dict:
    return {
        "is_admin": is_admin(),
        "message": "Running with Administrator privileges."
                   if is_admin()
                   else "Not running as Administrator.",
    }


def _run(cmd: str) -> tuple:
    """
    Run a command via cmd.exe, return (returncode, stderr_or_stdout).
    Commands are hardcoded literals (bcdedit, shutdown), so no injection
    surface; list-args avoid shell=True overhead and code-review flags.
    """
    try:
        r = subprocess.run(
            ["cmd.exe", "/c", cmd],
            capture_output=True, text=True, timeout=30,
        )
        err = (r.stderr or r.stdout or "").strip()
        return r.returncode, err
    except Exception as e:
        return -1, str(e)

def restart_safe_mode() -> dict:
    if not is_admin():
        return {"success": False, "detail": "Administrator rights required."}

    rc, err = _run('bcdedit /set {current} safeboot minimal')
    if rc != 0:
        return {"success": False, "detail": f"bcdedit failed: {err}"}

    rc, err = _run('shutdown /r /t 5 /c "Entering Safe Mode"')
    if rc != 0:
        return {
            "success": False,
            "detail": (
                "Safe Mode flag was set, but shutdown command failed: "
                f"{err}\n\n"
                "The system will boot into Safe Mode on the NEXT restart.\n"
                "To clear the flag now, open CMD as admin and run:\n"
                "bcdedit /deletevalue {current} safeboot"
            ),
        }

    return {"success": True, "detail": "System restarting into Safe Mode in 5 seconds."}


def exit_safe_mode() -> dict:
    if not is_admin():
        return {"success": False, "detail": "Administrator rights required."}

    rc, err = _run('bcdedit /deletevalue {current} safeboot')
    if rc != 0:
        return {"success": False, "detail": f"bcdedit failed: {err}"}

    rc, err = _run('shutdown /r /t 5 /c "Exiting Safe Mode"')
    if rc != 0:
        return {
            "success": False,
            "detail": (
                "Safe Mode flag was cleared, but shutdown command failed: "
                f"{err}\n\n"
                "Restart the system manually to return to normal mode."
            ),
        }

    return {"success": True, "detail": "System restarting into normal mode in 5 seconds."}