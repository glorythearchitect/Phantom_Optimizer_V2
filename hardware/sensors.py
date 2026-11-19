"""
hardware/sensors.py
Provides CPU, GPU, and system sensor readings for Phantom Optimizer.
Includes temperature, disk I/O, and network monitoring (future-ready).
"""

import subprocess
import psutil
import wmi
from core.configs import PS_TIMEOUT_S


# ===============================
# CPU TEMPERATURE
# ===============================

def get_cpu_temp():
    """
    Returns the current CPU temperature (°C) if available, otherwise "--".
    Uses WMI (root\\wmi) → MSAcpi_ThermalZoneTemperature.
    """
    try:
        c = wmi.WMI(namespace="root\\wmi")
        temps = c.MSAcpi_ThermalZoneTemperature()
        if temps:
            val = int((temps[0].CurrentTemperature / 10) - 273.15)
            if -30 <= val <= 120:
                return val
    except Exception:
        pass
    return "--"


# ===============================
# GPU TEMPERATURE
# ===============================

def get_gpu_temp():
    """
    Returns GPU temperature (°C) if available, otherwise "--".
    Tries NVIDIA SMI → PowerShell fallback.
    """
    # --- NVIDIA GPU ---
    try:
        result = subprocess.check_output(
            "nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader",
            shell=True, text=True, stderr=subprocess.DEVNULL, timeout=PS_TIMEOUT_S
        ).strip()
        if result.isdigit():
            val = int(result)
            if -30 <= val <= 120:
                return val
    except Exception:
        pass

    # --- AMD/Intel fallback ---
    try:
        ps_cmd = 'Get-CimInstance MSAcpi_ThermalZoneTemperature | Select-Object CurrentTemperature | ConvertTo-Json'
        result = subprocess.check_output(
            f'powershell -NoProfile -Command "{ps_cmd}"',
            shell=True, text=True, stderr=subprocess.DEVNULL, timeout=PS_TIMEOUT_S
        )
        import json
        data = json.loads(result)
        if isinstance(data, dict):
            data = [data]
        if data:
            val = int((data[0]["CurrentTemperature"] / 10) - 273.15)
            if -30 <= val <= 120:
                return val
    except Exception:
        pass

    return "--"


# ===============================
# DISK I/O MONITOR (future)
# ===============================

def get_disk_io():
    """
    Returns total disk read/write in MB since boot.
    Placeholder for live I/O monitoring (for v2 expansion).
    """
    try:
        io = psutil.disk_io_counters()
        read_mb = round(io.read_bytes / (1024 ** 2), 2)
        write_mb = round(io.write_bytes / (1024 ** 2), 2)
        return {"Read (MB)": read_mb, "Write (MB)": write_mb}
    except Exception:
        return {"Read (MB)": 0, "Write (MB)": 0}


# ===============================
# NETWORK USAGE MONITOR (future)
# ===============================

def get_network_usage():
    """
    Returns total network traffic in MB since boot.
    Placeholder for live network usage monitoring.
    """
    try:
        io = psutil.net_io_counters()
        sent_mb = round(io.bytes_sent / (1024 ** 2), 2)
        recv_mb = round(io.bytes_recv / (1024 ** 2), 2)
        return {"Sent (MB)": sent_mb, "Received (MB)": recv_mb}
    except Exception:
        return {"Sent (MB)": 0, "Received (MB)": 0}
