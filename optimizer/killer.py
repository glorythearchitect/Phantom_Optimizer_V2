"""
optimizer/killer.py
Safe process termination and automatic optimization.

Safety model (enforced at backend, not trustable by UI):
  - PID 0 (System Idle Process) and PID 4 (System) are never touchable.
  - The optimizer's own PID is never touchable.
  - System and user-whitelisted names are blocked at termination time.
  - PID/name identity is revalidated immediately before termination.
  - Every termination returns a structured KillResult.
  - No Qt imports, no dialogs. Pure backend.
"""
import os
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple

import psutil

from optimizer.whitelist import load_whitelist

from core.configs import (
    PROCESS_HEAVY_CPU,
    PROCESS_HEAVY_MEM_MB,
    OPTIMIZER_TERMINATE_GRACE_S,
    OPTIMIZER_KILL_GRACE_S,
)


# ===============================
# Protection
# ===============================

PROTECTED_PIDS = {0, 4}  # System Idle Process, System


def get_self_pid() -> int:
    return os.getpid()


# ===============================
# Result types
# ===============================

class KillStatus(str, Enum):
    TERMINATED = "terminated"
    KILLED = "killed"
    ACCESS_DENIED = "access_denied"
    NOT_FOUND = "not_found"
    PROTECTED = "protected"
    SELF_PROTECTED = "self_protected"
    FAILED = "failed"


@dataclass
class KillResult:
    pid: int
    name: str
    status: KillStatus
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass
class Candidate:
    pid: int
    name: str
    cpu: float
    mem_mb: float
    protected: bool = False

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "name": self.name,
            "cpu": round(self.cpu, 1),
            "mem_mb": round(self.mem_mb, 1),
            "protected": self.protected,
        }


# ===============================
# Core termination
# ===============================

def _terminate_one(pid: int, name: str, whitelist: set) -> KillResult:
    """Terminate a process after revalidating its identity and safety tag."""
    if pid in PROTECTED_PIDS:
        return KillResult(pid, name, KillStatus.PROTECTED, "System-protected PID")
    if pid == get_self_pid():
        return KillResult(pid, name, KillStatus.SELF_PROTECTED,
                          "Phantom Optimizer's own process")

    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return KillResult(pid, name, KillStatus.NOT_FOUND, "Process no longer exists")
    except psutil.AccessDenied:
        return KillResult(pid, name, KillStatus.ACCESS_DENIED,
                          "Access denied while opening process")
    except Exception as e:
        return KillResult(pid, name, KillStatus.FAILED, f"Unexpected error: {e}")

    # The UI's process tag is advisory; enforce the current whitelist here.
    try:
        current_name = (proc.name() or "").strip()
        if not current_name or current_name.casefold() != name.strip().casefold():
            return KillResult(pid, name, KillStatus.FAILED,
                              "Process identity changed; refresh the process list")
        protected_names = {entry.casefold() for entry in whitelist}
        if current_name.casefold() in protected_names:
            return KillResult(pid, current_name, KillStatus.PROTECTED,
                              "Process is protected by the system or user whitelist")
        if not proc.is_running():
            return KillResult(pid, name, KillStatus.NOT_FOUND,
                              "Process no longer exists")
    except psutil.NoSuchProcess:
        return KillResult(pid, name, KillStatus.NOT_FOUND, "Process no longer exists")
    except psutil.AccessDenied:
        return KillResult(pid, name, KillStatus.ACCESS_DENIED,
                          "Access denied while validating process identity")
    except Exception as e:
        return KillResult(pid, name, KillStatus.FAILED, f"Process validation failed: {e}")

    # Graceful terminate first
    try:
        proc.terminate()
    except psutil.NoSuchProcess:
        return KillResult(pid, name, KillStatus.TERMINATED, "Process exited during terminate")
    except psutil.AccessDenied:
        return KillResult(pid, name, KillStatus.ACCESS_DENIED,
                          "Access denied while terminating")
    except Exception as e:
        return KillResult(pid, name, KillStatus.FAILED, f"Terminate failed: {e}")

    try:
        proc.wait(timeout=OPTIMIZER_TERMINATE_GRACE_S)
        return KillResult(pid, name, KillStatus.TERMINATED)
    except psutil.TimeoutExpired:
        pass
    except psutil.NoSuchProcess:
        return KillResult(pid, name, KillStatus.TERMINATED, "Process exited during wait")

    # Force kill if still alive
    try:
        proc.kill()
        proc.wait(timeout=OPTIMIZER_KILL_GRACE_S)
        return KillResult(pid, name, KillStatus.KILLED, "Did not exit on terminate; force-killed")
    except psutil.NoSuchProcess:
        return KillResult(pid, name, KillStatus.KILLED, "Process exited during force-kill")
    except psutil.AccessDenied:
        return KillResult(pid, name, KillStatus.ACCESS_DENIED,
                          "Access denied while force-killing")
    except Exception as e:
        return KillResult(pid, name, KillStatus.FAILED, f"Force-kill failed: {e}")


# ===============================
# Public API
# ===============================

def kill_processes(pairs: List[Tuple[int, str]]) -> List[KillResult]:
    """
    Terminates the given processes.
    Each tuple: (PID, Name).
    Returns a list of KillResult (one per input pair, in order).
    """
    protected_names = load_whitelist()
    return [_terminate_one(pid, name, protected_names) for pid, name in pairs]


def auto_optimize(
    whitelist: set,
    cpu_threshold: float = PROCESS_HEAVY_CPU,
    mem_threshold: float = PROCESS_HEAVY_MEM_MB,
) -> List[KillResult]:
    """
    Detect heavy processes not in whitelist and terminate them.
    Protected PIDs are never candidates.
    """
    candidates = preview_candidates(whitelist, cpu_threshold, mem_threshold)
    pairs = [(c.pid, c.name) for c in candidates if not c.protected]
    return kill_processes(pairs)


def preview_candidates(
    whitelist: set,
    cpu_threshold: float = PROCESS_HEAVY_CPU,
    mem_threshold: float = PROCESS_HEAVY_MEM_MB,
) -> List[Candidate]:
    """
    Returns heavy candidates without killing them.
    Protected PIDs are included but flagged with protected=True.
    """
    import time

    # Warm up CPU sampling — first cpu_percent() call always returns 0.0.
    for p in psutil.process_iter(["pid"]):
        try:
            psutil.Process(p.info["pid"]).cpu_percent(interval=None)
        except Exception:
            pass
    time.sleep(0.2)

    preview: List[Candidate] = []
    self_pid = get_self_pid()

    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            pid = proc.info["pid"]
            name = (proc.info["name"] or "").strip()
            if not name:
                continue
            if name in whitelist:
                continue

            cpu = float(proc.cpu_percent(interval=None))
            mem_mb = (proc.info["memory_info"].rss or 0) / (1024 ** 2)

            if cpu > cpu_threshold or mem_mb > mem_threshold:
                protected = (pid in PROTECTED_PIDS) or (pid == self_pid)
                preview.append(Candidate(pid, name, cpu, mem_mb, protected))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return preview