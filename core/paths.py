"""
core/paths.py
Centralized path and file handling utilities for Phantom Optimizer.
Ensures correct asset resolution for both development and packaged (.exe) builds.
"""

import os
import sys
from datetime import datetime
from core.configs import WHITELIST_FILE, DEFAULT_REPORT_NAME


# =========================
# Base Directories
# =========================

def get_base_path() -> str:
    """
    Returns the base directory for the app.
    Works properly in both development (source) and frozen (PyInstaller) modes.
    """
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # PyInstaller temp directory
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_assets_path(*subpaths: str) -> str:
    """
    Returns a path inside the global /assets/ directory.
    Example:
        get_assets_path("icons", "cpu.png")
    """
    base = os.path.join(get_base_path(), "assets")
    return os.path.join(base, *subpaths)


def get_ui_assets_path(*subpaths: str) -> str:
    """
    Returns a path inside /app/ui_assets/ for styles, fonts, icons.
    """
    base = os.path.join(get_base_path(), "app", "ui_assets")
    return os.path.join(base, *subpaths)


# =========================
# File Paths
# =========================

def get_whitelist_path() -> str:
    """
    Returns the full path to the whitelist file.
    Source mode: <project>/whitelist.txt  (next to the code).
    Frozen mode: %APPDATA%\\PhantomOptimizer\\whitelist.txt  (persistent).
    Creates the file and its directory if missing.
    """
    if hasattr(sys, "_MEIPASS"):
        # Frozen: user data lives in APPDATA — _MEIPASS is destroyed on exit.
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        base_dir = os.path.join(appdata, "PhantomOptimizer")
    else:
        # Source: next to the project root (unchanged behavior).
        base_dir = get_base_path()

    try:
        os.makedirs(base_dir, exist_ok=True)
    except Exception:
        pass

    path = os.path.join(base_dir, WHITELIST_FILE)
    if not os.path.exists(path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("# Phantom Optimizer Whitelist\n")
        except Exception:
            pass
    return path

def get_report_path(suffix: str = None) -> str:
    """
    Returns a full report output path in the working directory.
    If suffix is provided, appends it before file extension.
    """
    filename = DEFAULT_REPORT_NAME
    if suffix:
        name, ext = os.path.splitext(DEFAULT_REPORT_NAME)
        filename = f"{name}_{suffix}{ext}"
    return os.path.join(os.getcwd(), filename)


def get_temp_path(filename: str) -> str:
    """
    Returns a path in the system temp directory.
    Example: get_temp_path('phantom_test.tmp')
    """
    import tempfile
    return os.path.join(tempfile.gettempdir(), filename)


# =========================
# Utility Functions
# =========================

def timestamp() -> str:
    """Return a short timestamp string for filenames."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: str):
    """Ensure a directory exists."""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
