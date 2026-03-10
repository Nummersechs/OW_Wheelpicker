# Architecture Overview (MVC-ish)

> Note: This project is still a vibe-code project ("vibe-coded") and is being cleaned up/refactored step by step.

## Target Shape

- `view/`: renders UI and emits Qt signals, with minimal domain logic.
- `controller/`: orchestrates user actions, mode switching, startup/shutdown, and glue code.
- `logic/` + `model/`: UI-free rules, calculations, and state handling.
- `services/`: reusable infrastructure (state store, sound, settings).

## Runtime Flow

1. `main.py`
   - bootstraps shared typed settings (`AppSettings` + `settings_provider`),
   - optionally enables quiet mode,
   - creates `QApplication`,
   - starts `controller.main_window.MainWindow(settings=...)`.
2. `controller/main_window.py`
   - coordinates runtime services and high-level state,
   - delegates UI build to `main_window_ui_builder.py`,
   - syncs dataclass runtime state via `main_window_runtime_bridge.py`,
   - initializes helper controllers (`StateSyncController`, `MapModeController`, `OpenQueueController`, ...),
   - shows initial mode choice in the overlay.
3. Interaction
   - view signals are handled by controller callbacks,
   - controllers delegate UI-free parts to `logic/` and state to `model/`/`services/`.
4. Persistence/Sync
   - `StateSyncController` orchestrates save/sync timers and signatures,
   - `LocalStatePersistenceQueue` handles debounced local persistence flow,
   - `RemoteRoleSyncService` handles async online sync via `requests` to `API_BASE_URL`.
5. Shutdown
   - `shutdown_manager.py` stops timers/workers cleanly and secures final state.

## Modules by Responsibility

### `view/`

- `wheel_view.py`: role wheel including name list, pair/subrole options, segment states.
- `wheel_widget.py`, `wheel_disc.py`, `wheel_spin_ops.py`: rendering, animation, and target-segment calculation.
- `list_panel.py`: list panel without wheel (map categories).
- `overlay.py`: startup overlay, result display, and confirm dialogs (delete/OCR).
- `name_list.py`: editable name lists including delete markers/subroles.
- `profile_dropdown.py`: roster profiles including drag-and-drop ordering.
- `spin_mode_toggle.py`, `style_helpers.py`, `screen_region_selector.py`: UI helpers.

### `controller/`

- `main_window.py`: central UI composition and signal wiring.
- `main_window_ui_builder.py`: extracted UI build steps from `MainWindow`.
- `main_window_runtime_bridge.py`: maps runtime dataclass fields to legacy attrs.
- `main_window_parts/main_window_*.py`: extracted MainWindow mixins (OCR, input, startup, spin, shutdown, appearance, mode, state, background, sound).
- `spin_service.py`: spin-all/spin-single/open-queue execution flow.
- `mode_manager.py`, `role_mode.py`: mode switching and hero-ban/role logic.
- `map_ui.py`, `map_mode.py`: encapsulated map UI and map mode controller logic.
- `state_sync.py`: state sync orchestrator (save/sync timers, debounce flow).
- `state_sync_components.py`: extracted components (`StateSnapshotBuilder`, `LocalStatePersistenceQueue`, `RemoteRoleSyncService`, payload helpers).
- `open_queue.py`: open-queue preview/override during spins.
- `ocr/ocr_capture_ops.py`, `ocr/ocr_import.py`, `ocr/ocr_role_import.py`: OCR capture, parsing, and merge into role lists (single-role import or all-roles import with optional per-name role/subrole assignment + balanced distribution fallback).
- `tooltip_manager.py`, `hover_tooltip_ops.py`, `focus_policy.py`, `runtime_tracing.py`: stability/tracing for hover/focus/tooltips.
- `shutdown_manager.py`, `timer_registry.py`, `result_state_ops.py`: shutdown robustness, timer lifecycle, result snapshots.

### `model/`

- `role_keys.py`: canonical role order and mapping helpers.
- `wheel_state.py`: UI-agnostic wheel state (effective names, disabled labels, pair parsing).
- `main_window_runtime_state.py`: startup/shutdown/ocr runtime dataclasses + phase enums.

### `logic/`

- `spin_engine.py`: deterministic target-rotation/spin plan.
- `spin_planner.py`: conflict-free role assignment via backtracking.
- `hero_ban_merge.py`: merge selected roles for hero-ban mode.
- `name_normalization.py`: unicode/token normalization (including OCR dedupe support).

### `services/`

- `state_store.py`: mode states, defaults, profiles, and capture/restore for save-state.
- `sound.py`: sound loading, warmup, preview, master volume.
- `app_settings.py`: typed config projection into runtime/startup/shutdown/ocr sections.
- `settings_provider.py`: shared settings provider used by startup/bootstrap and runtime modules.

### Cross-Cutting

- `i18n/`: `de`/`en` texts and `i18n.t(...)`.
- `utils/`: theme, Qt runtime helpers, UI helpers, flag icons.
- `config.py`: central feature flags, defaults, tracing, and OCR configuration.

## Persistence and Paths

- Save state: `saved_state.json`
  - in script runs under `owpicker_mvc/`
  - in PyInstaller builds next to the `.exe` (not inside temporary `_MEIPASS`).
- Traces (optional, config-driven): e.g. `flow_trace.log`, `focus_trace.log`, `hover_trace.log`.

## Runtime Phase Tracking

- `StartupPhase`: `idle` -> `showing_mode_choice` -> `warmup_running` -> `warmup_cooldown` -> `warmup_done` -> `finalized`
- `OCRPreloadPhase`: `idle|scheduled|deferred|running|done|failed|cancelled`
- `ShutdownPhase`: `idle` -> `close_requested` -> `stopping_workers` -> `waiting_threads` -> `finalizing_close` -> `closed`

These phases are stored in `StartupRuntimeState` / `ShutdownRuntimeState` and mirrored to legacy attributes by `MainWindowRuntimeBridgeMixin`.

## Tests (Current Focus)

- Logic/model: `test_spin_engine.py`, `test_spin_planner.py`, `test_wheel_state.py`, `test_name_normalization.py`.
- Service/controller helpers: `test_state_store.py`, `test_state_sync.py`, `test_spin_service_helpers.py`, `test_open_queue_controller.py`, `test_timer_registry.py`.
- UI-adjacent controller parts: `test_role_mode_controller.py`, `test_mode_results.py`, `test_main_window_input_filter.py`, `test_wheel_view_render_toggle.py`.
- OCR path: `test_ocr_import.py`, `test_ocr_role_import.py`.

## Next Reasonable Steps

1. Further decouple `main_window.py` (move more flow logic into specialized controllers).
2. Continue reducing direct `config` access in remaining modules toward injected `AppSettings`.
3. Expand UI-adjacent integration tests for startup/shutdown phase transitions and overlay flows.
