"""
system/network.py
Network connection listing for the Network Usage tool (Tools tab).

Tier 1 only: connection existence via psutil.net_connections().
No bandwidth. No bytes. No estimation. No fabrication.

Read-only. Returns structured data. No Qt imports.
"""

import os
import socket

import psutil

from optimizer.killer import PROTECTED_PIDS


def _get_process_name(pid: int) -> str | None:
    """Return process name, or None if process is gone / inaccessible."""
    try:
        return psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    except Exception:
        return None


def list_network_processes() -> list:
    """
    Group all network connections by owning PID.

    Returns a list of dicts, sorted by activity:
    {
        "pid":        int | None,
        "name":       str,
        "tcp_est":    int,    # TCP ESTABLISHED count
        "tcp_listen": int,    # TCP LISTEN count
        "udp":        int,    # UDP socket count
        "family":     str,    # "IPv4" | "IPv6" | "Both" | "-"
        "endpoints":  str,    # top 3 remote ip:port, comma-separated, or "-"
        "protected":  bool,   # PID 0, 4, or self
        "checkable":  bool,   # False if unverifiable
    }
    """
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return []
    except Exception:
        return []

    self_pid = os.getpid()
    by_pid = {}  # pid (int or None) -> aggregate

    for c in conns:
        pid = getattr(c, "pid", None)
        if pid not in by_pid:
            by_pid[pid] = {
                "pid": pid,
                "tcp_est": 0,
                "tcp_listen": 0,
                "tcp_other": 0,
                "udp": 0,
                "families": set(),
                "endpoints": {},
            }
        agg = by_pid[pid]

        # Address family
        fam = getattr(c, "family", None)
        if fam == socket.AF_INET:
            agg["families"].add("IPv4")
        elif fam == socket.AF_INET6:
            agg["families"].add("IPv6")

        # Transport protocol — SOCK_STREAM = TCP, SOCK_DGRAM = UDP
        ctype = getattr(c, "type", None)
        status = (getattr(c, "status", "") or "").upper()

        if ctype == socket.SOCK_STREAM:
            if status == "ESTABLISHED":
                agg["tcp_est"] += 1
            elif status == "LISTEN":
                agg["tcp_listen"] += 1
            else:
                agg["tcp_other"] += 1
        elif ctype == socket.SOCK_DGRAM:
            agg["udp"] += 1
        # else: not TCP or UDP — ignore

        # Remote endpoint (only for connected sockets, not for LISTEN)
        raddr = getattr(c, "raddr", None)
        if raddr and len(raddr) >= 2:
            ip, port = raddr[0], raddr[1]
            if ip and ip not in ("0.0.0.0", "::"):
                key = f"{ip}:{port}"
                agg["endpoints"][key] = agg["endpoints"].get(key, 0) + 1

    # ---- Build final rows ----
    results = []
    for pid, agg in by_pid.items():
        # Resolve identity + safety
        if pid is None:
            name = "Unidentified"
            checkable = False
            protected = False
        elif pid in PROTECTED_PIDS or pid == self_pid:
            resolved = _get_process_name(pid)
            name = resolved or f"PID {pid}"
            checkable = False
            protected = True
        else:
            resolved = _get_process_name(pid)
            if resolved is None:
                name = "Unknown"
                checkable = False
                protected = False
            else:
                name = resolved
                checkable = True
                protected = False

        # Family display
        fams = agg["families"]
        if len(fams) == 0:
            family = "-"
        elif len(fams) >= 2:
            family = "Both"
        else:
            family = next(iter(fams))

        # Top 3 remote endpoints by frequency
        eps = sorted(agg["endpoints"].items(), key=lambda kv: -kv[1])[:3]
        endpoints = ", ".join(k for k, _ in eps) if eps else "-"

        results.append({
            "pid": pid,
            "name": name,
            "tcp_est": agg["tcp_est"],
            "tcp_listen": agg["tcp_listen"],
            "udp": agg["udp"],
            "family": family,
            "endpoints": endpoints,
            "protected": protected,
            "checkable": checkable,
        })

    # Sort: unidentified last, then by total sockets desc, then name
    def sort_key(r):
        is_unid = 1 if r["pid"] is None else 0
        total = r["tcp_est"] + r["tcp_listen"] + r["udp"]
        return (is_unid, -total, r["name"].lower())

    results.sort(key=sort_key)
    return results