# Konfiguration für den Wett-Client.
# Passe diese URL an deinen Server an (sollte dieselbe sein wie im WheelPicker).
API_BASE_URL = "http://localhost:5326" # "https://wddys-macbook-air.tail455d76.ts.net/"

# Debug-Flag: steuert Ausgaben
DEBUG = False

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)
