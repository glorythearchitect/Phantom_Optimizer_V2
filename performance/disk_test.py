"""
performance/disk_test.py
Disk benchmark — sequential throughput + small-file IOPS, fsync'd, honest.

Note: Without fsync(), Windows write-back caching makes write_speed report
OS cache throughput (~5-20 GB/s) instead of device throughput. fsync()
forces the write to the physical device — the number you see is the number
the disk actually delivered.
"""
import os
import tempfile
import time


def _write_sequential(test_file, size_mb):
    """Write 4 MB blocks, fsync at end. Returns duration in seconds."""
    start = time.perf_counter()
    with open(test_file, "wb") as f:
        chunk = os.urandom(4 * 1024 * 1024)
        written = 0
        target = size_mb * 1024 * 1024
        while written < target:
            f.write(chunk)
            written += len(chunk)
        f.flush()
        os.fsync(f.fileno())  # ← the honest-write fix
    return time.perf_counter() - start


def _read_sequential(test_file):
    """Read 4 MB blocks. Returns duration in seconds."""
    start = time.perf_counter()
    with open(test_file, "rb") as f:
        while f.read(4 * 1024 * 1024):
            pass
    return time.perf_counter() - start


def _small_file_io(test_dir, count, size_kb):
    """Write then read `count` files of size_kb KB. fsync each write."""
    payload = os.urandom(size_kb * 1024)
    paths = []

    write_start = time.perf_counter()
    for i in range(count):
        p = os.path.join(test_dir, f"phantom_io_{i}.tmp")
        try:
            with open(p, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            paths.append(p)
        except Exception:
            continue
    write_dur = time.perf_counter() - write_start

    read_start = time.perf_counter()
    for p in paths:
        try:
            with open(p, "rb") as f:
                f.read()
        except Exception:
            continue
    read_dur = time.perf_counter() - read_start

    for p in paths:
        try:
            os.remove(p)
        except Exception:
            pass

    return write_dur, read_dur


def run_disk_speed_test(
    size_mb=256,
    small_file_count=50,
    small_file_kb=4,
    progress_cb=None,
) -> dict:
    """
    Disk benchmark: sequential write/read + small-file IOPS.

    Backward compat: `write_speed`, `read_speed`, `duration`, `size_mb`
    are still present so existing UI works unchanged.
    """
    def emit(pct, msg):
        if progress_cb:
            try: progress_cb(int(pct), str(msg))
            except Exception: pass

    test_dir = tempfile.gettempdir()
    test_file = os.path.join(test_dir, "phantom_disk_test.tmp")
    start_total = time.perf_counter()

    try:
        emit(10, "Sequential write...")
        write_time = _write_sequential(test_file, size_mb)
        write_speed = round(size_mb / write_time, 2) if write_time > 0 else 0.0

        emit(35, "Sequential read...")
        read_time = _read_sequential(test_file)
        read_speed = round(size_mb / read_time, 2) if read_time > 0 else 0.0

        emit(60, f"Small-file IOPS ({small_file_count} files)...")
        w_dur, r_dur = _small_file_io(test_dir, small_file_count, small_file_kb)
        write_iops = int(small_file_count / w_dur) if w_dur > 0 else 0
        read_iops = int(small_file_count / r_dur) if r_dur > 0 else 0

        total_duration = round(time.perf_counter() - start_total, 2)
        emit(100, "Complete")

        return {
            # Backward compat
            "write_speed": write_speed,
            "read_speed": read_speed,
            "duration": total_duration,
            "size_mb": size_mb,

            # New
            "write_iops": write_iops,
            "read_iops": read_iops,
            "small_file_size_kb": small_file_kb,
            "small_file_count": small_file_count,
            "error": None,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            os.remove(test_file)
        except Exception:
            pass