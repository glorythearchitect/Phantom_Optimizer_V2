"""
core/configs.py
Centralized constants, thresholds, URLs, and version info for Phantom Optimizer.
Every module should import from here instead of hardcoding values.
"""

# =========================
# App Information
# =========================
APP_NAME = "Phantom Optimizer"
APP_VERSION = "2.0"
APP_BUILD_DATE = "2025-11-02"
AUTHOR = "Glory The Architect (SSS)"
COMPATIBLE_OS = "Windows 10/11 (32-bit & 64-bit)"
PYTHON_MIN = "3.10+"
ADMIN_REQUIRED = True

# =========================
# Paths / Files
# =========================
WHITELIST_FILE = "whitelist.txt"
DEFAULT_REPORT_NAME = "diagnostics_report.txt"

# =========================
# Process / Performance Thresholds
# =========================
PROCESS_HEAVY_CPU = 40.0      # % CPU usage threshold for heavy process
PROCESS_HEAVY_MEM_MB = 800.0  # MB memory threshold for heavy process
CPU_HOT_C = 90                # °C (critical CPU temperature)
GPU_HOT_C = 85                # °C (critical GPU temperature)
RAM_CLEAN_THRESHOLD = 75      # % RAM usage to trigger cleaner suggestion
DISK_WARN_USAGE = 90          # % used space warning

# =========================
# Scan / Timeout Settings
# =========================
PS_TIMEOUT_S = 8              # PowerShell command timeout
CMD_TIMEOUT_S = 8             # CMD command timeout
AUTO_CHECK_INTERVAL_MIN = 30  # Interval for auto system checks
MONITOR_INTERVAL_SEC = 3      # Live monitor refresh interval

# =========================
# Logs / Diagnostics
# =========================
LOG_PULL_LIMIT = 100          # Number of event logs to fetch
ADV_LOG_PULL_LIMIT = 200      # Deeper logs for advanced tab
LOG_CATEGORIES = [
    "Device Plug/Unplug",
    "Thermal Warning",
    "Firmware/BIOS",
    "Boot Issue",
    "Storage Error",
    "CPU/GPU Issue",
    "General"
]

# =========================
# URLs / Online Features (future)
# =========================
ONLINE_SUGGESTIONS_URL = "https://phantom.glory/api/suggestions"
ONLINE_BENCHMARK_URL = "https://phantom.glory/api/benchmarks"
DRIVER_UPDATE_URL = "https://phantom.glory/api/drivers"

ENABLE_ONLINE_SUGGESTIONS = False
ENABLE_ONLINE_BENCHMARK = False
ENABLE_DRIVER_UPDATE = False

# =========================
# Visual / UI Presets
# =========================
THEME_PRIMARY = "#00FFFF"
THEME_ACCENT = "#FF00FF"
THEME_TEXT = "#E0E0E0"
THEME_BG = "#111111"
THEME_DARK = "#000000"

# =========================
# Developer Options
# =========================
DEBUG_MODE = False
LOG_EXCEPTIONS = True


# =========================
# Optimizer Thresholds (V2)
# =========================
OPTIMIZER_APP_CPU_THRESHOLD = 2.0        # % CPU to classify as "app" (vs background)
OPTIMIZER_APP_MEM_THRESHOLD_MB = 150     # MB to classify as "app"
OPTIMIZER_TERMINATE_GRACE_S = 3          # seconds to wait after terminate() before kill()
OPTIMIZER_KILL_GRACE_S = 2               # seconds to wait after kill()

# =========================
# GPU Test — GPU Pulse (V2)
# =========================
GPU_TEST_DURATION_S         = 8        # hard wall-clock cap
GPU_TEST_FRAME_CAP          = 20000    # hard frame cap (safety only —
                                       # time budget is the real limiter)
GPU_TEST_TEMP_WARN_C        = 85       # refuse to start above this
GPU_TEST_TEMP_ABORT_C       = 90       # abort mid-test above this
GPU_TEST_TEMP_CHECK_FRAMES  = 120      # re-check temp every N frames
GPU_TEST_PREVIEW_FRAMES     = 15       # stream preview every N frames
GPU_TEST_PREVIEW_W          = 480
GPU_TEST_PREVIEW_H          = 270
GPU_TEST_RENDER_W           = 1920
GPU_TEST_RENDER_H           = 1080
GPU_TEST_MANDEL_ITER        = 128      # bounded iteration count
GPU_TEST_OPS_PER_ITER       = 13       # conservative (6 mul + 5 add + 2 cmp)
GPU_TEST_JITTER_WARN_PCT    = 5
GPU_TEST_JITTER_FAIL_PCT    = 10
GPU_TEST_THROTTLE_WARN_PCT  = 5
GPU_TEST_GPU_USE_WARN_PCT   = 10       # nvidia-smi utilization % warning threshold
GPU_TEST_YIELD_FRAMES       = 15       # yield to event loop every N frames
GPU_TEST_HARD_TIMEOUT_S     = 20       # inline hard timeout for GUI-thread run
GPU_TEST_JITTER_MAD_WARN    = 10       # MAD-based jitter warn (%)
GPU_TEST_JITTER_MAD_FAIL    = 20       # MAD-based jitter fail (%)

# =========================
# CPU Test (V2)
# =========================
CPU_TEST_TEMP_WARN_C  = 85   # refuse to start above this
CPU_TEST_TEMP_ABORT_C = 90   # abort mid-test above this