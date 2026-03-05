# Startup and Shutdown Feature Checklist

## Scope
- `controller/main_window.py`
- `controller/main_window_parts/main_window_startup.py`
- `controller/main_window_parts/main_window_input.py`
- `controller/main_window_parts/main_window_shutdown.py`
- `controller/shutdown_manager.py`
- `controller/hover_tooltip_ops.py`

## Features
- [ ] Startup Mode Choice Overlay
- [ ] Startup Warmup Tasks (Sound/Tooltip/Map Prebuild optional)
- [ ] Input Guard und Event-Filter waehrend kritischer Startup-Phasen
- [ ] Deferred Visual Finalize (Theme/Language heavy updates)
- [ ] Optionales Shutdown Overlay
- [ ] Geordnete Shutdown-Sequenz (timer, sync, tooltip, sound)

## Versteckte/Non-Obvious Logik
- Startup kann Heavy-UI Updates deferen, um ersten Klickpfad fluessig zu halten.
- Input wird temporär geblockt/drained, um Race Conditions am Start zu reduzieren.
- CloseEvent ruft explizit `QMainWindow.closeEvent`, um Mixin-Rekursion zu vermeiden.
- OCR Async Jobs werden bei Close aktiv gecleant.

## Erwartetes Verhalten
- Beim Start keine ungewollten Fruehklicks auf aktive Controls.
- Nach Warmup sind Controls/Hover/Tooltips verlässlich aktiv.
- Beim Schliessen kein haengender Overlay-Zustand.
- Keine verbleibenden laufenden QThreads/QTimer nach Exit.

## Manuelle Checkliste
- [ ] Kaltstart testen: Overlay, Mode-Wahl, danach direkte Interaktion.
- [ ] Startup-Warmup Flags an/aus testen und Verhalten vergleichen.
- [ ] Waehrend Warmup Eingaben senden: erwarteter Guard greift.
- [ ] Hover/Tooltip nach Startup ohne Mausbewegung pruefen.
- [ ] Close waehrend OCR-Import und waehrend Spin testen.
- [ ] Mehrfach schnell oeffnen/schliessen: keine Leaks/Crash.

## Regression Hinweise
- Typische Bruchstellen: Event-Filter Activation, deferred finalize timing, close overlay race.
