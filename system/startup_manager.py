"""
Startup Manager utilities for Phantom Optimizer.
Uses Windows StartupApproved registry keys to enable/disable entries
without moving any files. This is the same mechanism Task Manager uses.

UI calls:
    list_startup_apps() -> List[Tuple[name, location, status, command]]
    enable_startup_item(name, location) -> bool
    disable_startup_item(name, location) -> bool
    remove_startup_item(name, location) -> bool
"""

import os
import winreg
from typing import List, Tuple

# ----- Locations -----
HKCU_RUN = "HKCU_Run"
HKLM_RUN = "HKLM_Run"
HKCU_RUNONCE = "HKCU_RunOnce"
HKLM_RUNONCE = "HKLM_RunOnce"
STARTUP_USER = "Startup_User"
STARTUP_ALL = "Startup_All"

REG_PATHS = {
    HKCU_RUN:     (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Run"),
    HKLM_RUN:     (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    HKCU_RUNONCE: (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
    HKLM_RUNONCE: (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
}

APPROVED_PATHS = {
    HKCU_RUN:     (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    HKLM_RUN:     (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    HKCU_RUNONCE: (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    HKLM_RUNONCE: (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    STARTUP_USER: (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"),
    STARTUP_ALL:  (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"),
}

# 12-byte status blobs (same format Windows uses)
ENABLED_BLOB  = b'\x02' + b'\x00' * 11
DISABLED_BLOB = b'\x03' + b'\x00' * 11


# ----- Folder helpers -----

def _startup_user_dir() -> str:
    return os.path.join(os.environ.get("APPDATA", ""),
                        r"Microsoft\Windows\Start Menu\Programs\Startup")


def _startup_all_dir() -> str:
    return os.path.join(os.environ.get("ProgramData", ""),
                        r"Microsoft\Windows\Start Menu\Programs\Startup")


# ----- StartupApproved helpers -----

def _read_approved(location: str, value_name: str):
    if location not in APPROVED_PATHS:
        return None
    hive, path = APPROVED_PATHS[location]
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as key:
            data, _ = winreg.QueryValueEx(key, value_name)
            if isinstance(data, (bytes, bytearray)) and len(data) >= 1:
                return bytes(data)
    except OSError:
        pass
    return None


def _write_approved(location: str, value_name: str, enabled: bool) -> bool:
    if location not in APPROVED_PATHS:
        return False
    hive, path = APPROVED_PATHS[location]
    try:
        with winreg.CreateKeyEx(hive, path, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_BINARY,
                              ENABLED_BLOB if enabled else DISABLED_BLOB)
        return True
    except OSError:
        return False


def _delete_approved(location: str, value_name: str) -> bool:
    if location not in APPROVED_PATHS:
        return False
    hive, path = APPROVED_PATHS[location]
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, value_name)
        return True
    except OSError:
        return False


def _is_enabled(blob, default: bool = True) -> bool:
    if blob is None or len(blob) < 1:
        return default
    first = blob[0]
    if first in (0x02, 0x06):
        return True
    if first == 0x03:
        return False
    return default


# ----- Registry Run helpers -----

def _list_registry_key(hive, path) -> List[Tuple[str, str]]:
    items = []
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    items.append((name, value))
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return items


def _delete_registry_value(hive, path, name) -> bool:
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
        return True
    except OSError:
        return False


# ----- Folder helpers -----

def _list_folder(folder: str) -> List[Tuple[str, str]]:
    """Return (display_name, filename) for each file in a Startup folder."""
    items = []
    if not folder or not os.path.isdir(folder):
        return items
    try:
        for fn in os.listdir(folder):
            full = os.path.join(folder, fn)
            if os.path.isdir(full):
                continue
            display = os.path.splitext(fn)[0]
            items.append((display, fn))
    except Exception:
        pass
    return items


def _remove_folder_file(folder: str, filename: str) -> bool:
    try:
        full = os.path.join(folder, filename)
        if os.path.isfile(full):
            os.remove(full)
            return True
    except Exception:
        pass
    return False


# ----- Legacy cleanup: remove any Disabled subfolder once -----

_migration_done = False


def _cleanup_legacy_disabled():
    global _migration_done
    if _migration_done:
        return
    _migration_done = True

    for folder in (_startup_user_dir(), _startup_all_dir()):
        legacy = os.path.join(folder, "Disabled")
        if not os.path.isdir(legacy):
            continue
        try:
            for fn in os.listdir(legacy):
                src = os.path.join(legacy, fn)
                if os.path.isdir(src):
                    continue
                dst = os.path.join(folder, fn)
                if os.path.exists(dst):
                    os.remove(src)
                else:
                    try:
                        os.replace(src, dst)
                    except Exception:
                        pass
            try:
                os.rmdir(legacy)
            except OSError:
                pass
        except Exception:
            pass


# ----- Public API -----

def list_startup_apps() -> List[Tuple[str, str, str, str]]:
    # Listing is read-only; never migrate or reactivate startup entries here.
    rows = []

    # Registry Run entries
    for loc, (hive, path) in REG_PATHS.items():
        for name, cmd in _list_registry_key(hive, path):
            blob = _read_approved(loc, name)
            enabled = _is_enabled(blob, default=True)
            rows.append((name, loc, "Enabled" if enabled else "Disabled", cmd))

    # Startup folders
    for loc, folder in ((STARTUP_USER, _startup_user_dir()),
                        (STARTUP_ALL, _startup_all_dir())):
        for display, filename in _list_folder(folder):
            blob = _read_approved(loc, filename)
            enabled = _is_enabled(blob, default=True)
            rows.append((display, loc, "Enabled" if enabled else "Disabled",
                         os.path.join(folder, filename)))

    rows.sort(key=lambda r: (r[2] != "Enabled", r[0].lower()))
    return rows


def disable_startup_item(name: str, location: str) -> bool:
    if location in REG_PATHS:
        return _write_approved(location, name, enabled=False)
    if location == STARTUP_USER:
        folder = _startup_user_dir()
    elif location == STARTUP_ALL:
        folder = _startup_all_dir()
    else:
        return False
    for display, filename in _list_folder(folder):
        if display == name:
            return _write_approved(location, filename, enabled=False)
    return False


def enable_startup_item(name: str, location: str) -> bool:
    if location in REG_PATHS:
        if _delete_approved(location, name):
            return True
        return _write_approved(location, name, enabled=True)
    if location == STARTUP_USER:
        folder = _startup_user_dir()
    elif location == STARTUP_ALL:
        folder = _startup_all_dir()
    else:
        return False
    for display, filename in _list_folder(folder):
        if display == name:
            if _delete_approved(location, filename):
                return True
            return _write_approved(location, filename, enabled=True)
    return False


def remove_startup_item(name: str, location: str) -> bool:
    if location in REG_PATHS:
        hive, path = REG_PATHS[location]
        ok = _delete_registry_value(hive, path, name)
        _delete_approved(location, name)
        return ok
    if location == STARTUP_USER:
        folder = _startup_user_dir()
    elif location == STARTUP_ALL:
        folder = _startup_all_dir()
    else:
        return False
    for display, filename in _list_folder(folder):
        if display == name:
            ok = _remove_folder_file(folder, filename)
            _delete_approved(location, filename)
            return ok
    return False