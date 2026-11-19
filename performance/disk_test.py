"""
performance/disk_test.py
Disk benchmark — sequential throughput + small-file IOPS.

Write measurements flush Python and OS file buffers with fsync. Read measurements
may still benefit from the Windows file cache; they are not guaranteed to represent
uncached physical-device throughput.
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
    successful_writes = 0
    successful_reads = 0

    write_start = time.perf_counter()
    for _ in range(count):
        try:
            fd, p = tempfile.mkstemp(prefix="phantom_io_", suffix=".tmp", dir=test_dir)
            os.close(fd)
            paths.append(p)
            with open(p, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            successful_writes += 1
        except Exception:
            continue
    write_dur = time.perf_counter() - write_start

    read_start = time.perf_counter()
    for p in paths:
        try:
            with open(p, "rb") as f:
                f.read()
            successful_reads += 1
        except Exception:
            continue
    read_dur = time.perf_counter() - read_start

    for p in paths:
        try:
            os.remove(p)
        except Exception:
            pass

    return write_dur, read_dur, successful_writes, successful_reads


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
    fd, test_file = tempfile.mkstemp(prefix="phantom_disk_test_", suffix=".tmp", dir=test_dir)
    os.close(fd)
    start_total = time.perf_counter()

    try:
        emit(10, "Sequential write...")
        write_time = _write_sequential(test_file, size_mb)
        write_speed = round(size_mb / write_time, 2) if write_time > 0 else 0.0

        emit(35, "Sequential read...")
        read_time = _read_sequential(test_file)
        read_speed = round(size_mb / read_time, 2) if read_time > 0 else 0.0

        emit(60, f"Small-file IOPS ({small_file_count} files)...")
        w_dur, r_dur, writes_ok, reads_ok = _small_file_io(
            test_dir, small_file_count, small_file_kb
        )
        write_iops = int(writes_ok / w_dur) if w_dur > 0 else 0
        read_iops = int(reads_ok / r_dur) if r_dur > 0 else 0

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
            "small_files_written": writes_ok,
            "small_files_read": reads_ok,
            "error": None,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            os.remove(test_file)
        except Exception:
            pass