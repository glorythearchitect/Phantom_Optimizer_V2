"""
optimizer/processes.py
Lists and classifies running processes for Phantom Optimizer.
No Qt imports.
"""
import time

import psutil

from core.configs import (
    OPTIMIZER_APP_CPU_THRESHOLD,
    OPTIMIZER_APP_MEM_THRESHOLD_MB,
    PROCESS_HEAVY_CPU,
    PROCESS_HEAVY_MEM_MB,
)
from optimizer.killer import PROTECTED_PIDS, get_self_pid
from optimizer.whitelist import DEFAULT_WHITELIST


# ===============================
# Existing: apps / background split
# ===============================

def list_processes(whitelist: set, search_term: str = "") -> dict:
    processes = {"apps": [], "background": []}
    search_term = search_term.lower()
    skip = PROTECTED_PIDS | {get_self_pid()}

    for p in psutil.process_iter(["pid"]):
        try:
            psutil.Process(p.info["pid"]).cpu_percent(interval=None)
        except Exception:
            pass
    time.sleep(0.2)

    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            pid = proc.info["pid"]
            if pid in skip:
                continue
            name = (proc.info["name"] or "").strip()
            if not name:
                continue
            if name in whitelist:
                continue
            if search_term and search_term not in name.lower():
                continue

            cpu = float(proc.cpu_percent(interval=None))
            mem_mb = round((proc.info["memory_info"].rss or 0) / (1024 ** 2), 1)

            target = (
                "apps"
                if (cpu >= OPTIMIZER_APP_CPU_THRESHOLD
                    or mem_mb >= OPTIMIZER_APP_MEM_THRESHOLD_MB)
                else "background"
            )
            processes[target].append((pid, name, cpu, mem_mb))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return processes


def get_process_count() -> int:
    try:
        return len(psutil.pids())
    except Exception:
        return 0


# ===============================
# New: full tagged process list
# ===============================

def _classify(name: str, pid: int, whitelist: set) -> str:
    """
    Tag priority:
      CRITICAL  - PID 0, 4, self
      SYSTEM    - in DEFAULT_WHITELIST (Windows critical)
      WHITELIST - user-added whitelist entry
      USER      - everything else
    """
    if pid in PROTECTED_PIDS or pid == get_self_pid():
        return "CRITICAL"
    if name in DEFAULT_WHITELIST:
        return "SYSTEM"
    if name in whitelist:
        return "WHITELIST"
    return "USER"


def list_all_processes(whitelist: set) -> list:
    """
    Returns every running process with a tag and heavy flag.
    Sorted by CPU desc, then memory desc.
    CRITICAL processes are pushed to the bottom.
    """
    for p in psutil.process_iter(["pid"]):
        try:
            psutil.Process(p.info["pid"]).cpu_percent(interval=None)
        except Exception:
            pass
    time.sleep(0.2)

    entries = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            pid = proc.info["pid"]
            name = (proc.info["name"] or "").strip()
            if not name:
                continue

            cpu = float(proc.cpu_percent(interval=None))
            mem_mb = round((proc.info["memory_info"].rss or 0) / (1024 ** 2), 1)
            tag = _classify(name, pid, whitelist)
            heavy = (cpu > PROCESS_HEAVY_CPU) or (mem_mb > PROCESS_HEAVY_MEM_MB)

            entries.append({
                "pid": pid,
                "name": name,
                "cpu": round(cpu, 1),
                "mem_mb": mem_mb,
                "tag": tag,
                "heavy": heavy,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort: non-critical first, then by usage desc.
    entries.sort(key=lambda e: (e["tag"] == "CRITICAL", -e["cpu"], -e["mem_mb"]))
    return entries