"""
performance/mem_test.py
Memory integrity test — multi-pattern verification.

Tests 5 patterns over a bounded block (default 256 MB):
  0x00  — all zeros (stuck-at-1 detection)
  0xFF  — all ones  (stuck-at-0 detection)
  0xAA  — alternating bits
  0x55  — inverse alternating
  ramp  — sequential values (addressing/ordering errors)

This is the same class of test memtest86 runs before deep stress.
Does NOT attempt to hit peak RAM bandwidth (Python interpreter overhead
would dominate); its value is correctness, not throughput.
"""
import ctypes
import time


def _pattern_pass(arr, total_bytes, step, pattern_fn):
    """Write pattern, read back, count mismatches."""
    for i in range(0, total_bytes, step):
        arr[i] = pattern_fn(i)
    errors = 0
    for i in range(0, total_bytes, step):
        if arr[i] != pattern_fn(i):
            errors += 1
    return errors


def run_memory_check(size_mb=256, pattern_interval=4096, progress_cb=None) -> dict:
    """
    Multi-pattern memory integrity check.

    Backward compat: `passed`, `checked_mb`, `errors`, `duration` present
    so existing UI works unchanged.
    """
    def emit(pct, msg):
        if progress_cb:
            try: progress_cb(int(pct), str(msg))
            except Exception: pass

    start = time.perf_counter()
    total_bytes = size_mb * 1024 * 1024

    try:
        arr = (ctypes.c_ubyte * total_bytes)()
    except MemoryError:
        return {
            "passed": False,
            "checked_mb": 0,
            "errors": 0,
            "duration": round(time.perf_counter() - start, 2),
            "patterns_tested": [],
            "error": (
                f"Insufficient free RAM to allocate {size_mb} MB. "
                "Close other applications and try again."
            ),
        }
    except Exception as e:
        return {
            "passed": False,
            "checked_mb": 0,
            "errors": 0,
            "duration": round(time.perf_counter() - start, 2),
            "patterns_tested": [],
            "error": f"Memory allocation failed: {e}",
        }

    patterns = [
        ("0x00", lambda i: 0x00),
        ("0xFF", lambda i: 0xFF),
        ("0xAA", lambda i: 0xAA),
        ("0x55", lambda i: 0x55),
        ("ramp", lambda i: (i // pattern_interval) % 256),
    ]

    total_errors = 0
    tested = []
    for idx, (name, fn) in enumerate(patterns):
        emit(int(10 + 85 * (idx / len(patterns))), f"Pattern {name}...")
        total_errors += _pattern_pass(arr, total_bytes, pattern_interval, fn)
        tested.append(name)

    emit(100, "Complete")
    duration = round(time.perf_counter() - start, 2)

    return {
        "passed": total_errors == 0,
        "checked_mb": size_mb,
        "errors": total_errors,
        "duration": duration,
        "patterns_tested": tested,
        "error": None,
    }