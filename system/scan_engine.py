"""
system/scan_engine.py
Progress-enabled scan functions for the Scan tab.

Each scan:
  - Emits progress via progress_cb(pct: int, message: str)
  - Honors cancellation via cancel.is_set()
  - Returns a structured dict, or None if cancelled
  - Is read-only. No system modification. No process termination.

Full / Phantom / Hardware scans reuse the same individual sub-scanners.
Software scan uses registry uninstall keys only (no Store apps).
"""

import os
import platform
import subprocess
import winreg

import psutil

from core.shell import run_ps
from core.configs import PS_TIMEOUT_S

# ---------- helpers ----------

def _check_cancel(cancel) -> bool:
    return cancel is not None and cancel.is_set()


def _emit(progress_cb, pct: int, message: str):
    if progress_cb is not None:
        try:
            progress_cb(int(pct), str(message))
        except Exception:
            pass


# ---------- individual sub-scanners ----------

def _scan_cpu():
    """Return (status, text). Status: OK | WARN | FAIL | N/A."""
    try:
        cpu_name = "Unknown"
        try:
            out = run_ps(
                "Get-CimInstance Win32_Processor | Select -First 1 -ExpandProperty Name",
                timeout=PS_TIMEOUT_S,
            )
            if out:
                cpu_name = out.strip().splitlines()[0]
        except Exception:
            pass

        usage = psutil.cpu_percent(interval=0.5)
        cores = psutil.cpu_count(logical=False) or 0
        threads = psutil.cpu_count(logical=True) or 0

        status = "WARN" if usage > 90 else "OK"
        text = f"{cpu_name} ({cores}C/{threads}T, {usage:.0f}% usage)"
        return (status, text)
    except Exception as e:
        return ("FAIL", f"CPU scan failed: {e}")


def _scan_gpu():
    try:
        gpus = []
        try:
            out = run_ps(
                "Get-CimInstance Win32_VideoController | Select -ExpandProperty Name",
                timeout=PS_TIMEOUT_S,
            )
            if out:
                gpus = [line.strip() for line in out.splitlines() if line.strip()]
        except Exception:
            pass

        if not gpus:
            return ("N/A", "No GPU detected")

        return ("OK", " | ".join(gpus))
    except Exception as e:
        return ("FAIL", f"GPU scan failed: {e}")


def _scan_memory():
    try:
        mem = psutil.virtual_memory()
        total_gb = round(mem.total / (1024 ** 3), 2)
        usage_pct = mem.percent
        status = "OK" if usage_pct < 90 else "WARN"
        return (status, f"{total_gb} GB, {usage_pct:.0f}% used")
    except Exception as e:
        return ("FAIL", f"Memory scan failed: {e}")


def _scan_disk():
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
            return ("N/A", "No disks detected")

        free_pct = ((total - used) / total) * 100
        status = "OK" if free_pct > 15 else "WARN"
        return (status, f"{round(total / (1024 ** 3), 1)} GB total, {free_pct:.0f}% free")
    except Exception as e:
        return ("FAIL", f"Storage scan failed: {e}")


def _scan_os():
    try:
        caption = ""
        try:
            out = run_ps(
                "(Get-CimInstance Win32_OperatingSystem).Caption",
                timeout=PS_TIMEOUT_S,
            )
            if out:
                caption = out.strip().splitlines()[0].strip()
        except Exception:
            pass
        if not caption:
            caption = f"{platform.system()} {platform.release()}"
        return ("OK", caption)
    except Exception as e:
        return ("FAIL", f"OS scan failed: {e}")


def _scan_security():
    try:
        defender_av = "Unknown"
        firewall = "Unknown"
        secure_boot = "Unknown"

        # --- Antivirus (Windows Defender AV service) ---
        try:
            out = run_ps("(Get-MpComputerStatus).AMServiceEnabled", timeout=PS_TIMEOUT_S)
            if out:
                defender_av = "Active" if out.strip().lower() in ("true", "1") else "Inactive"
        except Exception:
            pass

        # --- Firewall (check all three profiles) ---
        try:
            out = run_ps(
                "Get-NetFirewallProfile | Select-Object -ExpandProperty Enabled",
                timeout=PS_TIMEOUT_S,
            )
            if out:
                values = [l.strip().lower() for l in out.splitlines() if l.strip()]
                enabled = sum(1 for v in values if v in ("true", "1"))
                total = len(values)
                if total == 0:
                    firewall = "N/A"
                elif enabled == total:
                    firewall = "Active"
                elif enabled == 0:
                    firewall = "Inactive"
                else:
                    firewall = f"Partial ({enabled}/{total})"
        except Exception:
            pass

        # --- Secure Boot ---
        try:
            out = run_ps("Confirm-SecureBootUEFI", timeout=PS_TIMEOUT_S)
            if out:
                secure_boot = "Enabled" if "true" in out.lower() else "Disabled"
            else:
                secure_boot = "N/A"
        except Exception:
            secure_boot = "N/A"

        # Warn if anything critical is off
        status = "OK"
        if defender_av != "Active" or secure_boot == "Disabled" or firewall in ("Inactive", "Partial"):
            status = "WARN"

        return (
            status,
            f"Defender AV: {defender_av} | Firewall: {firewall} | Secure Boot: {secure_boot}"
        )
    except Exception as e:
        return ("FAIL", f"Security scan failed: {e}")


def _scan_battery():
    try:
        bat = psutil.sensors_battery()
        if bat is None:
            return ("N/A", "No battery detected")
        status = "WARN" if (not bat.power_plugged and bat.percent < 15) else "OK"
        state = "Charging" if bat.power_plugged else "On battery"
        return (status, f"{bat.percent:.0f}% ({state})")
    except Exception as e:
        return ("FAIL", f"Battery scan failed: {e}")


# ---------- health helpers ----------

def _compute_health(results: dict, warn_tolerance: int) -> str:
    fails = sum(1 for v in results.values() if v["status"] == "FAIL")
    warns = sum(1 for v in results.values() if v["status"] == "WARN")
    if fails > 0:
        return "CRITICAL"
    if warns == 0:
        return "GOOD"
    if warns <= warn_tolerance:
        return "FAIR"
    return "CRITICAL"


# ---------- full scan ----------

def scan_full(progress_cb=None, cancel=None):
    _emit(progress_cb, 0, "Starting full scan...")
    results = {}

    steps = [
        ("CPU",      _scan_cpu,      12, "Analyzing CPU..."),
        ("GPU",      _scan_gpu,      25, "Analyzing GPU..."),
        ("MEMORY",   _scan_memory,   40, "Analyzing memory..."),
        ("STORAGE",  _scan_disk,     55, "Analyzing storage..."),
        ("OS",       _scan_os,       68, "Reading OS info..."),
        ("SECURITY", _scan_security, 82, "Checking security..."),
        ("BATTERY",  _scan_battery,  93, "Reading battery..."),
    ]

    for name, fn, pct, msg in steps:
        if _check_cancel(cancel):
            return None
        _emit(progress_cb, pct, msg)
        try:
            status, text = fn()
        except Exception as e:
            status, text = "FAIL", str(e)
        results[name] = {"status": status, "text": text}

    if _check_cancel(cancel):
        return None
    _emit(progress_cb, 100, "Complete")

    return {"categories": results, "health": _compute_health(results, warn_tolerance=2)}


# ---------- phantom (quick) scan ----------

def scan_phantom(progress_cb=None, cancel=None):
    _emit(progress_cb, 0, "Starting quick scan...")
    results = {}

    steps = [
        ("CPU",     _scan_cpu,    30, "Analyzing CPU..."),
        ("MEMORY",  _scan_memory, 65, "Analyzing memory..."),
        ("STORAGE", _scan_disk,   100, "Analyzing storage..."),
    ]

    for name, fn, pct, msg in steps:
        if _check_cancel(cancel):
            return None
        _emit(progress_cb, pct, msg)
        try:
            status, text = fn()
        except Exception as e:
            status, text = "FAIL", str(e)
        results[name] = {"status": status, "text": text}

    if _check_cancel(cancel):
        return None
    _emit(progress_cb, 100, "Complete")

    return {"categories": results, "health": _compute_health(results, warn_tolerance=1)}


# ---------- software scan ----------

def _read_uninstall_entry(key):
    """Return (name, version, publisher) or None if entry should be skipped."""
    try:
        try:
            sys_comp, _ = winreg.QueryValueEx(key, "SystemComponent")
            if sys_comp == 1:
                return None
        except OSError:
            pass

        try:
            parent, _ = winreg.QueryValueEx(key, "ParentKeyName")
            if parent:
                return None
        except OSError:
            pass

        try:
            rel, _ = winreg.QueryValueEx(key, "ReleaseType")
            if rel and str(rel).lower() in ("update", "hotfix", "security update"):
                return None
        except OSError:
            pass

        try:
            name, _ = winreg.QueryValueEx(key, "DisplayName")
            if not name or not str(name).strip():
                return None
        except OSError:
            return None

        try:
            version, _ = winreg.QueryValueEx(key, "DisplayVersion")
        except OSError:
            version = "-"

        try:
            publisher, _ = winreg.QueryValueEx(key, "Publisher")
        except OSError:
            publisher = "-"

        # Path resolution: prefer InstallLocation, fall back to DisplayIcon or UninstallString
        install_location = ""
        try:
            loc, _ = winreg.QueryValueEx(key, "InstallLocation")
            if loc and str(loc).strip():
                install_location = str(loc).strip().strip('"')
        except OSError:
            pass

        if not install_location:
            try:
                icon, _ = winreg.QueryValueEx(key, "DisplayIcon")
                if icon and str(icon).strip():
                    icon = str(icon).strip().split(",")[0].strip().strip('"')
                    install_location = os.path.dirname(icon)
            except OSError:
                pass

        if not install_location:
            try:
                uninst, _ = winreg.QueryValueEx(key, "UninstallString")
                if uninst and str(uninst).strip():
                    uninst = str(uninst).strip().strip('"')
                    if "msiexec" not in uninst.lower():
                        install_location = os.path.dirname(uninst)
            except OSError:
                pass

        return (str(name), str(version) or "-", str(publisher) or "-",
                install_location or "-")
    except Exception:
        return None


def scan_software(progress_cb=None, cancel=None):
    _emit(progress_cb, 0, "Reading installed applications...")

    hives = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
         "HKLM 64-bit"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
         "HKLM 32-bit"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
         "HKCU"),
    ]

    apps = []
    seen = set()

    for i, (hive, path, label) in enumerate(hives):
        if _check_cancel(cancel):
            return None

        pct = int((i / len(hives)) * 90)
        _emit(progress_cb, pct, f"Reading {label}...")

        try:
            with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as key:
                count = winreg.QueryInfoKey(key)[0]
                for j in range(count):
                    if _check_cancel(cancel):
                        return None
                    try:
                        name = winreg.EnumKey(key, j)
                        with winreg.OpenKey(key, name) as sub:
                            info = _read_uninstall_entry(sub)
                            if info:
                                key_tuple = (info[0].lower(), info[1])
                                if key_tuple not in seen:
                                    seen.add(key_tuple)
                                    apps.append(info)
                    except OSError:
                        continue
        except OSError:
            continue

    if _check_cancel(cancel):
        return None

    apps.sort(key=lambda x: x[0].lower())
    _emit(progress_cb, 100, f"Found {len(apps)} applications")

    return {"apps": apps, "count": len(apps)}


# ---------- hardware scan ----------

def _scan_hw_cpu(cancel):
    out = {"name": None, "cores": None, "threads": None, "base_mhz": None}
    try:
        txt = run_ps(
            "Get-CimInstance Win32_Processor | Select -First 1 Name,"
            "NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed | ConvertTo-Json",
            timeout=PS_TIMEOUT_S,
        )
        if txt:
            import json
            d = json.loads(txt)
            if isinstance(d, list):
                d = d[0]
            out["name"] = d.get("Name")
            out["cores"] = d.get("NumberOfCores")
            out["threads"] = d.get("NumberOfLogicalProcessors")
            out["base_mhz"] = d.get("MaxClockSpeed")
    except Exception:
        pass
    return out


def _scan_hw_mb(cancel):
    mb = {"manufacturer": None, "product": None,
          "bios_vendor": None, "bios_version": None, "bios_date": None}
    try:
        import json
        txt = run_ps(
            "Get-CimInstance Win32_BaseBoard | Select Manufacturer,Product | ConvertTo-Json",
            timeout=PS_TIMEOUT_S,
        )
        if txt:
            d = json.loads(txt)
            if isinstance(d, list):
                d = d[0]
            mb["manufacturer"] = d.get("Manufacturer")
            mb["product"] = d.get("Product")
    except Exception:
        pass
    try:
        import json
        txt = run_ps(
            "Get-CimInstance Win32_BIOS | Select Manufacturer,SMBIOSBIOSVersion,ReleaseDate | ConvertTo-Json",
            timeout=PS_TIMEOUT_S,
        )
        if txt:
            d = json.loads(txt)
            if isinstance(d, list):
                d = d[0]
            mb["bios_vendor"] = d.get("Manufacturer")
            mb["bios_version"] = d.get("SMBIOSBIOSVersion")
            rd = d.get("ReleaseDate")
            if rd:
                # WMI returns /Date(...)/ or ISO-ish; keep short
                mb["bios_date"] = str(rd)[:10]
    except Exception:
        pass
    return mb

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


def _scan_hw_gpus(cancel):
    gpus = []
    try:
        import json
        txt = run_ps(
            "Get-CimInstance Win32_VideoController | "
            "Select Name,AdapterRAM,DriverVersion,CurrentHorizontalResolution,CurrentVerticalResolution | "
            "ConvertTo-Json",
            timeout=PS_TIMEOUT_S,
        )
        if txt:
            d = json.loads(txt)
            if isinstance(d, dict):
                d = [d]
            nv_map = _nvidia_vram_map()
            for g in d:
                name = g.get("Name", "Unknown")
                vram = 0.0
                try:
                    vram = round(int(g.get("AdapterRAM") or 0) / (1024 ** 3), 2)
                except Exception:
                    pass
                # WMI AdapterRAM is uint32 — correct via nvidia-smi
                for nv_name, nv_gb in nv_map.items():
                    if nv_name in (name or "").lower():
                        vram = nv_gb
                        break
                res = ""
                try:
                    h = g.get("CurrentHorizontalResolution")
                    v = g.get("CurrentVerticalResolution")
                    if h and v:
                        res = f"{h}x{v}"
                except Exception:
                    pass
                gpus.append({
                    "name": name,
                    "vram_gb": vram,
                    "driver": g.get("DriverVersion", "-"),
                    "resolution": res,
                })
    except Exception:
        pass
    return gpus

def _scan_hw_ram(cancel):
    total_gb = 0
    sticks = []
    try:
        mem = psutil.virtual_memory()
        total_gb = round(mem.total / (1024 ** 3), 2)
    except Exception:
        pass
    try:
        import json
        txt = run_ps(
            "Get-CimInstance Win32_PhysicalMemory | "
            "Select Manufacturer,PartNumber,Capacity,Speed,DeviceLocator | ConvertTo-Json",
            timeout=PS_TIMEOUT_S,
        )
        if txt:
            d = json.loads(txt)
            if isinstance(d, dict):
                d = [d]
            for s in d:
                cap = 0
                try:
                    cap = round(int(s.get("Capacity") or 0) / (1024 ** 3), 1)
                except Exception:
                    pass
                sticks.append({
                    "manufacturer": s.get("Manufacturer", "-"),
                    "part": s.get("PartNumber", "-"),
                    "size_gb": cap,
                    "speed_mhz": s.get("Speed", "-"),
                    "slot": s.get("DeviceLocator", "-"),
                })
    except Exception:
        pass
    return {"total_gb": total_gb, "sticks": sticks}


def _scan_hw_physical_disks(cancel):
    disks = []
    try:
        import json
        txt = run_ps(
            "Get-PhysicalDisk | "
            "Select FriendlyName,MediaType,Size,HealthStatus,OperationalStatus | "
            "ConvertTo-Json",
            timeout=PS_TIMEOUT_S,
        )
        if txt:
            d = json.loads(txt)
            if isinstance(d, dict):
                d = [d]
            for p in d:
                size = 0
                try:
                    size = round(int(p.get("Size") or 0) / (1024 ** 3), 1)
                except Exception:
                    pass
                disks.append({
                    "model": p.get("FriendlyName", "Unknown"),
                    "media": p.get("MediaType", "-"),
                    "size_gb": size,
                    "health": p.get("HealthStatus", "-"),
                    "status": p.get("OperationalStatus", "-"),
                })
    except Exception:
        pass
    return disks


def _scan_hw_volumes(cancel):
    vols = []
    try:
        for p in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(p.mountpoint)
                vols.append({
                    "mount": p.mountpoint,
                    "fs": p.fstype or "-",
                    "total_gb": round(u.total / (1024 ** 3), 1),
                    "used_gb": round(u.used / (1024 ** 3), 1),
                    "free_gb": round(u.free / (1024 ** 3), 1),
                    "percent": u.percent,
                })
            except Exception:
                continue
    except Exception:
        pass
    return vols


def _scan_hw_network(cancel):
    adapters = []
    try:
        import json
        txt = run_ps(
            "Get-CimInstance Win32_NetworkAdapter | "
            "Where-Object {$_.PhysicalAdapter -eq $true} | "
            "Select Name,Manufacturer,MACAddress,Speed | ConvertTo-Json",
            timeout=PS_TIMEOUT_S,
        )
        if txt:
            d = json.loads(txt)
            if isinstance(d, dict):
                d = [d]
            for a in d:
                speed_bps = a.get("Speed") or 0
                speed_mbps = None
                try:
                    if speed_bps:
                        speed_mbps = round(int(speed_bps) / 1_000_000, 1)
                except Exception:
                    pass
                adapters.append({
                    "name": a.get("Name", "Unknown"),
                    "vendor": a.get("Manufacturer", "-"),
                    "mac": a.get("MACAddress", "-"),
                    "speed_mbps": speed_mbps,
                })
    except Exception:
        pass
    return adapters


def _scan_hw_audio(cancel):
    devices = []
    try:
        import json
        txt = run_ps(
            "Get-CimInstance Win32_SoundDevice | "
            "Select Name,Manufacturer,Status | ConvertTo-Json",
            timeout=PS_TIMEOUT_S,
        )
        if txt:
            d = json.loads(txt)
            if isinstance(d, dict):
                d = [d]
            for s in d:
                devices.append({
                    "name": s.get("Name", "Unknown"),
                    "vendor": s.get("Manufacturer", "-"),
                    "status": s.get("Status", "-"),
                })
    except Exception:
        pass
    return devices


def _scan_hw_monitors(cancel):
    monitors = []
    try:
        import json
        txt = run_ps(
            "Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorID | "
            "ForEach-Object { [PSCustomObject]@{ "
            "Manufacturer = ($_.ManufacturerName | ForEach-Object {[char]$_}) -join ''; "
            "Name = ($_.UserFriendlyName | ForEach-Object {[char]$_}) -join ''; "
            "Year = $_.YearOfManufacture } } | ConvertTo-Json",
            timeout=PS_TIMEOUT_S,
        )
        if txt:
            d = json.loads(txt)
            if isinstance(d, dict):
                d = [d]
            for m in d:
                name = m.get("Name") or ""
                manufacturer = m.get("Manufacturer") or ""
                if isinstance(name, list):
                    name = "".join(chr(x) for x in name if x and x != 0)
                elif isinstance(name, str):
                    name = name.replace("\x00", "").strip()
                if isinstance(manufacturer, list):
                    manufacturer = "".join(chr(x) for x in manufacturer if x and x != 0)
                elif isinstance(manufacturer, str):
                    manufacturer = manufacturer.replace("\x00", "").strip()
                monitors.append({
                    "name": name or "Monitor",
                    "vendor": manufacturer or "-",
                    "year": m.get("Year") or "-",
                })
    except Exception:
        pass
    return monitors


def _scan_hw_usb(cancel):
    devices = []
    try:
        import json
        txt = run_ps(
            "Get-PnpDevice -Class USB -Status OK | "
            "Select FriendlyName,Manufacturer,Status | ConvertTo-Json",
            timeout=PS_TIMEOUT_S,
        )
        if txt:
            d = json.loads(txt)
            if isinstance(d, dict):
                d = [d]
            for u in d:
                name = u.get("FriendlyName") or "Unknown"
                if not name or name == "Unknown":
                    continue
                devices.append({
                    "name": name,
                    "vendor": u.get("Manufacturer", "-"),
                    "status": u.get("Status", "-"),
                })
    except Exception:
        pass
    return devices


def _scan_hw_sensors(cancel):
    out = {"cpu_temp": None, "gpu_temp": None}
    try:
        from hardware.sensors import get_cpu_temp, get_gpu_temp
        ct = get_cpu_temp()
        if isinstance(ct, (int, float)):
            out["cpu_temp"] = ct
        gt = get_gpu_temp()
        if isinstance(gt, (int, float)):
            out["gpu_temp"] = gt
    except Exception:
        pass
    return out


def scan_hardware(progress_cb=None, cancel=None):
    _emit(progress_cb, 0, "Starting hardware scan...")

    result = {
        "cpu": None,
        "motherboard": None,
        "gpus": [],
        "ram_gb": 0,
        "ram_sticks": [],
        "disks": [],
        "volumes": [],
        "network": [],
        "audio": [],
        "monitors": [],
        "usb": [],
        "sensors": {},
    }

    steps = [
        ("CPU",        _scan_hw_cpu,            8,  lambda v: result.update({"cpu": v})),
        ("Motherboard/BIOS", _scan_hw_mb,       18, lambda v: result.update({"motherboard": v})),
        ("GPU",        _scan_hw_gpus,           30, lambda v: result.update({"gpus": v})),
        ("RAM",        _scan_hw_ram,            42, None),
        ("Disks",      _scan_hw_physical_disks, 55, lambda v: result.update({"disks": v})),
        ("Volumes",    _scan_hw_volumes,        65, lambda v: result.update({"volumes": v})),
        ("Network",    _scan_hw_network,        75, lambda v: result.update({"network": v})),
        ("Audio",      _scan_hw_audio,          82, lambda v: result.update({"audio": v})),
        ("Monitors",   _scan_hw_monitors,       88, lambda v: result.update({"monitors": v})),
        ("USB",        _scan_hw_usb,            93, lambda v: result.update({"usb": v})),
        ("Sensors",    _scan_hw_sensors,        98, lambda v: result.update({"sensors": v})),
    ]

    for label, fn, pct, setter in steps:
        if _check_cancel(cancel):
            return None
        _emit(progress_cb, pct, f"Scanning {label}...")
        try:
            val = fn(cancel)
            if label == "RAM":
                result["ram_gb"] = val.get("total_gb", 0)
                result["ram_sticks"] = val.get("sticks", [])
            elif setter is not None:
                setter(val)
        except Exception:
            pass

    if _check_cancel(cancel):
        return None
    _emit(progress_cb, 100, "Complete")
    return result