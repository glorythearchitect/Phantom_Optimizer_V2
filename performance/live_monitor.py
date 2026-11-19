"""
performance/live_monitor.py
Collects live system stats for the Performance tab.
No Qt imports. Degrades gracefully when sensors unavailable.
"""

import subprocess
import time

import psutil

from hardware.sensors import get_cpu_temp, get_gpu_temp


# nvidia-smi cache — each call reloads the NVIDIA WDDM layer (~150-250 ms
# startup cost on some systems). Called at 1 Hz from the performance tab,
# this is expensive and heats laptops for no measurable gain. Cache for
# 2 seconds so the visual update rate is preserved but the underlying
# command runs at ~0.5 Hz.
_NVIDIA_CACHE = {"t": 0.0, "u": None, "temp": None}
_NVIDIA_CACHE_TTL = 2.0


def _gpu_stats_nvidia() -> tuple:
    """Cached nvidia-smi query returning (usage_pct, temp_c) or (None, None)."""
    now = time.monotonic()
    if now - _NVIDIA_CACHE["t"] < _NVIDIA_CACHE_TTL:
        return (_NVIDIA_CACHE["u"], _NVIDIA_CACHE["temp"])

    _NVIDIA_CACHE["t"] = now
    _NVIDIA_CACHE["u"] = None
    _NVIDIA_CACHE["temp"] = None

    try:
        out = subprocess.check_output(
            "nvidia-smi --query-gpu=utilization.gpu,temperature.gpu "
            "--format=csv,noheader,nounits",
            shell=True, text=True, stderr=subprocess.DEVNULL, timeout=3,
        ).strip()
        if not out:
            return (None, None)
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        if not lines:
            return (None, None)
        usages, temps = [], []
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                try:
                    usages.append(float(parts[0]))
                except ValueError:
                    pass
                try:
                    temps.append(float(parts[1]))
                except ValueError:
                    pass
        u = round(sum(usages) / len(usages), 1) if usages else None
        t = round(sum(temps) / len(temps), 1) if temps else None
        _NVIDIA_CACHE["u"] = u
        _NVIDIA_CACHE["temp"] = t
        return (u, t)
    except Exception:
        return (None, None)


def _disk_usage_pct() -> float | None:
    try:
        total = used = 0
        for p in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(p.mountpoint)
                total += u.total
                used += u.used
            except Exception:
                continue
        if total == 0:
            return None
        return round((used / total) * 100, 1)
    except Exception:
        return None


def get_live_stats() -> dict:
    """One snapshot of live metrics. Each value is a number or None."""
    cpu = None
    try:
        cpu = round(psutil.cpu_percent(interval=None), 1)
    except Exception:
        pass

    mem = None
    try:
        mem = round(psutil.virtual_memory().percent, 1)
    except Exception:
        pass

    disk = _disk_usage_pct()

    gpu, gpu_temp = _gpu_stats_nvidia()
    if gpu_temp is None:
        gpu_temp = get_gpu_temp()  # WMI fallback

    cpu_temp = get_cpu_temp()

    return {
        "cpu": cpu,
        "cpu_temp": cpu_temp,
        "gpu": gpu,
        "gpu_temp": gpu_temp,
        "mem": mem,
        "disk": disk,
    }