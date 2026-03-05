# Config Sanity Checklist

## Scope
- `config.py`

## Ziel
Schneller Audit, ob aktive Config-Kombinationen sinnvoll sind und keine widerspruechlichen Modi erzeugen.

## OCR Profil
- [ ] `OCR_ENGINE = "easyocr"`
- [ ] `OCR_EASYOCR_LANG` nur so breit wie noetig (Performance/Noise Tradeoff)
- [ ] `OCR_EASYOCR_DOWNLOAD_ENABLED` passend zu Deployment (online setup vs offline runtime)
- [ ] `OCR_FAST_MODE` und `OCR_ROW_PASS_*` auf Zielsystem abgestimmt
- [ ] Debug Flags nur waehrend Tuning aktiv

## Runtime/Trace Profil
- [ ] `QUIET=True` fuer Release ohne Debug-Noise
- [ ] Trace-Flags fuer Entwicklung gezielt an (`TRACE_FLOW`, `TRACE_SPIN_PERF`, ...)
- [ ] `LOG_OUTPUT_DIR` auf validen, schreibbaren Pfad

## Startup/UX Profil
- [ ] Input-Guard Delays nicht zu hoch (UX) und nicht zu niedrig (Race)
- [ ] `STARTUP_VISUAL_FINALIZE_DEFERRED` passend fuer Performance-Ziel
- [ ] `DISABLE_TOOLTIPS`/Tooltip-Cache konsistent mit Produktziel

## Spin/Mode Profil
- [ ] `SPIN_LIGHTWEIGHT_UI_LOCK` an fuer fluessigere Spins bei grossen Listen
- [ ] Watchdog-Werte (`SPIN_WATCHDOG_*`) fuer Zielhardware plausibel
- [ ] Open-Queue Settings mit geplanter Rolle/Slot-Logik getestet

## Release Quick Checks
- [ ] Offline Build: alle OCR-Modelle vorhanden oder bundling korrekt
- [ ] Logs landen im gewuenschten Ordner
- [ ] Keine Entwicklungsflags aktiv, die Laufzeit bremsen
