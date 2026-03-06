"""
Zentrale Konfiguration für das Overwatch-Tool.
Hier kannst du das Verhalten und die Startdaten des Programms anpassen.
"""

# ---------- Runtime / Logging ----------
DEBUG = False
# Relative paths are created inside the writable app state directory.
# Set to "" to keep logs directly in state dir, or use an absolute path.
LOG_OUTPUT_DIR = "logs"
# Master-Schalter für Release/EXE:
# - unterdrückt Konsole/Qt-Logs (siehe main.py)
# - deaktiviert zusätzlich alle internen Debug-/Trace-Logs
# - Save-State bleibt davon unberührt
QUIET = False


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
STARTUP_FINALIZE_DELAY_MS = 60
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
# Retry waits after close was already deferred once (keeps UI responsive).
SHUTDOWN_OCR_ASYNC_RETRY_GRACEFUL_WAIT_MS = 0
SHUTDOWN_OCR_ASYNC_RETRY_TERMINATE_WAIT_MS = 120
# Background OCR preload thread:
SHUTDOWN_OCR_PRELOAD_GRACEFUL_WAIT_MS = 1400
SHUTDOWN_OCR_PRELOAD_TERMINATE_WAIT_MS = 350
# Retry waits after close was already deferred once (keeps UI responsive).
SHUTDOWN_OCR_PRELOAD_RETRY_GRACEFUL_WAIT_MS = 0
SHUTDOWN_OCR_PRELOAD_RETRY_TERMINATE_WAIT_MS = 120
# Retry cadence while waiting for still-running threads during close.
SHUTDOWN_THREAD_RETRY_MS = 180
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
_disable_flags_if_quiet(
    "DEBUG",
    "TRACE_FLOW",
    "TRACE_SHUTDOWN",
    "TRACE_FOCUS",
    "TRACE_HOVER",
    "TRACE_SPIN_PERF",
    "TRACE_CLEAR_ON_START",
    "TRACE_STARTUP_VISUAL_FINALIZE_DEFER",
    "TRACE_OCR_PRELOAD_VERBOSE",
    "TRACE_SHUTDOWN_STEP_VERBOSE",
)

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
_disable_flags_if_quiet(
    "OCR_DEBUG_SHOW_REPORT",
    "OCR_DEBUG_INCLUDE_REPORT_TEXT",
    "OCR_DEBUG_LOG_TO_FILE",
    "OCR_DEBUG_LINE_ANALYSIS",
)
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
