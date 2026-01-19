from __future__ import annotations

import random

import i18n


class MapModeController:
    """Map-mode helpers to keep MainWindow slim and consistent."""

    def __init__(self, main_window) -> None:
        self._mw = main_window

    def rebuild_wheel(self) -> None:
        if self._mw.current_mode != "maps":
            return
        if hasattr(self._mw, "map_ui"):
            self._mw.map_ui.rebuild_combined()
        self._mw._update_spin_all_enabled()

    def load_state(self) -> None:
        if hasattr(self._mw, "map_ui"):
            self._mw.map_ui.load_state()
            self.rebuild_wheel()

    def capture_state(self) -> None:
        if hasattr(self._mw, "map_ui"):
            self._mw.map_ui.capture_state()

    def activate_mode(self) -> None:
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
        self.load_state()
        self._mw._update_title()
        self._mw._apply_mode_results(self._mw._mode_key())
        self._mw._update_spin_all_enabled()

    def retranslate_ui(self) -> None:
        if hasattr(self._mw, "map_ui"):
            self._mw.map_ui.set_language(self._mw.language)

    def spin_all(self, subset: list[str] | None = None) -> None:
        mw = self._mw
        if mw.pending > 0:
            return
        # Neuer Spin → finale Anzeige wieder erlauben
        mw._result_sent_this_spin = False
        combined = mw.map_ui.combined_names() if hasattr(mw, "map_ui") else []
        candidates = list(subset) if subset is not None else list(combined)
        if not candidates:
            mw.summary.setText(i18n.t("map.summary.prompt"))
            return
        mw._snapshot_results()
        mw.sound.stop_ding()
        mw._stop_all_wheels()
        mw._set_controls_enabled(False)
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
        else:
            mw.sound.stop_spin()
            mw._set_controls_enabled(True)
            mw.summary.setText(i18n.t("map.summary.prompt"))
        mw._update_cancel_enabled()

    def spin_single(self) -> None:
        # lokaler Spin im Map-Mode entspricht globalem Spin (nur ein Rad)
        self.spin_all()

    def spin_category(self, category: str) -> None:
        names = []
        if hasattr(self._mw, "map_ui"):
            names = self._mw.map_ui.names_for_category(category)
        self.spin_all(subset=names)
