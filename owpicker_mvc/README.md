# Overwatch 2 - Triple Wheel Picker (MVC-ish)

Overwatch 2 lineup/hero/map picker with role wheels, pair mode, hero-ban mode, and OCR import.

Status: This is still a vibe-code project ("vibe-coded") and is being cleaned up incrementally toward a clearer MVC structure.

## Run

```bash
python3 main.py
```

## Features (current)

- Modes: Players, Heroes, Maps, Hero-Ban.
- Open Queue mode for cross-role candidate pools.
- OCR name import (Tesseract) including candidate selection/replace flow.
- Persistent state (`saved_state.json`) including roster profiles.
- Optional online sync for role states and spin results.
- Theme/language switch and sound feedback.

## Tests

From the `owpicker_mvc/` directory:

```bash
python3 -m unittest discover tests
```

From the repo root:

```bash
python3 -m unittest discover owpicker_mvc/tests
```

## Windows EXE OCR (no extra install)

If you want OCR to work in the Windows EXE without requiring users to install Tesseract:

1. Use one bundle source:
   Local portable bundle under `owpicker_mvc/OCR/` (for example `tesseract.exe`, runtime DLLs, and `tessdata/*.traineddata`), or the Windows install folder (auto-detected): `C:\Program Files\Tesseract-OCR` (and x86 variant).  
   Optional explicit override: set `OW_TESSERACT_DIR` (or `TESSERACT_ROOT`) to your Tesseract folder.
2. Build with `OW_INCLUDE_OCR_BUNDLE=1` (enabled by default in the provided commands).
3. Verify build output contains lines like:
   - `[spec] OCR bundle files: ...`
   - `[spec] OCR languages: deu.traineddata, eng.traineddata`

At runtime `OCR_TESSERACT_CMD = "auto"` prefers bundled Tesseract in the EXE unpack directory and only falls back to PATH.

## Structure (short)

- `main.py`: entry point + quiet mode setup.
- `controller/`: MainWindow orchestration, mode handling, spin service, OCR, state sync, shutdown.
- `view/`: Qt widgets for wheel/list/overlay/profile UI.
- `logic/`: UI-free algorithms (`spin_engine`, `spin_planner`, `hero_ban_merge`, `name_normalization`).
- `model/`: role and wheel state helpers.
- `services/`: `state_store`, `sound`, `app_settings`.
- `i18n/`, `utils/`, `config.py`: cross-cutting concerns (texts, themes/helpers, feature flags).

## Docs

- Detailed architecture: `ARCHITECTURE.md`
