# Overwatch 2 - Triple Wheel Picker (MVC-ish)

Overwatch 2 lineup/hero/map picker with role wheels, pair mode, hero-ban mode, and OCR import.

Status: This is still a vibe-code project ("vibe-coded") and is being cleaned up incrementally toward a clearer MVC structure.

## Recent Refactoring Updates

- `MainWindow` was further split:
  - UI composition moved into `controller/main_window_ui_builder.py`
  - runtime state bridge moved into `controller/main_window_runtime_bridge.py`
- Runtime phases are now explicit in `model/main_window_runtime_state.py`:
  - `StartupPhase`
  - `ShutdownPhase`
  - `OCRPreloadPhase`
- State sync was split into components:
  - local persistence queue (`LocalStatePersistenceQueue`)
  - remote sync transport (`RemoteRoleSyncService`)
  - both in `controller/state_sync_components.py`
- Central settings provider added:
  - `services/settings_provider.py`
  - bootstrapped in `main.py`

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
python3 -m unittest discover tests/unit
python3 -m unittest discover tests/qt
python3 -m unittest discover tests
```

From the repo root:

```bash
python3 -m unittest discover -s owpicker_mvc/tests/unit -t owpicker_mvc
python3 -m unittest discover -s owpicker_mvc/tests/qt -t owpicker_mvc
python3 -m unittest discover -s owpicker_mvc/tests -t owpicker_mvc
```

Notes:
- Test layout is split into `tests/unit` (headless) and `tests/qt` (GUI/Qt-dependent).
- Qt-dependent modules self-guard via `tests/qt_test_guard.py`.
- If `PySide6` is missing, those modules are reported as `skipped` instead of failing during test discovery/import.

## OCR Warmup / First-Click Metrics

To measure OCR preload warmup and first OCR click latency from runtime traces:

```bash
python3 scripts/analyze_ocr_runtime_trace.py logs/ocr_runtime_trace.log
```

Optional:

```bash
python3 scripts/analyze_ocr_runtime_trace.py logs/ocr_runtime_trace.log --all-runs
```

The analyzer reports (per PID and summary):
- preload total duration
- in-process warmup duration
- first OCR request to worker-start latency
- first OCR request total latency
- first click to terminal OCR result latency

## Repo / Build Hygiene

Before packaging or creating release artifacts, clean local caches/build outputs:

```bash
python3 scripts/repo_hygiene.py --include-build
```

Optional cleanup for runtime/debug artifacts:

```bash
python3 scripts/repo_hygiene.py --include-build --include-logs --include-saved-state
```

Optional cleanup for bundled OCR models (large local artifacts):

```bash
python3 scripts/repo_hygiene.py --include-build --include-ocr-models
```

## Windows EXE OCR (EasyOCR only)

The Windows EXE uses EasyOCR and does not require users to install Tesseract.

Recommended dependency setup for warning-clean CPU builds:

```cmd
py -m pip install -r owpicker_mvc\requirements-ocr-windows-cpu.txt
```

This uses CPU-only torch wheels and avoids CUDA probe warnings (for example `nvcuda.dll`).

1. Download EasyOCR models once during build preparation.
2. Set `OW_OCR_ENGINE=easyocr` and `OW_INCLUDE_EASYOCR=1`.
3. Keep `OW_EASYOCR_HIDDENIMPORT_PROFILE=minimal` for lean builds (default).  
   Use `OW_EASYOCR_HIDDENIMPORT_PROFILE=full` only as fallback if a target system misses OCR modules.
4. Set `OW_EASYOCR_MODEL_DIR` to your local model folder so models are bundled into the EXE.
5. `OW_INCLUDE_REQUESTS` is optional and defaults to `0` (smaller/faster build). Set it to `1` only if you need online sync.
6. For smaller release builds, use `OW_BUILD_PROFILE=release`. On Windows, keep `OW_STRIP=0` unless you have a working `strip` tool installed.
7. Run the OCR dependency preflight once:
   - `python owpicker_mvc/scripts/ocr_dependency_probe.py`
8. Verify build output contains lines like:
   - `[spec] EasyOCR bundle enabled.`
   - `[spec] EasyOCR model source: ...`
   - `[spec] Build profile=... | dist_mode=... | strip=... | ...`
9. Important: preload all languages from `OCR_EASYOCR_LANG` (not only `en`) before building, otherwise onefile may miss required language models.

Example (Windows CMD):

```cmd
set OW_BUILD_PROFILE=release
set OW_PRUNE_QT=1
set OW_INCLUDE_REQUESTS=0
set OW_OCR_ENGINE=easyocr
set OW_INCLUDE_EASYOCR=1
set OW_EASYOCR_HIDDENIMPORT_PROFILE=minimal
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

- `main.py`: entry point, quiet mode setup, shared settings bootstrap.
- `controller/`: MainWindow orchestration, mode handling, spin service, OCR, state sync, shutdown.
  - `controller/map/`: map mode package (`ui.py`, `editor.py`, `styling.py`, `layout.py`, `categories.py`).
  - `controller/ocr/capture|pipeline|preload|runtime`: new OCR package paths (compatibility wrappers to legacy `ocr_*.py` modules during migration).
- `view/`: Qt widgets for wheel/list/overlay/profile UI.
- `logic/`: UI-free algorithms (`spin_engine`, `spin_planner`, `hero_ban_merge`, `name_normalization`).
- `model/`: role/wheel helpers and runtime phase enums.
- `services/`: `state_store`, `sound`, `app_settings`, `settings_provider`.
- `i18n/`, `utils/`, `config.py`: cross-cutting concerns (texts, themes/helpers, feature flags).

## Docs

- Detailed architecture: `ARCHITECTURE.md`
