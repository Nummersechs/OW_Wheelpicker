"""
Zentrale Konfiguration für das Overwatch-Tool.
Hier kannst du das Verhalten und die Startdaten des Programms anpassen.
"""

# ---------- Logging/Debug ----------
DEBUG = False
QUIET = True

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

# ---------- Server ----------
#API_BASE_URL = "https://wddys-macbook-air.tail455d76.ts.net/" 
API_BASE_URL = "http://localhost:5326"
