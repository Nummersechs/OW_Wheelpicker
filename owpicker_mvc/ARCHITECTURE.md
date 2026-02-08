# Architektur-Übersicht

- `view/` – reine UI-Komponenten
  - `wheel_view.py` (Rad + Namensliste + Buttons)
  - `overlay.py` (Ergebnis/Info)
  - `wheel_widget.py` (Rad/Pointer/Animation)
  - `name_list.py` (Namensliste + Zeilen)
  - Optional: `wheel_panel.py` für Buttons/Result separat
- `controller/` – MainWindow + Controller-Helper
  - `main_window.py` (UI/Wiring)
  - `map_ui.py` (Map-UI kapseln)
  - `map_mode.py` (Map-Mode Steuerung)
  - `mode_manager.py` (Modus-Wechsel, Hero-Ban-Visuals/Update)
  - `open_queue.py` (Open-Queue Preview/Override)
  - `player_list_panel.py` (All-Players Panel)
  - `role_mode.py` (Role-Mode Auswahl/Enable-Logik)
  - `state_sync.py` (Saved-State + Online-Sync)
  - `spin_service.py` (Spin-All/Single, Snapshot/Restore)
- `model/` – Zustandsmodelle
  - `roles.py` (bestehend)
  - `wheel_state.py` (Wheel-Listen/Disable-Logik)
- `logic/` – UI‑freie Logik
  - `spin_engine.py` (Spin‑Physik)
  - `spin_planner.py` (Backtracking‑Zuordnung für Spins)
  - `hero_ban_merge.py` (Hero‑Ban: Rollen-Auswahl zusammenführen)
- `services/` – wiederverwendbare Dienste
  - `sound.py` (bestehend)
  - `state_store.py` (Mode-States, Defaults, Capture)
- `i18n/` – Übersetzungen
  - `__init__.py` (Helper), `de.py`, `en.py`
- `config.py` – Konstanten, Defaults, API-Endpoints

Nächste sinnvolle Schritte:
1) Controller-Methoden weiter entschlacken (UI-spezifische Wiring weiter auslagern).
2) `wheel_view.py` weiter in Panel/Button-Layer trennen (optional).
3) Tests erweitern (UI-freie Komponenten).
