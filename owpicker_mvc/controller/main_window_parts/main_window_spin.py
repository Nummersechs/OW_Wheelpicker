from __future__ import annotations

import time

from PySide6 import QtCore

import i18n
from model.role_keys import role_for_wheel
from view.wheel_view import WheelView

from .. import spin_service


class MainWindowSpinMixin:
    def _on_open_count_changed(self, value: int) -> None:
        self._sync_open_queue_player_count(value, sync_slider=True)
        if hasattr(self, "open_queue") and self.open_queue.is_mode_active():
            self.open_queue.apply_slider_combination()
        if hasattr(self, "open_queue"):
            self._update_spin_all_enabled()

    def _open_queue_max_allowed_slots(self) -> int:
        open_queue = getattr(self, "open_queue", None)
        if open_queue is None:
            return 1
        return max(1, int(open_queue.max_slots_capacity()))

    def _set_open_count_slider_value(self, value: int, *, maximum: int | None = None) -> None:
        slider = getattr(self, "open_count_slider", None)
        if slider is None:
            return
        if maximum is not None and int(slider.maximum()) != int(maximum):
            slider.setMaximum(int(maximum))
        value_i = int(value)
        if int(slider.value()) == value_i:
            return
        blocker = QtCore.QSignalBlocker(slider)
        slider.setValue(value_i)
        del blocker

    def _set_open_count_label_value(self, value: int) -> None:
        label = getattr(self, "lbl_open_count_value", None)
        if label is not None:
            label.setText(str(int(value)))

    def _sync_open_queue_player_count(self, value: int, *, sync_slider: bool) -> int:
        shown = max(1, int(value))
        open_queue = getattr(self, "open_queue", None)
        if open_queue is None:
            if sync_slider:
                self._set_open_count_slider_value(shown)
            self._set_open_count_label_value(shown)
            return shown

        max_allowed = self._open_queue_max_allowed_slots()
        open_queue.set_player_count(shown, max_allowed=max_allowed)
        shown = open_queue.player_count(max_allowed=max_allowed)
        if sync_slider:
            self._set_open_count_slider_value(shown, maximum=max_allowed)
        self._set_open_count_label_value(shown)
        return shown

    def _sync_open_queue_plan_for_open_mode(self) -> tuple[list[tuple[str, object, int]], list[str]]:
        sender = self.sender()
        slider_sender = getattr(self, "open_count_slider", None)
        toggle_sender = getattr(self, "spin_mode_toggle", None)
        if not self.open_queue.is_applying_combination():
            if sender is None or sender is slider_sender or sender is toggle_sender:
                self.open_queue.apply_slider_combination()
            else:
                self.open_queue.sync_player_count_from_wheels()
        return self.open_queue.slot_plan(), self.open_queue.names()

    def _update_spin_all_enabled(self):
        """Aktiviere/Deaktiviere den 'Drehen'-Button je nach Auswahl."""
        # Keep the button responsive during startup/mode transitions.
        # The click-path guards in spin_all/_spin_single still prevent unsafe spins.
        open_names: list[str] | None = None
        enabled = False
        if getattr(self, "hero_ban_active", False):
            any_selected = any(w.btn_include_in_all.isChecked() for _role, w in self._role_wheels())
            # In Hero-Ban zählen die effektiven Namen des zentralen Rads (inkl. Override).
            has_candidates = bool(self.dps.get_effective_wheel_names())
            enabled = bool(any_selected and has_candidates and self.pending == 0)
        elif self.current_mode == "maps":
            any_selected = any(w.btn_include_in_all.isChecked() for w in getattr(self, "map_lists", {}).values())
            has_candidates = bool(self.map_ui.combined_names() if hasattr(self, "map_ui") else [])
            enabled = bool(any_selected and has_candidates and self.pending == 0)
        elif self.open_queue.is_mode_active():
            slot_plan, open_names = self._sync_open_queue_plan_for_open_mode()
            slots = sum(slots for _role, _wheel, slots in slot_plan)
            has_candidates = bool(slot_plan) and slots > 0 and len(open_names) >= slots
            enabled = bool(has_candidates and self.pending == 0)
        else:
            if self.open_queue.spin_mode_allowed():
                self.open_queue.sync_player_count_from_wheels()
            # Nur aktiv, wenn allgemein erlaubt UND mindestens ein Rad ausgewählt
            enabled = bool(self.role_mode.can_spin_all())
        self.btn_spin_all.setEnabled(enabled)
        self._update_spin_mode_ui()
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.update_button()
        self.open_queue.apply_preview(open_names)
        self._update_cancel_enabled()
        self._update_role_ocr_buttons_enabled()

    def _update_spin_mode_ui(self):
        if not hasattr(self, "spin_mode_toggle"):
            return
        allowed = self.open_queue.spin_mode_allowed()
        self.spin_mode_toggle.setVisible(allowed)
        show_open_controls = bool(allowed and self.open_queue.is_mode_active())
        if hasattr(self, "lbl_open_count"):
            self.lbl_open_count.setVisible(show_open_controls)
        if hasattr(self, "open_count_slider"):
            self.open_count_slider.setVisible(show_open_controls)
        if hasattr(self, "lbl_open_count_value"):
            self.lbl_open_count_value.setVisible(show_open_controls)
        if not allowed:
            self.spin_mode_toggle.setEnabled(False)
            if hasattr(self, "open_count_slider"):
                self.open_count_slider.setEnabled(False)
            return
        enabled = self.pending == 0
        self.spin_mode_toggle.setEnabled(enabled)
        max_allowed = self._open_queue_max_allowed_slots()
        requested = self.open_queue.player_count(max_allowed=max_allowed)
        requested = self._sync_open_queue_player_count(requested, sync_slider=True)
        if hasattr(self, "open_count_slider"):
            self.open_count_slider.setEnabled(bool(enabled and show_open_controls))
        self.spin_mode_toggle.set_texts(
            i18n.t("controls.spin_mode_role"),
            i18n.t("controls.spin_mode_open", count=requested),
        )

    def _set_widget_interactive_enabled(
        self,
        widget,
        enabled: bool,
        *,
        lightweight_spin_lock: bool,
    ) -> None:
        if lightweight_spin_lock:
            try:
                widget.set_interactive_enabled(enabled, disable_name_inputs=False)
                return
            except TypeError:
                pass
        widget.set_interactive_enabled(enabled)

    def _set_controls_enabled(self, en: bool, *, spin_mode: bool = False):
        lightweight_spin_lock = bool(spin_mode and not en and self._cfg("SPIN_LIGHTWEIGHT_UI_LOCK", True))
        if en:
            self._resume_background_ui_services()
            self._update_spin_all_enabled()
        else:
            self._pause_background_ui_services()
            self.btn_spin_all.setEnabled(False)
            if hasattr(self, "spin_mode_toggle"):
                self.spin_mode_toggle.setEnabled(False)
            if hasattr(self, "btn_all_players"):
                self.btn_all_players.setEnabled(False)
            if hasattr(self, "btn_open_q_ocr"):
                self.btn_open_q_ocr.setEnabled(False)
            if hasattr(self, "player_list_panel"):
                self.player_list_panel.hide_panel()
        for _role, w in self._role_wheels():
            self._set_widget_interactive_enabled(
                w,
                en,
                lightweight_spin_lock=lightweight_spin_lock,
            )
        if getattr(self, "current_mode", "") == "maps" and hasattr(self, "map_lists"):
            for w in self.map_lists.values():
                self._set_widget_interactive_enabled(
                    w,
                    en,
                    lightweight_spin_lock=lightweight_spin_lock,
                )
            if hasattr(self, "map_main"):
                self._set_widget_interactive_enabled(
                    self.map_main,
                    en,
                    lightweight_spin_lock=lightweight_spin_lock,
                )
        if not en:
            self._update_cancel_enabled()
        if self.hero_ban_active and en:
            self._set_hero_ban_visuals(True)
        self._update_role_ocr_buttons_enabled()
        self._refresh_app_event_filter_state()
        # Kein automatischer Hover-Refresh beim Aktivieren

    def _stop_all_wheels(self):
        for _role, w in self._role_wheels():
            w.hard_stop()
        if hasattr(self, "map_main"):
            try:
                self.map_main.hard_stop()
            except Exception:
                pass

    def _stop_spin_audio(self) -> None:
        sound = getattr(self, "sound", None)
        if sound is None:
            return
        stop_spin = getattr(sound, "stop_spin", None)
        if callable(stop_spin):
            stop_spin()
        stop_ding = getattr(sound, "stop_ding", None)
        if callable(stop_ding):
            stop_ding()

    def _restore_open_queue_spin_overrides_if_active(self) -> None:
        open_queue = getattr(self, "open_queue", None)
        if open_queue is None:
            return
        spin_active = getattr(open_queue, "spin_active", None)
        if not callable(spin_active) or not spin_active():
            return
        restore = getattr(open_queue, "restore_spin_overrides", None)
        if callable(restore):
            restore()

    def _spin_watchdog_enabled(self) -> bool:
        return bool(self._cfg("SPIN_WATCHDOG_ENABLED", False))

    def _ensure_spin_watchdog_timer(self) -> QtCore.QTimer | None:
        if not self._spin_watchdog_enabled():
            return None
        timer = getattr(self, "_spin_watchdog_timer", None)
        if timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._on_spin_watchdog_timeout)
            self._spin_watchdog_timer = timer
        return timer

    def _arm_spin_watchdog(self, expected_duration_ms: int) -> None:
        timer = self._ensure_spin_watchdog_timer()
        if timer is None:
            return
        try:
            expected = max(1, int(expected_duration_ms))
        except Exception:
            expected = 2500
        try:
            scale = float(self._cfg("SPIN_WATCHDOG_SCALE", 1.8))
        except Exception:
            scale = 1.8
        try:
            slack_ms = int(self._cfg("SPIN_WATCHDOG_SLACK_MS", 2500))
        except Exception:
            slack_ms = 2500
        try:
            min_timeout_ms = int(self._cfg("SPIN_WATCHDOG_MIN_MS", 2500))
        except Exception:
            min_timeout_ms = 2500
        timeout_ms = max(min_timeout_ms, int(expected * max(1.0, scale)) + max(0, slack_ms))
        timer.start(timeout_ms)

    def _disarm_spin_watchdog(self) -> None:
        timer = getattr(self, "_spin_watchdog_timer", None)
        if timer is not None:
            timer.stop()

    def _on_spin_watchdog_timeout(self) -> None:
        if not self._spin_watchdog_enabled():
            return
        if hasattr(self, "_trace_event"):
            self._trace_event("spin_watchdog_timeout", pending=self.pending)
        if self.pending <= 0:
            return
        timer = getattr(self, "_spin_watchdog_timer", None)
        running = False
        stalled: list[tuple[str, object]] = []
        for _role, wheel in self._role_wheels():
            try:
                if wheel.is_anim_running():
                    running = True
                    break
                if bool(getattr(wheel, "_is_spinning", False)) and hasattr(wheel, "_pending_result"):
                    stalled.append((_role, wheel))
            except Exception:
                pass
        if not running and hasattr(self, "map_main"):
            try:
                running = bool(self.map_main.is_anim_running())
            except Exception:
                running = False
        if running:
            if hasattr(self, "_trace_event"):
                self._trace_event("spin_watchdog_rearmed", pending=self.pending)
            if timer is not None:
                timer.start(750)
            return

        if stalled:
            if hasattr(self, "_trace_event"):
                self._trace_event(
                    "spin_watchdog_force_finish",
                    pending=self.pending,
                    roles=[role for role, _wheel in stalled],
                )
            for _role, wheel in stalled:
                try:
                    wheel._emit_result()
                except Exception:
                    pass
            if self.pending > 0 and timer is not None:
                timer.start(750)
            return

        if hasattr(self, "_trace_event"):
            self._trace_event("spin_watchdog_recovery", pending=self.pending)
        self.pending = 0
        self._spin_started_at_monotonic = None
        self._stop_spin_audio()
        self._restore_open_queue_spin_overrides_if_active()
        self._set_controls_enabled(True)
        self._update_cancel_enabled()

    def _mark_spin_started(self) -> None:
        self._spin_started_at_monotonic = time.monotonic()

    def _clear_spin_started(self) -> None:
        self._spin_started_at_monotonic = None

    def _recover_stale_pending_if_idle(self, source: str) -> bool:
        pending_now = int(getattr(self, "pending", 0) or 0)
        if pending_now <= 0:
            return False
        started_at = getattr(self, "_spin_started_at_monotonic", None)
        grace_ms = max(0, int(self._cfg("SPIN_STALE_RECOVERY_GRACE_MS", 250)))
        if started_at is not None:
            try:
                elapsed_ms = int((time.monotonic() - started_at) * 1000.0)
            except Exception:
                elapsed_ms = 0
            if elapsed_ms < grace_ms:
                return False
        busy = self._has_active_spin_animations(include_internal_flags=True)
        if busy:
            return False

        self._trace_event(
            "spin_stale_pending_recovered",
            source=source,
            pending_before=pending_now,
        )
        self.pending = 0
        self._disarm_spin_watchdog()
        self._clear_spin_started()
        self._stop_spin_audio()
        self._restore_open_queue_spin_overrides_if_active()
        self._set_controls_enabled(True)
        self._update_cancel_enabled()
        return True

    def _update_cancel_enabled(self):
        self.btn_cancel_spin.setEnabled(self.pending > 0)

    def spin_all(self):
        """Dreht alle selektierten Räder auf faire Weise."""
        if not self._prepare_spin_request("spin_all"):
            return
        self._trace_event(
            "spin_all_requested",
            mode=self.current_mode,
            pending=getattr(self, "pending", 0),
            open_mode=bool(self.open_queue.is_mode_active()),
            post_init=bool(getattr(self, "_post_choice_init_done", True)),
            restoring=bool(getattr(self, "_restoring_state", False)),
        )
        if self.current_mode == "maps":
            self.map_mode.spin_all()
        elif self.open_queue.is_mode_active():
            spin_service.spin_open_queue(self)
        else:
            spin_service.spin_all(self)

    def _spin_single(self, wheel: WheelView, mult: float = 1.0, hero_ban_override: bool = True):
        if not self._prepare_spin_request("spin_single"):
            return
        role = role_for_wheel(self, wheel) or "unknown"
        self._trace_event(
            "spin_single_requested",
            role=role,
            mode=self.current_mode,
            pending=getattr(self, "pending", 0),
            post_init=bool(getattr(self, "_post_choice_init_done", True)),
            restoring=bool(getattr(self, "_restoring_state", False)),
        )
        if self.current_mode == "maps":
            self.map_mode.spin_single()
        else:
            spin_service.spin_single(self, wheel, mult=mult, hero_ban_override=hero_ban_override)

    def _prepare_spin_request(self, source: str) -> bool:
        self._recover_stale_pending_if_idle(source=source)
        if hasattr(self, "_stop_ocr_background_preload_job"):
            try:
                self._stop_ocr_background_preload_job(reason=f"{source}_request")
            except Exception:
                pass
        if not bool(getattr(self, "_post_choice_init_done", True)):
            # Keep the spin click-path minimal. Deferred startup/UI tasks are
            # scheduled asynchronously and never forced inline here.
            self._trace_event(f"{source}_preinit_fallback")
            schedule = getattr(self, "_schedule_post_choice_init", None)
            if callable(schedule):
                try:
                    schedule(0)
                except Exception:
                    pass
        if bool(getattr(self, "_restoring_state", False)):
            self._trace_event(f"{source}_ignored", reason="state_restore_active")
            return False
        return True

    def _wheel_finished(self, _name: str):
        # Wenn laut State gar kein Spin aktiv ist, ignorieren wir alte/späte Signale,
        # z.B. von hard_stop() oder abgebrochenen Animationen.
        if self.pending <= 0:
            self._trace_event("spin_finish_ignored", result_name=_name, reason="pending_zero")
            return

        pending_before = int(self.pending)
        self.pending -= 1
        self._trace_event(
            "spin_finish_signal",
            result_name=_name,
            pending_before=pending_before,
            pending_after=self.pending,
        )

        # Nur wenn wir von >0 genau auf 0 fallen, ist "dieser" Spin abgeschlossen
        if self.pending == 0:
            self._disarm_spin_watchdog()
            self._clear_spin_started()
            if self._result_sent_this_spin:
                self._stop_spin_audio()
                self._set_controls_enabled(True)
                self._update_cancel_enabled()
                return
            self._result_sent_this_spin = True
            self._stop_spin_audio()
            self.sound.play_ding()

            if self.hero_ban_active:
                d = self.dps.get_result_value() or "–"
                self.summary.setText(i18n.t("summary.hero_ban", pick=d))
                self.overlay.show_message(
                    i18n.t("overlay.hero_ban_title"),
                    [d, "", ""],
                    show_disable_button=True,
                )
                self._last_results_snapshot = None
                self._update_cancel_enabled()
                return
            if self.map_mode.handle_spin_finished():
                return
            else:
                t = self.tank.get_result_value() or "–"
                d = self.dps.get_result_value() or "–"
                s = self.support.get_result_value() or "–"

                self.summary.setText(i18n.t("summary.team", tank=t, dps=d, sup=s))
                self.overlay.show_result(t, d, s)

                # Nur noch EIN Request pro abgeschlossenem Spin
                self.state_sync.send_spin_result(t, d, s)
            self._last_results_snapshot = None
            # Ergebnisse für den aktuellen Modus merken
            self._snapshot_mode_results()
            self._restore_open_queue_spin_overrides_if_active()
        self._update_cancel_enabled()

    def _cancel_spin(self):
        if self.pending <= 0:
            return
        sender = None
        sender_name = None
        sender_text = None
        sender_object = None
        try:
            sender = self.sender()
            sender_name = type(sender).__name__ if sender is not None else None
            sender_text = sender.text() if sender is not None and hasattr(sender, "text") else None
            sender_object = sender.objectName() if sender is not None and hasattr(sender, "objectName") else None
        except Exception:
            sender = None
        bypass_guard = bool(sender_object == "btn_cancel_spin")
        try:
            guard_ms = max(0, int(self._cfg("SPIN_CANCEL_GUARD_MS", 0)))
        except Exception:
            guard_ms = 0
        started_at = self._spin_started_at_monotonic
        if not bypass_guard and guard_ms > 0 and started_at is not None:
            elapsed_ms = int((time.monotonic() - started_at) * 1000.0)
            if elapsed_ms < guard_ms:
                self._trace_event(
                    "spin_cancel_ignored",
                    reason="guard_window",
                    elapsed_ms=elapsed_ms,
                    guard_ms=guard_ms,
                )
                return
        try:
            self._trace_event(
                "spin_cancel_requested",
                pending_before=self.pending,
                sender=sender_name,
                sender_text=sender_text,
                sender_object=sender_object,
            )
        except Exception:
            pass
        self._disarm_spin_watchdog()
        self._clear_spin_started()
        self._result_sent_this_spin = True  # unterdrückt finale Anzeige
        self.pending = 0
        self._stop_spin_audio()
        self._stop_all_wheels()
        # Ergebnisse wiederherstellen, falls Snapshot vorhanden
        self._restore_results_snapshot()
        self._restore_open_queue_spin_overrides_if_active()
        # Hinweis anzeigen, Ergebnisse/Summary beibehalten
        self.overlay.show_message(
            i18n.t("overlay.spin_cancelled_title"),
            [i18n.t("overlay.spin_cancelled_line1"), i18n.t("overlay.spin_cancelled_line2"), ""],
        )
        self._set_controls_enabled(True)
        self._update_cancel_enabled()
