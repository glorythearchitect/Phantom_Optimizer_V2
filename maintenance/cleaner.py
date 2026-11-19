"""
maintenance/cleaner.py
Performs targeted system cleanup operations for Phantom Optimizer.
- Reports actual bytes freed (delta before/after), not aspirational size.
- Thumbnail cache is scoped to thumbcache_*/iconcache_* files only.
- Windows Update cache cleanup is DISM-free (StartComponentCleanup is
  intentionally left to Windows Disk Cleanup — it blocks for minutes).
"""
import os
import shutil
import tempfile
from typing import List, Dict, Tuple


# -------------------------
# Common cleanup locations
# -------------------------

CLEAN_PATHS = {
    "Temp": os.environ.get("TEMP", r"C:\Windows\Temp"),
    "Prefetch": r"C:\Windows\Prefetch",
    "WindowsUpdateCache": r"C:\Windows\SoftwareDistribution\Download",
}

# These folders are cleaned surgically by prefix
THUMBNAIL_DIRS = [
    os.path.expandvars(r"%LocalAppData%\Microsoft\Windows\Explorer"),
]
THUMBNAIL_PREFIXES = ("thumbcache_", "iconcache_")

BROWSER_CACHES = {
    "Edge": os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\User Data\Default\Cache"),
    "Chrome": os.path.expandvars(r"%LocalAppData%\Google\Chrome\User Data\Default\Cache"),
}


# -------------------------
# Utility helpers
# -------------------------

def _folder_size(path: str) -> int:
    total = 0
    if not os.path.isdir(path):
        try:
            return os.path.getsize(path)
        except Exception:
            return 0
    for root, _, files in os.walk(path, topdown=True):
        for f in files:
            try:
                fp = os.path.join(root, f)
                total += os.path.getsize(fp)
            except Exception:
                continue
    return total


def _safe_delete(path: str) -> int:
    """
    Delete a selected cache/temp target without deleting its parent directory.
    Returns bytes that actually disappeared. Symlinks are unlinked, never followed.
    """
    if not os.path.lexists(path):
        return 0
    before = _folder_size(path)
    try:
        if os.path.islink(path) or os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            # Preserve the configured directory itself; remove only its contents.
            for entry in os.scandir(path):
                try:
                    if entry.is_symlink() or entry.is_file(follow_symlinks=False):
                        os.remove(entry.path)
                    elif entry.is_dir(follow_symlinks=False):
                        shutil.rmtree(entry.path, ignore_errors=False)
                except OSError:
                    continue
    except OSError:
        pass
    after = _folder_size(path) if os.path.lexists(path) else 0
    return max(0, before - after)


def _clean_thumbnail_files():
    """Delete only thumbcache_*/iconcache_* files. Returns bytes freed."""
    freed = 0
    for folder in THUMBNAIL_DIRS:
        if not os.path.isdir(folder):
            continue
        try:
            for fn in os.listdir(folder):
                if not fn.lower().startswith(THUMBNAIL_PREFIXES):
                    continue
                fp = os.path.join(folder, fn)
                try:
                    size = os.path.getsize(fp)
                    os.remove(fp)
                    freed += size
                except Exception:
                    continue
        except Exception:
            continue
    return freed


# -------------------------
# Core cleanup logic
# -------------------------

def scan_cleanup_targets() -> List[Tuple[str, float]]:
    """
    Estimates removable data size (MB) per category.
    Returns [(Category, SizeMB)] sorted desc, only entries > 1 MB.
    """
    targets = []

    for name, path in CLEAN_PATHS.items():
        try:
            if os.path.exists(path):
                size = round(_folder_size(path) / (1024 ** 2), 2)
                if size > 1:
                    targets.append((name, size))
        except Exception:
            continue

    # Thumbnail cache — sum only matching prefixes
    thumb_bytes = 0
    for folder in THUMBNAIL_DIRS:
        if not os.path.isdir(folder):
            continue
        try:
            for fn in os.listdir(folder):
                if fn.lower().startswith(THUMBNAIL_PREFIXES):
                    fp = os.path.join(folder, fn)
                    try:
                        thumb_bytes += os.path.getsize(fp)
                    except Exception:
                        continue
        except Exception:
            continue
    if thumb_bytes > 1 * 1024 * 1024:
        targets.append(("ThumbnailCache", round(thumb_bytes / (1024 ** 2), 2)))

    for name, path in BROWSER_CACHES.items():
        if os.path.exists(path):
            size = round(_folder_size(path) / (1024 ** 2), 2)
            if size > 1:
                targets.append((f"Browser: {name}", size))

    return sorted(targets, key=lambda x: x[1], reverse=True)


def perform_cleanup(dry_run: bool = True) -> Dict[str, float]:
    """
    Clean up safe locations.
    dry_run=True: only measures (no deletion).
    dry_run=False: deletes, then reports ACTUAL bytes freed per category.
    """
    results: Dict[str, float] = {}

    for name, path in CLEAN_PATHS.items():
        if not os.path.exists(path):
            continue
        if dry_run:
            size_mb = round(_folder_size(path) / (1024 ** 2), 2)
        else:
            size_mb = round(_safe_delete(path) / (1024 ** 2), 2)
        if size_mb >= 1:
            results[name] = size_mb

    # Thumbnail cache
    if dry_run:
        thumb_bytes = 0
        for folder in THUMBNAIL_DIRS:
            if not os.path.isdir(folder):
                continue
            try:
                for fn in os.listdir(folder):
                    if fn.lower().startswith(THUMBNAIL_PREFIXES):
                        try:
                            thumb_bytes += os.path.getsize(os.path.join(folder, fn))
                        except Exception:
                            continue
            except Exception:
                continue
        thumb_mb = round(thumb_bytes / (1024 ** 2), 2)
    else:
        thumb_mb = round(_clean_thumbnail_files() / (1024 ** 2), 2)
    if thumb_mb >= 1:
        results["ThumbnailCache"] = thumb_mb

    # Browser caches
    for name, path in BROWSER_CACHES.items():
        if not os.path.exists(path):
            continue
        if dry_run:
            size_mb = round(_folder_size(path) / (1024 ** 2), 2)
        else:
            size_mb = round(_safe_delete(path) / (1024 ** 2), 2)
        if size_mb >= 1:
            results[f"Browser: {name}"] = size_mb

    return results


def format_cleanup_report(results: Dict[str, float]) -> str:
    lines = [f"{k}: {v:.2f} MB" for k, v in results.items()]
    total = sum(results.values())
    lines.append(f"\nTotal{' Potential' if True else ''} Free Space: {total:.2f} MB")
    return "\n".join(lines)