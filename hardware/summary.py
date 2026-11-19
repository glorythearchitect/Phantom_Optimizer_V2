"""
hardware/summary.py
Per-category hardware text blocks for the Hardware Info tab.
Reuses existing modules; no new PowerShell logic. No caching.
"""
from hardware.diagnostics import load_advanced_info
from hardware.disks import get_disk_info
from hardware.drivers import list_driver_issues, list_installed_drivers
from hardware.sensors import get_cpu_temp, get_gpu_temp


def _split_diagnostics() -> dict:
    raw = load_advanced_info()
    sections = {
        "CPU": "", "GPU": "", "MEMORY": "", "DISKS": "",
        "DRIVERS": "", "SENSORS": ""
    }

    current = None
    buf = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("=====") and stripped.endswith("====="):
            if current and buf:
                sections[current] = "\n".join(buf).strip()
            header = stripped.strip("= ").upper()
            if "CPU" in header:
                current = "CPU"
            elif "GPU" in header:
                current = "GPU"
            elif "RAM" in header:
                current = "MEMORY"
            elif "STORAGE" in header:
                current = "DISKS"
            else:
                current = None
            buf = []
        elif current:
            buf.append(line)
    if current and buf:
        sections[current] = "\n".join(buf).strip()

    return sections


def get_cpu_info() -> str:
    return _split_diagnostics().get("CPU") or "CPU: Unavailable"


def get_gpu_info() -> str:
    return _split_diagnostics().get("GPU") or "GPU: Unavailable"


def get_memory_info() -> str:
    return _split_diagnostics().get("MEMORY") or "Memory: Unavailable"


def get_disks_info() -> str:
    lines = []
    for d in get_disk_info():
        lines.append(
            f"{d['Mountpoint']}  [{d['Type']} | {d['Partition Scheme']} | {d['Media Type']}]"
        )
        lines.append(
            f"  Size: {d['Size (GB)']} GB | Used: {d['Used (GB)']} GB | Free: {d['Free (GB)']} GB"
        )
        lines.append(f"  FS: {d['FS']} | Health: {d['Health']} | {d['Labels']}")
        lines.append("")
    return "\n".join(lines).strip() or "No disks detected."


def get_drivers_info() -> str:
    lines = []

    # ---- PROBLEM DEVICES ----
    lines.append("PROBLEM DEVICES")
    lines.append("──────────────────────────────")
    issues = list_driver_issues()
    has_issues = not (len(issues) == 1 and issues[0][0] == "All drivers appear OK")
    if has_issues:
        for name, status, code, devid in issues:
            lines.append(f"• {name}  [{status}]  code={code}")
            if devid:
                lines.append(f"    {devid}")
    else:
        lines.append("None detected.")

    lines.append("")

    # ---- INSTALLED DEVICES ----
    installed = list_installed_drivers()
    lines.append(f"INSTALLED DEVICES ({len(installed)})")
    lines.append("──────────────────────────────")

    CAP = 100
    for name, status, _devid in installed[:CAP]:
        lines.append(f"• {name}  [{status}]")
    if len(installed) > CAP:
        lines.append(f"... and {len(installed) - CAP} more")

    return "\n".join(lines).strip() or "No driver data."


def get_sensors_info() -> str:
    cpu_t = get_cpu_temp()
    gpu_t = get_gpu_temp()
    return (
        f"CPU Temperature: {cpu_t} °C\n"
        f"GPU Temperature: {gpu_t} °C"
    )