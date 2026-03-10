from __future__ import annotations

import random

import i18n


def _set_controls_enabled(mw, enabled: bool, *, spin_mode: bool = False) -> None:
    setter = getattr(mw, "_set_controls_enabled", None)
    if not callable(setter):
        return
    if spin_mode:
        try:
            setter(bool(enabled), spin_mode=True)
            return
        except TypeError:
            pass
    setter(bool(enabled))


class MapModeController:
    """Map-mode helpers to keep MainWindow slim and consistent."""

    def __init__(self, main_window) -> None:
        self._mw = main_window

    def rebuild_wheel(self) -> None:
        if self._mw.current_mode != "maps":
            return
        if hasattr(self._mw, "map_ui"):
            self._mw.map_ui.rebuild_combined(emit_state=False, force_wheel=True)
        self._mw._update_spin_all_enabled()

    def load_state(self) -> None:
        if hasattr(self._mw, "map_ui"):
            self._mw.map_ui.load_state()
        self._mw._update_spin_all_enabled()

    def capture_state(self) -> None:
        if hasattr(self._mw, "map_ui"):
            self._mw.map_ui.capture_state()

    def activate_mode(self) -> None:
        if hasattr(self._mw, "_ensure_map_ui"):
            self._mw._ensure_map_ui()
        if hasattr(self._mw, "mode_stack"):
            self._mw.mode_stack.setCurrentIndex(1)
        self._mw.hero_ban_active = False
        self._mw.dps.set_override_entries(None)
        self._mw.current_mode = "maps"
        if hasattr(self._mw, "player_list_panel"):
            self._mw.player_list_panel.hide_panel()
        self._mw.btn_mode_players.setChecked(False)
        self._mw.btn_mode_heroes.setChecked(False)
        self._mw.btn_mode_heroban.setChecked(False)
        self._mw.btn_mode_maps.setChecked(True)
        if hasattr(self._mw, "map_ui"):
            self._mw.map_ui.set_active(True)
        self.load_state()
        if not bool(getattr(self._mw, "_cfg", lambda _k, default=None: default)("TOOLTIP_CACHE_ON_START", True)):
            if hasattr(self._mw, "_refresh_tooltip_caches_async"):
                self._mw._refresh_tooltip_caches_async()
        self._mw._update_title()
        self._mw._apply_mode_results(self._mw._mode_key())
        self._mw._update_spin_all_enabled()

    def retranslate_ui(self) -> None:
        if hasattr(self._mw, "map_ui"):
            self._mw.map_ui.set_language(self._mw.language)

    def spin_all(self, subset: list[str] | None = None) -> None:
        mw = self._mw
        if hasattr(mw, "_trace_event"):
            try:
                mw._trace_event(
                    "map_spin_requested",
                    pending=mw.pending,
                    subset_count=0 if subset is None else len(subset),
                )
            except Exception:
                pass
        if mw.pending > 0:
            return
        if hasattr(mw, "_disarm_spin_watchdog"):
            mw._disarm_spin_watchdog()
        # Neuer Spin → finale Anzeige wieder erlauben
        mw._result_sent_this_spin = False
        combined = mw.map_ui.combined_names() if hasattr(mw, "map_ui") else []
        candidates = list(subset) if subset is not None else list(combined)
        if not candidates:
            mw.summary.setText(i18n.t("map.summary.prompt"))
            return
        mw._snapshot_results()
        mw.sound.stop_spin()
        mw.sound.stop_ding()
        mw._stop_all_wheels()
        if hasattr(mw, "_set_heavy_ui_updates_enabled"):
            try:
                mw._set_heavy_ui_updates_enabled(True)
            except Exception:
                pass
        _set_controls_enabled(mw, False, spin_mode=True)
        mw.summary.setText("")
        mw.pending = 0
        mw.overlay.hide()
        mw.sound.play_spin()
        duration = int(mw.duration.value())
        mw._pending_map_choice = None
        if hasattr(mw, "map_main"):
            # Wähle Zielname gezielt, falls möglich
            # Temporär override, falls subset vorgegeben
            if subset is not None:
                override_entries = [{"name": n, "subroles": [], "active": True} for n in candidates]
                mw.map_main.set_override_entries(override_entries)
                mw._map_temp_override = True
            else:
                mw._map_temp_override = False
            candidates = mw.map_main.get_effective_wheel_names(include_disabled=False)
            if candidates:
                choice = random.choice(candidates)
                mw._pending_map_choice = choice
                ok = mw.map_main.spin_to_name(choice, duration_ms=duration)
            else:
                ok = mw.map_main.spin(duration_ms=duration)
        else:
            ok = False
        if ok:
            mw.pending = 1
            if hasattr(mw, "_arm_spin_watchdog"):
                mw._arm_spin_watchdog(duration)
            if hasattr(mw, "_trace_event"):
                try:
                    mw._trace_event("map_spin_started", pending=mw.pending, duration_ms=duration)
                except Exception:
                    pass
        else:
            mw.sound.stop_spin()
            _set_controls_enabled(mw, True)
            if getattr(mw, "_map_temp_override", False):
                self.rebuild_wheel()
                mw._map_temp_override = False
            mw.summary.setText(i18n.t("map.summary.prompt"))
            if hasattr(mw, "_trace_event"):
                try:
                    mw._trace_event("map_spin_failed", pending=mw.pending, duration_ms=duration)
                except Exception:
                    pass
        mw._update_cancel_enabled()

    def spin_single(self) -> None:
        # lokaler Spin im Map-Mode entspricht globalem Spin (nur ein Rad)
        self.spin_all()

    def spin_category(self, category: str) -> None:
        names = []
        if hasattr(self._mw, "map_ui"):
            names = self._mw.map_ui.names_for_category(category)
        self.spin_all(subset=names)

    def handle_spin_finished(self) -> bool:
        """Handle end-of-spin UI updates for map mode."""
        mw = self._mw
        if mw.current_mode != "maps":
            return False
        choice = getattr(mw, "_pending_map_choice", None) or getattr(mw, "_map_result_text", "–")
        mw._map_result_text = choice
        mw._update_summary_from_results()
        mw.overlay.show_message(
            i18n.t("overlay.map_title"),
            [choice, "", ""],
            show_disable_button=True,
        )
        mw._last_results_snapshot = None
        mw._snapshot_mode_results()
        if getattr(mw, "_map_temp_override", False):
            self.rebuild_wheel()
            mw._map_temp_override = False
        _set_controls_enabled(mw, True)
        mw._update_cancel_enabled()
        return True
