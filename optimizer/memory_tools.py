"""
optimizer/memory_tools.py
Safe RAM optimization utilities.

Removed from old version (unsafe):
  - Clear-RecycleBin -Force (destructive, must be explicit/confirmed elsewhere)
  - system-wide MinWorkingSet mutation

No Qt imports. Returns structured data only.
"""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass

import psutil

from optimizer.killer import PROTECTED_PIDS, get_self_pid


# ===============================
# Windows access rights
# ===============================
# Least privilege combination sufficient for EmptyWorkingSet.
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SET_QUOTA = 0x0100
ACCESS_RIGHTS = PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SET_QUOTA


# ===============================
# Result type
# ===============================

@dataclass
class MemoryResult:
    freed_mb: float
    before_mb: float
    after_mb: float
    success: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "freed_mb": self.freed_mb,
            "before_mb": self.before_mb,
            "after_mb": self.after_mb,
            "success": self.success,
            "detail": self.detail,
        }


# ===============================
# RAM trim
# ===============================

def clean_ram() -> MemoryResult:
    """
    Trims working sets of user processes to release memory.
    Skips protected PIDs and the optimizer's own process.
    Silent: returns MemoryResult, no dialogs.
    """
    before = psutil.virtual_memory().available / (1024 ** 2)
    skip = PROTECTED_PIDS | {get_self_pid()}

    try:
        psapi = ctypes.WinDLL("psapi")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        empty = psapi.EmptyWorkingSet
        empty.argtypes = [wintypes.HANDLE]
        empty.restype = wintypes.BOOL

        open_process = kernel.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE

        close_handle = kernel.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        trimmed = 0
        for proc in psutil.process_iter(["pid"]):
            pid = proc.info["pid"]
            if pid in skip:
                continue
            handle = open_process(ACCESS_RIGHTS, False, pid)
            if not handle:
                continue
            try:
                if empty(handle):
                    trimmed += 1
            except Exception:
                pass
            finally:
                close_handle(handle)
    except Exception as e:
        after = psutil.virtual_memory().available / (1024 ** 2)
        return MemoryResult(
            freed_mb=0.0,
            before_mb=round(before, 1),
            after_mb=round(after, 1),
            success=False,
            detail=f"Working set trim failed: {e}",
        )

    after = psutil.virtual_memory().available / (1024 ** 2)
    freed = max(0.0, round(after - before, 1))
    return MemoryResult(
        freed_mb=freed,
        before_mb=round(before, 1),
        after_mb=round(after, 1),
        success=trimmed > 0,
        detail=(
            "Working sets trimmed for " + str(trimmed) + " processes. "
            "The available-memory change is system-wide and is not attributable "
            "solely to this operation."
            if trimmed else "No process working set could be trimmed."
        ),
    )


# ===============================
# Memory status
# ===============================

def get_memory_status() -> dict:
    try:
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "Total (GB)": round(vm.total / (1024 ** 3), 2),
            "Used (GB)": round((vm.total - vm.available) / (1024 ** 3), 2),
            "Available (GB)": round(vm.available / (1024 ** 3), 2),
            "Usage (%)": int(vm.percent),
            "Swap Used (GB)": round(swap.used / (1024 ** 3), 2),
            "Swap Total (GB)": round(swap.total / (1024 ** 3), 2),
        }
    except Exception:
        return {
            "Total (GB)": 0.0,
            "Used (GB)": 0.0,
            "Available (GB)": 0.0,
            "Usage (%)": 0,
            "Swap Used (GB)": 0.0,
            "Swap Total (GB)": 0.0,
        }


# ===============================
# Combined
# ===============================

def full_memory_optimize() -> dict:
    """
    Runs RAM trim and returns combined status.
    No dialogs; controller decides how to present.
    """
    trim = clean_ram()
    status = get_memory_status()
    return {
        "freed_mb": trim.freed_mb,
        "success": trim.success,
        "detail": trim.detail,
        "before_mb": trim.before_mb,
        "after_mb": trim.after_mb,
        "status": status,
    }