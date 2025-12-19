# Architektur-Übersicht

- `view/` – reine UI-Komponenten
  - `wheel_view.py` (Rad + Namensliste + Buttons)
  - `overlay.py` (Ergebnis/Info)
  - `wheel_widget.py` (Rad/Pointer/Animation)
  - `name_list.py` (Namensliste + Zeilen)
  - Optional: `wheel_panel.py` für Buttons/Result separat
- `controller/` – MainWindow + Controller-Helper
  - `main_window.py` (UI/Wiring)
  - `mode_manager.py` (Modus-Wechsel, Hero-Ban-Visuals/Update)
  - `spin_service.py` (Spin-All/Single, Snapshot/Restore)
- `model/` – Zustandsmodelle
  - `roles.py` (bestehend)
  - `state_models.py` (neu: Entry/Role/Mode-Snapshot)
- `services/` – wiederverwendbare Dienste
  - `sound.py` (bestehend)
  - `persistence.py` (Load/Save saved_state.json)
  - `state_store.py` (Mode-States, Defaults, Capture)
  - `sync_service.py` (HTTP für Spin-Result & Rollen-Sync)
  - `spin_planner.py` (Backtracking-Zuordnung für Spins)
  - `hero_ban_merge.py` (Hero-Ban: Rollen-Auswahl zusammenführen)
- `i18n/` – Übersetzungen
  - `__init__.py` (Helper), `de.py`, `en.py`
- `config.py` – Konstanten, Defaults, API-Endpoints

Nächste sinnvolle Schritte:
1) Controller-Methoden weiter entschlacken (UI-spezifische Wiring weiter auslagern).
2) `wheel_view.py` weiter in Panel/Button-Layer trennen (optional).
3) Tests erweitern (UI-freie Komponenten).
