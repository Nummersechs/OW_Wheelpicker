# Feature Checklists

Zentraler Ordner fuer funktionale Checklisten und Verhaltensdokumentation.

## Enthaltene Checklisten
- `OCR_FEATURE_CHECKLIST.md`
- `UI_THEME_FEATURE_CHECKLIST.md`
- `SPIN_MODE_FEATURE_CHECKLIST.md`
- `STATE_SYNC_RUNTIME_FEATURE_CHECKLIST.md`
- `STARTUP_SHUTDOWN_FEATURE_CHECKLIST.md`
- `CONFIG_SANITY_CHECKLIST.md`

## Ziel
- Features transparent machen
- versteckte Logik sichtbar machen
- erwartetes Verhalten definieren
- manuelle Regressionstests als Checkliste pflegen

## Pflege-Regeln
- Bei Feature-Aenderungen Checkliste im selben Commit aktualisieren.
- In jeder Checkliste: Scope, Erwartung, Risiken, Testschritte pflegen.
- Wenn vorhanden, auch passende automatisierte Testdateien/Commands in der Checkliste referenzieren.
- Wenn neue Subsysteme entstehen, neue Datei in diesem Ordner anlegen und hier verlinken.
