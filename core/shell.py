"""
core/shell.py
PowerShell / CMD wrappers with stderr suppressed and strict timeouts.
Uses subprocess list-args — no shell=True, no quote-escaping pitfalls.
"""
import subprocess
import json


def run_ps(cmd: str, timeout: int = 8) -> str:
    """Run a PowerShell command, return stdout (stripped) or "" on failure."""
    try:
        return subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", cmd],
            text=True, stderr=subprocess.DEVNULL, timeout=timeout,
        ).strip()
    except Exception:
        return ""


def ps_json(cmd: str, timeout: int = 8, depth: int = 4):
    """
    Run a PowerShell command, parse ConvertTo-Json output.
    stderr is discarded — merging it into stdout would break json.loads()
    on any PowerShell warning.
    """
    try:
        full_cmd = f"{cmd} | ConvertTo-Json -Depth {depth}"
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", full_cmd],
            text=True, stderr=subprocess.DEVNULL, timeout=timeout,
        )
        if output:
            return json.loads(output)
    except Exception:
        pass
    return None


def run_cmd(cmd: str, timeout: int = 8) -> str:
    """Run a plain command via cmd.exe, return stdout or "" on failure."""
    try:
        return subprocess.check_output(
            ["cmd.exe", "/c", cmd],
            text=True, stderr=subprocess.DEVNULL, timeout=timeout,
        ).strip()
    except Exception:
        return ""


def ping_test(host: str = "8.8.8.8", count: int = 1) -> bool:
    """Basic connectivity test — True if reachable."""
    try:
        out = subprocess.check_output(
            ["ping", "-n", str(count), host],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
        return "TTL=" in out
    except Exception:
        return False