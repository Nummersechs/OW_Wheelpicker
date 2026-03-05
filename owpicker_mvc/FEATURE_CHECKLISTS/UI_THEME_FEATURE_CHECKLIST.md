# UI and Theme Feature Checklist

## Scope
- `view/style_helpers.py`
- `utils/theme.py`
- `view/name_list.py`
- `view/wheel_view.py`
- `view/overlay.py`
- `controller/main_window_parts/main_window_appearance.py`

## Features
- [ ] Light/Dark Theme Umschaltung ohne Neustart
- [ ] Globales Palette-Update und konsistente Widgetfarben
- [ ] Rollen-Buttons, Slider, Listen und ToolButtons im aktiven Theme
- [ ] Namenliste mit konsistenten Row- und Editor-Hoehen
- [ ] Subrole-Checkboxen mit einheitlichem Styling
- [ ] Overlay (Status/Mode/Picker) folgt aktivem Theme

## Versteckte/Non-Obvious Logik
- Style-Strings werden gecached (weniger Re-Styling-Kosten).
- `set_stylesheet_if_needed` verhindert unnötige Re-Applys.
- Global Stylesheet ist absichtlich statisch; Farben kommen ueber `QPalette`.
- Namenliste nutzt `QListWidget` mit Index-Widgets und eigenem Delegate.
- OCR-Picker setzt eigene Width-Profile, aber gleiche Row-Height-Basis wie Namenliste.

## Erwartetes Verhalten
- Themewechsel aendert Farbe und Kontrast sichtbar auf allen Hauptwidgets.
- Keine „halb dark / halb light“ Mischzustaende nach Mode-Switch.
- Namenliste hat keine abgeschnittenen Zeilen oder springende Zeilenhoehen.
- Subrole-UI bleibt ausgerichtet und horizontal stabil.

## Manuelle Checkliste
- [ ] App starten, Light pruefen: Buttons, Labels, Listen, Overlay.
- [ ] Auf Dark wechseln, gleiche Screens erneut pruefen.
- [ ] Zurueck auf Light wechseln, keine stale Styles.
- [ ] Name-Liste: 20+ Eintraege, Scrollbar und Auswahl sauber.
- [ ] Subrole-Rows: Checkbox-Rand, Hover, Toggle, Disabled-State.
- [ ] OCR-Picker oeffnen und mit Wheel-Namenliste visuell vergleichen.
- [ ] Fenster resize (klein/gross): kein Layoutbruch.

## Regression Hinweise
- Typische Bruchstellen: gecachte Styles mit falschem Key, fehlende Palette-Rollen, hardcoded Farben.
