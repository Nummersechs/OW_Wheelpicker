"""
Zentrale Konfiguration für das Overwatch-Tool.
Hier kannst du das Verhalten und die Startdaten des Programms anpassen.
"""

# ---------- Logging/Debug ----------
DEBUG = False
# Master-Schalter für Release/EXE:
# - unterdrückt Konsole/Qt-Logs (siehe main.py)
# - deaktiviert zusätzlich alle internen Debug-/Trace-Logs
# - Save-State bleibt davon unberührt
QUIET = False
TRACE_FLOW = False
TRACE_SHUTDOWN = False
TRACE_FOCUS = False
TRACE_HOVER = False
TRACE_CLEAR_ON_START = False
FOCUS_TRACE_DURATION_S = 12.0
FOCUS_TRACE_MAX_EVENTS = 800
DISABLE_TOOLTIPS = True
FOCUS_TRACE_WINDOW_EVENTS = True
FOCUS_TRACE_WINDOWS_ONLY = True
FOCUS_TRACE_SNAPSHOT_INTERVAL_MS = 200
FOCUS_TRACE_SNAPSHOT_COUNT = 20
HOVER_TRACE_MAX_EVENTS = 200
HOVER_TRACE_BUDGET_PER_VIEW = 20
HOVER_POKE_ON_REARM = True
# Nur aktivieren, wenn Hover auf einem Zielsystem sonst nicht zuverlässig ist.
# Globales MouseMove-Forwarding erhöht Event-Last deutlich.
HOVER_FORWARD_MOUSEMOVE = False
HOVER_FORWARD_INTERVAL_MS = 50
STARTUP_DROP_CHOICE_POINTER_EVENTS = True
MODE_CHOICE_INPUT_GUARD_MS = 260
STARTUP_FINALIZE_DELAY_MS = 60
STARTUP_WARMUP_COOLDOWN_MS = 500
STARTUP_INPUT_DRAIN_MS = 180
# Für schnelleren Start standardmäßig Platform-Style nutzen.
FORCE_FUSION_STYLE = False
HOVER_PUMP_ON_START = False
# 0 = kein Timeout (läuft bis echte Hover-Events erkannt werden)
HOVER_PUMP_DURATION_MS = 0
HOVER_PUMP_INTERVAL_MS = 90
HOVER_WATCHDOG_ON = True
HOVER_WATCHDOG_INTERVAL_MS = 350
HOVER_WATCHDOG_STALE_MS = 900
HOVER_WATCHDOG_COOLDOWN_MS = 700
HOVER_WATCHDOG_REQUIRE_MOVE_MS = 0

# QUIET erzwingt "silent runtime" für alle Debug-/Trace-Kanäle.
if QUIET:
    DEBUG = False
    TRACE_FLOW = False
    TRACE_SHUTDOWN = False
    TRACE_FOCUS = False
    TRACE_HOVER = False
    TRACE_CLEAR_ON_START = False

# ---------- Performance / Resource policy ----------
MAP_PREBUILD_ON_START = False
SOUND_WARMUP_ON_START = False
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
# Suspend optional background UI services while spinning to keep animation smooth.
PAUSE_BACKGROUND_UI_SERVICES_DURING_SPIN = True

# ---------- OCR Import (prototype) ----------
# OCR engine (local/offline):
# - "easyocr" is the active/default backend.
OCR_ENGINE = "easyocr"
# OCR language packs are the biggest speed factor.
# Keep this minimal for fast OCR; add more languages only when needed.
# English-first default for in-game player names.
OCR_TESSERACT_LANG = "eng"
# EasyOCR language list (comma/plus separated), e.g. "en" or "en,de".
OCR_EASYOCR_LANG = "en"
# Local model paths for EasyOCR (optional). Keep empty to use EasyOCR defaults.
OCR_EASYOCR_MODEL_DIR = ""
OCR_EASYOCR_USER_NETWORK_DIR = ""
OCR_EASYOCR_GPU = False
# Keep False for strict offline behavior (no model downloads at runtime).
OCR_EASYOCR_DOWNLOAD_ENABLED = False
# Keep OCR runtime fully asleep until the first OCR import click.
OCR_RUNTIME_SLEEP_UNTIL_USED = True
# Release cached OCR runtimes after idle (0 disables automatic release).
# Lower value = faster sleep when OCR is not used.
OCR_IDLE_CACHE_RELEASE_MS = 30000
# If cache release is due while a spin is active, retry after this delay.
OCR_IDLE_CACHE_RELEASE_BUSY_RETRY_MS = 2500
# Keep cache release on spin disabled by default to avoid UI-thread spikes at
# spin start when OCR runtimes were initialized before.
OCR_RELEASE_CACHE_ON_SPIN = False
OCR_TESSERACT_PSM = 11
OCR_TESSERACT_FALLBACK_PSM = 6
OCR_TESSERACT_RETRY_EXTRA_PSMS = [7, 13]
OCR_TESSERACT_TIMEOUT_S = 8.0
# Windows override for OCR timeout (seconds). Lower = more responsive.
OCR_TESSERACT_TIMEOUT_S_WINDOWS = 6.0
OCR_FAST_MODE = True
# 0 = all generated variants, >0 = cap variant count per OCR run
OCR_MAX_VARIANTS = 2
# Windows override: prefer one quick variant first for faster OCR response.
OCR_MAX_VARIANTS_WINDOWS = 1
# In fast mode, stop after the first variant that yields text
OCR_STOP_AFTER_FIRST_VARIANT_SUCCESS = False
# Retry with a more thorough OCR pass when fast mode found too few names.
OCR_RECALL_RETRY_ENABLED = True
# Retry trigger threshold (0 disables retry trigger).
OCR_RECALL_RETRY_MIN_CANDIDATES = 5
# Retry trigger threshold for too many detected names.
OCR_RECALL_RETRY_MAX_CANDIDATES = 7
# Retry trigger if too many very short names (len<=2) are present.
OCR_RECALL_RETRY_SHORT_NAME_MAX_RATIO = 0.34
# Variant cap for retry pass (0 = same/all prepared variants).
OCR_RECALL_RETRY_MAX_VARIANTS = 4
# Retry can include fallback PSM for better recall.
OCR_RECALL_RETRY_USE_FALLBACK_PSM = True
# Retry timeout multiplier (>= 1.0).
OCR_RECALL_RETRY_TIMEOUT_SCALE = 1.35
# If low-count OCR results remain after retry, relax support filtering to avoid
# dropping single-pass names.
OCR_RECALL_RELAX_SUPPORT_ON_LOW_COUNT = True
# Used for OCR candidate quality scoring and pass selection.
OCR_EXPECTED_CANDIDATES = 5
# Row-based fallback OCR for low-count results (tries to OCR each detected text row).
OCR_ROW_PASS_ENABLED = True
OCR_ROW_PASS_ALWAYS_RUN = True
OCR_ROW_PASS_MIN_CANDIDATES = 5
OCR_ROW_PASS_BRIGHTNESS_THRESHOLD = 145
OCR_ROW_PASS_MIN_PIXELS_RATIO = 0.015
OCR_ROW_PASS_MERGE_GAP_PX = 2
OCR_ROW_PASS_MIN_HEIGHT_PX = 7
OCR_ROW_PASS_MAX_ROWS = 12
OCR_ROW_PASS_PAD_PX = 2
OCR_ROW_PASS_NAME_X_RATIO = 0.58
# Row projection window used for line segmentation.
# Helps avoid continuous bright borders/checkbox columns in OCR pick overlay.
OCR_ROW_PASS_PROJECTION_X_START_RATIO = 0.08
OCR_ROW_PASS_PROJECTION_X_END_RATIO = 0.92
OCR_ROW_PASS_PROJECTION_COL_MAX_RATIO = 0.84
OCR_ROW_PASS_SCALE_FACTOR = 4
OCR_ROW_PASS_INCLUDE_MONO = True
OCR_ROW_PASS_TIMEOUT_SCALE = 0.55
OCR_ROW_PASS_PSMS = [7, 13, 6]
# OCR debug: shows a detailed report dialog after each OCR run.
OCR_DEBUG_SHOW_REPORT = False
# Keep enabled with OCR_DEBUG_SHOW_REPORT so the dialog receives the full report text.
OCR_DEBUG_INCLUDE_REPORT_TEXT = False
OCR_DEBUG_REPORT_MAX_CHARS = 24000
# Persist OCR debug reports into a file for easier sharing/analysis.
OCR_DEBUG_LOG_TO_FILE = False
OCR_DEBUG_LOG_FILE = "ocr_debug.log"
OCR_DEBUG_LOG_MAX_CHARS = 200000
# Per-line parser diagnostics (accepted/dropped + reason) inside debug report.
OCR_DEBUG_LINE_ANALYSIS = False
OCR_DEBUG_LINE_MAX_ENTRIES_PER_RUN = 60
# QUIET erzwingt zusätzlich: keine OCR-Debug-Reports/Dateilogs.
if QUIET:
    OCR_DEBUG_SHOW_REPORT = False
    OCR_DEBUG_INCLUDE_REPORT_TEXT = False
    OCR_DEBUG_LOG_TO_FILE = False
    OCR_DEBUG_LINE_ANALYSIS = False
# Optional manual vocabulary that improves OCR correction for known player names.
# Keep disabled by default to avoid bias from hardcoded names.
OCR_USE_NAME_HINTS = False
OCR_NAME_HINTS = []
OCR_NAME_HINTS_ONLY_WHEN_SET = True
OCR_HINT_CORRECTION_MIN_SCORE = 0.62
OCR_HINT_CORRECTION_LOW_CONF_MIN_SCORE = 0.28
# OCR variants tailored for player list screenshots.
OCR_INCLUDE_LEFT_CROP_VARIANTS = True
OCR_NAME_COLUMN_CROP_RATIO = 0.50
OCR_INCLUDE_MONO_VARIANTS = True
OCR_SCALE_FACTOR = 3
OCR_NAME_MIN_CHARS = 2
OCR_NAME_MAX_CHARS = 24
OCR_NAME_MAX_WORDS = 2
OCR_NAME_MAX_DIGIT_RATIO = 0.45
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
# Upper repaint rate for explicit spin repaint requests (<=0 disables throttling).
SPIN_REPAINT_MAX_FPS = 45
# Spin fallback watchdogs for overloaded systems.
SPIN_WATCHDOG_ENABLED = True
SPIN_WATCHDOG_SCALE = 1.8
SPIN_WATCHDOG_SLACK_MS = 2500
SPIN_WATCHDOG_MIN_MS = 2500
WHEEL_SPIN_GUARD_ENABLED = True

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

# Helden-Defaults nach Rolle (2026 Season 1)
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
    "Control": ["Antarctic Peninsula", "Busan", "Ilios", "Lijiang Tower", "Nepal", "Oasis", "Samoa"],
    "Escort": ["Circuit Royal", "Dorado", "Havana", "Junkertown", "Rialto", "Route 66", "Shambali Monastery", "Watchpoint: Gibraltar"],
    "Hybrid": ["Blizzard World", "Eichenwalde", "Hollywood", "King's Row", "Midtown", "Numbani", "Paraíso"],
    "Push": ["Colosseo", "Esperança", "New Queen Street", "Runasapi"],
    "Flashpoint": ["Aatlis", "New Junk City", "Suravasa"],
    "Assault": ["Hanamura", "Horizon Lunar Colony", "Paris", "Temple of Anubis", "Volskaya Industries"],
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

# ---------- Server ----------
#API_BASE_URL = "https://wddys-macbook-air.tail455d76.ts.net/" 
API_BASE_URL = "http://localhost:5326"
