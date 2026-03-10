"""
Zentrale Konfiguration für das Overwatch-Tool.
Hier kannst du das Verhalten und die Startdaten des Programms anpassen.
"""

import sys


def _as_bool(value) -> bool:
    """Best-effort bool coercion with support for common string forms."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _normalize_str(value, default: str = "") -> str:
    text = str(value if value is not None else "").strip()
    if text:
        return text
    return str(default)


def _normalize_csv_list(value, default: list[str]) -> list[str]:
    if isinstance(value, str):
        raw_tokens = [tok.strip() for tok in value.replace("+", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_tokens = [str(tok).strip() for tok in value]
    else:
        raw_tokens = []
    deduped: list[str] = []
    seen: set[str] = set()
    for token in raw_tokens:
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(token)
    if deduped:
        return deduped
    return list(default)


def _normalize_int_list(value, default: list[int], *, min_value: int = 0, max_value: int = 10_000) -> list[int]:
    if isinstance(value, str):
        raw_items = [part.strip() for part in value.replace(";", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = []
    normalized: list[int] = []
    seen: set[int] = set()
    for item in raw_items:
        number = _as_int(item, min_value)
        number = max(int(min_value), min(int(max_value), int(number)))
        if number in seen:
            continue
        seen.add(number)
        normalized.append(number)
    if normalized:
        return normalized
    return [max(int(min_value), min(int(max_value), int(v))) for v in default]

# ---------- Runtime / Logging ----------
DEBUG = False
# Relative paths are created inside the writable app state directory.
# Set to "" to keep logs directly in state dir, or use an absolute path.
LOG_OUTPUT_DIR = "logs"
# Master-Schalter für Release/EXE:
# - unterdrückt Konsole/Qt-Logs (siehe main.py)
# - unterdrückt zusätzlich Python-Warnings und Logging-Ausgaben
# - deaktiviert zusätzlich alle internen Debug-/Trace-Logs
# - Save-State bleibt davon unberührt
QUIET = False
# Prevent duplicate starts on Windows (e.g. fast double-click on the EXE).
WINDOWS_SINGLE_INSTANCE = True
WINDOWS_SINGLE_INSTANCE_LOCK_NAME = "ow_wheelpicker_instance"


def _disable_flags_if_quiet(*flag_names: str) -> None:
    """Setzt angegebene bool-Flags auf False, wenn QUIET aktiv ist."""
    if not QUIET:
        return
    g = globals()
    for name in flag_names:
        g[name] = False


# Trace / Focus
TRACE_FLOW = True
TRACE_SHUTDOWN = False
TRACE_FOCUS = False
TRACE_HOVER = False
TRACE_SPIN_PERF = True
TRACE_CLEAR_ON_START = False
# Reduziert Rauschen in flow_trace.log durch häufige Startup-/OCR-Events.
# Bei Bedarf für tiefe Analysen temporär aktivieren.
TRACE_STARTUP_VISUAL_FINALIZE_DEFER = False
TRACE_OCR_PRELOAD_VERBOSE = False
TRACE_OCR_RUNTIME = True
TRACE_SHUTDOWN_STEP_VERBOSE = False
FOCUS_TRACE_DURATION_S = 12.0
FOCUS_TRACE_MAX_EVENTS = 800
DISABLE_TOOLTIPS = True
FOCUS_TRACE_WINDOW_EVENTS = True
FOCUS_TRACE_WINDOWS_ONLY = True
FOCUS_TRACE_SNAPSHOT_INTERVAL_MS = 200
FOCUS_TRACE_SNAPSHOT_COUNT = 20
HOVER_TRACE_MAX_EVENTS = 200
HOVER_TRACE_BUDGET_PER_VIEW = 20
HOVER_POKE_ON_REARM = False
# Nur aktivieren, wenn Hover auf einem Zielsystem sonst nicht zuverlässig ist.
# Globales MouseMove-Forwarding erhöht Event-Last deutlich.
HOVER_FORWARD_MOUSEMOVE = False
HOVER_FORWARD_INTERVAL_MS = 50

# Startup interaction / input-guard
STARTUP_DROP_CHOICE_POINTER_EVENTS = True
MODE_CHOICE_INPUT_GUARD_MS = 260
# Enables/disables the Online mode button in the startup choice overlay.
# Keep disabled in this version until online flow is fully released.
MODE_CHOICE_ONLINE_ENABLED = False
STARTUP_FINALIZE_DELAY_MS = 60
# Additional cooldown after startup warmup before controls are re-enabled.
# Set to 0 for no extra delay.
STARTUP_WARMUP_COOLDOWN_MS = 0
STARTUP_INPUT_DRAIN_MS = 0
# Minimum startup lock duration for global input filtering.
# Set to 0 to disable this additional lock window.
STARTUP_MIN_BLOCK_INPUT_MS = 0
# While startup input lock is active, immediately clear focus/activation
# events so the window cannot be interacted with accidentally.
STARTUP_CLEAR_FOCUS_WHILE_BLOCKED = True
# Run visual/theme finalize after mode choice and only when UI is idle.
# This keeps the first interaction path responsive on slower systems.
STARTUP_VISUAL_FINALIZE_DEFERRED = True
STARTUP_VISUAL_FINALIZE_DELAY_MS = 280
STARTUP_VISUAL_FINALIZE_BUSY_RETRY_MS = 250
# Kurze Abschluss-Einblendung beim Beenden anzeigen.
SHUTDOWN_OVERLAY_ENABLED = True
SHUTDOWN_OVERLAY_DELAY_MS = 320
# Shutdown wait windows for OCR worker threads.
# Async OCR import thread (normal OCR action):
SHUTDOWN_OCR_ASYNC_GRACEFUL_WAIT_MS = 1200
SHUTDOWN_OCR_ASYNC_TERMINATE_WAIT_MS = 700
# Background OCR preload thread:
SHUTDOWN_OCR_PRELOAD_GRACEFUL_WAIT_MS = 1400
SHUTDOWN_OCR_PRELOAD_TERMINATE_WAIT_MS = 350
# On Windows, force-stop OCR preload immediately on close to avoid lingering
# background processes when the window is closed during preload warmup.
SHUTDOWN_OCR_PRELOAD_FORCE_STOP_ON_CLOSE = True
# Fallback profile for other QThreads found during close.
SHUTDOWN_CHILD_THREAD_GRACEFUL_WAIT_MS = 350
SHUTDOWN_CHILD_THREAD_TERMINATE_WAIT_MS = 250
# Maximum cumulative defer time while waiting for OCR/background threads during
# close. After this timeout, shutdown falls back to orphaned-thread cleanup.
SHUTDOWN_THREAD_MAX_DEFER_MS = 2500
# Minimum interval between repeated blocker snapshots in flow trace while close
# is waiting on running threads.
SHUTDOWN_BLOCKER_TRACE_INTERVAL_MS = 250
# Additional wait window for non-daemon Python threads discovered during close.
SHUTDOWN_PYTHON_THREAD_MAX_DEFER_MS = 1800
# Additional guard: request app.quit() again shortly after close accepted.
SHUTDOWN_APP_QUIT_GUARD_MS = 1500
# Last in-event-loop fallback: force QApplication.exit(0) after close.
SHUTDOWN_APP_FORCE_EXIT_LOOP_MS = 2400
# Keep main window visible while shutdown is still in progress. This prevents
# the "window is gone but process still runs" impression on Windows.
SHUTDOWN_KEEP_WINDOW_VISIBLE_UNTIL_EXIT = bool(sys.platform.startswith("win"))
# Process-level fallback for stuck shutdowns (e.g. orphaned OCR worker threads).
# Enabled by default on Windows, where background lingering was reported.
SHUTDOWN_FORCE_EXIT_WATCHDOG_ENABLED = bool(sys.platform.startswith("win"))
# Hard-exit deadline after first close request. Set 0 to disable.
SHUTDOWN_FORCE_EXIT_WATCHDOG_MS = 12000
# If shutdown had to orphan a still-running thread, shorten hard-exit deadline.
SHUTDOWN_FORCE_EXIT_ON_ORPHAN_MS = 2200
# Keep OCR runtime cache release out of shutdown by default.
# Cache release can be expensive (gc/torch) and app exit already frees memory.
SHUTDOWN_RELEASE_OCR_CACHE = False
# Delay used when deferred post-choice initialization must be retried because
# the wheel is currently spinning.
POST_CHOICE_INIT_BUSY_RETRY_MS = 220
# Für schnelleren Start standardmäßig Platform-Style nutzen.
FORCE_FUSION_STYLE = False
HOVER_PUMP_ON_START = False
# 0 = kein Timeout (läuft bis echte Hover-Events erkannt werden)
HOVER_PUMP_DURATION_MS = 0
HOVER_PUMP_INTERVAL_MS = 90

# QUIET erzwingt "silent runtime" für alle Debug-/Trace-Kanäle.
QUIET_DISABLED_TRACE_FLAGS = (
    "DEBUG",
    "TRACE_FLOW",
    "TRACE_SHUTDOWN",
    "TRACE_FOCUS",
    "TRACE_HOVER",
    "TRACE_SPIN_PERF",
    "TRACE_CLEAR_ON_START",
    "TRACE_STARTUP_VISUAL_FINALIZE_DEFER",
    "TRACE_OCR_PRELOAD_VERBOSE",
    "TRACE_OCR_RUNTIME",
    "TRACE_SHUTDOWN_STEP_VERBOSE",
)
_disable_flags_if_quiet(*QUIET_DISABLED_TRACE_FLAGS)

# ---------- Performance / Resource policy ----------
MAP_PREBUILD_ON_START = True
SOUND_WARMUP_ON_START = True
# Warm wheel caches during startup warmup so first spin starts immediately.
STARTUP_WHEEL_CACHE_WARMUP = True
# Keep OCR preload out of the main startup warmup so Online/Offline choice
# becomes clickable faster. OCR preload still runs in its own background path.
STARTUP_OCR_PRELOAD = False
# Do not block mode-choice forever if OCR preload stalls.
STARTUP_OCR_PRELOAD_MAX_WAIT_MS = 1800
# If OCR preload has already started in a worker thread, allow extra warmup
# wait so startup warmup does not finish while preload is still in progress.
STARTUP_OCR_PRELOAD_RUNNING_MAX_WAIT_MS = 14000
# Do not block mode-choice forever if map prebuild stalls.
STARTUP_MAP_PREBUILD_MAX_WAIT_MS = 2200
# Tooltip cache refresh remains asynchronous (post-choice/post-init) and is
# intentionally not counted as a startup warmup task.
TOOLTIP_CACHE_ON_START = False
SOUND_WARMUP_LAZY_STEP_MS = 25
# Use a lightweight control lock during spin so large name lists are not fully
# disabled/re-styled at spin start (helps animation under CPU load).
SPIN_LIGHTWEIGHT_UI_LOCK = True
# Pause incremental sound warmup while spinning to keep the UI thread free.
PAUSE_SOUND_WARMUP_DURING_SPIN = True
# Small safety gap between stop(old spin/ding) and start(new spin sound).
# -1 = auto (Windows uses a small delay, others use 0ms), >=0 = explicit ms.
# Profiles for Windows auto mode: low=20ms, balanced=30ms, high=40ms, auto=35ms.
# Default to "high" to prioritize clean separation between end-ding and next spin.
SOUND_SPIN_RESTART_GAP_PROFILE = "high"
SOUND_SPIN_RESTART_GAP_MS = -1
# Additional stop-tail guard for audio backends that release output asynchronously.
# -1 = auto profile, >=0 = explicit milliseconds.
SOUND_AUDIO_STOP_GUARD_MS = -1
STATE_SAVE_DEBOUNCE_MS = 220
NETWORK_SYNC_DEBOUNCE_MS = 220
NETWORK_SYNC_WORKERS = 2
# Retry delay used by wheel widgets when cache warmup should be postponed
# (startup overlay visible, spin active, or updates paused).
WHEEL_CACHE_WARMUP_RETRY_MS = 180
# Suspend optional background UI services while spinning to keep animation smooth.
PAUSE_BACKGROUND_UI_SERVICES_DURING_SPIN = True

# ---------- OCR Import ----------
# OCR engine (local/offline):
# - "easyocr" is the active/default backend.
OCR_ENGINE = "easyocr"
# EasyOCR language list (comma/plus separated), e.g. "en" or "en,de".
# Default includes German, Japanese, Chinese (simplified), and Korean.
# Note: More languages increase OCR runtime.
OCR_EASYOCR_LANG = "en,de,ja,ch_sim,ko"
# Local model paths for EasyOCR (optional). Keep empty to use EasyOCR defaults.
OCR_EASYOCR_MODEL_DIR = ""
OCR_EASYOCR_USER_NETWORK_DIR = ""
# "auto" picks the best available device in this order: CUDA -> MPS -> CPU.
# You can force a specific backend with "cpu", "mps", or "cuda".
OCR_EASYOCR_GPU = "auto"
# Keep False for strict offline behavior (no model downloads at runtime).
OCR_EASYOCR_DOWNLOAD_ENABLED = False
# Keep OCR runtime fully asleep until the first OCR import click.
OCR_RUNTIME_SLEEP_UNTIL_USED = True
# Optional low-priority background preload after startup warmup.
# Helps reduce first-click OCR latency while keeping startup responsive.
OCR_BACKGROUND_PRELOAD_ENABLED = True
OCR_BACKGROUND_PRELOAD_DELAY_MS = 2500
# Keep preload off during the first startup seconds to avoid contention with
# the first user interaction/spin click.
OCR_BACKGROUND_PRELOAD_MIN_UPTIME_MS = 8000
# Allow startup warmup to bypass overlay/cooldown gating for upfront preload.
OCR_BACKGROUND_PRELOAD_ALLOW_DURING_STARTUP = True
# If startup/spin is still busy when preload is due, retry later.
OCR_BACKGROUND_PRELOAD_BUSY_RETRY_MS = 1800
# Timeout for the OCR background-preload subprocess. If exceeded, preload is
# aborted so shutdown can stay responsive.
OCR_PRELOAD_SUBPROCESS_TIMEOUT_S = 60.0
# Use a helper subprocess for preload probe. In frozen Windows builds this can
# spawn an extra app process, so runtime defaults switch to in-process probe.
OCR_PRELOAD_USE_SUBPROCESS_PROBE = True
# Frozen Windows override for preload probe subprocess usage.
OCR_PRELOAD_USE_SUBPROCESS_PROBE_WIN_FROZEN = False
# After subprocess readiness probe, also warm EasyOCR reader cache in-process.
# This makes the first real OCR click much faster because reader init/import
# already happened in the app runtime (not only in a helper subprocess).
OCR_PRELOAD_INPROCESS_CACHE_WARMUP = True
# Keep an already running preload thread alive during spin/background pause by
# default. This improves preload reliability and avoids repeated cold starts.
# Enable only if spin smoothness on very weak systems is more important.
OCR_PRELOAD_CANCEL_RUNNING_ON_SPIN = False
# Release cached OCR runtimes after idle (0 disables automatic release).
# Lower value = faster sleep when OCR is not used.
OCR_IDLE_CACHE_RELEASE_MS = 30000
# If cache release is due while a spin is active, retry after this delay.
OCR_IDLE_CACHE_RELEASE_BUSY_RETRY_MS = 2500
# Keep cache release on spin disabled by default to avoid UI-thread spikes at
# spin start when OCR runtimes were initialized before.
OCR_RELEASE_CACHE_ON_SPIN = False
# OCR parsing/runtime knobs (engine-agnostic naming).
OCR_PRIMARY_PSM = 11
OCR_FALLBACK_PSM = 6
OCR_RETRY_EXTRA_PSMS = [7, 13]
OCR_TIMEOUT_S = 8.0
# Windows override for OCR timeout (seconds). Lower = more responsive.
OCR_TIMEOUT_S_WINDOWS = 6.0
OCR_FAST_MODE = True
# 0 = all generated variants, >0 = cap variant count per OCR run
OCR_MAX_VARIANTS = 2
# Windows override: prefer one quick variant first for faster OCR response.
OCR_MAX_VARIANTS_WINDOWS = 1
# In fast mode, stop after the first variant that yields text
OCR_STOP_AFTER_FIRST_VARIANT_SUCCESS = False
# Additional fast-mode short-circuit: if the first variant already contains
# enough confident lines, skip remaining variants for this pass.
OCR_FAST_MODE_CONFIDENT_LINE_STOP = True
# 0 = use current expected candidate count as minimum line threshold.
OCR_FAST_MODE_CONFIDENT_LINE_MIN_LINES = 0
OCR_FAST_MODE_CONFIDENT_LINE_MIN_AVG_CONF = 68.0
# Allows early stop even if one expected line is missing, as long as confidence
# is high enough (helps skip expensive second variant on stable captures).
OCR_FAST_MODE_CONFIDENT_LINE_MISSING_TOLERANCE = 1
OCR_FAST_MODE_CONFIDENT_LINE_MIN_AVG_CONF_TOLERANT = 78.0
# Lightweight visual row pre-count in fast mode: use fewer probe variants and
# usually only one expected-row guess to cut redundant preprocessing.
OCR_PRECOUNT_FAST_PROBE_ENABLED = True
OCR_PRECOUNT_FAST_PROBE_SINGLE_EXPECTED = True
OCR_PRECOUNT_FAST_PROBE_MAX_VARIANTS = 1
# Retry with a more thorough OCR pass when fast mode found too few names.
OCR_RECALL_RETRY_ENABLED = True
# Retry trigger threshold (0 disables retry trigger).
OCR_RECALL_RETRY_MIN_CANDIDATES = 5
# Retry trigger threshold for too many detected names.
OCR_RECALL_RETRY_MAX_CANDIDATES = 7
# Retry trigger if too many very short names (len<=2) are present.
OCR_RECALL_RETRY_SHORT_NAME_MAX_RATIO = 0.34
# Skip retry when primary OCR is already clean/high-confidence and only
# narrowly below min candidate target (avoids expensive redundant repass).
OCR_RECALL_RETRY_SKIP_WHEN_PRIMARY_CLEAN = True
OCR_RECALL_RETRY_SKIP_PRIMARY_CLEAN_MIN_COUNT = 4
OCR_RECALL_RETRY_SKIP_PRIMARY_CLEAN_MAX_SHORTFALL = 1
OCR_RECALL_RETRY_SKIP_PRIMARY_CLEAN_MIN_AVG_CONF = 78.0
# Variant cap for retry pass (0 = same/all prepared variants).
OCR_RECALL_RETRY_MAX_VARIANTS = 4
# Retry can include fallback PSM for better recall.
OCR_RECALL_RETRY_USE_FALLBACK_PSM = True
# Retry timeout multiplier (>= 1.0).
OCR_RECALL_RETRY_TIMEOUT_SCALE = 1.35
# If low-count OCR results remain after retry, relax support filtering to avoid
# dropping single-pass names.
OCR_RECALL_RELAX_SUPPORT_ON_LOW_COUNT = True
# Row-based fallback OCR for low-count results (tries to OCR each detected text row).
OCR_ROW_PASS_ENABLED = True
OCR_ROW_PASS_ALWAYS_RUN = True
# If primary OCR already has stable, non-noisy candidates, skip row-pass even
# when ALWAYS_RUN is enabled (major speed-up on clean captures).
OCR_ROW_PASS_SKIP_WHEN_PRIMARY_STABLE = True
# 0 = dynamic default max(3, expected_candidates - 1)
OCR_ROW_PASS_PRIMARY_STABLE_MIN_CANDIDATES = 0
# If expected row estimate is only slightly above primary OCR count (projection
# overcount), allow stable-primary shortcut with relaxed expected row count.
OCR_ROW_PASS_PRIMARY_STABLE_RELAXED_EXPECTED_GAP = 3
OCR_ROW_PASS_PRIMARY_STABLE_RELAXED_MIN_AVG_CONF = 76.0
OCR_ROW_PASS_MIN_CANDIDATES = 5
OCR_ROW_PASS_BRIGHTNESS_THRESHOLD = 145
OCR_ROW_PASS_MIN_PIXELS_RATIO = 0.015
OCR_ROW_PASS_MERGE_GAP_PX = 2
OCR_ROW_PASS_MIN_HEIGHT_PX = 7
OCR_ROW_PASS_MAX_ROWS = 12
OCR_ROW_PASS_PAD_PX = 2
# Wider default row crop to reduce right-side truncation.
OCR_ROW_PASS_NAME_X_RATIO = 0.72
# If True, row-pass OCR also evaluates full-width rows in addition to name crop.
OCR_ROW_PASS_FULL_WIDTH_FALLBACK = True
# If True, use full-width crop only when the right edge looks clipped.
# Keeps recall for truncated names but avoids doubling OCR calls on clean rows.
OCR_ROW_PASS_FULL_WIDTH_EDGE_ONLY = True
# If True, run full-width fallback only when name-crop votes are still uncertain.
# This avoids expensive full-width retries once the name-crop already looks reliable.
OCR_ROW_PASS_FULL_ONLY_WHEN_NAME_UNCERTAIN = True
OCR_ROW_PASS_FULL_ONLY_WHEN_NAME_UNCERTAIN_MIN_CONF = 68.0
# If True, skip full-width retries when name base+scaled variants were both empty.
# This removes expensive full-width calls on obvious empty/noise rows.
OCR_ROW_PASS_SKIP_FULL_WHEN_NAME_EMPTY = True
# If True, also skip full-width retries when name variants only produce
# very weak low-confidence signal without any candidate votes.
OCR_ROW_PASS_SKIP_FULL_WHEN_NAME_LOW_CONF = True
OCR_ROW_PASS_SKIP_FULL_WHEN_NAME_LOW_CONF_MAX_CONF = 12.0
# Row projection window used for line segmentation.
# Helps avoid continuous bright borders/checkbox columns in OCR pick overlay.
OCR_ROW_PASS_PROJECTION_X_START_RATIO = 0.08
OCR_ROW_PASS_PROJECTION_X_END_RATIO = 0.92
OCR_ROW_PASS_PROJECTION_COL_MAX_RATIO = 0.84
OCR_ROW_PASS_SCALE_FACTOR = 4
OCR_ROW_PASS_INCLUDE_MONO = True
# If True, skip mono variants when base+scaled already produced no text.
# Reduces expensive no-signal retries on empty noise rows.
OCR_ROW_PASS_SKIP_MONO_WHEN_NON_MONO_EMPTY = True
# If True, skip mono variants when base+scaled produced text but only very
# weak low-confidence signal (typically noise).
OCR_ROW_PASS_SKIP_MONO_WHEN_NON_MONO_LOW_CONF = True
OCR_ROW_PASS_SKIP_MONO_WHEN_NON_MONO_LOW_CONF_MAX_CONF = 12.0
OCR_ROW_PASS_TIMEOUT_SCALE = 0.55
OCR_ROW_PASS_PSMS = [7, 13, 6]
# Keep one OCR winner per detected visual row to avoid duplicates from
# alternate render variants of the same line.
OCR_ROW_PASS_SINGLE_NAME_PER_ROW = True
# Treat primary pass as "complete-ish" when it is within this gap to expected.
OCR_ROW_PASS_PRIMARY_COMPLETE_MARGIN = 1
# Row-pass early stop target per visual row. Lower values reduce OCR calls.
OCR_ROW_PASS_VOTE_TARGET_SINGLE_NAME = 2
OCR_ROW_PASS_VOTE_TARGET_SINGLE_NAME_WHEN_PRIMARY_COMPLETE = 1
OCR_ROW_PASS_VOTE_TARGET_MULTI_NAME = 3
# If primary pass is already complete-ish, use only the first row-pass PSM to
# reduce expensive OCR attempts in fallback mode.
OCR_ROW_PASS_SINGLE_PSM_WHEN_PRIMARY_COMPLETE = True
# Fast-mode shortcut: if a row already has one very high-confidence candidate,
# stop this row early instead of forcing additional variants/crops.
OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_STOP = True
OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_MIN_CONF = 96.0
OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_STOP_WHEN_PRIMARY_COMPLETE = True
OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_MIN_CONF_WHEN_PRIMARY_COMPLETE = 72.0
# Early row-line filter before expensive parsing (keeps high-confidence lines).
OCR_ROW_PASS_LINE_PREFILTER_ENABLED = True
OCR_ROW_PASS_LINE_PREFILTER_LOW_CONF = 22.0
OCR_ROW_PASS_LINE_PREFILTER_HIGH_CONF_BYPASS = 72.0
OCR_ROW_PASS_LINE_PREFILTER_MIN_ALNUM = 2
OCR_ROW_PASS_LINE_PREFILTER_MIN_ALPHA_RATIO = 0.42
OCR_ROW_PASS_LINE_PREFILTER_MAX_PUNCT_RATIO = 0.65
# Prevent low-confidence row lines from inflating candidate stats.
OCR_ROW_PASS_LINE_STATS_MIN_CONF = 8.0
# If primary pass already has enough candidates and early row probes are weak,
# abort row-pass quickly to avoid expensive tail noise scans.
OCR_ROW_PASS_EARLY_ABORT_ON_PRIMARY_STRONG = True
OCR_ROW_PASS_EARLY_ABORT_PROBE_ROWS = 3
# If primary already reached expected row count, use a shorter probe window
# before aborting weak row-pass prefixes.
OCR_ROW_PASS_EARLY_ABORT_PROBE_ROWS_WHEN_PRIMARY_COMPLETE = 2
OCR_ROW_PASS_EARLY_ABORT_LOW_CONF = 22.0
# 0 = dynamic default max(4, expected_candidates - 2)
OCR_ROW_PASS_EARLY_ABORT_PRIMARY_MIN_CANDIDATES = 0
# Try mono variants only when current row votes are uncertain.
OCR_ROW_PASS_MONO_RETRY_ONLY_WHEN_UNCERTAIN = True
OCR_ROW_PASS_MONO_RETRY_MIN_CONF = 70.0
# For rows beyond expected_candidates, use a lighter OCR strategy after enough
# names were already collected (no full-width, no mono, 1 vote target).
OCR_ROW_PASS_EXTRA_ROWS_LIGHT_MODE = True
# 0 = dynamic default max(3, expected_candidates - 2)
OCR_ROW_PASS_EXTRA_ROWS_LIGHT_MODE_MIN_COLLECTED = 0
# Stop row-pass tail once expected_candidates are already collected.
# Limits expensive extra-row OCR calls without changing core row coverage.
OCR_ROW_PASS_STOP_WHEN_EXPECTED_REACHED = True
# Fast-mode row limit: process only expected+extra rows (with a small floor)
# instead of all detected rows, to avoid OCR on obvious tail noise rows.
OCR_ROW_PASS_ADAPTIVE_MAX_ROWS = True
OCR_ROW_PASS_ADAPTIVE_EXTRA_ROWS = 2
# Tail-noise guard: stop row-pass after N consecutive rows without new names
# once enough names were already collected (0 disables).
OCR_ROW_PASS_CONSECUTIVE_EMPTY_ROW_STOP = 2
# 0 = dynamic default max(3, expected_candidates - 1)
OCR_ROW_PASS_EMPTY_ROW_STOP_MIN_COLLECTED = 0
# OCR debug: shows a detailed report dialog after each OCR run.
OCR_DEBUG_SHOW_REPORT = False
# Keep enabled with OCR_DEBUG_SHOW_REPORT so the dialog receives the full report text.
OCR_DEBUG_INCLUDE_REPORT_TEXT = True
OCR_DEBUG_REPORT_MAX_CHARS = 24000
# Persist OCR debug reports into a file for easier sharing/analysis.
OCR_DEBUG_LOG_TO_FILE = True
OCR_DEBUG_LOG_FILE = "ocr_debug.log"
OCR_DEBUG_LOG_MAX_CHARS = 200000
# Per-line parser diagnostics (accepted/dropped + reason) inside debug report.
OCR_DEBUG_LINE_ANALYSIS = True
OCR_DEBUG_LINE_MAX_ENTRIES_PER_RUN = 60
# High-level mapping trace: each OCR line with strict/relaxed parse + final selection.
OCR_DEBUG_TRACE_LINE_MAPPING = True
OCR_DEBUG_TRACE_MAX_ENTRIES = 220
# QUIET erzwingt zusätzlich: keine OCR-Debug-Reports/Dateilogs.
QUIET_DISABLED_OCR_DEBUG_FLAGS = (
    "OCR_DEBUG_SHOW_REPORT",
    "OCR_DEBUG_INCLUDE_REPORT_TEXT",
    "OCR_DEBUG_LOG_TO_FILE",
    "OCR_DEBUG_LINE_ANALYSIS",
)
_disable_flags_if_quiet(*QUIET_DISABLED_OCR_DEBUG_FLAGS)
# Optional manual vocabulary that improves OCR correction for known player names.
# Keep disabled by default to avoid bias from hardcoded names.
OCR_USE_NAME_HINTS = False
OCR_NAME_HINTS = []
OCR_NAME_HINTS_ONLY_WHEN_SET = True
OCR_HINT_CORRECTION_MIN_SCORE = 0.62
OCR_HINT_CORRECTION_LOW_CONF_MIN_SCORE = 0.28
# OCR variants tailored for player list screenshots.
# Left-crop variants can truncate long names; keep disabled by default.
OCR_INCLUDE_LEFT_CROP_VARIANTS = False
OCR_NAME_COLUMN_CROP_RATIO = 0.50
OCR_INCLUDE_MONO_VARIANTS = True
OCR_SCALE_FACTOR = 3
OCR_NAME_MIN_CHARS = 2
# Allow longer OCR names so trailing parts are not dropped prematurely.
OCR_NAME_MAX_CHARS = 64
OCR_NAME_MAX_WORDS = 8
# Add at most this many line-parser fallback candidates when strict multi-line
# extraction missed lines (helps recover borderline rows without over-noising).
OCR_LINE_RECALL_MAX_ADDITIONS = 2
# Keep at most one parsed candidate per OCR text line.
OCR_SINGLE_NAME_PER_LINE = False
# If strict line parsing fails, run one relaxed parse pass for recall.
OCR_LINE_RELAXED_FALLBACK = True
OCR_NAME_MAX_DIGIT_RATIO = 0.45
# If True, OCR parsing aggressively trims on special characters/icons.
# Disabled by default to avoid cutting player lines too early.
OCR_NAME_SPECIAL_CHAR_CONSTRAINT = False
OCR_NAME_MIN_SUPPORT = 1
OCR_NAME_MIN_CONFIDENCE = 43.0
OCR_NAME_LOW_CONFIDENCE_MIN_SUPPORT = 2
OCR_NAME_CONFIDENCE_FILTER_NOISY_ONLY = True
OCR_NAME_HIGH_COUNT_THRESHOLD = 8
OCR_NAME_HIGH_COUNT_MIN_SUPPORT = 2
OCR_NAME_MAX_CANDIDATES = 12
OCR_NAME_NEAR_DUP_MIN_CHARS = 8
OCR_NAME_NEAR_DUP_MAX_LEN_DELTA = 1
OCR_NAME_NEAR_DUP_SIMILARITY = 0.90
OCR_NAME_NEAR_DUP_TAIL_MIN_CHARS = 3
OCR_NAME_NEAR_DUP_TAIL_HEAD_SIMILARITY = 0.70
OCR_USE_NATIVE_MAC_CAPTURE = True
# Hide the main window during region selection (recommended on Windows).
OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE = True
OCR_CAPTURE_PREPARE_DELAY_MS = 120
# Optional Windows-specific delay before capture selector opens.
OCR_CAPTURE_PREPARE_DELAY_MS_WINDOWS = 70
# UX: in Qt selector, confirm on mouse release instead of requiring Enter.
OCR_QT_SELECTOR_AUTO_ACCEPT_ON_RELEASE = True
OCR_CAPTURE_TIMEOUT_S = 45.0
# Separate OCR runtime trace for import/thread diagnostics.
OCR_RUNTIME_TRACE_FILE = "ocr_runtime_trace.log"
# Best-effort soft cap for trace file size (bytes). Older content is trimmed.
OCR_RUNTIME_TRACE_MAX_BYTES = 2_000_000

# ---------- Sprache ----------
# Voreingestellte Sprache, wenn keine Auswahl gespeichert wurde
DEFAULT_LANGUAGE = "en"

def debug_print(*args, **kwargs):
    """Wrapper um print, der nur aktiv ist, wenn DEBUG True ist."""
    if DEBUG and not QUIET:
        print(*args, **kwargs)

# ---------- UI / Animation ----------
WHEEL_RADIUS = 136
MIN_DURATION_MS = 0
MAX_DURATION_MS = 10000
DEFAULT_DURATION_MS = 3000
# Spin fallback watchdogs for overloaded systems.
SPIN_WATCHDOG_ENABLED = False
SPIN_WATCHDOG_SCALE = 1.8
SPIN_WATCHDOG_SLACK_MS = 2500
SPIN_WATCHDOG_MIN_MS = 2500
WHEEL_SPIN_GUARD_ENABLED = True
# Guard window for cancel clicks right after spin start.
# 0 disables the guard so the first cancel click is applied immediately.
SPIN_CANCEL_GUARD_MS = 0
# Fast stale-pending recovery guard: if no wheel is actually spinning/running,
# pending can be reset after this short grace period.
SPIN_STALE_RECOVERY_GRACE_MS = 250

# ---------- Startdaten ----------
PLAYER_PROFILE_MAX_SLOTS = 6
PLAYER_PROFILE_DEFAULT_NAMES = [
    "Main Roster",
    "PUGs",
    "Roster 3",
    "Roster 4",
    "Roster 5",
    "Roster 6",
]

DEFAULT_NAMES = {
    "Tank": ["Grymllon", "SpB"],
    "Damage": ["CoMaE", "DenMuchel", "Massith", "Pledoras"],
    "Support": ["blue", "Nummersechs", "Tillinski", "Internetwaffel"],
}

# Helden-Defaults nach Rolle
DEFAULT_HEROES = {
    "Tank": [
        "D.Va", "Domina", "Doomfist", "Hazard", "Junker Queen", "Mauga",
        "Orisa", "Ramattra", "Reinhardt", "Roadhog", "Sigma", "Winston",
        "Wrecking Ball", "Zarya",
    ],
    "Damage": [
        "Anran", "Ashe", "Bastion", "Cassidy", "Echo", "Emre", "Freja",
        "Genji", "Hanzo", "Junkrat", "Mei", "Pharah", "Reaper", "Sojourn",
        "Soldier: 76", "Sombra", "Symmetra", "Torbjorn", "Tracer",
        "Vendetta", "Venture", "Widowmaker",
    ],
    "Support": [
        "Ana", "Baptiste", "Brigitte", "Illari", "Jetpack Cat", "Juno",
        "Kiriko", "Lifeweaver", "Lucio", "Mercy", "Mizuki", "Moira",
        "Wuyang", "Zenyatta",
    ],
}

LABEL_FONT_SIZE = 14
LABEL_FONT_BOLD = True

# ---------- Maps ----------
MAP_CATEGORIES = [
    "Control",
    "Escort",
    "Hybrid",
    "Push",
    "Flashpoint",
    "Assault",
    "Clash",
]

# Basis-Map-Pools pro Kategorie
DEFAULT_MAPS = {
    "Control": [
        "Antarctic Peninsula",
        "Busan",
        "Ilios",
        "Lijiang Tower",
        "Nepal",
        "Oasis",
        "Samoa",
    ],
    "Escort": [
        "Circuit Royal",
        "Dorado",
        "Havana",
        "Junkertown",
        "Rialto",
        "Route 66",
        "Shambali Monastery",
        "Watchpoint: Gibraltar",
    ],
    "Hybrid": [
        "Blizzard World",
        "Eichenwalde",
        "Hollywood",
        "King's Row",
        "Midtown",
        "Numbani",
        "Paraíso",
    ],
    "Push": ["Colosseo", "Esperança", "New Queen Street", "Runasapi"],
    "Flashpoint": ["Aatlis", "New Junk City", "Suravasa"],
    "Assault": [
        "Hanamura",
        "Horizon Lunar Colony",
        "Paris",
        "Temple of Anubis",
        "Volskaya Industries",
    ],
    "Clash": ["Hanaoka", "Throne of Anubis"],
}
# Welche Map-Kategorien beim Start aktiviert sein sollen.
# Wenn ein Eintrag fehlt, gilt er als deaktiviert.
MAP_INCLUDE_DEFAULTS = [
    "Control",
    "Escort",
    "Hybrid",
    "Push",
    "Flashpoint",
    # "Assault",  # bewusst aus
    # "Clash",    # bewusst aus
]

# Dynamische Höhe der Namenslisten im Map-Mode.
# Die sichtbaren Reihen werden pro Map-Typ anhand der aktuellen Namensanzahl
# zwischen MIN und MAX begrenzt.
MAP_LIST_NAMES_MIN_VISIBLE_ROWS = 2
MAP_LIST_NAMES_MAX_VISIBLE_ROWS = 6
MAP_LIST_NAMES_EXTRA_PADDING_PX = 8

# ---------- Server ----------
API_BASE_URL = "http://localhost:5326"


def _normalize_config_values() -> None:
    """Normalize and harden config values to consistent runtime-safe types."""
    global QUIET
    global DEBUG
    global LOG_OUTPUT_DIR
    global WINDOWS_SINGLE_INSTANCE
    global WINDOWS_SINGLE_INSTANCE_LOCK_NAME
    global DEFAULT_LANGUAGE
    global OCR_ENGINE
    global OCR_EASYOCR_LANG
    global OCR_RETRY_EXTRA_PSMS
    global OCR_ROW_PASS_PSMS
    global MIN_DURATION_MS
    global MAX_DURATION_MS
    global DEFAULT_DURATION_MS
    global NETWORK_SYNC_WORKERS
    global PLAYER_PROFILE_MAX_SLOTS
    global OCR_NAME_MIN_CHARS
    global OCR_NAME_MAX_CHARS
    global OCR_NAME_MAX_WORDS
    global OCR_MAX_VARIANTS
    global OCR_MAX_VARIANTS_WINDOWS
    global OCR_RECALL_RETRY_MAX_VARIANTS
    global OCR_TIMEOUT_S
    global OCR_TIMEOUT_S_WINDOWS
    global OCR_PRELOAD_SUBPROCESS_TIMEOUT_S
    global MAP_LIST_NAMES_MIN_VISIBLE_ROWS
    global MAP_LIST_NAMES_MAX_VISIBLE_ROWS
    global MAP_LIST_NAMES_EXTRA_PADDING_PX
    global SOUND_SPIN_RESTART_GAP_PROFILE
    global SOUND_SPIN_RESTART_GAP_MS
    global SOUND_AUDIO_STOP_GUARD_MS
    global MAP_CATEGORIES
    global MAP_INCLUDE_DEFAULTS
    global DEFAULT_MAPS
    global API_BASE_URL

    QUIET = _as_bool(QUIET)
    DEBUG = _as_bool(DEBUG)
    LOG_OUTPUT_DIR = _normalize_str(LOG_OUTPUT_DIR, "logs")
    WINDOWS_SINGLE_INSTANCE = _as_bool(WINDOWS_SINGLE_INSTANCE)
    WINDOWS_SINGLE_INSTANCE_LOCK_NAME = _normalize_str(WINDOWS_SINGLE_INSTANCE_LOCK_NAME, "ow_wheelpicker_instance")

    DEFAULT_LANGUAGE = _normalize_str(DEFAULT_LANGUAGE, "en").lower()
    if DEFAULT_LANGUAGE not in {"de", "en"}:
        DEFAULT_LANGUAGE = "en"

    OCR_ENGINE = _normalize_str(OCR_ENGINE, "easyocr").lower()
    if OCR_ENGINE != "easyocr":
        OCR_ENGINE = "easyocr"

    OCR_EASYOCR_LANG = ",".join(_normalize_csv_list(OCR_EASYOCR_LANG, ["en"]))
    OCR_RETRY_EXTRA_PSMS = _normalize_int_list(OCR_RETRY_EXTRA_PSMS, [7, 13], min_value=1, max_value=99)
    OCR_ROW_PASS_PSMS = _normalize_int_list(OCR_ROW_PASS_PSMS, [7, 13, 6], min_value=1, max_value=99)

    MIN_DURATION_MS = max(0, _as_int(MIN_DURATION_MS, 0))
    MAX_DURATION_MS = max(MIN_DURATION_MS, _as_int(MAX_DURATION_MS, 10_000))
    DEFAULT_DURATION_MS = max(MIN_DURATION_MS, min(MAX_DURATION_MS, _as_int(DEFAULT_DURATION_MS, 3_000)))

    NETWORK_SYNC_WORKERS = max(1, _as_int(NETWORK_SYNC_WORKERS, 2))
    PLAYER_PROFILE_MAX_SLOTS = max(1, _as_int(PLAYER_PROFILE_MAX_SLOTS, 6))

    OCR_NAME_MIN_CHARS = max(1, _as_int(OCR_NAME_MIN_CHARS, 2))
    OCR_NAME_MAX_CHARS = max(OCR_NAME_MIN_CHARS, _as_int(OCR_NAME_MAX_CHARS, 64))
    OCR_NAME_MAX_WORDS = max(1, _as_int(OCR_NAME_MAX_WORDS, 8))

    OCR_MAX_VARIANTS = max(0, _as_int(OCR_MAX_VARIANTS, 2))
    OCR_MAX_VARIANTS_WINDOWS = max(0, _as_int(OCR_MAX_VARIANTS_WINDOWS, 1))
    OCR_RECALL_RETRY_MAX_VARIANTS = max(0, _as_int(OCR_RECALL_RETRY_MAX_VARIANTS, 4))

    OCR_TIMEOUT_S = max(0.5, _as_float(OCR_TIMEOUT_S, 8.0))
    OCR_TIMEOUT_S_WINDOWS = max(0.5, _as_float(OCR_TIMEOUT_S_WINDOWS, 6.0))
    OCR_PRELOAD_SUBPROCESS_TIMEOUT_S = max(1.0, _as_float(OCR_PRELOAD_SUBPROCESS_TIMEOUT_S, 60.0))

    MAP_LIST_NAMES_MIN_VISIBLE_ROWS = max(1, _as_int(MAP_LIST_NAMES_MIN_VISIBLE_ROWS, 2))
    MAP_LIST_NAMES_MAX_VISIBLE_ROWS = max(
        MAP_LIST_NAMES_MIN_VISIBLE_ROWS,
        _as_int(MAP_LIST_NAMES_MAX_VISIBLE_ROWS, 6),
    )
    MAP_LIST_NAMES_EXTRA_PADDING_PX = max(0, _as_int(MAP_LIST_NAMES_EXTRA_PADDING_PX, 8))
    SOUND_SPIN_RESTART_GAP_PROFILE = _normalize_str(
        SOUND_SPIN_RESTART_GAP_PROFILE,
        "balanced",
    ).lower()
    if SOUND_SPIN_RESTART_GAP_PROFILE not in {"auto", "low", "balanced", "high", "custom"}:
        SOUND_SPIN_RESTART_GAP_PROFILE = "balanced"
    SOUND_SPIN_RESTART_GAP_MS = max(-1, _as_int(SOUND_SPIN_RESTART_GAP_MS, -1))
    SOUND_AUDIO_STOP_GUARD_MS = max(-1, _as_int(SOUND_AUDIO_STOP_GUARD_MS, -1))

    map_categories = _normalize_csv_list(MAP_CATEGORIES, list(DEFAULT_MAPS.keys()))
    MAP_CATEGORIES = list(map_categories)

    cleaned_defaults: dict[str, list[str]] = {}
    for category in MAP_CATEGORIES:
        raw_names = DEFAULT_MAPS.get(category, [])
        if not isinstance(raw_names, (list, tuple, set)):
            raw_names = []
        cleaned_names = _normalize_csv_list(raw_names, [])
        cleaned_defaults[category] = cleaned_names
    DEFAULT_MAPS = cleaned_defaults

    include_defaults = _normalize_csv_list(MAP_INCLUDE_DEFAULTS, [])
    MAP_INCLUDE_DEFAULTS = [name for name in include_defaults if name in MAP_CATEGORIES]

    API_BASE_URL = _normalize_str(API_BASE_URL, "http://localhost:5326")

    # Re-apply quiet guards after type normalization so invalid overrides
    # cannot accidentally re-enable debug output.
    _disable_flags_if_quiet(*(QUIET_DISABLED_TRACE_FLAGS + QUIET_DISABLED_OCR_DEBUG_FLAGS))


_normalize_config_values()
