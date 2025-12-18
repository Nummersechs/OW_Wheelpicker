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
- `controller.py`: MainWindow/Wiring, delegiert an Services
- `services/`: Logik/Helper  
  - `state_store.py`, `persistence.py` (State/Save)  
  - `spin_service.py`, `spin_planner.py` (Spin-Logik)  
  - `mode_manager.py`, `hero_ban_merge.py` (Modes/Hero-Ban)  
  - `sync_service.py` (HTTP), `sound.py`
- `config.py`: Defaults/Styles/API
- `model/`: Zustandsmodelle (`state_models.py`, `roles.py`)
- `tests/`: Unit-Tests für Services (`spin_planner`, `hero_ban_merge`, `state_store`)

Mehr Details: `ARCHITECTURE.md`.
