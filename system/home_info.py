"""
system/home_info.py
General system info collector for the Home tab.
Read-only. Returns a compact summary of the machine.
"""
import getpass
import platform
import subprocess

import psutil

from core.shell import run_ps
from core.configs import PS_TIMEOUT_S


def _windows_name() -> str:
    try:
        caption = run_ps(
            "(Get-CimInstance Win32_OperatingSystem).Caption",
            timeout=PS_TIMEOUT_S,
        )
        if caption:
            caption = caption.strip().splitlines()[0].strip()
            if caption:
                return caption
    except Exception:
        pass
    try:
        return f"{platform.system()} {platform.release()}"
    except Exception:
        return "Unavailable"


def _cpu_name() -> str:
    try:
        out = run_ps(
            "Get-CimInstance Win32_Processor | Select -First 1 -ExpandProperty Name",
            timeout=PS_TIMEOUT_S,
        )
        if out:
            return out.strip().splitlines()[0]
    except Exception:
        pass
    return platform.processor() or "Unavailable"


def _nvidia_vram_map() -> dict:
    """{lowercase nvidia-smi name: vram_gb} — corrects WMI's 4 GB cap."""
    out_map = {}
    try:
        out = subprocess.check_output(
            "nvidia-smi --query-gpu=name,memory.total "
            "--format=csv,noheader,nounits",
            shell=True, text=True, stderr=subprocess.DEVNULL, timeout=3,
        ).strip()
        if not out:
            return out_map
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            name, vram_mb = parts[0], parts[1]
            try:
                vram_gb = round(float(vram_mb) / 1024, 1)
            except (ValueError, TypeError):
                continue
            out_map[name.lower()] = vram_gb
    except Exception:
        pass
    return out_map


def _gpu_info() -> dict:
    """
    Returns:
        {
            "names":       [str, ...],     # all detected (backward compat)
            "primary":     str,            # discrete preferred
            "primary_vram_gb": float,
            "details":     [{name, vram_gb, kind}, ...],
        }
    """
    result = {
        "names": [],
        "primary": "Unavailable",
        "primary_vram_gb": 0.0,
        "details": [],
    }
    try:
        out = run_ps(
            "Get-CimInstance Win32_VideoController | "
            "Select -Property Name, AdapterRAM, DriverVersion | ConvertTo-Json",
            timeout=PS_TIMEOUT_S,
        )
        if not out:
            return result
        import json
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        nv_map = _nvidia_vram_map()
        details = []
        for g in data:
            name = (g.get("Name") or "").strip()
            if not name:
                continue
            vram_bytes = int(g.get("AdapterRAM") or 0)
            vram_gb = round(vram_bytes / (1024 ** 3), 1) if vram_bytes else 0.0
            # Override for NVIDIA (WMI AdapterRAM is uint32)
            for nv_name, nv_gb in nv_map.items():
                if nv_name in name.lower():
                    vram_gb = nv_gb
                    break

            n = name.lower()
            if any(k in n for k in ("nvidia", "geforce", "rtx", "gtx", "quadro")):
                kind = "discrete"
            elif any(k in n for k in ("radeon rx", "radeon pro", "radeon vii")):
                kind = "discrete"
            elif "radeon" in n and "graphics" in n:
                kind = "integrated"
            elif "intel" in n:
                kind = "discrete" if "arc" in n else "integrated"
            elif vram_gb >= 2.0:
                kind = "discrete"
            else:
                kind = "unknown"

            details.append({"name": name, "vram_gb": vram_gb, "kind": kind})

        result["names"] = [d["name"] for d in details]
        result["details"] = details

        if details:
            discrete = [d for d in details if d["kind"] == "discrete"]
            primary = (
                max(discrete, key=lambda d: d["vram_gb"])
                if discrete else details[0]
            )
            result["primary"] = primary["name"]
            result["primary_vram_gb"] = primary["vram_gb"]
    except Exception:
        pass
    return result


def _ram_total_gb() -> float:
    try:
        return round(psutil.virtual_memory().total / (1024 ** 3), 2)
    except Exception:
        return 0.0


def _disk_totals():
    total = 0
    free = 0
    try:
        for p in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(p.mountpoint)
                total += u.total
                free += u.free
            except Exception:
                continue
    except Exception:
        pass
    return round(total / (1024 ** 3), 1), round(free / (1024 ** 3), 1)


def get_home_info() -> dict:
    info = {
        "username":            "Unavailable",
        "device_name":         "Unavailable",
        "windows":             "Unavailable",
        "cpu_name":            "Unavailable",
        "gpu_names":           [],              # backward compat
        "gpu_primary":         "Unavailable",   # new
        "gpu_primary_vram_gb": 0.0,             # new
        "gpu_details":         [],              # new
        "ram_total_gb":        0.0,
        "disk_total_gb":       0.0,
        "disk_free_gb":        0.0,
    }

    try:
        info["username"] = getpass.getuser()
    except Exception:
        pass

    try:
        info["device_name"] = platform.node()
    except Exception:
        pass

    info["windows"] = _windows_name()
    info["cpu_name"] = _cpu_name()

    gpu = _gpu_info()
    info["gpu_names"] = gpu["names"]
    info["gpu_primary"] = gpu["primary"]
    info["gpu_primary_vram_gb"] = gpu["primary_vram_gb"]
    info["gpu_details"] = gpu["details"]

    info["ram_total_gb"] = _ram_total_gb()

    total, free = _disk_totals()
    info["disk_total_gb"] = total
    info["disk_free_gb"] = free

    return info