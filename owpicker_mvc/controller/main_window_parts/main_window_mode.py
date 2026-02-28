from __future__ import annotations

import time

from PySide6 import QtCore

import config
from .. import mode_manager
from model.role_keys import role_wheel_map


class MainWindowModeMixin:
    def _activate_role_modes(self):
        if hasattr(self, "mode_stack"):
            self.mode_stack.setCurrentIndex(0)
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.hide_panel()

    def _on_mode_button_clicked(self, target: str):
        self._trace_event("mode_button_clicked", target=target)
        if self._post_choice_input_guard_active():
            self._trace_event("mode_switch_ignored", target=target, reason="mode_choice_input_guard")
            return
        if not self._post_choice_init_done and not self._overlay_choice_active():
            self._ensure_post_choice_ready()
        if target != "maps" and getattr(self, "_pending_map_mode_switch", False):
            self._pending_map_mode_switch = False
            self._trace_event("mode_switch_cancelled", target=target)
        if target == "maps" and not getattr(self, "_map_lists_ready", False):
            self._trace_event("mode_switch_deferred", target=target)
            self._pending_map_mode_switch = True
            self._schedule_map_prebuild(force=True)
            self._set_map_button_loading(True, reason="mode_switch_deferred")
            self._set_map_button_enabled(False)
            return
        if target == "maps":
            self._pending_map_mode_switch = False
        # Aktuelle Ergebnisse für den Modus merken, bevor wir wechseln
        self._snapshot_mode_results()
        if target == "maps":
            self._ensure_map_ui()
            # Merk dir, welcher Rollen-Modus gerade in den Wheels steckt,
            # damit Map-Mode-Saves später nicht versehentlich den falschen Modus überschreiben.
            self.last_non_hero_mode = self.current_mode
            if self.hero_ban_active:
                self.hero_ban_active = False
                self.dps.set_override_entries(None)
                self._set_hero_ban_visuals(False)
            # vorherige Zustände sichern
            self._state_store.capture_mode_from_wheels(
                self.current_mode,
                role_wheel_map(self),
                hero_ban_active=self.hero_ban_active,
            )
            self.map_mode.capture_state()
            self.map_mode.activate_mode()
            self._sync_mode_stack()
            self._trace_event("mode_switch:maps_done")
            return

        # wenn wir aus dem Map-Mode zurückkommen, zuerst speichern
        if self.current_mode == "maps":
            self.map_mode.capture_state()
            if hasattr(self, "map_ui"):
                self.map_ui.set_active(False)
        self._activate_role_modes()
        mode_manager.on_mode_button_clicked(self, target)
        self._sync_mode_stack()
        self._trace_event("mode_switch:roles_done", target=target)
        if not self._cfg("DISABLE_TOOLTIPS", False) and not self._cfg("TOOLTIP_CACHE_ON_START", False):
            self._refresh_tooltip_caches_async()

    @QtCore.Slot(bool)
    def _on_mode_chosen(self, online: bool):
        if getattr(self, "_mode_choice_locked", False):
            return
        self._mode_choice_locked = True
        self._apply_mode_choice(online)

    def _apply_mode_choice(self, online: bool):
        if getattr(self, "_closing", False):
            return
        self._flush_blocked_input_stats("mode_choice")
        self._flush_hover_prime_deferred_trace()
        self._arm_post_choice_input_guard(reason="mode_choice")
        self._refresh_app_event_filter_state()
        self._hover_prime_pending = False
        self._hover_prime_reason = None
        self.online_mode = online
        self._set_controls_enabled(True)
        self._set_heavy_ui_updates_enabled(True)
        warmup_done = bool(getattr(self, "_startup_warmup_done", False))
        self._post_choice_init_done = warmup_done
        if warmup_done:
            elapsed = None
            if self._choice_shown_at is not None:
                elapsed = round(time.monotonic() - self._choice_shown_at, 3)
            self._trace_event(
                "apply_mode_choice",
                online=online,
                elapsed=elapsed,
                delay_ms=0,
                warmup_done=True,
            )
        else:
            # Schwere Arbeiten nach der Auswahl leicht verzögern, um "Early Click"-Lags zu vermeiden.
            delay_ms = self._post_choice_delay_ms
            if self._choice_shown_at is not None:
                elapsed = time.monotonic() - self._choice_shown_at
                if elapsed < 0.8:
                    delay_ms = max(delay_ms, 900)
                    self._post_choice_step_ms = 140
                    self._post_choice_warmup_step_ms = 55
                else:
                    self._post_choice_step_ms = 90
                    self._post_choice_warmup_step_ms = 40
                self._trace_event(
                    "apply_mode_choice",
                    online=online,
                    elapsed=round(elapsed, 3),
                    delay_ms=delay_ms,
                )
            self._schedule_post_choice_init(delay_ms)
        # Ensure hover tracking is active right after mode choice (no focus changes).
        self._schedule_hover_rearm("mode_choice")
        self._schedule_hover_rearm("mode_choice:late", delay_ms=250)
        self._hover_seen = False
        # Force a short hover pump so hover becomes responsive even if the cursor didn't move.
        self._start_hover_pump(reason="mode_choice", duration_ms=2000, force=True)

        if self.online_mode:
            config.debug_print("Online-Modus aktiv.")
        else:
            config.debug_print("Offline-Modus aktiv.")
        # Sync ggf. neu einplanen oder abbrechen
        self.state_sync.sync_all_roles()
        if bool(getattr(self, "_startup_visual_finalize_pending", False)):
            self._schedule_startup_visual_finalize(
                delay_ms=int(self._cfg("STARTUP_VISUAL_FINALIZE_DELAY_MS", 280))
            )
        self._schedule_wheel_cache_warmup(delay_ms=120)
        self._refresh_app_event_filter_state()

    def _overlay_choice_active(self) -> bool:
        overlay = getattr(self, "overlay", None)
        if not overlay or not overlay.isVisible():
            return False
        view = getattr(overlay, "_last_view", {}) or {}
        return view.get("type") == "online_choice"

    def _set_map_button_enabled(self, enabled: bool) -> None:
        if hasattr(self, "btn_mode_maps"):
            try:
                self.btn_mode_maps.setEnabled(bool(enabled))
            except Exception:
                pass

    def _mark_stack_switching(self, delay_ms: int = 140) -> None:
        if getattr(self, "_closing", False):
            return
        self._stack_switching = True
        timer = getattr(self, "_stack_switch_timer", None)
        if timer is not None:
            timer.start(max(0, int(delay_ms)))
        self._trace_event("stack_switching", active=True, delay_ms=delay_ms)

    def _clear_stack_switching(self) -> None:
        if not getattr(self, "_stack_switching", False):
            return
        self._stack_switching = False
        self._trace_event("stack_switching", active=False)
        # Stack-Wechsel kann Hover-Eingaenge verlieren -> Pump nach dem Wechsel neu starten.
        self._hover_seen = False
        self._hover_forward_last = None
        self._rearm_hover_tracking(reason="stack_switching:done")
        self._schedule_hover_rearm("stack_switching:late", delay_ms=250)

    def _sync_mode_stack(self) -> None:
        if not hasattr(self, "mode_stack"):
            return
        self._mark_stack_switching()
        self._trace_event("sync_mode_stack:before")
        if self.current_mode == "maps":
            self.mode_stack.setCurrentIndex(1)
            if hasattr(self, "map_ui"):
                self.map_ui.set_active(True)
        else:
            self.mode_stack.setCurrentIndex(0)
            if hasattr(self, "map_ui"):
                self.map_ui.set_active(False)
        self._update_title()
        self._update_spin_all_enabled()
        if getattr(self, "role_container", None):
            self.role_container.update()
        if getattr(self, "map_container", None):
            self.map_container.update()
        self._trace_event("sync_mode_stack:after", force_vis=True)
        self._trace_event("sync_mode_stack:after")
