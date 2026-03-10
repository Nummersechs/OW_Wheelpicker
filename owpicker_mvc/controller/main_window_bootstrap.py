from __future__ import annotations

import os
import time
from pathlib import Path

import i18n
from services.app_settings import AppSettings
from services import settings_provider
from utils import theme as theme_util


class MainWindowBootstrapMixin:
    """Bootstrap settings, persistent state, and early theme setup."""

    def _bootstrap_settings_and_theme(self, settings: AppSettings | None):
        # Resolve base directories (assets vs writable state) and load persisted state.
        self._asset_dir = self._asset_base_dir()
        self._state_dir = self._state_base_dir()
        self._state_file = self._get_state_file()
        resolved_settings = settings if isinstance(settings, AppSettings) else settings_provider.get_settings()
        if not isinstance(resolved_settings, AppSettings):
            resolved_settings = AppSettings(values={})
        # Backward-compatible fallback for environments that still instantiate
        # MainWindow without bootstrapping the shared settings provider.
        if not resolved_settings.values:
            try:
                import config as app_config
            except ImportError:
                pass
            else:
                resolved_settings = AppSettings.from_module(app_config)
                settings_provider.set_settings(resolved_settings)
        self.settings = resolved_settings
        self._quiet_mode = self._runtime_bool("quiet", "QUIET", False)
        configured_log_dir = self._runtime_str("log_output_dir", "LOG_OUTPUT_DIR", "logs").strip()
        log_root = Path(configured_log_dir) if configured_log_dir else Path()
        if not configured_log_dir:
            log_root = self._state_dir
        elif not log_root.is_absolute():
            log_root = self._state_dir / log_root
        self._log_dir = log_root
        if not self._quiet_mode:
            try:
                self._log_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                self._log_dir = self._state_dir
        self._run_id = f"{int(time.time() * 1000)}_{os.getpid()}"
        saved = self._load_saved_state(self._state_file)
        default_lang = self._runtime_str("default_language", "DEFAULT_LANGUAGE", "en")
        self.language = saved.get("language", default_lang) if isinstance(saved, dict) else default_lang
        i18n.set_language(self.language)
        self.theme = saved.get("theme", "light") if isinstance(saved, dict) else "light"
        if self.theme not in theme_util.THEMES:
            self.theme = "light"
        # Apply palette/global stylesheet baseline early so startup overlays/widgets
        # pick the persisted theme immediately.
        try:
            theme_util.apply_app_theme(
                theme_util.get_theme(self.theme),
                force_fusion_style=bool(self._cfg("FORCE_FUSION_STYLE", False)),
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass
        return saved
