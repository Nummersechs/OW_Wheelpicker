# Config Sanity Checklist

## Scope
- `config.py`

## Ziel
Schneller Audit, ob aktive Config-Kombinationen sinnvoll sind und keine widerspruechlichen Modi erzeugen.

## OCR Profil
- [ ] `OCR_ENGINE = "easyocr"`
- [ ] `OCR_EASYOCR_LANG` nur so breit wie noetig (Performance/Noise Tradeoff)
- [ ] `OCR_EASYOCR_DOWNLOAD_ENABLED` passend zu Deployment (online setup vs offline runtime)
- [ ] `OCR_PRELOAD_INPROCESS_CACHE_WARMUP` passend gesetzt (geringere First-Click-Latenz vs mehr Startup-Load)
- [ ] `OCR_BACKGROUND_PRELOAD_ENABLED`/`OCR_BACKGROUND_PRELOAD_DELAY_MS`/`OCR_BACKGROUND_PRELOAD_MIN_UPTIME_MS` auf Zielgeraet abgestimmt
- [ ] `OCR_BACKGROUND_PRELOAD_ALLOW_DURING_STARTUP` nur aktiv, wenn Startup-Interaktion dadurch nicht leidet
- [ ] `OCR_FAST_MODE` und `OCR_ROW_PASS_*` auf Zielsystem abgestimmt
- [ ] Debug Flags nur waehrend Tuning aktiv

## Runtime/Trace Profil
- [ ] `QUIET=True` fuer Release ohne Debug-Noise
- [ ] Trace-Flags fuer Entwicklung gezielt an (`TRACE_FLOW`, `TRACE_SPIN_PERF`, ...)
- [ ] `LOG_OUTPUT_DIR` auf validen, schreibbaren Pfad

## Startup/UX Profil
- [ ] Input-Guard Delays nicht zu hoch (UX) und nicht zu niedrig (Race)
- [ ] `STARTUP_OCR_PRELOAD` und `STARTUP_OCR_PRELOAD_*_WAIT_MS` konsistent mit gewuenschtem Mode-Choice-Verhalten
- [ ] `STARTUP_VISUAL_FINALIZE_DEFERRED` passend fuer Performance-Ziel
- [ ] `DISABLE_TOOLTIPS`/Tooltip-Cache konsistent mit Produktziel

## Shutdown Profil
- [ ] OCR-Thread-Wait-Profile (`SHUTDOWN_OCR_ASYNC_*`, `SHUTDOWN_OCR_PRELOAD_*`) auf reale Laufzeiten abgestimmt
- [ ] `SHUTDOWN_THREAD_MAX_DEFER_MS` so gesetzt, dass Close nicht haengt und trotzdem sauber cleanuped
- [ ] `SHUTDOWN_RELEASE_OCR_CACHE` nur aktivieren, wenn Exit-Latenz akzeptabel bleibt

## Spin/Mode Profil
- [ ] `SPIN_LIGHTWEIGHT_UI_LOCK` an fuer fluessigere Spins bei grossen Listen
- [ ] Watchdog-Werte (`SPIN_WATCHDOG_*`) fuer Zielhardware plausibel
- [ ] Open-Queue Settings mit geplanter Rolle/Slot-Logik getestet

## Release Quick Checks
- [ ] Offline Build: alle OCR-Modelle vorhanden oder bundling korrekt
- [ ] Logs landen im gewuenschten Ordner
- [ ] Keine Entwicklungsflags aktiv, die Laufzeit bremsen
