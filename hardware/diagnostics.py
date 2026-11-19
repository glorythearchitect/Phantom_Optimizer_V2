"""
hardware/diagnostics.py
Collects detailed system diagnostics using PowerShell and WMI.
Used for the Advanced tab and report exports.
"""

import platform
import json
import subprocess
import psutil
from core.shell import run_ps, ps_json
from core.configs import PS_TIMEOUT_S

def _nvidia_vram_map() -> dict:
    """
    {lowercase nvidia-smi name: vram_gb} — used to correct WMI AdapterRAM,
    which is a uint32 and caps at ~4 GB on cards with larger VRAM.
    """
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

def load_advanced_info() -> str:
    """
    Builds a complete hardware and system report as formatted text.
    Gathers data from PowerShell + psutil.
    Returns the result string (ready for export or UI display).
    """
    info = []

    # ========== CPU ==========
    info.append("===== CPU =====")
    try:
        cpu_data = ps_json(
            'Get-CimInstance Win32_Processor | Select Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed',
            timeout=PS_TIMEOUT_S
        )
        if isinstance(cpu_data, dict):
            cpu_data = [cpu_data]
        for c in cpu_data or []:
            info.append(f"CPU: {c.get('Name', '?')}")
            info.append(f"Cores: {c.get('NumberOfCores', '?')} | Threads: {c.get('NumberOfLogicalProcessors', '?')}")
            info.append(f"Base Clock: {c.get('MaxClockSpeed', '?')} MHz")
    except Exception:
        info.append("CPU: Unavailable")

    # ========== Motherboard & BIOS ==========
    info.append("\n===== Motherboard & BIOS =====")
    try:
        mb = ps_json('Get-CimInstance Win32_BaseBoard | Select Manufacturer,Product', timeout=PS_TIMEOUT_S)
        bios = ps_json('Get-CimInstance Win32_BIOS | Select Manufacturer,SMBIOSBIOSVersion,ReleaseDate', timeout=PS_TIMEOUT_S)
        if isinstance(mb, dict):
            info.append(f"{mb.get('Manufacturer', '?')} {mb.get('Product', '?')}")
        if isinstance(bios, dict):
            info.append(f"BIOS: {bios.get('Manufacturer', '?')} {bios.get('SMBIOSBIOSVersion', '?')} ({bios.get('ReleaseDate', '?')})")
    except Exception:
        info.append("Unavailable")

    # ========== GPU ==========
    info.append("\n===== GPU =====")
    try:
        gpus = ps_json(
            'Get-CimInstance Win32_VideoController | Select Name,AdapterRAM,DriverVersion,CurrentRefreshRate',
            timeout=PS_TIMEOUT_S
        )
        if isinstance(gpus, dict):
            gpus = [gpus]
        nv_map = _nvidia_vram_map()
        for g in gpus or []:
            name = g.get("Name", "?")
            vram_mb = int(g.get("AdapterRAM") or 0) // (1024 ** 2)
            # Correct for WMI AdapterRAM uint32 cap using nvidia-smi
            for nv_name, nv_gb in nv_map.items():
                if nv_name in (name or "").lower():
                    vram_mb = int(nv_gb * 1024)
                    break
            drv = g.get("DriverVersion", "?")
            hz = g.get("CurrentRefreshRate", "N/A")
            info.append(f"{name} ({vram_mb} MB) | Driver: {drv} | Refresh: {hz} Hz")
    except Exception:
        info.append("GPU: Unavailable")
        
    # ========== RAM ==========
    info.append("\n===== RAM =====")
    try:
        total_ram = round(psutil.virtual_memory().total / (1024 ** 3), 2)
        info.append(f"Total: {total_ram} GB")
        ram_data = ps_json(
            'Get-CimInstance Win32_PhysicalMemory | Select Manufacturer,Capacity,Speed',
            timeout=PS_TIMEOUT_S
        )
        if isinstance(ram_data, dict):
            ram_data = [ram_data]
        for r in ram_data or []:
            try:
                size_gb = int(r.get("Capacity", 0)) // (1024 ** 3)
            except Exception:
                size_gb = 0
            info.append(f"Stick: {r.get('Manufacturer', '?')} {size_gb} GB @ {r.get('Speed', '?')} MHz")
    except Exception:
        info.append("RAM: Unavailable")

    # ========== Storage ==========
    info.append("\n===== Storage =====")
    try:
        disks = ps_json(
            'Get-CimInstance Win32_DiskDrive | Select Model,Size,Status',
            timeout=PS_TIMEOUT_S
        )
        if isinstance(disks, dict):
            disks = [disks]
        for d in disks or []:
            try:
                size_gb = round(int(d.get("Size", 0)) / (1024 ** 3), 2)
            except Exception:
                size_gb = 0
            info.append(f"{d.get('Model', '?')} - {size_gb} GB (Health: {d.get('Status', 'Unknown')})")
    except Exception:
        info.append("Storage: Unavailable")

    # ========== OS Info ==========
    info.append("\n===== OS =====")
    try:
        os_info = f"{platform.system()} {platform.release()} Build {platform.version()}"
        info.append(os_info)
    except Exception:
        info.append("OS: Unavailable")

    # ========== Battery ==========
    info.append("\n===== Battery =====")
    try:
        battery = psutil.sensors_battery()
        if battery:
            status = "Charging" if battery.power_plugged else "On Battery"
            info.append(f"{battery.percent}% ({status})")
        else:
            info.append("No battery detected")
    except Exception:
        info.append("Battery: Unavailable")

    # ========== Security ==========
    info.append("\n===== Security =====")
    try:
        secure_boot = run_ps('(Get-ItemProperty -Path HKLM:\\SYSTEM\\CurrentControlSet\\Control\\SecureBoot\\State).UEFISecureBootEnabled')
        tpm = run_ps('Get-CimInstance -Namespace Root\\CIMv2\\Security\\MicrosoftTpm -Class Win32_Tpm | Select SpecVersion')
        defender = run_ps('Get-MpComputerStatus | Select AMServiceEnabled')
        info.append("Secure Boot: Enabled" if "1" in secure_boot else "Secure Boot: Disabled")
        info.append("TPM: Present" if "SpecVersion" in tpm else "TPM: Not Detected")
        info.append("Windows Defender: Active" if "True" in defender else "Windows Defender: Inactive")
    except Exception:
        info.append("Security: Unavailable")

    # ========== Network ==========
    info.append("\n===== Network =====")
    try:
        nets = ps_json(
            'Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {$_.IPEnabled -eq $true} | Select Description,IPAddress,Speed',
            timeout=PS_TIMEOUT_S
        )
        if isinstance(nets, dict):
            nets = [nets]
        for n in nets or []:
            ip = n.get("IPAddress", ["N/A"])
            if isinstance(ip, list):
                ip = ip[0]
            info.append(f"{n.get('Description','?')} | IP: {ip} | Speed: {n.get('Speed','?')} bps")
    except Exception:
        info.append("Network: Unavailable")

    return "\n".join(info)
