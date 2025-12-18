# Architektur-Übersicht (Zielbild)

- `view/` – reine UI-Komponenten
  - `wheel_view.py` (Rad + Namensliste + Buttons)
  - `overlay.py` (Ergebnis/Info)
  - `wheel_widget.py` (Rad/Pointer/Animation)
  - `name_list.py` (Namensliste + Zeilen)
  - **Ziel**: ggf. noch `wheel_panel.py` für Buttons/Result separat
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
  - `spin_service.py` (Spin-All/Single, Snapshot/Restore)
  - `mode_manager.py` (Modus-Wechsel, Hero-Ban-Visuals/Update)
- `config.py` – Konstanten, Defaults, API-Endpoints

Nächste sinnvolle Schritte:
1) Controller weiter aufsplitten (UI/MainWindow, Mode-Manager, Spin-Service).
2) `wheel_view.py` weiter in Panel/Button-Layer trennen (optional).
3) Tests erweitern (UI-freie Komponenten).
