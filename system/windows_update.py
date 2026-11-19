"""
system/windows_update.py
Windows Update pause/status using PowerShell + Get-HotFix.
"""

from datetime import datetime
from core.shell import run_ps


def get_update_status() -> dict:
    """
    Returns a dictionary with key update status details.
    Uses PowerShell Get-WindowsUpdateSettings (Win10+) if available,
    otherwise falls back to registry / Get-HotFix info.
    """
    status = {
        "Pause State": "Unknown",
        "Paused Until": "N/A",
        "Automatic Updates": "Unknown",
        "Last Update": "Unknown",
    }

    # --- Pause state & AU settings ---
    try:
        cmd = (
            'Get-WindowsUpdateSettings | Select -Property '
            'IsPauseFeatureUpdatesEnabled, IsPauseQualityUpdatesEnabled, '
            'PauseFeatureUpdatesStartTime, PauseQualityUpdatesStartTime, '
            'PauseFeatureUpdatesEndTime, PauseQualityUpdatesEndTime, '
            'BranchReadinessLevel, DeferFeatureUpdatesPeriodInDays, DeferQualityUpdatesPeriodInDays '
            '| ConvertTo-Json -Depth 3'
        )
        data = run_ps(cmd)
        if data:
            import json
            s = json.loads(data)
            pause_enabled = (
                s.get("IsPauseFeatureUpdatesEnabled")
                or s.get("IsPauseQualityUpdatesEnabled")
            )
            status["Pause State"] = "Paused" if pause_enabled else "Active"
            status["Paused Until"] = (
                s.get("PauseFeatureUpdatesEndTime")
                or s.get("PauseQualityUpdatesEndTime")
                or "N/A"
            )
    except Exception:
        pass

    # --- Automatic updates state ---
    try:
        result = run_ps(
            '(Get-ItemProperty -Path "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU").NoAutoUpdate'
        )
        if result:
            status["Automatic Updates"] = "Disabled" if "1" in result else "Enabled"
    except Exception:
        status["Automatic Updates"] = "Enabled"

    # --- Last update info — modern replacement for deprecated `wmic qfe` ---
    try:
        out = run_ps(
            "Get-HotFix | Sort-Object InstalledOn -Descending "
            "| Select -First 1 -Property HotFixID, InstalledOn "
            "| ConvertTo-Json -Depth 2"
        )
        if out:
            import json
            d = json.loads(out)
            if isinstance(d, list) and d:
                d = d[0]
            if isinstance(d, dict) and d.get("HotFixID"):
                installed = d.get("InstalledOn") or ""
                status["Last Update"] = (
                    f"{d.get('HotFixID', '?')} ({str(installed)[:10]})"
                    .replace(" ()", "")
                    .replace("(", "")
                    .replace(")", "")
                    .strip()
                )
    except Exception:
        pass

    return status


def pause_updates(days: int = 7) -> bool:
    """Pauses both feature and quality updates for N days (1-35)."""
    days = max(1, min(days, 35))
    try:
        cmd = (
            f"Set-WindowsUpdate -PauseUpdates -Days {days}; "
            "Write-Output 'OK'"
        )
        result = run_ps(cmd, timeout=15)
        return "OK" in str(result)
    except Exception:
        return False


def format_update_status(status: dict) -> str:
    """Simple multi-line string ready for UI display."""
    return (
        f"Pause State: {status.get('Pause State','Unknown')}\n"
        f"Paused Until: {status.get('Paused Until','N/A')}\n"
        f"Automatic Updates: {status.get('Automatic Updates','Unknown')}\n"
        f"Last Update: {status.get('Last Update','Unknown')}\n"
        f"Last Checked: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )