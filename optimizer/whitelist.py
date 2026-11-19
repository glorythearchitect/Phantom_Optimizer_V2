"""
optimizer/whitelist.py
Manages the safe process whitelist for Phantom Optimizer.
Merges system-default safe processes with user-defined entries.
"""

import os
from core.paths import get_whitelist_path


# ===============================
# Default Whitelist
# ===============================

DEFAULT_WHITELIST = {
    # --- Windows Core ---
    "System", "Registry", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "winlogon.exe", "svchost.exe",
    "explorer.exe", "dwm.exe", "MemCompression",
    "Idle", "System Idle Process", "Secure System",

    # --- Graphics & Audio ---
    "audiodg.exe", "nvcontainer.exe", "atieclxx.exe",
    "IntelAudioService.exe", "IntelGraphicsSoftwareService.exe",
    "IntelGraphicsSoftware.Service.exe",

    # --- Security ---
    "MsMpEng.exe", "SecurityHealthService.exe", "WinDefend.exe",

    # --- UI & Shell ---
    "ShellExperienceHost.exe", "StartMenuExperienceHost.exe",
    "ApplicationFrameHost.exe", "RuntimeBroker.exe", "sihost.exe",
    "ctfmon.exe", "Widgets.exe", "WidgetService.exe",

    # --- System Helpers ---
    "SearchIndexer.exe", "SearchHost.exe", "SystemSettingsBroker.exe",
    "spoolsv.exe", "conhost.exe",
}


# ===============================
# User Whitelist Loader
# ===============================

def load_whitelist() -> set:
    """
    Loads the combined whitelist (default + user-defined).
    Creates whitelist.txt if missing.
    """
    path = get_whitelist_path()
    merged = set(DEFAULT_WHITELIST)

    try:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write("# Add your safe process names below, one per line\n")
        else:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    name = line.strip()
                    if name and not name.startswith("#"):
                        merged.add(name)
    except Exception:
        pass

    return merged


# ===============================
# Whitelist Editing
# ===============================

def add_to_whitelist(name: str) -> bool:
    """
    Adds a process name to user whitelist file.
    Returns True if successful.
    """
    path = get_whitelist_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}\n")
        return True
    except Exception:
        return False


def remove_from_whitelist(name: str) -> bool:
    """
    Removes a process name from user whitelist.
    Returns True if removed successfully.
    """
    path = get_whitelist_path()
    try:
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            lines = [l for l in f if l.strip() and not l.strip().startswith("#")]
        new_lines = [l for l in lines if l.strip().lower() != name.lower()]
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Safe processes\n")
            f.writelines(new_lines)
        return True
    except Exception:
        return False


# ===============================
# Utilities
# ===============================

def is_safe(name: str, whitelist: set) -> bool:
    """
    Returns True if the process name is in the whitelist.
    """
    return name.strip() in whitelist
