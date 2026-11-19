"""
performance/gpu_test.py
GPU Pulse benchmark — bounded, math-driven, no cancellation.

Safety gates (each independently prevents damage):
  1. Import gate        — PyOpenGL missing → supported: False, no crash
  2. Pre-test temp gate — GPU > 85 °C → refuse, return immediately
  3. Context gate       — GL context creation fail → graceful return
  4. Frame cap          — 300 frames hard ceiling
  5. Wall-clock gate    — 8 s hard ceiling
  6. Mid-test temp gate — GPU > 90 °C → abort, no partial numbers
  7. Per-frame timeout  — frame > 500 ms → abort (TDR-adjacent)
  8. Cleanup gate       — always in finally: destroy FBO/context/surface

No threading.Event — test runs to completion or safety abort.
"""

import struct
import time
import ctypes
import subprocess
import statistics

from core.configs import (
    GPU_TEST_DURATION_S,
    GPU_TEST_FRAME_CAP,
    GPU_TEST_TEMP_WARN_C,
    GPU_TEST_TEMP_ABORT_C,
    GPU_TEST_TEMP_CHECK_FRAMES,
    GPU_TEST_PREVIEW_FRAMES,
    GPU_TEST_PREVIEW_W,
    GPU_TEST_PREVIEW_H,
    GPU_TEST_RENDER_W,
    GPU_TEST_RENDER_H,
    GPU_TEST_MANDEL_ITER,
    GPU_TEST_OPS_PER_ITER,
    GPU_TEST_JITTER_WARN_PCT,
    GPU_TEST_JITTER_FAIL_PCT,
    GPU_TEST_JITTER_MAD_WARN,
    GPU_TEST_JITTER_MAD_FAIL,
    GPU_TEST_YIELD_FRAMES,
    GPU_TEST_HARD_TIMEOUT_S,
    GPU_TEST_THROTTLE_WARN_PCT,
    GPU_TEST_GPU_USE_WARN_PCT,
)
from performance.gpu_shaders import (
    FILL_VERTEX_SRC, FILL_FRAGMENT_SRC,
    ALU_VERTEX_SRC, ALU_FRAGMENT_SRC,
)


# ============================================================
# Pre-check helpers
# ============================================================

def _check_gl_available() -> tuple:
    """Returns (ok: bool, reason: str). Never raises."""
    try:
        from OpenGL import GL  # noqa: F401
        return (True, "")
    except ImportError:
        return (False, "PyOpenGL not installed. Install: pip install PyOpenGL")
    except Exception as e:
        return (False, f"PyOpenGL check failed: {e}")

def _get_nvidia_smi_info() -> dict:
    """Query nvidia-smi for accurate VRAM + driver (WMI caps at 4 GB)."""
    info = {}
    try:
        out = subprocess.check_output(
            "nvidia-smi --query-gpu=name,memory.total,driver_version "
            "--format=csv,noheader,nounits",
            shell=True, text=True, stderr=subprocess.DEVNULL, timeout=3,
        ).strip()
        if not out:
            return info
        best = None
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            name, vram_mb, driver = parts[0], parts[1], parts[2]
            try:
                vram_gb = round(float(vram_mb) / 1024, 1)
            except (ValueError, TypeError):
                vram_gb = 0.0
            cand = {"name": name, "vram_gb": vram_gb, "driver": driver}
            if best is None or cand["vram_gb"] > best["vram_gb"]:
                best = cand
        if best:
            info = best
    except Exception:
        pass
    return info


def _classify_gpu(name: str, vram_gb: float) -> str:
    """
    Classify GPU as 'discrete' | 'integrated' | 'unknown'.
    Rules (name-first, VRAM as tiebreaker):
      - NVIDIA / GeForce / RTX / GTX / Quadro  → discrete
      - AMD Radeon RX / Pro / VII               → discrete
      - AMD Radeon (plain) / Vega / Graphics    → integrated
      - Intel Arc                               → discrete
      - Intel (anything else)                   → integrated
      - VRAM ≥ 2 GB                              → discrete
    """
    n = (name or "").lower()
    if any(k in n for k in ("nvidia", "geforce", "rtx", "gtx", "quadro")):
        return "discrete"
    if any(k in n for k in ("radeon rx", "radeon pro", "radeon vii")):
        return "discrete"
    if "radeon" in n and "graphics" in n:
        return "integrated"
    if "intel" in n:
        return "discrete" if "arc" in n else "integrated"
    if vram_gb >= 2.0:
        return "discrete"
    return "unknown"


def _pick_primary_gpu(gpus: list):
    """Return the preferred/primary GPU dict, or None."""
    if not gpus:
        return None
    if len(gpus) == 1:
        return gpus[0]
    discrete = [g for g in gpus if g.get("kind") == "discrete"]
    if discrete:
        return max(discrete, key=lambda g: g.get("vram_gb", 0))
    return gpus[0]


def _get_gpu_identity() -> dict:
    """
    Detect ALL GPUs and pick the primary (discrete preferred).
    Robust against:
      - WMI stderr noise (uses subprocess with list args)
      - AdapterRAM uint32 cap (nvidia-smi overrides for NVIDIA)
      - Multi-GPU (iGPU + dGPU on laptops)

    Returns:
      {
        "name":         str,   # primary GPU name
        "driver":       str,
        "vram_gb":      float,
        "primary_kind": str,   # 'discrete' | 'integrated' | 'unknown'
        "all_gpus":     [ { name, driver, vram_gb, kind }, ... ],
      }
    Never raises.
    """
    info = {
        "name": "Unknown GPU",
        "driver": "-",
        "vram_gb": 0.0,
        "primary_kind": "unknown",
        "all_gpus": [],
    }

    nv_info = _get_nvidia_smi_info()

    # WMI via list-args subprocess — no quoting issues, no stderr mixing.
    ps_cmd = (
        'Get-CimInstance Win32_VideoController | '
        'ForEach-Object { '
        '$_.Name + "||" + $_.DriverVersion + "||" + $_.AdapterRAM '
        '}'
    )
    raw = ""
    try:
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", ps_cmd],
            text=True, stderr=subprocess.DEVNULL, timeout=6,
        ) or ""
    except Exception:
        raw = ""

    gpus = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or "||" not in line:
            continue
        parts = line.split("||")
        if len(parts) < 3:
            continue
        name = parts[0].strip()
        driver = (parts[1].strip() or "-")
        try:
            vram_bytes = int(parts[2].strip() or 0)
        except (ValueError, TypeError):
            vram_bytes = 0
        if not name:
            continue

        # VRAM: WMI value, but override with nvidia-smi for NVIDIA
        vram_gb = round(vram_bytes / (1024 ** 3), 1) if vram_bytes else 0.0
        if "nvidia" in name.lower() and nv_info.get("vram_gb"):
            vram_gb = nv_info["vram_gb"]
            if nv_info.get("driver"):
                driver = nv_info["driver"]

        gpus.append({
            "name": name,
            "driver": driver,
            "vram_gb": vram_gb,
            "kind": _classify_gpu(name, vram_gb),
        })

    if gpus:
        info["all_gpus"] = gpus
        primary = _pick_primary_gpu(gpus)
        if primary:
            info["name"] = primary["name"]
            info["driver"] = primary["driver"]
            info["vram_gb"] = primary["vram_gb"]
            info["primary_kind"] = primary["kind"]
        return info

    # WMI failed but nvidia-smi worked → still show the real NVIDIA card
    if nv_info.get("name"):
        entry = {
            "name": nv_info["name"],
            "driver": nv_info.get("driver", "-"),
            "vram_gb": nv_info.get("vram_gb", 0.0),
            "kind": "discrete",
        }
        info.update({
            "name": entry["name"],
            "driver": entry["driver"],
            "vram_gb": entry["vram_gb"],
            "primary_kind": "discrete",
            "all_gpus": [entry],
        })
    return info


_GPU_TEMP_CACHE = {"t": 0.0, "temp": "--"}
_GPU_TEMP_CACHE_TTL = 2.0


def _read_gpu_temp():
    """Returns int/float °C, or '--' if unavailable.

    Cached for 2s.

    Why: get_gpu_temp() spawns nvidia-smi as a subprocess (~50-150 ms on
    Windows). The ALU phase calls this every GPU_TEST_TEMP_CHECK_FRAMES
    frames. At ~500 fps, 60-frame interval = 35 spawns over 4s of test —
    enough accumulated spawn overhead to slow the LAST 20% of frames and
    trigger a FALSE "thermal throttle" reading. Cache makes the call
    O(1) after the first read, so the mid-test gate costs nothing.
    """
    now = time.monotonic()
    if now - _GPU_TEMP_CACHE["t"] < _GPU_TEMP_CACHE_TTL:
        return _GPU_TEMP_CACHE["temp"]
    _GPU_TEMP_CACHE["t"] = now
    try:
        from hardware.sensors import get_gpu_temp
        _GPU_TEMP_CACHE["temp"] = get_gpu_temp()
    except Exception:
        _GPU_TEMP_CACHE["temp"] = "--"
    return _GPU_TEMP_CACHE["temp"]


def _detect_gpu_users() -> dict:
    """
    Best-effort detection of processes using the GPU.

    Returns:
      {
        "confirmed": [...],   # from nvidia-smi compute-apps (reliable)
        "possible":  [...],   # from process-name heuristics (may be idle)
        "util_pct":  float | None,   # NVIDIA utilization, max across GPUs
      }
    """
    confirmed = []
    possible = []
    util_pct = None

    # Confirmed: NVIDIA compute apps
    try:
        out = subprocess.check_output(
            "nvidia-smi --query-compute-apps=pid,process_name "
            "--format=csv,noheader",
            shell=True, text=True, stderr=subprocess.DEVNULL, timeout=3,
        ).strip()
        if out:
            for line in out.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    tag = f"{parts[1]} (PID {parts[0]})"
                    if tag not in confirmed:
                        confirmed.append(tag)
    except Exception:
        pass

    # NVIDIA utilization %
    try:
        out = subprocess.check_output(
            "nvidia-smi --query-gpu=utilization.gpu "
            "--format=csv,noheader,nounits",
            shell=True, text=True, stderr=subprocess.DEVNULL, timeout=3,
        ).strip()
        if out:
            vals = []
            for line in out.splitlines():
                try:
                    vals.append(float(line.strip()))
                except ValueError:
                    continue
            if vals:
                util_pct = max(vals)
    except Exception:
        pass

    # Possible: known GPU-using process names (heuristic — cross-vendor)
    KNOWN_HEAVY = {
        "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe",
        "discord.exe", "slack.exe", "teams.exe", "zoom.exe",
        "obs64.exe", "obs32.exe", "obs.exe",
        "vlc.exe", "mpc-hc64.exe", "mpv.exe",
        "steam.exe", "steamwebhelper.exe",
        "photoshop.exe", "blender.exe", "unity.exe",
    }
    try:
        import psutil
        for p in psutil.process_iter(["pid", "name"]):
            try:
                name = (p.info["name"] or "").lower()
                if name in KNOWN_HEAVY:
                    tag = f"{p.info['name']} (PID {p.info['pid']})"
                    if tag not in confirmed and tag not in possible:
                        possible.append(tag)
            except Exception:
                continue
    except Exception:
        pass

    return {
        "confirmed": confirmed,
        "possible": possible,
        "util_pct": util_pct,
    }


def get_gpu_info_only() -> dict:
    """Fast info for the confirmation dialog. No GL context created."""
    info = _get_gpu_identity()
    temp = _read_gpu_temp()
    info["temp_c"] = temp
    info["temp_ok"] = (
        isinstance(temp, (int, float)) and temp <= GPU_TEST_TEMP_WARN_C
    )
    info["gpu_users"] = _detect_gpu_users()
    ok, reason = _check_gl_available()
    info["gl_available"] = ok
    info["gl_reason"] = reason
    return info


# ============================================================
# Preview grab (from FBO — no PyOpenGL readback needed)
# ============================================================

def _grab_preview(fbo, target_w, target_h):
    from PyQt6.QtCore import Qt
    try:
        img = fbo.toImage()
        if img.isNull():
            return None
        return img.scaled(
            target_w, target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    except Exception:
        return None


# ============================================================
# Main benchmark
# ============================================================

def run_gpu_benchmark(progress_cb=None, preview_cb=None, yield_cb=None) -> dict:
    """
    Run the GPU Pulse benchmark.

    Runs on the GUI thread. QOffscreenSurface is a GUI-thread-only class
    on Qt; creating it on a worker thread causes Qt to fall back to a
    QWindow-based surface which Windows binds to the integrated GPU.

    progress_cb(pct: int, msg: str)
    preview_cb(qimage: QImage)
    yield_cb(): optional callback for cooperative yielding between frames
                (caller should pass QApplication.processEvents)

    No cancel — runs to completion or safety abort.
    Every return path is a structured dict; never raises.
    """
    def emit_progress(pct, msg):
        if progress_cb:
            try: progress_cb(int(pct), str(msg))
            except Exception: pass

    def emit_preview(fbo):
        if preview_cb:
            try:
                img = _grab_preview(fbo, GPU_TEST_PREVIEW_W, GPU_TEST_PREVIEW_H)
                if img is not None:
                    preview_cb(img)
            except Exception: pass

    def emit_yield():
        if yield_cb:
            try: yield_cb()
            except Exception: pass

    # --- Gate 1: PyOpenGL available? ---
    ok, reason = _check_gl_available()
    identity = _get_gpu_identity()
    if not ok:
        return {
            "supported": False,
            "reason": reason,
            "gpu_name": identity["name"],
            "driver_version": identity["driver"],
            "vram_gb": identity["vram_gb"],
            "all_gpus": identity.get("all_gpus", []),
            "notes": ["Install PyOpenGL: pip install PyOpenGL"],
        }
    
    # --- Gate 2: pre-test temp ---
    temp_before = _read_gpu_temp()
    if isinstance(temp_before, (int, float)) and temp_before > GPU_TEST_TEMP_WARN_C:
        return {
            "supported": True,
            "aborted": "pre_hot",
            "temp_before_c": temp_before,
            "gpu_name": identity["name"],
            "driver_version": identity["driver"],
            "vram_gb": identity["vram_gb"],
            "all_gpus": identity.get("all_gpus", []),
            "notes": [
                f"GPU is already at {temp_before} °C (limit: {GPU_TEST_TEMP_WARN_C} °C).",
                "Let it cool down before benchmarking.",
            ],
        }

    # --- Imports (deferred so missing PyOpenGL is caught above) ---
    from PyQt6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
    from PyQt6.QtOpenGL import (
        QOpenGLShaderProgram, QOpenGLShader,
        QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat,
    )
    from OpenGL import GL

    # --- Gate 3: create context ---
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 0)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.NoProfile)
    fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)

    surface = QOffscreenSurface()
    surface.setFormat(fmt)
    surface.create()
    if not surface.isValid():
        return {
            "supported": False,
            "reason": "Offscreen surface creation failed (driver issue)",
            **identity,
        }

    context = QOpenGLContext()
    context.setFormat(fmt)
    if not context.create():
        surface.destroy()
        return {
            "supported": False,
            "reason": "OpenGL 3.0 context creation failed",
            **identity,
        }

    if not context.makeCurrent(surface):
        context.destroy()
        surface.destroy()
        return {
            "supported": False,
            "reason": "GL makeCurrent failed",
            **identity,
        }

    gl_version = "unknown"
    try:
        raw = GL.glGetString(GL.GL_VERSION)
        if raw:
            gl_version = raw.decode() if isinstance(raw, bytes) else str(raw)
    except Exception:
        pass

    gl_renderer = "unknown"
    try:
        raw = GL.glGetString(GL.GL_RENDERER)
        if raw:
            gl_renderer = raw.decode() if isinstance(raw, bytes) else str(raw)
    except Exception:
        pass

    fbo = None
    prog_fill = None
    prog_alu = None
    vbo_id = 0
    vao_id = 0
    alu_iterations = GPU_TEST_MANDEL_ITER  # overridden by warmup measurement
    t_start = time.perf_counter()

    # Fresh temp read for pre-test gate — ignore any cache from prior run
    _GPU_TEMP_CACHE["t"] = 0.0
    _GPU_TEMP_CACHE["temp"] = "--"

    try:
        W, H = GPU_TEST_RENDER_W, GPU_TEST_RENDER_H

        # --- FBO ---
        fbo_fmt = QOpenGLFramebufferObjectFormat()
        fbo_fmt.setAttachment(QOpenGLFramebufferObject.Attachment.NoAttachment)
        fbo_fmt.setSamples(0)
        fbo = QOpenGLFramebufferObject(W, H, fbo_fmt)
        if not fbo.isValid():
            return {
                "supported": False,
                "reason": "FBO creation failed",
                **identity, "gl_version": gl_version,
            }

        # --- VAO (required for core-profile contexts) ---
        # Some drivers (notably modern NVIDIA on Windows) promote a
        # "3.0 / NoProfile" request into a core-profile context where the
        # default VAO 0 is invalid. Without an explicitly bound VAO,
        # glEnableVertexAttribArray() returns GL_INVALID_OPERATION (1282).
        # Creating + binding a VAO is a no-op on compat profiles and required
        # on core profiles — safe either way.
        vao_id = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(vao_id)

        # --- VBO (fullscreen quad, triangle strip) ---
        vbo_id = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_id)
        verts = struct.pack("8f", -1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, len(verts), verts, GL.GL_STATIC_DRAW)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

        # --- Compile shaders ---
        def compile_program(vert_src, frag_src):
            p = QOpenGLShaderProgram()
            if not p.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vert_src):
                raise RuntimeError(f"Vertex compile: {p.log()}")
            if not p.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, frag_src):
                raise RuntimeError(f"Fragment compile: {p.log()}")
            p.bindAttributeLocation("a_pos", 0)
            if not p.link():
                raise RuntimeError(f"Link: {p.log()}")
            return p

        try:
            prog_fill = compile_program(FILL_VERTEX_SRC, FILL_FRAGMENT_SRC)
            prog_alu = compile_program(ALU_VERTEX_SRC, ALU_FRAGMENT_SRC)
        except Exception as e:
            return {
                "supported": False,
                "reason": f"Shader compile/link failed: {e}",
                **identity, "gl_version": gl_version,
            }

        fbo.bind()
        GL.glViewport(0, 0, W, H)
        GL.glClearColor(0.0, 0.0, 0.0, 1.0)

        # =====================================================
        # Fill phase (50% of budget)
        # =====================================================
        emit_progress(2, "Fill Rate phase...")
        fill_durations = []
        fill_frames = 0
        fill_budget = GPU_TEST_DURATION_S * 0.5
        fill_t0 = time.perf_counter()

        prog_fill.bind()
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_id)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, ctypes.c_void_p(0))

        while fill_frames < GPU_TEST_FRAME_CAP:
            elapsed = time.perf_counter() - fill_t0
            if elapsed >= fill_budget:
                break
            # Inline hard timeout — protects against driver stalls
            if time.perf_counter() - t_start > GPU_TEST_HARD_TIMEOUT_S:
                prog_fill.release()
                return {
                    "supported": True, "aborted": "hard_timeout",
                    "duration_s": round(time.perf_counter() - t_start, 2),
                    "temp_after_c": _read_gpu_temp(),
                    "gpu_name": identity["name"],
                    "driver_version": identity["driver"],
                    "vram_gb": identity["vram_gb"],
                    "all_gpus": identity.get("all_gpus", []),
                    "gl_version": gl_version,
                    "gl_renderer": gl_renderer,
                    "notes": ["Fill phase exceeded hard timeout — aborting."],
                }

            frame_t0 = time.perf_counter()
            prog_fill.setUniformValue("u_time", float(elapsed))
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
            GL.glFinish()
            dt = time.perf_counter() - frame_t0
            fill_durations.append(dt)
            fill_frames += 1

            # Gate 7: per-frame timeout
            if dt > 0.5:
                prog_fill.release()
                return {
                    "supported": True, "aborted": "frame_timeout",
                    "duration_s": round(time.perf_counter() - t_start, 2),
                    "gpu_name": identity["name"],
                    "all_gpus": identity.get("all_gpus", []),
                    "gl_version": gl_version,
                    "gl_renderer": gl_renderer,
                    "notes": ["A single frame exceeded 500 ms — GPU or driver stall."],
                }

            if fill_frames % GPU_TEST_PREVIEW_FRAMES == 0:
                pct = 2 + int(48 * elapsed / fill_budget)
                emit_progress(pct, f"Fill Rate — frame {fill_frames}")
                emit_preview(fbo)
            if fill_frames % GPU_TEST_YIELD_FRAMES == 0:
                emit_yield()

        prog_fill.release()

        # =====================================================
        # ALU phase (remaining 50%)
        # =====================================================
        emit_progress(52, "ALU warmup — calibrating workload...")
        alu_durations = []
        alu_frames = 0
        alu_budget = GPU_TEST_DURATION_S * 0.5

        prog_alu.bind()
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_id)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, ctypes.c_void_p(0))

        # ── Warmup + adaptive iteration count ──────────────────────────
        # Render 30 frames at baseline. Median time tells us how
        # powerful the GPU is. Scale iterations so the actual test
        # runs ~4s of MEANINGFUL load on every GPU (weak or flagship).
        WARMUP_FRAMES = 30
        prog_alu.setUniformValue("u_max_iter", int(GPU_TEST_MANDEL_ITER))
        warmup_durations = []
        for _ in range(WARMUP_FRAMES):
            if time.perf_counter() - t_start > GPU_TEST_HARD_TIMEOUT_S:
                break
            wt0 = time.perf_counter()
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
            GL.glFinish()
            warmup_durations.append(time.perf_counter() - wt0)
            # Yield to event loop periodically — matches the timed phases
            # and prevents paint-event pile-up during warmup.
            if len(warmup_durations) % 10 == 0:
                emit_yield()

        # Discard the first 5 frames: driver pipeline JIT + cache warmup on
        # the very first draws can be 5-15 ms and would skew the median
        # upward, causing the calibrator to pick a workload tier that's
        # too light. The steady-state frames reflect real sustained speed.
        warmup_steady = (
            warmup_durations[5:]
            if len(warmup_durations) > 5
            else warmup_durations
        )

        if len(warmup_steady) >= 5:
            median_ms = statistics.median(warmup_steady) * 1000.0
            if median_ms < 0.15:
                alu_iterations = 4096   # 32× — only true flagships (4090, 5090)
            elif median_ms < 0.5:
                alu_iterations = 2048   # 16× — high-discrete (RTX 4060+)
            elif median_ms < 1.2:
                alu_iterations = 1024   #  8× — mid-discrete
            elif median_ms < 2.5:
                alu_iterations = 512    #  4× — low-mid discrete / strong iGPU
            elif median_ms < 20.0:
                alu_iterations = 128    # baseline    — integrated/old
            elif median_ms < 50.0:
                alu_iterations = 64     # 2× lighter
            else:
                alu_iterations = 32     # 4× lighter  — very weak
            emit_progress(
                54,
                f"ALU calibrated: {alu_iterations} iters "
                f"(warmup {median_ms:.2f} ms/frame)",
            )
        else:
            alu_iterations = GPU_TEST_MANDEL_ITER  # fallback

        prog_alu.setUniformValue("u_max_iter", int(alu_iterations))

        # ── Timed ALU phase ────────────────────────────────────────────
        emit_progress(56, f"ALU Throughput ({alu_iterations} iters)...")
        alu_t0 = time.perf_counter()

        while alu_frames < GPU_TEST_FRAME_CAP:
            elapsed = time.perf_counter() - alu_t0
            if elapsed >= alu_budget:
                break
            # Inline hard timeout
            if time.perf_counter() - t_start > GPU_TEST_HARD_TIMEOUT_S:
                prog_alu.release()
                return {
                    "supported": True, "aborted": "hard_timeout",
                    "duration_s": round(time.perf_counter() - t_start, 2),
                    "temp_after_c": _read_gpu_temp(),
                    "gpu_name": identity["name"],
                    "driver_version": identity["driver"],
                    "vram_gb": identity["vram_gb"],
                    "all_gpus": identity.get("all_gpus", []),
                    "gl_version": gl_version,
                    "gl_renderer": gl_renderer,
                    "notes": ["ALU phase exceeded hard timeout — aborting."],
                }

            # Gate 6: mid-test temp check
            if alu_frames > 0 and alu_frames % GPU_TEST_TEMP_CHECK_FRAMES == 0:
                cur_temp = _read_gpu_temp()
                if isinstance(cur_temp, (int, float)) and cur_temp >= GPU_TEST_TEMP_ABORT_C:
                    prog_alu.release()
                    return {
                        "supported": True, "aborted": "thermal", "partial": True,
                        "duration_s": round(time.perf_counter() - t_start, 2),
                        "temp_after_c": cur_temp,
                        "gpu_name": identity["name"],
                        "driver_version": identity["driver"],
                        "vram_gb": identity["vram_gb"],
                        "all_gpus": identity.get("all_gpus", []),
                        "gl_version": gl_version,
                        "gl_renderer": gl_renderer,
                        "notes": [
                            f"Test aborted at {cur_temp} °C for safety "
                            f"(limit: {GPU_TEST_TEMP_ABORT_C} °C).",
                            "Partial results discarded — cool the GPU and re-run.",
                        ],
                    }

            frame_t0 = time.perf_counter()
            prog_alu.setUniformValue("u_time", float(elapsed))
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
            GL.glFinish()
            dt = time.perf_counter() - frame_t0
            alu_durations.append(dt)
            alu_frames += 1

            if dt > 0.5:
                prog_alu.release()
                return {
                    "supported": True, "aborted": "frame_timeout",
                    "duration_s": round(time.perf_counter() - t_start, 2),
                    "gpu_name": identity["name"],
                    "all_gpus": identity.get("all_gpus", []),
                    "gl_version": gl_version,
                    "gl_renderer": gl_renderer,
                    "notes": ["ALU frame exceeded 500 ms — GPU too slow or driver stall."],
                }

            if alu_frames % GPU_TEST_PREVIEW_FRAMES == 0:
                pct = 52 + int(40 * elapsed / alu_budget)
                emit_progress(pct, f"ALU — frame {alu_frames}")
                emit_preview(fbo)
            if alu_frames % GPU_TEST_YIELD_FRAMES == 0:
                emit_yield()

        prog_alu.release()

        # =====================================================
        # Metrics
        # =====================================================
        emit_progress(95, "Computing metrics...")

        # Fill rate
        fill_time = sum(fill_durations)
        fill_mpix_s = (
            (W * H * fill_frames) / 1_000_000
        ) / max(fill_time, 0.001)

        # ALU throughput — two numbers:
        #   1. raw throughput at calibrated iters (for internal validation)
        #   2. NORMALIZED to baseline 128 iters (for cross-GPU comparison)
        #
        # Normalization is just a scaling: at 4096 iters each pixel does
        # 32× more work. Dividing by that factor gives "what this GPU
        # would score at 128 iters" — the same unit Intel runs at.
        alu_time = sum(alu_durations)
        ops_per_pixel_actual = alu_iterations * GPU_TEST_OPS_PER_ITER
        total_ops_actual = W * H * ops_per_pixel_actual * alu_frames
        alu_mops_s_actual = (total_ops_actual / 1_000_000) / max(alu_time, 0.001)

        # Normalized back to baseline 128 iters
        iteration_scale = alu_iterations / float(GPU_TEST_MANDEL_ITER)
        alu_mops_s = alu_mops_s_actual / iteration_scale

        # Frame time jitter — MAD-based (median absolute deviation).
        # Uses ALU steady-state only. MAD is robust to outliers: one slow
        # frame out of 295 won't misclassify a stable GPU as unstable.
        # Also compute mean/std for diagnostics; verdict uses MAD.
        WARMUP = 5
        alu_steady = alu_durations[WARMUP:] if len(alu_durations) > WARMUP else alu_durations
        if len(alu_steady) >= 4:
            median_dt = statistics.median(alu_steady)
            mad = statistics.median([abs(dt - median_dt) for dt in alu_steady])
            jitter_pct = (mad / median_dt * 100) if median_dt > 0 else 0.0
            mean_dt = statistics.mean(alu_steady)
            jitter_mean_pct = (
                (statistics.pstdev(alu_steady) / mean_dt * 100)
                if mean_dt > 0 else 0.0
            )
        else:
            jitter_pct = 0.0
            jitter_mean_pct = 0.0

        # Thermal headroom (ALU phase, steady-state only)
        fps_first = fps_last = 0.0
        thermal_pct = 0.0
        if len(alu_steady) >= 10:
            n = len(alu_steady)
            k = max(2, n // 5)
            first = statistics.mean(alu_steady[:k])
            last = statistics.mean(alu_steady[-k:])
            fps_first = 1.0 / first if first > 0 else 0.0
            fps_last = 1.0 / last if last > 0 else 0.0
            if fps_first > 0:
                thermal_pct = max(0.0, (fps_first - fps_last) / fps_first * 100)

        # Stability verdict — MAD-based thresholds (more conservative than
        # the mean/std thresholds because MAD values are ~60% of std).
        if jitter_pct > GPU_TEST_JITTER_MAD_FAIL:
            stability = "UNSTABLE_DELIVERY"
        elif thermal_pct > GPU_TEST_THROTTLE_WARN_PCT:
            stability = "THERMAL_THROTTLE"
        elif jitter_pct > GPU_TEST_JITTER_MAD_WARN:
            stability = "MILD_JITTER"
        else:
            stability = "STABLE"

        notes = []
        if thermal_pct > GPU_TEST_THROTTLE_WARN_PCT:
            notes.append(f"FPS dropped {thermal_pct:.1f}% during the run — GPU is throttling.")
            notes.append("Check airflow, fan speed, and dust buildup.")
        if jitter_pct > GPU_TEST_JITTER_MAD_FAIL:
            notes.append(f"Frame time jitter is {jitter_pct:.1f}% — delivery is unstable.")

        # Cross-check: which vendor did OpenGL actually run on?
        def _vendor(t):
            tl = (t or "").lower()
            if "nvidia" in tl: return "nvidia"
            if "amd" in tl or "radeon" in tl: return "amd"
            if "intel" in tl: return "intel"
            if "microsoft" in tl or "software" in tl: return "microsoft"
            return ""
        primary_vendor = _vendor(identity["name"])
        renderer_vendor = _vendor(gl_renderer)
        if (primary_vendor and renderer_vendor
                and primary_vendor != renderer_vendor):
            notes.append(
                f"OpenGL rendered via '{gl_renderer}' ({renderer_vendor}), "
                f"not '{identity['name']}' ({primary_vendor})."
            )
            notes.append(
                "On hybrid-GPU systems, OpenGL may use the integrated GPU. "
                "To benchmark the discrete GPU, set Phantom Optimizer to "
                "'High performance' in Windows Settings → Display → Graphics."
            )
            notes.append(
                f"Note: temperature readings are from '{identity['name']}' "
                f"(the primary GPU), not from the GPU that actually "
                f"performed this benchmark."
            )

        temp_after = _read_gpu_temp()

        emit_progress(100, "Complete")

        return {
            "supported": True,
            "gpu_name": identity["name"],
            "driver_version": identity["driver"],
            "vram_gb": identity["vram_gb"],
            "primary_kind": identity.get("primary_kind", "unknown"),
            "all_gpus": identity.get("all_gpus", []),
            "gl_version": gl_version,
            "gl_renderer": gl_renderer,
            "duration_s": round(time.perf_counter() - t_start, 2),
            "fill_rate_mpix_s": round(fill_mpix_s, 1),
            "alu_mops_s": round(alu_mops_s, 1),           # normalized
            "alu_mops_s_actual": round(alu_mops_s_actual, 1),  # raw
            "fill_frames": fill_frames,
            "alu_frames": alu_frames,
            "fps_first_second": round(fps_first, 1),
            "fps_last_second": round(fps_last, 1),
            "frame_jitter_pct": round(jitter_pct, 2),
            "frame_jitter_mean_pct": round(jitter_mean_pct, 2),
            "thermal_headroom_pct": round(thermal_pct, 2),
            "temp_before_c": temp_before,
            "temp_after_c": temp_after,
            "stability": stability,
            "notes": notes,
        }

    except Exception as e:
        return {
            "supported": False,
            "reason": f"Runtime error: {e}",
            "gpu_name": identity["name"],
            "driver_version": identity["driver"],
            "vram_gb": identity["vram_gb"],
            "all_gpus": identity.get("all_gpus", []),
            "gl_version": gl_version,
            "gl_renderer": gl_renderer,
        }

    finally:
        # Gate 8: cleanup — every step isolated
        try:
            GL.glBindVertexArray(0)
        except Exception: pass
        try:
            if vao_id:
                GL.glDeleteVertexArrays(1, [vao_id])
        except Exception: pass
        try:
            if vbo_id:
                GL.glDeleteBuffers(1, [vbo_id])
        except Exception: pass
        try:
            if prog_fill: prog_fill.removeAllShaders()
        except Exception: pass
        try:
            if prog_alu: prog_alu.removeAllShaders()
        except Exception: pass
        try:
            if fbo: fbo.release()
        except Exception: pass
        try:
            context.doneCurrent()
            context.destroy()
        except Exception: pass
        try:
            surface.destroy()
        except Exception: pass