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
- OCR name import (local/offline) with two flows:
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

## Windows EXE OCR (EasyOCR only)

The Windows EXE uses EasyOCR and does not require users to install Tesseract.

1. Download EasyOCR models once during build preparation.
2. Set `OW_OCR_ENGINE=easyocr` and `OW_INCLUDE_EASYOCR=1`.
3. Set `OW_EASYOCR_MODEL_DIR` to your local model folder so models are bundled into the EXE.
4. `OW_INCLUDE_REQUESTS` is optional and defaults to `0` (smaller/faster build). Set it to `1` only if you need online sync.
5. For smaller release builds, use `OW_BUILD_PROFILE=release`. On Windows, keep `OW_STRIP=0` unless you have a working `strip` tool installed.
6. Verify build output contains lines like:
   - `[spec] EasyOCR bundle enabled.`
   - `[spec] EasyOCR model source: ...`
   - `[spec] Build profile=... | dist_mode=... | strip=... | ...`
7. Important: preload all languages from `OCR_EASYOCR_LANG` (not only `en`) before building, otherwise onefile may miss required language models.

Example (Windows CMD):

```cmd
set OW_BUILD_PROFILE=release
set OW_PRUNE_QT=1
set OW_INCLUDE_REQUESTS=0
set OW_OCR_ENGINE=easyocr
set OW_INCLUDE_EASYOCR=1
set OW_EASYOCR_MODEL_DIR=%CD%\owpicker_mvc\EasyOCR\model
set OW_DIST_MODE=onedir
pyinstaller --noconfirm --clean owpicker_mvc/OverwatchWheels.spec
```

During OCR region selection, the main window is hidden by default (`OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE = True`).
In the Qt capture selector (used on Windows), region selection now confirms on mouse release by default (`OCR_QT_SELECTOR_AUTO_ACCEPT_ON_RELEASE = True`), so pressing Enter is optional.

## Local EasyOCR backend

The app uses `easyocr` as a fully local OCR backend (no cloud/API calls).

1. Install optional dependency:

```bash
pip install -r requirements-ocr-local.txt
```

2. Set in `config.py`:

```python
OCR_ENGINE = "easyocr"
OCR_EASYOCR_LANG = "en"  # e.g. "en,de"
OCR_EASYOCR_DOWNLOAD_ENABLED = False  # strict offline mode
```

Notes:
- In strict offline mode (`OCR_EASYOCR_DOWNLOAD_ENABLED = False`), required model files must already exist locally.

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
