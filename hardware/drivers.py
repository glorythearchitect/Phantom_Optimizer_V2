"""
hardware/drivers.py
Handles system driver listing, backup, and restore operations.
No Qt imports. Returns structured data — controllers handle UI.
"""
import os
import subprocess
import wmi
from core.shell import run_ps, run_cmd
from core.configs import PS_TIMEOUT_S, ENABLE_DRIVER_UPDATE, DRIVER_UPDATE_URL


# ===============================
# DRIVER CHECK & STATUS
# ===============================

def list_driver_issues() -> list:
    """
    Returns a list of driver issues detected via WMI (Win32_PnPEntity).
    Each item: (Name, Status, ErrorCode, DeviceID)
    """
    try:
        c = wmi.WMI()
    except Exception:
        return [("WMI not available", "N/A", "-", "-")]

    issues = []
    seen = set()
    for device in c.Win32_PnPEntity():
        try:
            code = int(getattr(device, "ConfigManagerErrorCode", 0) or 0)
            name = getattr(device, "Name", "Unknown")
            devid = getattr(device, "DeviceID", "")
            status = getattr(device, "Status", "Unknown")
            key = (name, devid)
            if key in seen:
                continue
            seen.add(key)
            if code != 0 or status != "OK":
                if devid.startswith("ROOT\\"):
                    continue
                issues.append((name, status, code, devid))
        except Exception:
            continue

    if not issues:
        issues.append(("All drivers appear OK", "OK", 0, ""))
    return issues


def list_installed_drivers() -> list:
    """
    Returns ALL installed PnP devices as a list of tuples:
        (Name, Status, DeviceID)
    """
    try:
        c = wmi.WMI()
    except Exception:
        return []

    entries = []
    seen = set()
    for device in c.Win32_PnPEntity():
        try:
            name = getattr(device, "Name", "") or ""
            if not name:
                continue
            devid = getattr(device, "DeviceID", "") or ""
            status = getattr(device, "Status", "Unknown")
            key = (name, devid)
            if key in seen:
                continue
            seen.add(key)
            entries.append((name, status, devid))
        except Exception:
            continue
    return entries


# ===============================
# DRIVER BACKUP / RESTORE (no dialogs)
# ===============================

def backup_drivers(output_dir: str = "driver_backup") -> dict:
    """
    Export all third-party drivers to output_dir.
    Returns: {"success": bool, "path": str, "detail": str}
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        run_ps(f'Export-WindowsDriver -Online -Destination "{output_dir}"', timeout=120)
        return {
            "success": True,
            "path": os.path.abspath(output_dir),
            "detail": f"Drivers exported to {os.path.abspath(output_dir)}",
        }
    except Exception as e:
        return {"success": False, "path": "", "detail": str(e)}


def restore_driver(driver_path: str) -> dict:
    """
    Install a driver from a .inf file path.
    Returns: {"success": bool, "detail": str}
    """
    if not os.path.exists(driver_path):
        return {"success": False, "detail": f"File not found: {driver_path}"}
    try:
        run_cmd(f'pnputil /add-driver "{driver_path}" /install', timeout=30)
        return {
            "success": True,
            "detail": f"Driver installed: {os.path.basename(driver_path)}",
        }
    except Exception as e:
        return {"success": False, "detail": str(e)}


def check_online_updates() -> dict:
    """
    Placeholder for the future online driver updater.
    Returns: {"success": bool, "detail": str, "updates": list}
    """
    if not ENABLE_DRIVER_UPDATE:
        return {
            "success": False,
            "detail": "Online driver update feature is disabled.",
            "updates": [],
        }
    return {
        "success": True,
        "detail": f"Would query: {DRIVER_UPDATE_URL}",
        "updates": [],
    }


def repair_driver(name: str) -> dict:
    """
    Attempts to disable/re-enable a device to force driver reload.
    Returns: {"success": bool, "detail": str}
    """
    try:
        ps_cmd = (
            f'Get-PnpDevice | Where-Object {{$_.FriendlyName -like "*{name}*"}} '
            '| ForEach-Object {Disable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false; '
            'Enable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false}'
        )
        run_ps(ps_cmd, timeout=20)
        return {"success": True, "detail": f"Attempted repair for: {name}"}
    except Exception as e:
        return {"success": False, "detail": str(e)}