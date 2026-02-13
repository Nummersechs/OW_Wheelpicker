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
STATE_SAVE_DEBOUNCE_MS = 220
NETWORK_SYNC_DEBOUNCE_MS = 220
NETWORK_SYNC_WORKERS = 2

# ---------- OCR Import (prototype) ----------
# OCR_TESSERACT_CMD:
# - "auto" (recommended): prefers bundled OCR runtime in EXE, then falls back to PATH
# - absolute path (optional): force a specific binary
OCR_TESSERACT_CMD = "auto"
# OCR language packs are the biggest speed factor.
# Keep this minimal for fast OCR; add more languages only when needed.
# German + English mixed default.
OCR_TESSERACT_LANG = "deu+eng"
OCR_TESSERACT_PSM = 6
OCR_TESSERACT_FALLBACK_PSM = 11
OCR_TESSERACT_TIMEOUT_S = 8.0
OCR_FAST_MODE = True
# 0 = all generated variants, >0 = cap variant count per OCR run
OCR_MAX_VARIANTS = 2
# In fast mode, stop after the first variant that yields text
OCR_STOP_AFTER_FIRST_VARIANT_SUCCESS = True
OCR_NAME_MIN_CHARS = 2
OCR_NAME_MAX_CHARS = 24
OCR_NAME_MAX_WORDS = 2
OCR_NAME_MAX_DIGIT_RATIO = 0.45
OCR_NAME_MIN_SUPPORT = 1
OCR_NAME_HIGH_COUNT_THRESHOLD = 8
OCR_NAME_HIGH_COUNT_MIN_SUPPORT = 2
OCR_NAME_MAX_CANDIDATES = 12
OCR_NAME_NEAR_DUP_MIN_CHARS = 8
OCR_NAME_NEAR_DUP_MAX_LEN_DELTA = 1
OCR_NAME_NEAR_DUP_SIMILARITY = 0.90
OCR_NAME_NEAR_DUP_TAIL_MIN_CHARS = 3
OCR_NAME_NEAR_DUP_TAIL_HEAD_SIMILARITY = 0.70
OCR_SCALE_FACTOR = 2
OCR_USE_NATIVE_MAC_CAPTURE = True
# Hide the main window during region selection (recommended on Windows).
OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE = True
OCR_CAPTURE_PREPARE_DELAY_MS = 120
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
