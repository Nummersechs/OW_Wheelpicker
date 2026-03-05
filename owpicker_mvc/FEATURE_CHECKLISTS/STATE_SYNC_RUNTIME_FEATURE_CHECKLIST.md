# State Sync and Runtime Feature Checklist

## Scope
- `controller/state_sync.py`
- `services/state_store.py`
- `services/app_settings.py`
- `controller/runtime_tracing.py`
- `controller/shutdown_manager.py`
- `main.py`

## Features
- [ ] Persistenz in `saved_state.json`
- [ ] Debounced Save und Debounced Network-Sync
- [ ] Optionales Online-Sync fuer Rollenzustand und Spin-Result
- [ ] Resource-Snapshot fuer Shutdown-Diagnose
- [ ] Logdateien in konfiguriertem Log-Ordner

## Versteckte/Non-Obvious Logik
- Saves werden signaturbasiert dedupliziert (kein unnötiger Disk-Write).
- Network-Requests laufen im ThreadPool und werden bei Shutdown gecancelt.
- Pending Save/Sync Payload wird getrackt und bei Flush zusammengefuehrt.
- Runtime-Trace kann je nach `QUIET` und Trace-Flags teilweise deaktiviert sein.

## Erwartetes Verhalten
- UI-Aenderungen landen robust im Saved State.
- Bei Offline-Mode keine Network-Requests.
- Bei Online-Mode keine UI-Blockade durch Sync.
- Shutdown endet ohne haengende Futures/Timer.

## Manuelle Checkliste
- [ ] App starten, Werte aendern (Namen, Theme, Sprache, Mode), neu starten: Werte wieder da.
- [ ] Bei schneller Eingabe/mehreren Aenderungen: State trotzdem konsistent gespeichert.
- [ ] Online aus: kein Sync-Versuch in Logs.
- [ ] Online an: Sync-Requests laufen, UI bleibt responsive.
- [ ] App waehrend laufendem Sync schliessen: sauberer Exit.
- [ ] `resource_snapshot` vor/nach Shutdown plausibel.

## Regression Hinweise
- Typische Bruchstellen: Debounce race, executor lifecycle, state signature false positives.
