from __future__ import annotations


class MainWindowRuntimeBridgeMixin:
    """Syncs runtime dataclass state onto legacy MainWindow attributes."""

    _STARTUP_RUNTIME_ATTRS: dict[str, str] = {
        "_startup_phase": "startup_phase",
        "_startup_finalize_done": "finalize_done",
        "_startup_finalize_scheduled": "finalize_scheduled",
        "_startup_visual_finalize_pending": "visual_finalize_pending",
        "_startup_block_input": "block_input",
        "_startup_block_input_until": "block_input_until",
        "_startup_warmup_running": "warmup_running",
        "_startup_warmup_done": "warmup_done",
        "_startup_warmup_finalize_scheduled": "warmup_finalize_scheduled",
        "_startup_task_queue": "task_queue",
        "_startup_current_task": "current_task",
        "_startup_waiting_for_map": "waiting_for_map",
        "_startup_map_prebuild_deadline": "map_prebuild_deadline",
        "_startup_waiting_for_ocr_preload": "waiting_for_ocr_preload",
        "_startup_ocr_preload_deadline": "ocr_preload_deadline",
        "_startup_ocr_preload_started_at": "ocr_preload_started_at",
        "_startup_ocr_preload_running_wait_logged": "ocr_preload_running_wait_logged",
        "_ocr_preload_phase": "ocr_preload_phase",
        "_ocr_preload_phase_reason": "ocr_preload_phase_reason",
        "_startup_drain_active": "drain_active",
    }
    _SHUTDOWN_RUNTIME_ATTRS: dict[str, str] = {
        "_shutdown_phase": "shutdown_phase",
        "_closing": "closing",
        "_close_overlay_active": "close_overlay_active",
        "_close_overlay_done": "close_overlay_done",
        "_close_overlay_timer": "close_overlay_timer",
        "_close_retry_timer": "close_retry_timer",
        "_close_thread_wait_started_at": "close_thread_wait_started_at",
        "_shutdown_force_exit_deadline": "shutdown_force_exit_deadline",
        "_shutdown_force_exit_watchdog_token": "shutdown_force_exit_watchdog_token",
        "_shutdown_blocker_trace_last_at": "shutdown_blocker_trace_last_at",
    }
    _STARTUP_RUNTIME_FIELDS: dict[str, str] = {
        field_name: attr_name for attr_name, field_name in _STARTUP_RUNTIME_ATTRS.items()
    }
    _SHUTDOWN_RUNTIME_FIELDS: dict[str, str] = {
        field_name: attr_name for attr_name, field_name in _SHUTDOWN_RUNTIME_ATTRS.items()
    }

    def _sync_startup_runtime_attrs(self) -> None:
        state = getattr(self, "_startup_state", None)
        if state is None:
            return
        for attr, field_name in self._STARTUP_RUNTIME_ATTRS.items():
            super().__setattr__(attr, getattr(state, field_name))

    def _sync_shutdown_runtime_attrs(self) -> None:
        state = getattr(self, "_shutdown_state", None)
        if state is None:
            return
        for attr, field_name in self._SHUTDOWN_RUNTIME_ATTRS.items():
            super().__setattr__(attr, getattr(state, field_name))

    def _set_startup_runtime_state(self, **updates: object) -> None:
        state = getattr(self, "_startup_state", None)
        field_to_attr = self._STARTUP_RUNTIME_FIELDS
        for field_name, value in updates.items():
            attr_name = field_to_attr.get(field_name)
            if attr_name is None:
                raise AttributeError(f"Unknown startup runtime field: {field_name}")
            if state is not None:
                setattr(state, field_name, value)
            super().__setattr__(attr_name, value)

    def _set_shutdown_runtime_state(self, **updates: object) -> None:
        state = getattr(self, "_shutdown_state", None)
        field_to_attr = self._SHUTDOWN_RUNTIME_FIELDS
        for field_name, value in updates.items():
            attr_name = field_to_attr.get(field_name)
            if attr_name is None:
                raise AttributeError(f"Unknown shutdown runtime field: {field_name}")
            if state is not None:
                setattr(state, field_name, value)
            super().__setattr__(attr_name, value)
