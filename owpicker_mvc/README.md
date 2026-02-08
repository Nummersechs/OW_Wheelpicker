# Overwatch 2 – Triple Wheel Picker (MVC-ish)

## Lauf
```
python3 main.py
```

## Architektur (Kurzfassung)
- `view/`: UI-Komponenten  
  - `wheel_view.py` (Rad-Panel, Buttons, Resultate)  
  - `wheel_widget.py` (Rad/Pointer/Animation)  
  - `name_list.py` (Namensliste + Zeilen)  
  - `overlay.py` (Result/Info)
- `controller/`: MainWindow/Wiring + Controller-Helper  
  - `main_window.py` (UI/Wiring)  
  - `mode_manager.py`, `spin_service.py` (Modus/Spins)
- `logic/`: UI‑freie Logik
  - `spin_engine.py` (Spin‑Physik)
  - `spin_planner.py` (Spin‑Logik)
  - `hero_ban_merge.py` (Modes/Hero‑Ban)
- `services/`: Logik/Helper  
  - `state_store.py` (State/Save)
  - `sound.py`
- `i18n/`: Übersetzungen (`__init__.py`, `de.py`, `en.py`)
- `config.py`: Defaults/Styles/API
- `model/`: Zustandsmodelle (`roles.py`, `wheel_state.py`)
- `tests/`: Unit-Tests für Logik/Services (`spin_planner`, `hero_ban_merge`, `state_store`)

Mehr Details: `ARCHITECTURE.md`.
