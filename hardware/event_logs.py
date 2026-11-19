"""
hardware/event_logs.py
Reads and categorizes Windows Event Viewer logs related to hardware and system health.
Used by Hardware Logs tab and Advanced diagnostics.
"""

import win32evtlog
from core.configs import LOG_PULL_LIMIT, ADV_LOG_PULL_LIMIT


# ===============================
# Basic Log Fetcher
# ===============================

def get_recent_system_warnings(limit: int = LOG_PULL_LIMIT):
    """
    Reads the latest 'System' event logs (Errors + Warnings).
    Returns a list of tuples: (Time, Source, Message)
    """
    logs = []
    try:
        hand = win32evtlog.OpenEventLog("localhost", "System")
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        while len(logs) < limit:
            events = win32evtlog.ReadEventLog(hand, flags, 0)
            if not events:
                break
            for ev in events:
                if ev.EventType in [1, 2]:
                    time_str = ev.TimeGenerated.Format()
                    src = ev.SourceName
                    msg = str(ev.StringInserts)
                    logs.append((time_str, src, msg))
                    if len(logs) >= limit:
                        break
        win32evtlog.CloseEventLog(hand)
    except Exception as e:
        logs.append(("Error", "EventLog", f"Failed to read logs: {e}"))
    return logs


# ===============================
# Categorized Hardware Logs
# ===============================

def get_categorized_logs(limit: int = ADV_LOG_PULL_LIMIT):
    """
    Reads deeper event logs (System + HardwareEvents + Application).
    Classifies logs into categories like Storage, CPU/GPU, Thermal, etc.
    Returns a list of tuples: (Category, Time, Source, Message)
    """
    all_logs = []
    sources = [("System", limit // 2), ("HardwareEvents", limit // 3), ("Application", limit // 3)]

    try:
        for logtype, per_limit in sources:
            try:
                hand = win32evtlog.OpenEventLog("localhost", logtype)
            except Exception:
                continue  # Skip unavailable logs

            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            count = 0
            while count < per_limit:
                events = win32evtlog.ReadEventLog(hand, flags, 0)
                if not events:
                    break
                for ev in events:
                    if ev.EventType not in [1, 2]:
                        continue
                    time_str = ev.TimeGenerated.Format()
                    src = ev.SourceName
                    msg = str(ev.StringInserts)
                    cat = classify_log(src, msg)
                    all_logs.append((cat, time_str, src, msg))
                    count += 1
                    if count >= per_limit:
                        break
                if count >= per_limit:
                    break
            win32evtlog.CloseEventLog(hand)

    except Exception as e:
        all_logs.append(("Error", "EventLog", "System", f"Failed to load categorized logs: {e}"))

    return all_logs[:limit]


# ===============================
# Classification Logic
# ===============================

def classify_log(source: str, message: str) -> str:
    """
    Categorizes event log entries into hardware-relevant groups.
    """
    msg_low = (message or "").lower()
    src_low = (source or "").lower()

    if "pnp" in src_low or "usb" in msg_low or "device" in msg_low:
        return "Device Plug/Unplug"
    if "thermal" in msg_low or "temperature" in msg_low or "overheat" in msg_low:
        return "Thermal Warning"
    if "bios" in msg_low or "firmware" in msg_low:
        return "Firmware/BIOS"
    if "boot" in msg_low or "startup" in msg_low:
        return "Boot Issue"
    if "disk" in msg_low or "smart" in msg_low or "storage" in msg_low:
        return "Storage Error"
    if "processor" in msg_low or "cpu" in msg_low or "gpu" in msg_low or "display" in msg_low:
        return "CPU/GPU Issue"
    if "power" in msg_low or "battery" in msg_low or "supply" in msg_low:
        return "Power Event"
    if "tcp" in msg_low or "dhcp" in msg_low or "network" in msg_low or "adapter" in msg_low:
        return "Network Event"
    if "memory" in msg_low or "ram" in msg_low:
        return "Memory Warning"
    return "General"


# ===============================
# Quick Access Filters
# ===============================

def get_last_event(category: str) -> tuple:
    """
    Fetches the most recent event of a given category.
    Returns (Time, Source, Message) or None.
    """
    logs = get_categorized_logs(limit=200)
    for cat, t, src, msg in logs:
        if category.lower() in cat.lower():
            return (t, src, msg)
    return None


def format_log_entry(entry: tuple) -> str:
    """
    Converts a log tuple into formatted text for UI.
    """
    if not entry:
        return "No recent event found."
    t, src, msg = entry
    return f"Time: {t}\nSource: {src}\nMessage: {msg}"
