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
- OCR name import (Tesseract) with two flows:
  - Role OCR buttons import into a single role (Tank/DPS/Support).
  - `All Roles OCR` provides 5 checkboxes per name: `Tank`, `DPS`, `Support`, `Main`, `Flex`. Unchecked names are distributed evenly across roles.
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
2. Build with OCR bundling enabled (`OW_INCLUDE_OCR_BUNDLE=1`) and choose a mode:
   - `OW_OCR_BUNDLE_MODE=minimal` (default): bundle only `tesseract(.exe)`, required runtime libraries, and requested language packs.
   - `OW_OCR_BUNDLE_MODE=full`: bundle the full OCR folder as-is.
3. For minimal mode, set language packs explicitly, e.g. `OW_OCR_LANGS=deu+eng` (optional `OW_OCR_INCLUDE_OSD=1`).
4. Choose distribution mode:
   - `OW_DIST_MODE=onedir` (default on Windows): faster app startup, folder output.
   - `OW_DIST_MODE=onefile`: single EXE, slower startup (self-extract at launch).
5. `OW_INCLUDE_REQUESTS` is optional and defaults to `0` (smaller/faster build). Set it to `1` only if you need online sync.
6. For smaller release builds, use `OW_BUILD_PROFILE=release`. On Windows, keep `OW_STRIP=0` unless you have a working `strip` tool installed.
7. Verify build output contains lines like:
   - `[spec] OCR bundle files: ...`
   - `[spec] OCR languages: deu.traineddata, eng.traineddata`
   - `[spec] Build profile=... | dist_mode=... | strip=...`

Example (Windows CMD):

```cmd
set OW_BUILD_PROFILE=release
set OW_PRUNE_QT=1
set OW_INCLUDE_REQUESTS=0
set OW_INCLUDE_OCR_BUNDLE=1
set OW_OCR_BUNDLE_MODE=minimal
set OW_OCR_LANGS=deu+eng
set OW_OCR_INCLUDE_OSD=1
set OW_DIST_MODE=onedir
pyinstaller --noconfirm --clean owpicker_mvc/OverwatchWheels.spec
```

At runtime `OCR_TESSERACT_CMD = "auto"` prefers bundled Tesseract in the EXE unpack directory and only falls back to PATH.
During OCR region selection, the main window is hidden by default (`OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE = True`).
In the Qt capture selector (used on Windows), region selection now confirms on mouse release by default (`OCR_QT_SELECTOR_AUTO_ACCEPT_ON_RELEASE = True`), so pressing Enter is optional.

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
