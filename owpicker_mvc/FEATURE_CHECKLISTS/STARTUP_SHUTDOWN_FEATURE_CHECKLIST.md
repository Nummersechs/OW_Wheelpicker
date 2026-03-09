# Startup and Shutdown Feature Checklist

## Scope
- `controller/main_window.py`
- `controller/main_window_parts/main_window_startup.py`
- `controller/main_window_parts/main_window_input.py`
- `controller/main_window_parts/main_window_shutdown.py`
- `view/overlay.py`
- `controller/shutdown_manager.py`
- `controller/hover_tooltip_ops.py`

## Features
- [ ] Startup Mode Choice Overlay
- [ ] Startup Mode Choice Buttons bleiben deaktiviert mit Loading-Tooltip bis Warmup/Input-Drain fertig ist
- [ ] Startup Warmup Tasks (Wheel-Cache/Sound/Map optional, OCR-Preload optional)
- [ ] Input Guard und Event-Filter waehrend kritischer Startup-Phasen
- [ ] Deferred Visual Finalize (Theme/Language heavy updates)
- [ ] Optionales Shutdown Overlay
- [ ] Geordnete Shutdown-Sequenz (timer, sync, tooltip, sound)
- [ ] Non-blocking Close-Path mit OCR-Thread-Stop (defer/retry statt UI-blockierendem wait)
- [ ] Fallback-Orphaning fuer haengende OCR-Threads nach Max-Defer-Budget

## Versteckte/Non-Obvious Logik
- Startup kann Heavy-UI Updates deferen, um ersten Klickpfad fluessig zu halten.
- Input wird temporär geblockt/drained, um Race Conditions am Start zu reduzieren.
- CloseEvent ruft explizit `QMainWindow.closeEvent`, um Mixin-Rekursion zu vermeiden.
- OCR Async/Preload Jobs werden bei Close aktiv gecleant; wenn sie nicht stoppen, werden sie kontrolliert detached/orphaned.
- Mode-Choice Tooltips werden im Loading-Zustand priorisiert, auch wenn ein frueher Tooltip bereits sichtbar war.

## Erwartetes Verhalten
- Beim Start keine ungewollten Fruehklicks auf aktive Controls.
- Solange Startup laeuft zeigen Online/Offline konsistent den Loading-Tooltip.
- Nach Warmup sind Controls/Hover/Tooltips verlässlich aktiv.
- Beim Schliessen kein haengender Overlay-Zustand.
- Keine verbleibenden laufenden QThreads/QTimer nach Exit.

## Manuelle Checkliste
- [ ] Kaltstart testen: Overlay, Mode-Wahl, danach direkte Interaktion.
- [ ] Hover auf Offline/Online waehrend Startup: Tooltip zeigt Loading-Hinweis, danach normalen Text.
- [ ] Startup-Warmup Flags an/aus testen und Verhalten vergleichen.
- [ ] Waehrend Warmup Eingaben senden: erwarteter Guard greift.
- [ ] Hover/Tooltip nach Startup ohne Mausbewegung pruefen.
- [ ] Close waehrend OCR-Import und waehrend Spin testen.
- [ ] Mehrfach schnell oeffnen/schliessen: keine Leaks/Crash.

## Automatisierte Tests
- [ ] `python3 -m unittest -q tests.test_main_window_input_filter`
- [ ] `python3 -m unittest -q tests.test_main_window_shutdown_mixin`
- [ ] `python3 -m unittest -q tests.test_overlay_choice_tooltips`

## Regression Hinweise
- Typische Bruchstellen: Event-Filter Activation, deferred finalize timing, close overlay race.
