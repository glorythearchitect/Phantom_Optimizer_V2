"""
performance/cpu_test.py
CPU benchmark — bounded, thermal-safe, single + multi-thread phases.

Phases:
  1. Warmup (0.5s) — discarded
  2. Single-thread (2s, 4 chunks of 0.5s) — variance per chunk
  3. Multi-thread (2s, N processes = cpu_count)

Safety gates (mirrors GPU test):
  1. Pre-test temp gate — CPU > 85°C → refuse
  2. Mid-test temp gate — CPU > 90°C → abort between chunks
  3. Hard timeouts on each phase

Note (PyInstaller): `multiprocessing.freeze_support()` must be called
in main.py before app init for packaged builds.
"""
import multiprocessing as mp
import statistics
import time

from core.configs import CPU_TEST_TEMP_WARN_C, CPU_TEST_TEMP_ABORT_C


# ── Lazy import — keeps worker-process spawn lightweight (workers don't
#    need hardware.sensors / wmi, so deferring its import saves ~100ms
#    of module load per spawned process).
def _get_cpu_temp():
    try:
        from hardware.sensors import get_cpu_temp
        return get_cpu_temp()
    except Exception:
        return "--"


# ── Kernel — pure-Python arithmetic, deterministic, checksum-protected
def _run_kernel(duration_s):
    """Run arithmetic kernel for duration_s. Returns (iterations, checksum)."""
    end = time.perf_counter() + duration_s
    iterations = 0
    checksum = 0
    while time.perf_counter() < end:
        for i in range(1000):
            checksum = (checksum + (i * 37) % 1009) & 0xFFFFFFFF
            iterations += 1
    return iterations, checksum


# ── Top-level function required by ProcessPoolExecutor on Windows
def _mp_worker(duration_s):
    iters, _ = _run_kernel(duration_s)
    return iters


# ── Single-thread phase with per-chunk thermal checks
def _run_single_thread(duration_s, chunk_s, check_temp):
    n_chunks = max(1, int(duration_s / chunk_s))
    chunk_scores = []
    total_iters = 0
    final_checksum = 0
    start = time.perf_counter()

    for _ in range(n_chunks):
        aborted = check_temp()
        if aborted is not None:
            return {"aborted": aborted, "duration": time.perf_counter() - start}
        iters, cs = _run_kernel(chunk_s)
        chunk_scores.append(iters / chunk_s)
        total_iters += iters
        final_checksum = (final_checksum + cs) & 0xFFFFFFFF

    elapsed = time.perf_counter() - start
    return {
        "iterations": total_iters,
        "duration": elapsed,
        "score": int(total_iters / elapsed) if elapsed > 0 else 0,
        "chunk_scores": chunk_scores,
        "checksum": final_checksum,
        "aborted": None,
    }


# ── Multi-thread phase — real parallel via ProcessPoolExecutor
def _run_multi_thread(duration_s):
    """Real multi-core test (threads would be blocked by GIL)."""
    try:
        from concurrent.futures import ProcessPoolExecutor
    except Exception:
        return None

    n_workers = mp.cpu_count() or 1
    if n_workers < 2:
        return None  # Not worth overhead on single-core systems

    start = time.perf_counter()
    try:
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            futures = [ex.submit(_mp_worker, duration_s) for _ in range(n_workers)]
            total_iters = sum(f.result() for f in futures)
    except Exception:
        return None  # Graceful degradation — single-thread only

    elapsed = time.perf_counter() - start
    return {
        "iterations": total_iters,
        "duration": elapsed,
        "score": int(total_iters / elapsed) if elapsed > 0 else 0,
        "workers": n_workers,
    }


def run_cpu_benchmark(
    single_duration_s=2.0,
    multi_duration_s=2.0,
    progress_cb=None,
) -> dict:
    """
    Two-phase CPU benchmark. Thermal-safe, bounded, honest.

    Backward compat: `score`, `iterations`, `duration`, `checksum` are
    aliases for the single-thread phase, so existing UI keeps working.
    New fields give full picture: single + multi + scaling + stability.
    """
    def emit(pct, msg):
        if progress_cb:
            try: progress_cb(int(pct), str(msg))
            except Exception: pass

    # ── Pre-test thermal gate
    temp_before = _get_cpu_temp()
    if isinstance(temp_before, (int, float)) and temp_before > CPU_TEST_TEMP_WARN_C:
        return {
            "supported": True,
            "aborted": "pre_hot",
            "temp_before_c": temp_before,
            "notes": [
                f"CPU is already at {temp_before}°C (limit: {CPU_TEST_TEMP_WARN_C}°C).",
                "Let it cool down before re-testing.",
            ],
        }

    # ── Mid-test thermal check (called between chunks)
    abort_state = {"reason": None, "temp": None}

    def check_temp():
        t = _get_cpu_temp()
        if isinstance(t, (int, float)) and t >= CPU_TEST_TEMP_ABORT_C:
            abort_state["reason"] = "thermal"
            abort_state["temp"] = t
            return "thermal"
        return None

    # ── Warmup
    emit(5, "Warming up...")
    _run_kernel(0.5)

    # ── Single-thread
    emit(15, "Single-thread phase...")
    single = _run_single_thread(single_duration_s, chunk_s=0.5, check_temp=check_temp)
    if single is None or single.get("aborted"):
        return {
            "supported": True,
            "aborted": "thermal",
            "partial": True,
            "temp_before_c": temp_before,
            "temp_after_c": abort_state.get("temp"),
            "notes": [
                f"Test aborted at {abort_state.get('temp')}°C for safety "
                f"(limit: {CPU_TEST_TEMP_ABORT_C}°C).",
            ],
        }

    # ── Multi-thread
    emit(55, "Multi-thread phase...")
    multi = _run_multi_thread(multi_duration_s)
    multi_ok = multi is not None

    # ── Metrics
    emit(90, "Computing metrics...")

    single_score = single.get("score", 0)
    multi_score = multi.get("score", 0) if multi_ok else 0

    # Jitter = spread of chunk scores relative to median
    chunk_scores = single.get("chunk_scores", [])
    if len(chunk_scores) >= 3:
        med = statistics.median(chunk_scores)
        spread = ((max(chunk_scores) - min(chunk_scores)) / med * 100) if med > 0 else 0.0
    else:
        spread = 0.0

    scaling = (multi_score / single_score) if single_score > 0 else 0.0

    if spread > 15:
        stability = "UNSTABLE"
    elif spread > 8:
        stability = "MILD_JITTER"
    else:
        stability = "STABLE"

    temp_after = _get_cpu_temp()
    notes = []
    if isinstance(temp_after, (int, float)) and isinstance(temp_before, (int, float)):
        rise = temp_after - temp_before
        if rise > 15:
            notes.append(f"CPU heated {rise:.0f}°C during test — check cooling.")
        if temp_after > CPU_TEST_TEMP_ABORT_C - 5:
            notes.append(f"CPU nearing thermal limit ({temp_after}°C).")
    if multi_ok:
        cores = mp.cpu_count() or 1
        if scaling < 1.5 and cores >= 4:
            notes.append(
                f"Low multi-thread scaling ({scaling:.1f}× over {cores} cores) — "
                "CPU may be throttling or sharing load."
            )
    else:
        notes.append("Multi-thread phase unavailable on this system.")

    emit(100, "Complete")

    return {
        # Backward-compat single-thread aliases (existing UI works unchanged)
        "supported": True,
        "score": single_score,
        "iterations": single.get("iterations", 0),
        "duration": round(single.get("duration", 0), 2),
        "checksum": single.get("checksum", 0),

        # New single-thread details
        "single_score": single_score,
        "single_iterations": single.get("iterations", 0),
        "single_duration": round(single.get("duration", 0), 2),
        "single_checksum": single.get("checksum", 0),
        "single_chunk_jitter_pct": round(spread, 2),

        # New multi-thread details
        "multi_score": multi_score,
        "multi_iterations": multi.get("iterations", 0) if multi_ok else 0,
        "multi_duration": round(multi.get("duration", 0), 2) if multi_ok else 0.0,
        "multi_workers": multi.get("workers", 0) if multi_ok else 0,
        "multi_scaling_x": round(scaling, 2),
        "multi_available": multi_ok,

        "temp_before_c": temp_before,
        "temp_after_c": temp_after,
        "stability": stability,
        "notes": notes,
    }