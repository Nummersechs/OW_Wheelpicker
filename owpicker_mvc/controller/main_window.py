from pathlib import Path
from typing import Callable

from PySide6 import QtCore, QtWidgets

import i18n
from . import (
    hover_tooltip_ops,
    result_state_ops,
    runtime_tracing,
)
from .main_window_parts.main_window_input import MainWindowInputMixin
from .main_window_parts.main_window_appearance import MainWindowAppearanceMixin
from .main_window_parts.main_window_background import MainWindowBackgroundMixin
from .main_window_parts.main_window_mode import MainWindowModeMixin
from .main_window_parts.main_window_ocr import MainWindowOCRMixin
from .main_window_parts.main_window_shutdown import MainWindowShutdownMixin
from .main_window_parts.main_window_sound import MainWindowSoundMixin
from .main_window_parts.main_window_startup import MainWindowStartupMixin
from .main_window_parts.main_window_state import MainWindowStateMixin
from .main_window_parts.main_window_spin import MainWindowSpinMixin
from .main_window_bootstrap import MainWindowBootstrapMixin
from .main_window_runtime_bridge import MainWindowRuntimeBridgeMixin
from .main_window_runtime_setup import MainWindowRuntimeSetupMixin
from .main_window_ui_builder import MainWindowUIBuilderMixin
from services.app_settings import AppSettings
from model.role_keys import role_wheels
from .state_sync import StateSyncController


class MainWindow(
    MainWindowBootstrapMixin,
    MainWindowRuntimeBridgeMixin,
    MainWindowRuntimeSetupMixin,
    MainWindowUIBuilderMixin,
    MainWindowStateMixin,
    MainWindowShutdownMixin,
    MainWindowAppearanceMixin,
    MainWindowModeMixin,
    MainWindowOCRMixin,
    MainWindowSoundMixin,
    MainWindowStartupMixin,
    MainWindowBackgroundMixin,
    MainWindowSpinMixin,
    MainWindowInputMixin,
    QtWidgets.QMainWindow,
):
    def __init__(self, settings: AppSettings | None = None):
        super().__init__()
        saved = self._bootstrap_settings_and_theme(settings)

        self.setWindowTitle(i18n.t("app.title.main"))
        self.resize(1200, 650)
        self._init_sound_manager()
        self._init_runtime_state_and_services(saved)
        central, root = self._build_root()
        self._build_header(root, saved)
        self._build_mode_switcher(root)
        role_container = self._build_role_container()
        self._build_map_container()
        self._build_mode_stack(root, role_container)
        self._apply_initial_mode_state()
        self._wire_spin_signals()
        self._build_controls(root)
        self._build_summary(root)
        self._init_spin_state()
        self._build_overlay(central)
        self._install_event_filters()
        self._show_mode_choice()
        self._connect_state_signals()
        self._schedule_finalize_startup()
        self._apply_focus_policy_defaults()
        self._schedule_clear_focus()
        try:
            self.setMouseTracking(True)
            central.setMouseTracking(True)
        except (AttributeError, RuntimeError):
            pass

    def _cfg(self, key: str, default=None):
        settings = getattr(self, "settings", None)
        if settings is not None and hasattr(settings, "resolve"):
            try:
                return settings.resolve(key, default)
            except (AttributeError, TypeError, ValueError):
                pass
        if settings is not None and hasattr(settings, "get"):
            try:
                return settings.get(key, default)
            except (AttributeError, TypeError):
                pass
        legacy_config = getattr(self, "_legacy_config", None)
        if legacy_config is None:
            try:
                import config as app_config
            except ImportError:
                app_config = None
            legacy_config = app_config
            try:
                self._legacy_config = app_config
            except (AttributeError, RuntimeError, TypeError):
                pass
        if legacy_config is not None:
            return getattr(legacy_config, key, default)
        return default

    def _runtime_settings(self):
        settings = getattr(self, "settings", None)
        return getattr(settings, "runtime", None)

    def _trace_settings(self):
        settings = getattr(self, "settings", None)
        return getattr(settings, "trace", None)

    def _spin_ui_settings(self):
        settings = getattr(self, "settings", None)
        return getattr(settings, "spin_ui", None)

    def _runtime_bool(self, attr: str, key: str, default: bool) -> bool:
        section = self._runtime_settings()
        if section is not None and hasattr(section, attr):
            try:
                return bool(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg(key, default))

    def _runtime_str(self, attr: str, key: str, default: str) -> str:
        section = self._runtime_settings()
        if section is not None and hasattr(section, attr):
            value = str(getattr(section, attr, default) or "").strip()
            return value or str(default)
        value = str(self._cfg(key, default) or "").strip()
        return value or str(default)

    def _trace_bool(self, attr: str, key: str, default: bool) -> bool:
        section = self._trace_settings()
        if section is not None and hasattr(section, attr):
            try:
                return bool(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg(key, default))

    def _spin_ui_bool(self, attr: str, key: str, default: bool) -> bool:
        section = self._spin_ui_settings()
        if section is not None and hasattr(section, attr):
            try:
                return bool(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg(key, default))

    def _debug_print(self, *args, **kwargs) -> None:
        if not self._runtime_bool("debug", "DEBUG", False):
            return
        if self._runtime_bool("quiet", "QUIET", False):
            return
        try:
            print(*args, **kwargs)
        except OSError:
            pass

    def _write_trace_run_header(self, enabled: bool, trace_file: Path) -> None:
        if not enabled:
            return
        try:
            trace_file.parent.mkdir(parents=True, exist_ok=True)
            if self._trace_bool("clear_on_start", "TRACE_CLEAR_ON_START", False):
                trace_file.write_text("", encoding="utf-8")
            with trace_file.open("a", encoding="utf-8") as handle:
                handle.write(f"=== run {self._run_id} ===\n")
        except OSError:
            pass

    @staticmethod
    def _load_saved_state(state_file: Path):
        return StateSyncController.load_saved_state(state_file)

    def _role_wheels(self) -> list[tuple[str, object]]:
        return role_wheels(self)

    @staticmethod
    def _role_state_key(role: str) -> str:
        return {
            "Tank": "tank",
            "Damage": "dps",
            "Support": "support",
        }.get(role, role.strip().lower())

    def _on_overlay_closed(self):
        if self.pending <= 0:
            self._set_controls_enabled(True)
        else:
            self._trace_event("overlay_closed_ignored", reason="spin_active", pending=self.pending)
            self._update_cancel_enabled()
        self.sound.stop_ding()
        if self.hero_ban_active:
            self._hero_ban_override_role = None
            self._update_hero_ban_wheel()
        # Ensure hover tracking re-arms after the choice overlay disappears.
        self._schedule_hover_rearm("overlay_closed", force=True)
        self._schedule_hover_rearm("overlay_closed:late", delay_ms=200)
        # Tooltip/Truncation nach finalem Layout aktualisieren
        if not self._runtime_bool("disable_tooltips", "DISABLE_TOOLTIPS", False):
            self._set_tooltips_ready(False)
            self._schedule_tooltip_refresh("overlay_closed", delay_ms=120)
        self._refresh_app_event_filter_state()

    def _on_overlay_disable_results(self):
        last_view = getattr(self.overlay, "_last_view", {}) or {}
        if last_view.get("type") != "result":
            return
        data = last_view.get("data") or ()
        role_wheels_list = self._role_wheels()
        if len(data) != len(role_wheels_list):
            return
        mapping = [(wheel, data[idx]) for idx, (_role, wheel) in enumerate(role_wheels_list)]
        names_to_remove: set[str] = set()
        for wheel, label in mapping:
            if hasattr(wheel, "result_label_names"):
                names_to_remove.update(wheel.result_label_names(label))
            elif isinstance(label, str) and label.strip():
                names_to_remove.add(label.strip())
        if not names_to_remove:
            return
        for _role, wheel in role_wheels_list:
            if hasattr(wheel, "deactivate_names"):
                wheel.deactivate_names(names_to_remove)

    def _on_overlay_delete_names_confirmed(self):
        panel = getattr(self, "_pending_delete_names_panel", None)
        self._pending_delete_names_panel = None
        if panel is None:
            return
        try:
            panel.confirm_delete_marked()
        except (AttributeError, RuntimeError):
            return

    def _on_overlay_delete_names_cancelled(self):
        self._pending_delete_names_panel = None

    def _mode_key(self) -> str:
        return result_state_ops.mode_key(self)

    def _snapshot_mode_results(self):
        result_state_ops.snapshot_mode_results(self)

    def _apply_mode_results(self, key: str):
        result_state_ops.apply_mode_results(self, key)

    def _update_summary_from_results(self):
        result_state_ops.update_summary_from_results(self)

    def _refresh_tooltip_caches_async(
        self,
        delay_step_ms: int = 80,
        on_done: Callable[[], None] | None = None,
        reason: str | None = None,
        force: bool = False,
    ):
        hover_tooltip_ops.refresh_tooltip_caches_async(
            self,
            delay_step_ms=delay_step_ms,
            on_done=on_done,
            reason=reason,
            force=force,
        )

    def _set_tooltips_ready(self, ready: bool = True):
        hover_tooltip_ops.set_tooltips_ready(self, ready=ready)

    def _on_role_ocr_import_clicked(self, role_key: str) -> None:
        from .ocr.capture import ops as ocr_capture_ops

        ocr_capture_ops.on_role_ocr_import_clicked(self, role_key)

    def _on_open_q_ocr_clicked(self) -> None:
        if not self._role_ocr_import_available("all"):
            return
        if hasattr(self, "btn_open_q_ocr"):
            self.btn_open_q_ocr.setEnabled(False)
        self._on_role_ocr_import_clicked("all")
        self._update_role_ocr_buttons_enabled()

    def _snapshot_results(self):
        result_state_ops.snapshot_results(self)

    def _restore_results_snapshot(self):
        result_state_ops.restore_results_snapshot(self)

    def _trace_event(self, name: str, **extra) -> None:
        runtime_tracing.trace_event(self, name, **extra)
