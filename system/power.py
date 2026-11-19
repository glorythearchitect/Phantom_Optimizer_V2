"""
system/power.py
Power plan management via Windows 'powercfg'.
Robust parser that tolerates localized and vendor-specific output.
"""

import re
import subprocess
import psutil


_GUID_RE = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


def list_power_plans() -> list:
    """
    Returns a list of tuples: (GUID, Name, Active)
    """
    plans = []
    try:
        out = subprocess.check_output(
            "powercfg /L", shell=True, text=True,
            stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            m = _GUID_RE.search(line)
            if not m:
                continue
            guid = m.group(1)
            name_m = re.search(r"\(([^)]+)\)", line)
            name = name_m.group(1).strip() if name_m else guid
            active = "*" in line
            plans.append((guid, name, active))
    except Exception:
        pass
    return plans


def get_active_plan() -> str:
    try:
        out = subprocess.check_output(
            "powercfg /GETACTIVESCHEME", shell=True, text=True,
            stderr=subprocess.DEVNULL
        )
        m = re.search(r"\(([^)]+)\)", out)
        if m:
            return m.group(1).strip()
        return out.strip() or "Unknown"
    except Exception:
        return "Unknown"


def set_power_plan(name_or_guid: str) -> bool:
    try:
        plans = list_power_plans()
        match = None
        target = name_or_guid.strip().lower()
        for guid, name, _ in plans:
            if target in (guid.lower(), name.lower()):
                match = guid
                break
        if not match:
            return False
        subprocess.run(f"powercfg /S {match}", shell=True, check=False)
        return True
    except Exception:
        return False


def get_power_status() -> str:
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return "Unknown"
        return "AC" if battery.power_plugged else "Battery"
    except Exception:
        return "Unknown"


def auto_switch_power_plan(ac_plan="Balanced", battery_plan="Power Saver") -> str:
    try:
        status = get_power_status()
        if status == "AC":
            set_power_plan(ac_plan)
            return ac_plan
        elif status == "Battery":
            set_power_plan(battery_plan)
            return battery_plan
        return "No Change"
    except Exception:
        return "Error"


def format_power_status() -> str:
    plans = list_power_plans()
    active = [p for p in plans if p[2]]
    active_name = active[0][1] if active else "Unknown"
    src = get_power_status()
    return f"Active Plan: {active_name}\nPower Source: {src}"