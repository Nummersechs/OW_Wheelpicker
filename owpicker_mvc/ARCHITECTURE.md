# Architektur-Übersicht (Zielbild)

- `view/` – reine UI-Komponenten
  - `wheel_view.py` (Rad + Namensliste + Buttons)
  - `overlay.py` (Ergebnis/Info)
  - **Ziel**: weiter aufteilen in `wheel_widget.py`, `name_list.py`, `wheel_panel.py`
- `controller.py` – aktuelles MainWindow, wird perspektivisch entschlackt
  - **Ziel**: in `controller/main_window.py`, `controller/mode_manager.py`, `controller/spin_service.py` aufsplitten
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
- `config.py` – Konstanten, Defaults, API-Endpoints

Nächste sinnvolle Schritte:
1) State-Handling aus `controller.py` in einen `state_store` auslagern (nutzt `state_models.py` + `persistence.py`).
2) Controller aufspalten in UI (MainWindow) und Logik (Mode-/HeroBan-/Spin-Services).
3) `wheel_view.py` in kleinere Widgets teilen.
