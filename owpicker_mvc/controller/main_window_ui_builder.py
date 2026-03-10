from __future__ import annotations

from typing import Any

import i18n
from PySide6 import QtCore, QtWidgets

from model.mode_keys import AppMode
from model.role_keys import role_wheel_map
from utils import theme as theme_util, ui_helpers
from view.adaptive_summary_label import AdaptiveSummaryLabel
from view.overlay import ResultOverlay
from view.profile_dropdown import PlayerProfileDropdown
from view.spin_mode_toggle import SpinModeToggle
from view.wheel_view import WheelView
from view import style_helpers, ui_tokens

from .map_mode import MapModeController
from .open_queue import OpenQueueController
from .player_list_panel import PlayerListPanelController
from .role_mode import RoleModeController


class MainWindowUIBuilderMixin:
    def _build_root(self) -> tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(
            ui_tokens.ROOT_MARGIN_H,
            ui_tokens.ROOT_MARGIN_TOP,
            ui_tokens.ROOT_MARGIN_H,
            ui_tokens.ROOT_MARGIN_BOTTOM,
        )
        root.setSpacing(ui_tokens.ROOT_SPACING)
        return central, root

    def _build_header(self, root: QtWidgets.QVBoxLayout, saved: dict) -> None:
        current_theme = theme_util.get_theme(getattr(self, "theme", "light"))
        self.title = QtWidgets.QLabel("")
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        style_helpers.apply_theme_roles(current_theme, ((self.title, "label.window_title"),))

        # Lautstärke-Regler oben rechts
        vol_row = QtWidgets.QHBoxLayout()
        vol_row.setContentsMargins(0, 0, 0, 2)
        vol_row.setSpacing(ui_tokens.SECTION_SPACING)
        vol_row.addStretch(1)
        spacer_for_balance = QtWidgets.QSpacerItem(160, 0, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
        vol_row.addItem(spacer_for_balance)
        vol_row.addWidget(self.title, 0, QtCore.Qt.AlignCenter)
        vol_row.addStretch(1)
        self.lbl_volume_icon = QtWidgets.QToolButton()
        self.lbl_volume_icon.setText("🔊")
        self.lbl_volume_icon.setCursor(QtCore.Qt.PointingHandCursor)
        self.lbl_volume_icon.setToolTip(i18n.t("volume.icon_tooltip"))
        self.lbl_volume_icon.setStyleSheet("font-size:18px; padding:0 4px; background:transparent; border:none;")
        self.lbl_volume_icon.clicked.connect(self._on_volume_icon_clicked)
        self.volume_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.setFixedHeight(ui_tokens.BUTTON_HEIGHT_SM)
        self.volume_slider.setToolTip(i18n.t("volume.slider_tooltip"))
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.sliderReleased.connect(self._play_volume_preview)
        self.volume_slider.sliderPressed.connect(self._play_volume_preview)
        self.btn_language = QtWidgets.QToolButton()
        self.btn_language.setAutoRaise(True)
        self.btn_language.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_language.setFixedSize(40, 32)
        self.btn_language.setIconSize(QtCore.QSize(28, 20))
        self.btn_language.clicked.connect(self._toggle_language)
        self.btn_theme = QtWidgets.QToolButton()
        self.btn_theme.setAutoRaise(True)
        self.btn_theme.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_theme.setFixedSize(40, 32)
        self.btn_theme.setIconSize(QtCore.QSize(24, 24))
        self.btn_theme.clicked.connect(self._toggle_theme)
        style_helpers.apply_theme_roles(
            current_theme,
            (
                (self.btn_language, "tool.button"),
                (self.btn_theme, "tool.button"),
            ),
        )
        vol_row.addWidget(self.lbl_volume_icon, 0, QtCore.Qt.AlignVCenter)
        vol_row.addWidget(self.volume_slider, 0, QtCore.Qt.AlignVCenter)
        vol_row.addSpacing(6)
        vol_row.addWidget(self.btn_language, 0, QtCore.Qt.AlignVCenter)
        vol_row.addSpacing(4)
        vol_row.addWidget(self.btn_theme, 0, QtCore.Qt.AlignVCenter)
        vol_row.addStretch(0)
        root.addLayout(vol_row)
        saved_volume = saved.get("volume", 100)
        try:
            self.volume_slider.setValue(int(saved_volume))
        except Exception:
            pass
        self._on_volume_changed(self.volume_slider.value())
        self._last_volume_before_mute = self.volume_slider.value()

    def _build_mode_switcher(self, root: QtWidgets.QVBoxLayout) -> None:
        # Modus-Schalter (Spieler / Helden / Hero-Ban / Maps)
        self.btn_mode_players = QtWidgets.QPushButton(i18n.t("mode.players"))
        self.btn_mode_players.setCheckable(True)
        self.btn_mode_players.setToolTip(i18n.t("mode.players_tooltip"))
        self.btn_mode_heroes = QtWidgets.QPushButton(i18n.t("mode.heroes"))
        self.btn_mode_heroes.setCheckable(True)
        self.btn_mode_heroes.setToolTip(i18n.t("mode.heroes_tooltip"))
        self.btn_mode_heroban = QtWidgets.QPushButton(i18n.t("mode.hero_ban"))
        self.btn_mode_heroban.setCheckable(True)
        self.btn_mode_heroban.setToolTip(i18n.t("mode.hero_ban_tooltip"))
        self.btn_mode_maps = QtWidgets.QPushButton(i18n.t("mode.maps"))
        self.btn_mode_maps.setCheckable(True)
        self.btn_mode_maps.setToolTip(i18n.t("mode.maps_tooltip"))
        # Fixe Breiten, damit Sprache die Buttons nicht springen lässt
        ui_helpers.set_fixed_width_from_translations(
            [
                self.btn_mode_players,
                self.btn_mode_heroes,
                self.btn_mode_heroban,
                self.btn_mode_maps,
            ],
            ["mode.players", "mode.heroes", "mode.hero_ban", "mode.maps", "mode.maps_loading"],
            padding=34,
        )
        self._mode_buttons = [
            self.btn_mode_players,
            self.btn_mode_heroes,
            self.btn_mode_heroban,
            self.btn_mode_maps,
        ]
        for btn in self._mode_buttons:
            btn.setProperty("modeButton", True)
            btn.setFixedHeight(ui_tokens.BUTTON_HEIGHT_MODE)
            btn.toggled.connect(self._update_mode_button_styles)
        self.btn_mode_players.clicked.connect(lambda: self._on_mode_button_clicked("players"))
        self.btn_mode_heroes.clicked.connect(lambda: self._on_mode_button_clicked("heroes"))
        self.btn_mode_heroban.clicked.connect(lambda: self._on_mode_button_clicked("hero_ban"))
        self.btn_mode_maps.clicked.connect(lambda: self._on_mode_button_clicked("maps"))
        mode_group = QtWidgets.QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self.btn_mode_players)
        mode_group.addButton(self.btn_mode_heroes)
        mode_group.addButton(self.btn_mode_heroban)
        mode_group.addButton(self.btn_mode_maps)
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.setContentsMargins(0, 2, 0, 4)
        mode_row.setSpacing(ui_tokens.SECTION_SPACING)
        self.lbl_player_profile = QtWidgets.QLabel(i18n.t("players.profile_label"))
        self.player_profile_dropdown = PlayerProfileDropdown()
        self.player_profile_dropdown.setMinimumWidth(158)
        self.player_profile_dropdown.setFixedHeight(ui_tokens.INPUT_HEIGHT_MD)
        self.player_profile_dropdown.profileActivated.connect(self._on_player_profile_changed)
        self.player_profile_dropdown.profileRenamed.connect(self._on_player_profile_name_edited)
        self.player_profile_dropdown.orderChanged.connect(self._on_player_profile_reordered)
        self._refresh_player_profile_combo()
        mode_row.addWidget(self.lbl_player_profile)
        mode_row.addWidget(self.player_profile_dropdown)
        mode_row.addSpacing(10)
        mode_row.addStretch(1)
        self.lbl_mode = QtWidgets.QLabel(i18n.t("label.mode"))
        self.lbl_mode.setToolTip(i18n.t("label.mode_tooltip"))
        mode_row.addWidget(self.lbl_mode)
        mode_row.addWidget(self.btn_mode_players)
        mode_row.addWidget(self.btn_mode_heroes)
        mode_row.addWidget(self.btn_mode_heroban)
        mode_row.addWidget(self.btn_mode_maps)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

    def _capture_players_state_for_profiles(self) -> None:
        if getattr(self, "current_mode", "") != "players":
            return
        if getattr(self, "hero_ban_active", False):
            return
        self._state_store.capture_mode_from_wheels(
            "players",
            role_wheel_map(self),
            hero_ban_active=False,
        )

    def _refresh_player_profile_combo(self) -> None:
        if not hasattr(self, "player_profile_dropdown"):
            return
        names = self._state_store.get_player_profile_names()
        idx = self._state_store.get_active_player_profile_index()
        self._player_profile_combo_syncing = True
        try:
            self.player_profile_dropdown.set_profiles(names, idx)
            self.player_profile_dropdown.set_dropdown_tooltip(i18n.t("players.profile_tooltip"))
        finally:
            self._player_profile_combo_syncing = False

    def _on_player_profile_changed(self, index: int) -> None:
        if self._player_profile_combo_syncing:
            return
        if index < 0:
            return
        self._capture_players_state_for_profiles()
        changed = self._state_store.set_active_player_profile(index)
        if not changed:
            return
        if getattr(self, "current_mode", "") == "players" and not getattr(self, "hero_ban_active", False):
            self._load_mode_into_wheels("players", hero_ban=False)
        self._refresh_player_profile_combo()
        if not getattr(self, "_restoring_state", False):
            self.state_sync.save_state(sync=False)

    def _on_player_profile_name_edited(self, index: int | None = None, name: str | None = None) -> None:
        if self._player_profile_combo_syncing:
            return
        if not hasattr(self, "player_profile_dropdown"):
            return
        idx = int(index) if isinstance(index, int) else self.player_profile_dropdown.current_profile_index()
        if idx < 0:
            return
        label = name if isinstance(name, str) else self.player_profile_dropdown.current_profile_name()
        changed = self._state_store.rename_player_profile(idx, label)
        self._refresh_player_profile_combo()
        if changed and not getattr(self, "_restoring_state", False):
            self.state_sync.save_state(sync=False)

    def _on_player_profile_reordered(self, order: list[int] | None = None) -> None:
        if self._player_profile_combo_syncing:
            return
        if not hasattr(self, "player_profile_dropdown"):
            return
        resolved = list(order) if isinstance(order, list) else self.player_profile_dropdown.current_order()
        if not resolved:
            return
        changed = self._state_store.reorder_player_profiles(resolved)
        if not changed:
            return
        self._refresh_player_profile_combo()
        if not getattr(self, "_restoring_state", False):
            self.state_sync.save_state(sync=False, immediate=True)

    def _build_role_container(self) -> QtWidgets.QWidget:
        # ----- Rolle/Grid-Container (Players/Heroes/Hero-Ban) -----
        role_container = QtWidgets.QWidget()
        self.role_container = role_container
        grid = QtWidgets.QGridLayout(role_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(ui_tokens.GRID_SPACING)
        # Alle drei Spalten gleichmäßig strecken, damit die Breiten beim Moduswechsel stabil bleiben
        for col in range(3):
            grid.setColumnStretch(col, 1)

        # Startzustand pro Rolle (Spieler-Modus)
        active_states = self._state_store.get_mode_state(self.current_mode)
        tank_state = active_states["Tank"]
        dps_state = active_states["Damage"]
        support_state = active_states["Support"]

        self.tank = WheelView(
            "Tank",
            tank_state.get("entries", []),
            pair_mode=tank_state.get("pair_mode", False),
            allow_pair_toggle=True,
            subrole_labels=["MT", "OT"],
        )
        self.btn_tank_ocr_import = QtWidgets.QPushButton(i18n.t("ocr.tank_button"))
        self.btn_tank_ocr_import.setFixedHeight(ui_tokens.BUTTON_HEIGHT_MD)
        self.btn_tank_ocr_import.clicked.connect(
            lambda _checked=False: self._on_role_ocr_import_clicked("tank")
        )
        self.tank.set_wheel_overlay_widget(
            self.btn_tank_ocr_import,
            margin_top=0,
            margin_right=8,
        )
        self._register_role_ocr_button("tank", self.btn_tank_ocr_import)
        self.dps = WheelView(
            "Damage",
            dps_state.get("entries", []),
            pair_mode=dps_state.get("pair_mode", True),
            allow_pair_toggle=True,
            subrole_labels=["HS", "FDPS"],
        )
        self.btn_dps_ocr_import = QtWidgets.QPushButton(i18n.t("ocr.dps_button"))
        self.btn_dps_ocr_import.setFixedHeight(ui_tokens.BUTTON_HEIGHT_MD)
        self.btn_dps_ocr_import.clicked.connect(
            lambda _checked=False: self._on_role_ocr_import_clicked("dps")
        )
        self.dps.set_wheel_overlay_widget(
            self.btn_dps_ocr_import,
            margin_top=0,
            margin_right=8,
        )
        self._register_role_ocr_button("dps", self.btn_dps_ocr_import)
        self.support = WheelView(
            "Support",
            support_state.get("entries", []),
            pair_mode=support_state.get("pair_mode", True),
            allow_pair_toggle=True,
            subrole_labels=["MS", "FS"],
        )
        self.btn_support_ocr_import = QtWidgets.QPushButton(i18n.t("ocr.support_button"))
        self.btn_support_ocr_import.setFixedHeight(ui_tokens.BUTTON_HEIGHT_MD)
        self.btn_support_ocr_import.clicked.connect(
            lambda _checked=False: self._on_role_ocr_import_clicked("support")
        )
        self.support.set_wheel_overlay_widget(
            self.btn_support_ocr_import,
            margin_top=0,
            margin_right=8,
        )
        self._register_role_ocr_button("support", self.btn_support_ocr_import)
        for panel in (self.tank.names_panel, self.dps.names_panel, self.support.names_panel):
            panel.set_delete_confirm_handler(
                lambda count, _panel=panel: self._request_delete_names_confirm(_panel, count)
            )
        self.role_mode = RoleModeController(self)

        grid.addWidget(self.tank, 0, 0)
        grid.addWidget(self.dps, 0, 1)
        grid.addWidget(self.support, 0, 2)
        self.btn_all_players = QtWidgets.QPushButton(i18n.t("players.list_button"))
        ui_helpers.set_fixed_width_from_translations([self.btn_all_players], ["players.list_button"], padding=40)
        self.btn_all_players.setFixedHeight(ui_tokens.BUTTON_HEIGHT_MD)
        self.btn_all_players.setToolTip(i18n.t("players.list_button_tooltip"))
        self.player_list_panel = PlayerListPanelController(self, self.btn_all_players)
        self.btn_all_players.clicked.connect(self.player_list_panel.toggle_panel)
        self.btn_open_q_ocr = QtWidgets.QPushButton(i18n.t("ocr.open_q_button"))
        ui_helpers.set_fixed_width_from_translations([self.btn_open_q_ocr], ["ocr.open_q_button"], padding=40)
        self.btn_open_q_ocr.setFixedHeight(ui_tokens.BUTTON_HEIGHT_MD)
        self.btn_open_q_ocr.setToolTip(i18n.t("ocr.open_q_button_tooltip"))
        self.btn_open_q_ocr.clicked.connect(self._on_open_q_ocr_clicked)
        self._role_status_row = QtWidgets.QWidget()
        role_status_layout = QtWidgets.QHBoxLayout(self._role_status_row)
        role_status_layout.setContentsMargins(0, 0, 0, 0)
        role_status_layout.setSpacing(ui_tokens.SECTION_SPACING)
        role_status_layout.addWidget(self.btn_all_players, 0, QtCore.Qt.AlignVCenter)
        role_status_layout.addWidget(self.btn_open_q_ocr, 0, QtCore.Qt.AlignVCenter)
        role_status_layout.addSpacing(max(6, int(ui_tokens.SECTION_SPACING // 2)))
        self._role_summary_host = QtWidgets.QWidget()
        self._role_summary_host.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self._role_summary_host_layout = QtWidgets.QHBoxLayout(self._role_summary_host)
        self._role_summary_host_layout.setContentsMargins(0, 0, 0, 0)
        self._role_summary_host_layout.setSpacing(0)
        self._role_summary_host_layout.addStretch(1)
        role_status_layout.addWidget(self._role_summary_host, 1)
        grid.addWidget(self._role_status_row, 1, 0, 1, 3)
        self._update_role_ocr_buttons_enabled()
        # Basisbreiten nach dem ersten Layout ermitteln
        QtCore.QTimer.singleShot(0, self._capture_role_base_widths)
        return role_container

    def _build_map_container(self) -> None:
        # ----- Map-Mode-Container -----
        self._map_result_text = "–"
        self._map_initialized = False
        self.map_mode = MapModeController(self)
        self.map_container = QtWidgets.QWidget()
        self.map_container.setFocusPolicy(QtCore.Qt.NoFocus)
        self._map_container_layout = QtWidgets.QVBoxLayout(self.map_container)
        self._map_container_layout.setContentsMargins(0, 0, 0, 0)
        self._map_container_layout.setSpacing(0)

    def _ensure_map_ui(self) -> None:
        """Build map UI lazily to keep startup fast."""
        self._trace_event("ensure_map_ui:start", map_initialized=getattr(self, "_map_initialized", False))
        if getattr(self, "_map_initialized", False):
            return
        from controller.map import MapUI

        self._map_init_in_progress = True
        try:
            self._map_lists_ready = False
            self.map_ui = MapUI(
                self._state_store,
                self.language,
                self.theme,
                tuple(wheel for _role, wheel in self._role_wheels()),
                defer_lists=True,
                settings=self.settings,
            )
            self.map_ui.listsBuilt.connect(self._on_map_lists_ready)
            self._map_container_layout.addWidget(self.map_ui.container)
            self.map_ui.stateChanged.connect(self._update_spin_all_enabled)
            self.map_ui.stateChanged.connect(self.state_sync.save_state)
            self.map_ui.requestSpinCategory.connect(self.map_mode.spin_category)
            # Kompatibilitäts-Aliase, damit bestehende Logik funktioniert
            self.map_main = self.map_ui.map_main
            self.map_lists = self.map_ui.map_lists
            if not getattr(self, "_map_spin_connected", False):
                try:
                    self.map_main.spun.connect(self._wheel_finished)
                    self._map_spin_connected = True
                except Exception:
                    pass
            self.map_ui.set_language(self.language)
            self.map_ui.apply_theme(theme_util.get_theme(self.theme))
            # Map-Mode soll keinen Fokus ziehen
            try:
                self.map_ui.container.setFocusPolicy(QtCore.Qt.NoFocus)
            except Exception:
                pass
            for w in (self.map_ui.map_main, *self.map_ui.map_lists.values()):
                try:
                    w.setFocusPolicy(QtCore.Qt.NoFocus)
                except Exception:
                    pass
                view = getattr(w, "view", None)
                if view:
                    try:
                        view.setFocusPolicy(QtCore.Qt.NoFocus)
                    except Exception:
                        pass
            self._map_initialized = True
            self._trace_event("ensure_map_ui:done")
            self._apply_focus_policy_defaults()
        finally:
            self._map_init_in_progress = False

    def _build_mode_stack(self, root: QtWidgets.QVBoxLayout, role_container: QtWidgets.QWidget) -> None:
        # ----- Stacked Content -----
        self.mode_stack = QtWidgets.QStackedLayout()
        self.mode_stack.addWidget(role_container)  # index 0
        self.mode_stack.addWidget(self.map_container)  # index 1
        root.addLayout(self.mode_stack, 1)

    def _apply_initial_mode_state(self) -> None:
        # Aktiven Modus vollständig anwenden (Einträge, Toggles etc.)
        self.btn_mode_players.setChecked(self.current_mode == "players")
        self.btn_mode_heroes.setChecked(self.current_mode == "heroes")
        self.btn_mode_heroban.setChecked(False)
        self._update_mode_button_styles()
        self._load_mode_into_wheels(self.current_mode)

    def _wire_spin_signals(self) -> None:
        # Spin-Signale
        self.tank.request_spin.connect(lambda: self._spin_single(self.tank, 1.00))
        self.dps.request_spin.connect(lambda: self._spin_single(self.dps, 1.10))
        self.support.request_spin.connect(lambda: self._spin_single(self.support, 1.20))

    def _build_controls(self, root: QtWidgets.QVBoxLayout) -> None:
        # --- Controls unten wie gehabt ---
        controls = QtWidgets.QHBoxLayout()
        controls.setContentsMargins(0, 4, 0, 0)
        controls.setSpacing(ui_tokens.SECTION_SPACING)
        root.addLayout(controls)
        self.duration = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        spin_ui = self._spin_ui_settings()
        min_duration = int(getattr(spin_ui, "min_duration_ms", self._cfg("MIN_DURATION_MS", 0)))
        max_duration = int(getattr(spin_ui, "max_duration_ms", self._cfg("MAX_DURATION_MS", 10000)))
        if max_duration < min_duration:
            max_duration = min_duration
        default_duration = int(
            getattr(
                spin_ui,
                "default_duration_ms",
                self._cfg("DEFAULT_DURATION_MS", 3000),
            )
        )
        default_duration = max(min_duration, min(max_duration, default_duration))
        self.duration.setRange(min_duration, max_duration)
        self.duration.setValue(default_duration)
        self.duration.setToolTip(i18n.t("controls.anim_duration_tooltip"))
        self.btn_spin_all = QtWidgets.QPushButton(i18n.t("controls.spin_all"))
        self.btn_spin_all.setObjectName("btn_spin_all")
        ui_helpers.set_fixed_width_from_translations([self.btn_spin_all], ["controls.spin_all"], padding=40)
        self.btn_spin_all.setFixedHeight(ui_tokens.BUTTON_HEIGHT_XL)
        self.btn_spin_all.setToolTip(i18n.t("controls.spin_all_tooltip"))
        self.btn_spin_all.clicked.connect(self.spin_all)
        self.spin_mode_toggle = SpinModeToggle()
        self.spin_mode_toggle.setToolTip(i18n.t("controls.spin_mode_tooltip"))
        self.spin_mode_toggle.valueChanged.connect(self._update_spin_all_enabled)
        self.lbl_open_count = QtWidgets.QLabel(i18n.t("controls.open_count_label"))
        self.lbl_open_count.setToolTip(i18n.t("controls.open_count_tooltip"))
        self.open_count_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.open_count_slider.setRange(1, 6)
        self.open_count_slider.setValue(3)
        self.open_count_slider.setFixedWidth(96)
        self.open_count_slider.setToolTip(i18n.t("controls.open_count_tooltip"))
        self.open_count_slider.valueChanged.connect(self._on_open_count_changed)
        self.lbl_open_count_value = QtWidgets.QLabel("3")
        self.lbl_open_count_value.setMinimumWidth(18)
        self.lbl_open_count_value.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.lbl_open_count_value.setToolTip(i18n.t("controls.open_count_tooltip"))
        controls.addStretch(1)
        self.lbl_anim_duration = QtWidgets.QLabel(i18n.t("controls.anim_duration"))
        controls.addWidget(self.lbl_anim_duration)
        self.duration.setFixedHeight(ui_tokens.SLIDER_HEIGHT_MD)
        controls.addWidget(self.duration)
        controls.addWidget(self.spin_mode_toggle)
        controls.addWidget(self.lbl_open_count)
        controls.addWidget(self.open_count_slider)
        controls.addWidget(self.lbl_open_count_value)
        controls.addWidget(self.btn_spin_all)
        self.btn_cancel_spin = QtWidgets.QPushButton(i18n.t("controls.cancel_spin"))
        self.btn_cancel_spin.setObjectName("btn_cancel_spin")
        ui_helpers.set_fixed_width_from_translations([self.btn_cancel_spin], ["controls.cancel_spin"], padding=40)
        self.btn_cancel_spin.setFixedHeight(ui_tokens.BUTTON_HEIGHT_XL)
        self.btn_cancel_spin.setEnabled(False)
        self.btn_cancel_spin.setToolTip(i18n.t("controls.cancel_spin_tooltip"))
        style_helpers.style_danger_button(self.btn_cancel_spin, theme_util.get_theme(getattr(self, "theme", "light")))
        self.btn_cancel_spin.clicked.connect(self._cancel_spin)
        controls.addWidget(self.btn_cancel_spin)
        controls.addStretch(1)
        self.lbl_open_count.setVisible(False)
        self.open_count_slider.setVisible(False)
        self.lbl_open_count_value.setVisible(False)

    def _build_summary(self, root: QtWidgets.QVBoxLayout) -> None:
        current_theme = theme_util.get_theme(getattr(self, "theme", "light"))
        self.summary = AdaptiveSummaryLabel(
            "",
            empty_height=max(1, int(ui_tokens.ROOT_SPACING)),
        )
        self.summary.setAlignment(QtCore.Qt.AlignCenter)
        summary_host_layout = getattr(self, "_role_summary_host_layout", None)
        self._summary_inline = bool(summary_host_layout)
        summary_role = "label.summary_inline" if self._summary_inline else "label.summary"
        style_helpers.apply_theme_roles(current_theme, ((self.summary, summary_role),))
        if self._summary_inline:
            summary_host_layout.addWidget(self.summary, 1, QtCore.Qt.AlignVCenter)
            summary_host_layout.addStretch(1)
            return
        root.addWidget(self.summary)

    def _init_spin_state(self) -> None:
        self.pending = 0
        self._result_sent_this_spin = False
        self._last_results_snapshot: dict | None = None
        self._spin_started_at_monotonic: float | None = None
        self._spin_watchdog_timer: QtCore.QTimer | None = None
        if self._spin_ui_bool("spin_watchdog_enabled", "SPIN_WATCHDOG_ENABLED", False):
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._on_spin_watchdog_timeout)
            self._spin_watchdog_timer = timer
        self.open_queue = OpenQueueController(self)
        if hasattr(self, "open_count_slider"):
            self.open_queue.set_player_count(int(self.open_count_slider.value()))
        for _role, w in self._role_wheels():
            w.spun.connect(self._wheel_finished)
        if hasattr(self, "map_main"):
            self.map_main.spun.connect(self._wheel_finished)

    def _build_overlay(self, central: QtWidgets.QWidget) -> None:
        self.overlay = ResultOverlay(parent=central)
        # ResultOverlay defaults to light internally; enforce persisted app theme.
        theme = theme_util.get_theme(getattr(self, "theme", "light"))
        self.overlay.apply_theme(theme, theme_util.tool_button_stylesheet(theme))
        self.overlay.hide()
        self.overlay.closed.connect(self._on_overlay_closed)
        self.overlay.languageToggleRequested.connect(self._toggle_language)
        self.overlay.disableResultsRequested.connect(self._on_overlay_disable_results)
        self.overlay.deleteNamesConfirmed.connect(self._on_overlay_delete_names_confirmed)
        self.overlay.deleteNamesCancelled.connect(self._on_overlay_delete_names_cancelled)
        self.overlay.ocrImportConfirmed.connect(self._on_overlay_ocr_import_confirmed)
        self.overlay.ocrImportReplaceRequested.connect(self._on_overlay_ocr_import_replace_requested)
        self.overlay.ocrImportCancelled.connect(self._on_overlay_ocr_import_cancelled)

        self.online_mode = False  # Standard
        self.overlay.modeChosen.connect(self._on_mode_chosen)

    def _request_delete_names_confirm(self, panel: Any, count: int) -> bool:
        overlay = getattr(self, "overlay", None)
        if overlay is None:
            return False
        self._pending_delete_names_panel = panel
        try:
            overlay.show_delete_names_confirm(int(count))
        except Exception:
            self._pending_delete_names_panel = None
            return False
        return True

    def _connect_state_signals(self) -> None:
        # JETZT: Save-Hooks anschließen
        for _role, w in self._role_wheels():
            w.stateChanged.connect(self.state_sync.save_state)
            w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)
            w.stateChanged.connect(self._update_spin_all_enabled)
            w.stateChanged.connect(self._on_wheel_state_changed)
            w.btn_include_in_all.toggled.connect(self._on_role_include_toggled)
            if getattr(w, "toggle", None) is not None:
                w.toggle.stateChanged.connect(self._update_spin_all_enabled)
        if hasattr(self, "map_lists"):
            for w in self.map_lists.values():
                w.stateChanged.connect(self.state_sync.save_state)
                w.btn_include_in_all.toggled.connect(self.state_sync.save_state)
                w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)
                # Sicherstellen, dass Buttons aktiv bleiben (nicht wie disabled im UI aussehen)
                w.btn_local_spin.setEnabled(True)
                w.btn_include_in_all.setEnabled(True)
