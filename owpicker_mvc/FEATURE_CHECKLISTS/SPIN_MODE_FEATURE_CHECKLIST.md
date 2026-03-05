# Spin and Mode Feature Checklist

## Scope
- `controller/spin_service.py`
- `logic/spin_engine.py`
- `logic/spin_planner.py`
- `controller/open_queue.py`
- `controller/role_mode.py`
- `controller/mode_manager.py`
- `controller/main_window_parts/main_window_spin.py`
- `controller/main_window_parts/main_window_mode.py`

## Features
- [ ] Rollen-Spin fuer selektierte Wheels
- [ ] Open-Queue Spin Mode mit Slot-Plan 1..6
- [ ] Hero-Ban Modus mit zentraler DPS-Ansicht
- [ ] Spin-All Enable/Disable korrekt bei Pending/Mode/Selection
- [ ] Spin-Watchdog fuer haengende Spins
- [ ] Sound-Start/Stop fuer Spin und Ding

## Versteckte/Non-Obvious Logik
- Open Queue nutzt feste Rollenverteilung pro Spieleranzahl.
- Pair-Mode/Subrole-Mode werden fuer Spin-Overrides temporär gesetzt und sauber restauriert.
- `spin_all` deaktiviert Heavy-UI waehrend Spin und reaktiviert danach.
- Ergebnisreihenfolge wird ueber Planner/Service bestimmt, nicht nur ueber UI-Index.

## Erwartetes Verhalten
- Keine Rolle spinnt ohne Selektion.
- Open Queue Preview zeigt denselben Kandidatenpool wie finaler Spin.
- Hero-Ban blendet nicht-zentrale Wheels visuell ab, aber bleibt steuerbar wie vorgesehen.
- Nach Spin-Ende: Controls, Sound und Overlay sind in validem Zustand.

## Manuelle Checkliste
- [ ] Role-Mode: 1, 2, 3 Rollen selektieren und Spin-All testen.
- [ ] Open-Mode: Slider 1..6, Slot-Plan und Kandidatenzahl pruefen.
- [ ] Open-Mode waehrend/nahe Spin umschalten: keine inkonsistente Preview.
- [ ] Hero-Ban an/aus: visuelle Zustände und Interaktion korrekt.
- [ ] Spin abbrechen/Stop: Pending faellt auf 0, Buttons aktiv, Sound stoppt.
- [ ] Watchdog absichtlich triggern (lange Dauer/Fehlerpfad) und Recovery pruefen.

## Regression Hinweise
- Typische Bruchstellen: Restore von Overrides, Pending Counter, Toggle-State nach Moduswechsel.
