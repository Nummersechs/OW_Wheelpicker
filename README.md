# OW_Wheelpicker

Overwatch 2 Lineup-/Hero-Picker mit drei Rollenrädern. Aktueller Stand (vibe-coded und laufend aufgeräumt):
- Modes: Spieler, Helden, Hero-Ban (zentrale Zusammenführung, Rollenfilter über Buttons).
- UI: siehe `owpicker_mvc/view/` (Rad, Namenslisten, Overlay).
- Services: State/Persistenz, Spin-Logik, Hero-Ban-Merge, HTTP-Sync in `owpicker_mvc/services/`.

Entwickeln/Starten
```
cd owpicker_mvc
python3 main.py
```

Tests (UI-frei)
```
python3 -m unittest discover owpicker_mvc/tests
```

Weitere Details zur Struktur: `owpicker_mvc/ARCHITECTURE.md`.
