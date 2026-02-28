from __future__ import annotations

import config
import i18n
from PySide6 import QtCore, QtGui, QtWidgets

from .. import mode_manager
from utils import flag_icons, theme as theme_util, ui_helpers
from view import style_helpers

# Fallback für "unbegrenzt" bei Widgetbreiten/Höhen (PySide6 exportiert QWIDGETSIZE_MAX nicht immer)
QWIDGETSIZE_MAX = getattr(QtWidgets, "QWIDGETSIZE_MAX", getattr(QtCore, "QWIDGETSIZE_MAX", 16777215))


class MainWindowAppearanceMixin:
    def _apply_theme(self, defer_heavy: bool = False):
        """Apply the selected light/dark theme without freezing the UI."""
        theme = theme_util.get_theme(getattr(self, "theme", "light"))
        if self._applied_theme_key == theme.key:
            self._theme_heavy_pending = bool(defer_heavy)
            if not defer_heavy and hasattr(self, "btn_theme"):
                self.btn_theme.setEnabled(True)
            return
        theme_util.apply_app_theme(theme)  # einmal zentral, danach in Scheiben

        # Schnelle/kleine Updates sofort
        style_helpers.apply_theme_roles(
            theme,
            (
                (getattr(self, "btn_language", None), "tool.button"),
                (getattr(self, "btn_theme", None), "tool.button"),
                (getattr(self, "title", None), "label.window_title"),
                (getattr(self, "lbl_player_profile", None), "label.section_muted"),
                (getattr(self, "lbl_mode", None), "label.section"),
                (getattr(self, "lbl_anim_duration", None), "label.section"),
                (getattr(self, "lbl_open_count", None), "label.section"),
                (getattr(self, "lbl_open_count_value", None), "label.section"),
                (getattr(self, "summary", None), "label.summary"),
            ),
        )
        self._update_theme_button_label()
        if hasattr(self, "player_profile_dropdown"):
            self.player_profile_dropdown.apply_theme(theme)
        if hasattr(self, "map_ui"):
            # Map UI should switch immediately as well; relying only on the
            # deferred heavy pass can leave stale colors in map mode.
            self.map_ui.apply_theme(theme)
        if getattr(self, "_mode_buttons", None):
            for btn in self._mode_buttons:
                style_helpers.apply_theme_role(btn, theme, "button.mode")
            # Ensure initial checked mode button gets the correct visual state
            # immediately, even before deferred heavy-theme updates run.
            self._update_mode_button_styles(force=True)
        style_helpers.apply_theme_roles(
            theme,
            (
                (getattr(self, "volume_slider", None), "slider.horizontal"),
                (getattr(self, "duration", None), "slider.horizontal"),
                (getattr(self, "open_count_slider", None), "slider.horizontal"),
                (getattr(self, "btn_spin_all", None), "button.primary"),
                (getattr(self, "btn_all_players", None), "button.primary"),
                (getattr(self, "btn_open_q_ocr", None), "button.primary"),
                (getattr(self, "btn_cancel_spin", None), "button.danger"),
            ),
        )
        if hasattr(self, "spin_mode_toggle"):
            self.spin_mode_toggle.apply_theme(theme)
        for btn in self._role_ocr_buttons.values():
            style_helpers.apply_theme_role(btn, theme, "button.primary")
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.apply_theme()
        if hasattr(self, "overlay"):
            tool_style = theme_util.tool_button_stylesheet(theme)
            self.overlay.apply_theme(theme, tool_style)

        self._theme_heavy_pending = bool(defer_heavy)
        self._applied_theme_key = theme.key
        if defer_heavy:
            return
        self._apply_theme_heavy(theme, step_ms=15)

    def _apply_theme_heavy(self, theme: theme_util.Theme, step_ms: int = 15):
        # Größere Widget-Mengen in einem Block aktualisieren, um Timer-Overhead zu sparen.
        del step_ms  # kept in signature for compatibility with existing callers

        targets = []
        for _role, wheel in self._role_wheels():
            if wheel and hasattr(wheel, "apply_theme"):
                targets.append(wheel)

        freeze_targets: list[QtWidgets.QWidget] = []
        for candidate in (
            self.centralWidget(),
            getattr(self, "role_container", None),
            getattr(self, "map_container", None),
        ):
            if isinstance(candidate, QtWidgets.QWidget):
                freeze_targets.append(candidate)
        dedup: list[QtWidgets.QWidget] = []
        seen_ids: set[int] = set()
        for widget in freeze_targets:
            wid = id(widget)
            if wid in seen_ids:
                continue
            seen_ids.add(wid)
            dedup.append(widget)

        for widget in dedup:
            widget.setUpdatesEnabled(False)
        try:
            for wheel in targets:
                wheel.apply_theme(theme)
            if hasattr(self, "map_ui"):
                self.map_ui.apply_theme(theme)
            self._update_mode_button_styles(force=True)
        finally:
            for widget in dedup:
                widget.setUpdatesEnabled(True)
                widget.update()

        # Theme-Button wieder freigeben, falls er kurz deaktiviert wurde.
        if hasattr(self, "btn_theme"):
            self.btn_theme.setEnabled(True)

    def _update_mode_button_styles(self, *_args, force: bool = False):
        """
        Polisht nur Buttons, deren checked-Zustand sich geändert hat, um
        unnötige Reflows bei Theme-/UI-Updates zu vermeiden.
        """
        if not getattr(self, "_mode_buttons", None):
            return
        checked_cache = getattr(self, "_mode_button_checked_cache", {})
        for btn in self._mode_buttons:
            checked = bool(btn.isChecked())
            cache_key = id(btn)
            if not force and checked_cache.get(cache_key) == checked:
                continue
            style = btn.style()
            if style is not None:
                style.unpolish(btn)
                style.polish(btn)
            btn.updateGeometry()
            checked_cache[cache_key] = checked
        self._mode_button_checked_cache = checked_cache

    def _capture_role_base_widths(self):
        """Merkt sich die aktuelle Breite jeder Rollen-Karte als Referenz."""
        widths: dict[str, int] = {}
        for name, widget in self._role_wheels():
            w = widget.width() or widget.sizeHint().width()
            widths[name] = max(1, int(w))
        self._role_base_widths = widths

    def _apply_role_width_lock(self, lock: bool):
        """
        Begrenze/entgrenze die Rollenbreiten – in Hero-Ban sperren wir auf die
        gemerkte Basisbreite, damit z.B. Tank nicht breiter wird.
        """
        if not self._role_base_widths:
            self._capture_role_base_widths()
        for name, widget in self._role_wheels():
            base = self._role_base_widths.get(name, widget.sizeHint().width() or widget.width())
            if lock:
                fixed = max(1, int(base))
                widget.setMinimumWidth(fixed)
                widget.setMaximumWidth(fixed)
            else:
                widget.setMinimumWidth(0)
                widget.setMaximumWidth(QWIDGETSIZE_MAX)

    def resizeEvent(self, e: QtGui.QResizeEvent):
        super().resizeEvent(e)
        if self.overlay and self.centralWidget():
            self.overlay.setGeometry(self.centralWidget().rect())
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.on_resize()

    def _set_hero_ban_visuals(self, active: bool):
        """Delegiert an den Mode-Manager und sperrt Breiten in Hero-Ban."""
        self._apply_role_width_lock(active)
        mode_manager.set_hero_ban_visuals(self, active)

    def _update_title(self):
        if self.current_mode == "maps":
            text = i18n.t("app.title.map")
        else:
            text = i18n.t("app.title.main")
        self.title.setText(text)
        self.setWindowTitle(text)

    def _switch_language(self, lang: str):
        lang = lang if lang in i18n.SUPPORTED_LANGS else "de"
        if lang == getattr(self, "language", "de"):
            return
        self._trace_event("switch_language", lang=lang)
        self.language = lang
        self._apply_language()
        # Nach Sprachwechsel Label-Messungen aktualisieren, damit Tooltips weiter funktionieren
        self._set_tooltips_ready(False)
        self._refresh_tooltip_caches_async()
        # Falls das Online/Offline-Overlay offen ist, Aktivierung sicherstellen
        last_view = getattr(self.overlay, "_last_view", {}) or {}
        if last_view.get("type") == "online_choice":
            self.overlay.set_choice_enabled(True)
        if not getattr(self, "_restoring_state", False):
            self.state_sync.save_state()

    def _toggle_language(self):
        """Toggle between German and English via the single flag button."""
        next_lang = "en" if self.language == "de" else "de"
        self._switch_language(next_lang)

    def _toggle_theme(self):
        """Switch between light and dark mode."""
        if hasattr(self, "btn_theme"):
            self.btn_theme.setEnabled(False)
        self.theme = "dark" if getattr(self, "theme", "light") == "light" else "light"
        self._apply_theme()
        if not getattr(self, "_restoring_state", False):
            self.state_sync.save_state()

    def _update_theme_button_label(self):
        """Update text/tooltip of the theme toggle."""
        if not hasattr(self, "btn_theme"):
            return
        is_dark = getattr(self, "theme", "light") == "dark"
        self.btn_theme.setText("☀️" if is_dark else "🌙")
        tooltip = i18n.t("theme.toggle.to_light") if is_dark else i18n.t("theme.toggle.to_dark")
        self.btn_theme.setToolTip(tooltip)

    def _apply_language(self, defer_heavy: bool = False):
        i18n.set_language(self.language)
        if hasattr(self, "btn_language"):
            self.btn_language.setIcon(flag_icons.icon_for_language(self.language))
            self.btn_language.setText("")  # avoid emoji fallback on Windows
            tooltip = i18n.t("language.tooltip.de") if self.language == "de" else i18n.t("language.tooltip.en")
            self.btn_language.setToolTip(tooltip)
        if hasattr(self, "lbl_player_profile"):
            self.lbl_player_profile.setText(i18n.t("players.profile_label"))
        if hasattr(self, "player_profile_dropdown"):
            self._refresh_player_profile_combo()
        self.lbl_mode.setText(i18n.t("label.mode"))
        self.lbl_mode.setToolTip(i18n.t("label.mode_tooltip"))
        self.btn_mode_players.setText(i18n.t("mode.players"))
        self.btn_mode_players.setToolTip(i18n.t("mode.players_tooltip"))
        self.btn_mode_heroes.setText(i18n.t("mode.heroes"))
        self.btn_mode_heroes.setToolTip(i18n.t("mode.heroes_tooltip"))
        self.btn_mode_heroban.setText(i18n.t("mode.hero_ban"))
        self.btn_mode_heroban.setToolTip(i18n.t("mode.hero_ban_tooltip"))
        if getattr(self, "_map_button_loading", False):
            self.btn_mode_maps.setText(i18n.t("mode.maps_loading"))
        else:
            self.btn_mode_maps.setText(i18n.t("mode.maps"))
        self.btn_mode_maps.setToolTip(i18n.t("mode.maps_tooltip"))
        self.lbl_volume_icon.setToolTip(i18n.t("volume.icon_tooltip"))
        self.volume_slider.setToolTip(i18n.t("volume.slider_tooltip"))
        self.btn_spin_all.setText(i18n.t("controls.spin_all"))
        self.btn_spin_all.setToolTip(i18n.t("controls.spin_all_tooltip"))
        if hasattr(self, "spin_mode_toggle"):
            self.spin_mode_toggle.setToolTip(i18n.t("controls.spin_mode_tooltip"))
        self.btn_cancel_spin.setText(i18n.t("controls.cancel_spin"))
        self.btn_cancel_spin.setToolTip(i18n.t("controls.cancel_spin_tooltip"))
        self.lbl_anim_duration.setText(i18n.t("controls.anim_duration"))
        self.duration.setToolTip(i18n.t("controls.anim_duration_tooltip"))
        if hasattr(self, "lbl_open_count"):
            self.lbl_open_count.setText(i18n.t("controls.open_count_label"))
            self.lbl_open_count.setToolTip(i18n.t("controls.open_count_tooltip"))
        if hasattr(self, "open_count_slider"):
            self.open_count_slider.setToolTip(i18n.t("controls.open_count_tooltip"))
        if hasattr(self, "lbl_open_count_value"):
            self.lbl_open_count_value.setToolTip(i18n.t("controls.open_count_tooltip"))
        if hasattr(self, "btn_all_players"):
            self.btn_all_players.setText(i18n.t("players.list_button"))
            self.btn_all_players.setToolTip(i18n.t("players.list_button_tooltip"))
            ui_helpers.set_fixed_width_from_translations([self.btn_all_players], ["players.list_button"], padding=40)
        if hasattr(self, "btn_open_q_ocr"):
            self.btn_open_q_ocr.setText(i18n.t("ocr.open_q_button"))
            self.btn_open_q_ocr.setToolTip(i18n.t("ocr.open_q_button_tooltip"))
            ui_helpers.set_fixed_width_from_translations([self.btn_open_q_ocr], ["ocr.open_q_button"], padding=40)
        self._refresh_all_role_ocr_button_texts()
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.set_language(self.language)
        self._update_title()
        if hasattr(self, "overlay"):
            self.overlay.set_language(self.language)
            # Flag auf dem Overlay aktualisieren
            self.overlay._apply_flag()
        self._update_theme_button_label()
        self._update_spin_mode_ui()
        self._update_summary_from_results()

        self._language_heavy_pending = bool(defer_heavy)
        if defer_heavy:
            return
        self._apply_language_heavy()

    def _apply_language_heavy(self):
        for _role, w in self._role_wheels():
            w.set_language(self.language)
        if hasattr(self, "map_mode"):
            self.map_mode.retranslate_ui()

    def _update_hero_ban_wheel(self):
        """Delegiert an den Mode-Manager."""
        mode_manager.update_hero_ban_wheel(self)

    def _on_role_include_toggled(self, _checked: bool):
        if self.hero_ban_active:
            # Zurück in den normalen Zusammenführungsmodus
            self._hero_ban_override_role = None
            self._update_hero_ban_wheel()

    def _on_wheel_state_changed(self):
        """Reagiert auf Änderungen in den Rädern (z.B. Namensliste) im Hero-Ban-Modus."""
        if not self.hero_ban_active:
            return
        if self._hero_ban_rebuild:
            # Signal kam während eines Rebuilds → später nachholen
            self._hero_ban_pending = True
            return
        self._hero_ban_override_role = None
        self._update_hero_ban_wheel()

    def _set_heavy_ui_updates_enabled(self, enabled: bool) -> None:
        """Defer expensive wheel painting while the mode-choice overlay is visible."""
        self._trace_event("set_heavy_ui_updates", enabled=enabled)
        wheels_to_update = [wheel for _role, wheel in self._role_wheels()]
        wheels_to_update.append(getattr(self, "map_main", None))
        for w in wheels_to_update:
            if not w:
                continue
            try:
                w.setUpdatesEnabled(enabled)
            except Exception:
                pass
            view = getattr(w, "view", None)
            if view:
                try:
                    view.setUpdatesEnabled(enabled)
                except Exception:
                    pass
