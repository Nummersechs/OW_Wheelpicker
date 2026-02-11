"""
Zentrale Konfiguration für das Overwatch-Tool.
Hier kannst du das Verhalten und die Startdaten des Programms anpassen.
"""

# ---------- Logging/Debug ----------
DEBUG = False
QUIET = False
TRACE_FLOW = True
TRACE_SHUTDOWN = False
TRACE_FOCUS = True
TRACE_HOVER = True
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
HOVER_FORWARD_MOUSEMOVE = True
HOVER_FORWARD_INTERVAL_MS = 50
STARTUP_DROP_CHOICE_POINTER_EVENTS = True
MODE_CHOICE_INPUT_GUARD_MS = 260
HOVER_PUMP_ON_START = False
# 0 = kein Timeout (läuft bis echte Hover-Events erkannt werden)
HOVER_PUMP_DURATION_MS = 0
HOVER_PUMP_INTERVAL_MS = 90
HOVER_WATCHDOG_ON = True
HOVER_WATCHDOG_INTERVAL_MS = 350
HOVER_WATCHDOG_STALE_MS = 900
HOVER_WATCHDOG_COOLDOWN_MS = 700
HOVER_WATCHDOG_REQUIRE_MOVE_MS = 0

# ---------- Performance / Resource policy ----------
MAP_PREBUILD_ON_START = False
SOUND_WARMUP_ON_START = False
TOOLTIP_CACHE_ON_START = False
SOUND_WARMUP_LAZY_STEP_MS = 25
STATE_SAVE_DEBOUNCE_MS = 160

# ---------- OCR Import (prototype) ----------
OCR_TESSERACT_CMD = "tesseract"
OCR_TESSERACT_LANG = "eng+jpn+chi_sim+chi_tra+kor"
OCR_TESSERACT_PSM = 6
OCR_TESSERACT_FALLBACK_PSM = 11
OCR_TESSERACT_TIMEOUT_S = 8.0
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
OCR_CAPTURE_PREPARE_DELAY_MS = 120
OCR_CAPTURE_TIMEOUT_S = 45.0

# ---------- Sprache ----------
# Voreingestellte Sprache, wenn keine Auswahl gespeichert wurde
DEFAULT_LANGUAGE = "en"

def debug_print(*args, **kwargs):
    """Wrapper um print, der nur aktiv ist, wenn DEBUG True ist."""
    if DEBUG:
        print(*args, **kwargs)

# ---------- UI / Animation ----------
WHEEL_RADIUS = 136
MIN_DURATION_MS = 0
MAX_DURATION_MS = 10000
DEFAULT_DURATION_MS = 3000

# ---------- Startdaten ----------
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
# Added label box config
LABEL_FONT_SIZE = 14
LABEL_FONT_BOLD = True
LABEL_BOX_ENABLED = True
LABEL_BOX_PADDING = 4
LABEL_BOX_RADIUS = 6
LABEL_BOX_BG = (0,0,0,160)
LABEL_BOX_BORDER=(255,255,255,200)
LABEL_BOX_BORDER_WIDTH=1
LABEL_TEXT_COLOR=(255,255,255,255)

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
