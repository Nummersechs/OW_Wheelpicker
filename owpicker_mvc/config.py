"""
Zentrale Konfiguration für das Overwatch-Tool.
Hier kannst du das Verhalten und die Startdaten des Programms anpassen.
"""

# ---------- Logging/Debug ----------
DEBUG = False
QUIET = False
TRACE_FLOW = True
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

# Helden-Defaults nach Rolle (inkl. Vandetta)
DEFAULT_HEROES = {
    "Tank": [
        "D.Va", "Doomfist", "Hazard", "Junker Queen", "Mauga", "Orisa",
        "Ramattra", "Reinhardt", "Roadhog", "Sigma", "Winston",
        "Wrecking Ball", "Zarya",
    ],
    "Damage": [
        "Ashe", "Bastion", "Cassidy", "Echo", "Genji",
        "Hanzo", "Junkrat", "Mei", "Pharah", "Reaper",
        "Sojourn", "Soldier: 76", "Sombra", "Symmetra", "Torbjorn",
        "Tracer", "Vendetta", "Venture", "Widowmaker",
    ],
    "Support": [
        "Ana", "Baptiste", "Brigitte", "Illari", "Juno", "Kiriko",
        "Lifeweaver", "Lucio", "Mercy", "Moira", "Wuyang", "Zenyatta",
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
