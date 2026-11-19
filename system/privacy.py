"""
system/privacy.py
Privacy controls for Phantom Optimizer.
All changes are reversible registry writes.
"""

import winreg
from typing import Dict

_PRIVACY_PATHS = {
    "Telemetry": ("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0, 3),
    "AdvertisingID": ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0, 1),
    "TipsAndSuggestions": ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SubscribedContent-338387Enabled", 0, 1),
    "TailoredExperiences": ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 0, 1),
    "ActivityTracking": ("HKCU", r"SOFTWARE\Policies\Microsoft\Windows\System", "PublishUserActivities", 0, 1),
}


def _get_hive(hive_name: str):
    return {
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
    }.get(hive_name, winreg.HKEY_CURRENT_USER)


def _read_value(hive, path: str, name: str):
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, name)
            return val
    except OSError:
        return None


def _write_value(hive, path: str, name: str, value: int):
    try:
        with winreg.CreateKeyEx(hive, path, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
            return True
    except OSError:
        return False


def get_privacy_status() -> Dict[str, str]:
    status = {}
    for key, (hive_name, path, name, off_val, on_val) in _PRIVACY_PATHS.items():
        hive = _get_hive(hive_name)
        val = _read_value(hive, path, name)
        if val is None:
            status[key] = "Not Configured (Windows Default)"
        elif val == on_val:
            status[key] = "Enabled"
        elif val == off_val:
            status[key] = "Disabled"
        else:
            status[key] = f"Custom ({val})"
    return status


def set_privacy_option(option: str, enable: bool) -> bool:
    if option not in _PRIVACY_PATHS:
        return False
    hive_name, path, name, off_val, on_val = _PRIVACY_PATHS[option]
    hive = _get_hive(hive_name)
    return _write_value(hive, path, name, on_val if enable else off_val)


def toggle_all_privacy(enable: bool) -> Dict[str, bool]:
    result = {}
    for key in _PRIVACY_PATHS.keys():
        result[key] = set_privacy_option(key, enable)
    return result


def format_privacy_status(status: Dict[str, str]) -> str:
    lines = [f"{k}: {v}" for k, v in status.items()]
    return "\n".join(lines)