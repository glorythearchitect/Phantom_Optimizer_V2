"""
hardware/disks.py
Provides detailed disk and partition information for Phantom Optimizer.
Detects filesystem, partition style, type, usage stats, and SMART health.
"""

import os
import psutil
import wmi
from core.shell import ps_json
from core.configs import PS_TIMEOUT_S


def get_disk_health_map() -> dict:
    """
    Returns {FriendlyName: HealthStatus} using PowerShell Get-PhysicalDisk.
    Example:
        {'Samsung SSD 980': 'OK', 'WD Blue': 'Warning'}
    """
    health_map = {}
    try:
        pd = ps_json("Get-PhysicalDisk | Select FriendlyName, HealthStatus, OperationalStatus", timeout=PS_TIMEOUT_S)
        if isinstance(pd, list):
            for d in pd:
                name = str(d.get("FriendlyName", "")).strip()
                health = str(d.get("HealthStatus", "")).strip()
                status = str(d.get("OperationalStatus", "")).strip()
                if not name:
                    continue
                if any(x in health for x in ("Warning", "Degraded")) or "Degraded" in status:
                    health_map[name] = "Warning"
                elif any(x in health for x in ("Unhealthy", "Failed")) or "Failed" in status:
                    health_map[name] = "Unhealthy"
                elif any(x in health for x in ("Healthy", "OK")) or "OK" in status:
                    health_map[name] = "OK"
                else:
                    health_map[name] = "Unknown"
        elif isinstance(pd, dict):
            name = str(pd.get("FriendlyName", "")).strip()
            health = str(pd.get("HealthStatus", "")).strip()
            health_map[name] = health or "Unknown"
    except Exception:
        pass
    return health_map


def get_disk_info() -> list:
    """
    Return a list of dictionaries describing logical volumes.
    Each item includes:
        Device, Mountpoint, Type, FS, Size (GB), Used (GB), Free (GB),
        Partition Scheme, Media Type, Labels, Health
    """
    disks = []
    try:
        c = wmi.WMI()
    except Exception:
        c = None

    # --- Partition style + Media type map ---
    disk_map = {}
    gd = ps_json("Get-Disk | Select Number, PartitionStyle, MediaType, FriendlyName, Size", timeout=PS_TIMEOUT_S)
    if isinstance(gd, list):
        for d in gd:
            try:
                disk_map[int(d.get("Number", -1))] = d
            except Exception:
                continue
    elif isinstance(gd, dict):
        try:
            disk_map[int(gd.get("Number", -1))] = gd
        except Exception:
            pass

    # --- SMART / Health map ---
    health_map = get_disk_health_map()

    # --- Collect logical disks ---
    if c is not None:
        try:
            for disk in c.Win32_DiskDrive():
                num = None
                try:
                    if disk.DeviceID and "PHYSICALDRIVE" in disk.DeviceID.upper():
                        num = int(disk.DeviceID.split("PHYSICALDRIVE")[1])
                except Exception:
                    pass

                part_style = "Unknown"
                media_type = getattr(disk, "MediaType", "Unknown")
                if num is not None and num in disk_map:
                    part_style = disk_map[num].get("PartitionStyle", "Unknown")
                    media_type_ps = disk_map[num].get("MediaType") or ""
                    if media_type_ps:
                        media_type = media_type_ps

                health_status = "Unknown"
                try:
                    friendly = disk.Caption or getattr(disk, "Model", "")
                    for key in health_map.keys():
                        if key.lower() in friendly.lower():
                            health_status = health_map[key]
                            break
                except Exception:
                    pass

                # Walk partitions
                try:
                    parts = disk.associators("Win32_DiskDriveToDiskPartition")
                except Exception:
                    parts = []

                for part in parts:
                    try:
                        logicals = part.associators("Win32_LogicalDiskToPartition")
                    except Exception:
                        logicals = []

                    for logical in logicals:
                        mount = logical.DeviceID
                        if not mount.endswith("\\"):
                            mount += "\\"

                        try:
                            usage = psutil.disk_usage(mount)
                            total_gb = round(usage.total / (1024 ** 3), 2)
                            used_gb = round(usage.used / (1024 ** 3), 2)
                            free_gb = round(usage.free / (1024 ** 3), 2)
                        except Exception:
                            total_gb = used_gb = free_gb = 0

                        fstype = "Unknown"
                        try:
                            for p in psutil.disk_partitions(all=True):
                                if p.device.upper().startswith(logical.DeviceID.upper()):
                                    fstype = p.fstype or "Unknown"
                                    break
                        except Exception:
                            pass

                        labels = classify_volume(mount, part_style, media_type)
                        disks.append({
                            "Device": logical.DeviceID,
                            "Mountpoint": mount,
                            "Type": "Local Disk",
                            "FS": fstype,
                            "Size (GB)": total_gb,
                            "Used (GB)": used_gb,
                            "Free (GB)": free_gb,
                            "Partition Scheme": part_style,
                            "Media Type": media_type,
                            "Health": health_status,
                            "Labels": labels
                        })
        except Exception:
            pass

    # --- Add unassociated removable drives ---
    try:
        for p in psutil.disk_partitions(all=False):
            if not any(d["Device"].upper().startswith(p.device[:2].upper()) for d in disks):
                try:
                    usage = psutil.disk_usage(p.mountpoint)
                    total_gb = round(usage.total / (1024 ** 3), 2)
                    used_gb = round(usage.used / (1024 ** 3), 2)
                    free_gb = round(usage.free / (1024 ** 3), 2)
                except Exception:
                    total_gb = used_gb = free_gb = 0
                disks.append({
                    "Device": p.device,
                    "Mountpoint": p.mountpoint,
                    "Type": "Removable" if "removable" in (p.opts or "").lower() else "Local Disk",
                    "FS": p.fstype or "Unknown",
                    "Size (GB)": total_gb,
                    "Used (GB)": used_gb,
                    "Free (GB)": free_gb,
                    "Partition Scheme": "Unknown",
                    "Media Type": "Unknown",
                    "Health": "Unknown",
                    "Labels": "External"
                })
    except Exception:
        pass

    return disks


def classify_volume(mount: str, part_style: str, media_type: str) -> str:
    """
    Classifies volume role and type using both WMI and system vars.
    Always returns at least Local/External + GPT/MBR if detectable.
    """
    labels = []

    # Base type
    if "USB" in (media_type or "").upper() or "Removable" in (media_type or ""):
        labels.append("External")
    else:
        labels.append("Local")

    # Partition scheme
    if "GPT" in (part_style or "").upper():
        labels.append("GPT")
    elif "MBR" in (part_style or "").upper():
        labels.append("MBR")

    # WMI enhanced checks
    try:
        import wmi
        c = wmi.WMI()
        for part in c.Win32_DiskPartition():
            for ld in part.associators("Win32_LogicalDiskToPartition"):
                if ld.DeviceID == mount.rstrip("\\"):
                    if getattr(part, "BootPartition", False):
                        labels.append("Boot")
                    if getattr(part, "PrimaryPartition", False):
                        labels.append("Primary")
                    # Detect dynamic disks from partition Type
                    if "dynamic" in str(getattr(part, "Type", "")).lower():
                        labels.append("Dynamic")
                    # Detect system drive
                    sys_drive = os.getenv("SystemDrive", "C:")
                    if ld.DeviceID.upper().startswith(sys_drive.upper()):
                        labels.append("System")
                    break
    except Exception:
        pass

    # Ensure at least GPT/MBR or Unknown label
    if not any(x in labels for x in ("GPT", "MBR")):
        labels.append("Unknown")

    # Clean duplicates
    return " | ".join(sorted(set(labels)))
