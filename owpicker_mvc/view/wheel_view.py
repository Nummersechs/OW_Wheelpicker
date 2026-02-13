from contextlib import contextmanager
from typing import List, Optional
from PySide6 import QtCore, QtWidgets
from view.base_panel import BasePanel
from view.wheel_widget import WheelWidget
from view import wheel_spin_ops
from view.wheel_view_entries_mixin import WheelViewEntriesMixin
from model.wheel_state import WheelState
import i18n
from utils import qt_runtime, theme as theme_util, ui_helpers

_WHEEL_INDICATOR_STYLE_CACHE: dict[str, str] = {}
_WHEEL_RESULT_STYLE_CACHE: dict[str, str] = {}
_RESET_TOOL_STYLE_CACHE: dict[str, str] = {}


def _wheel_indicator_style(theme: theme_util.Theme) -> str:
    cached = _WHEEL_INDICATOR_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = f"""
            QCheckBox::indicator,
            QListView::indicator {{
                width: 6px;
                height: 6px;
                border: 2px solid {theme.text};
                border-radius: 3px;
                background: {theme.base};
            }}

            QCheckBox::indicator:checked,
            QListView::indicator:checked {{
                background: {theme.primary};
            }}

            /* Scrollbar-Farben im aktiven Theme halten */
            QScrollBar:vertical {{
                background:{theme.frame_bg};
                width:12px;
                margin:2px;
                border-radius:6px;
            }}
            QScrollBar::handle:vertical {{
                background:{theme.slider_handle};
                min-height:24px;
                border-radius:6px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height:0px;
                background:transparent;
            }}
            QScrollBar::sub-page:vertical,
            QScrollBar::add-page:vertical {{
                background:{theme.slider_groove};
                border-radius:6px;
            }}
            QScrollBar:horizontal {{
                background:{theme.frame_bg};
                height:12px;
                margin:2px;
                border-radius:6px;
            }}
            QScrollBar::handle:horizontal {{
                background:{theme.slider_handle};
                min-width:24px;
                border-radius:6px;
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width:0px;
                background:transparent;
            }}
            QScrollBar::sub-page:horizontal,
            QScrollBar::add-page:horizontal {{
                background:{theme.slider_groove};
                border-radius:6px;
            }}
            """
    _WHEEL_INDICATOR_STYLE_CACHE[theme.key] = cached
    return cached


def _wheel_result_style(theme: theme_util.Theme) -> str:
    cached = _WHEEL_RESULT_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = f"font-size:14px; color:{theme.muted_text}; margin-top:6px;"
    _WHEEL_RESULT_STYLE_CACHE[theme.key] = cached
    return cached


def _reset_button_style(theme: theme_util.Theme) -> str:
    cached = _RESET_TOOL_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    tool_style = theme_util.tool_button_stylesheet(theme)
    cached = (
        f"{tool_style} "
        f"QToolButton {{ color:{theme.primary}; background:{theme.base}; "
        f"border:1px solid {theme.primary}; border-radius:6px; }} "
        f"QToolButton:disabled {{ color:{theme.disabled_text}; background:{theme.alt_base}; "
        f"border:1px solid {theme.border}; border-radius:6px; }}"
    )
    _RESET_TOOL_STYLE_CACHE[theme.key] = cached
    return cached


class WheelView(WheelViewEntriesMixin, BasePanel):
    spun = QtCore.Signal(str)
    def __init__(self, title: str, defaults: List[str], pair_mode=False, allow_pair_toggle=False, subrole_labels: Optional[List[str]] = None, title_key: Optional[str] = None):
        self.pair_mode = pair_mode
        self.allow_pair_toggle = allow_pair_toggle
        self._is_spinning = False
        self.use_subrole_filter = False
        default_spin_label = i18n.t("wheel.spin_role")
        super().__init__(
            title=title,
            spin_label=default_spin_label,
            names_hint_text="",
            subrole_labels=subrole_labels,
            title_key=title_key,
            header_mode="custom",
        )
        self._default_spin_label = default_spin_label
        self._custom_spin_label: Optional[str] = None
        self._suppress_wheel_render = False
        self._suppress_state_signal = False
        self._force_spin_enabled = False
        self._wheel_state = WheelState(
            pair_mode=self.pair_mode,
            use_subrole_filter=self.use_subrole_filter,
            subrole_labels=self.subrole_labels,
        )
        self._entries_cache: dict[str, list] | None = None
        self._subrole_controls_visible = True
        self._header_controls_visible = True
        self._show_names_visible = True
        self._names_change_timer: QtCore.QTimer | None = None
        self._subrole_visibility_applied: tuple[bool, int] | None = None
        self._tooltip_rev = 0
        self._wheel_overlay_widget: QtWidgets.QWidget | None = None
        self._wheel_overlay_margin_top = 8
        self._wheel_overlay_margin_right = 8
        self._last_entries_signature: tuple | None = None
        self._applied_theme_key_local: str | None = None
        self.view = WheelWidget(self._effective_names_from(defaults))
        self.view.viewport().installEventFilter(self)
        self.view.segmentToggled.connect(self._on_segment_toggled)
        self.wheel = self.view.wheel
        self._wheel_state.last_wheel_names = list(self.wheel.names)
        self._result_state: str = "empty"  # empty | value | too_few
        self._result_value: Optional[str] = None

        header = self.header_layout
        header.setContentsMargins(0, 0, 0, 0)

        self.btn_reset_segments = QtWidgets.QToolButton()
        self.btn_reset_segments.setText("↺")
        self.btn_reset_segments.setToolTip(i18n.t("wheel.reset_disabled_tooltip"))
        self.btn_reset_segments.setAutoRaise(True)
        self.btn_reset_segments.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_reset_segments.setFixedSize(30, 30)
        self.btn_reset_segments.clicked.connect(self.reset_disabled_segments)
        self._update_reset_button_state()

        header.addWidget(self.btn_reset_segments, 0, QtCore.Qt.AlignVCenter)
        header.addStretch(1)
        header.addWidget(self.label)
        header.addStretch(1)

        self.toggle = None
        if allow_pair_toggle:
            self.toggle = QtWidgets.QCheckBox(i18n.t("wheel.pairs_toggle"))
            self.toggle.setChecked(self.pair_mode)
            self.toggle.stateChanged.connect(self._on_toggle_pair_mode)
            header.setSpacing(12)
            header.addWidget(self.toggle, 0, QtCore.Qt.AlignVCenter)
        self.chk_subroles = None
        if self.subrole_labels and allow_pair_toggle:
            self.chk_subroles = QtWidgets.QCheckBox(i18n.t("wheel.subroles_toggle"))
            self.chk_subroles.setChecked(False)
            hint = i18n.t("wheel.subroles_hint_generic")
            if len(self.subrole_labels) >= 2:
                hint = i18n.t(
                    "wheel.subroles_hint_labels",
                    a=self.subrole_labels[0],
                    b=self.subrole_labels[1],
                )
            self.chk_subroles.setToolTip(hint)
            self.chk_subroles.setEnabled(self.pair_mode)
            self.chk_subroles.stateChanged.connect(self._on_toggle_subroles)
            header.addWidget(self.chk_subroles, 0, QtCore.Qt.AlignVCenter)

        # Optional: Checkbox "Namen anzeigen" im Header
        self.chk_show_names = QtWidgets.QCheckBox(i18n.t("wheel.show_names"))
        self.chk_show_names.setChecked(True)
        self.chk_show_names.stateChanged.connect(self._on_toggle_show_names)
        header.addWidget(self.chk_show_names, 0, QtCore.Qt.AlignVCenter)

        # ---------- Ergebnis-Widget: Label + Löschen-Icon ----------
        self.result = QtWidgets.QLabel("–")
        # Text links, vertikal mittig
        self.result.setAlignment(QtCore.Qt.AlignCenter)
        self.result.setStyleSheet(
            "font-size:14px; color:#666; margin-top:6px;"
        )

        self.btn_clear_result = QtWidgets.QToolButton()
        self.btn_clear_result.setText("✖")
        self.btn_clear_result.setToolTip(i18n.t("wheel.clear_result_tooltip"))
        self.btn_clear_result.setAutoRaise(True)  # kein blauer Button, nur Icon
        self.btn_clear_result.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_clear_result.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                color: #b00020;
                font-size: 14px;
            }
            QToolButton:hover {
                color: #ff1744;
            }
        """)
        self.btn_clear_result.clicked.connect(self._clear_result)
        self.btn_clear_result.setVisible(False)  # nur zeigen, wenn Ergebnis da ist

        # Container-Widget für Ergebnis + Icon
        self.result_widget = QtWidgets.QWidget()
        result_layout = QtWidgets.QHBoxLayout(self.result_widget)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(4)

        # [ Stretch | Ergebnis | X | Stretch ]
        result_layout.addStretch(1)
        result_layout.addWidget(self.result, 0, QtCore.Qt.AlignVCenter)
        result_layout.addSpacing(4)
        result_layout.addWidget(self.btn_clear_result, 0, QtCore.Qt.AlignVCenter)
        result_layout.addStretch(1)

        self.add_body_widget(self.view, 1)
        self.add_body_widget(self.result_widget)

        # Start-Namen anlegen – neue Namen sind standardmäßig aktiv (Checked)
        for entry in self._normalize_entries(defaults):
            self.names.add_name(
                entry["name"],
                subroles=entry.get("subroles", []),
                active=entry.get("active", True),
            )
        
        # Falls gar keine Defaults/Saved Names vorhanden sind, eine leere Zeile hinzufügen
        if self.names.count() == 0:
            self.names.add_name("")

        # Änderungen an Text oder Häkchen überwachen
        self.names.itemChanged.connect(self._on_names_list_changed)
        self.names.model().rowsInserted.connect(self._on_names_list_changed)
        self.names.model().rowsRemoved.connect(self._on_names_list_changed)
        self.names.metaChanged.connect(self._on_names_list_changed)
        # Neue Zeilen sollen sofort die korrekte Sichtbarkeit der Subrollen übernehmen
        self.names.model().rowsInserted.connect(lambda *_: self._apply_subrole_visibility())
        self.btn_include_in_all.setToolTip(i18n.t("wheel.include_tooltip"))
        self._apply_fixed_widths()
        
        # Startwert für Namensanzahl merken und UI initial justieren
        self._last_name_count = len(self._base_names())
        self._update_name_dependent_ui()
        self._apply_placeholder()
        self._apply_result_state()

        # Default theme; main window reapplies the persisted choice.
        self.apply_theme(theme_util.get_theme("light"))
        QtCore.QTimer.singleShot(0, self._refit_view)

    def set_wheel_overlay_widget(
        self,
        widget: QtWidgets.QWidget,
        *,
        margin_top: int = 8,
        margin_right: int = 8,
    ) -> None:
        if widget is None:
            return
        self._wheel_overlay_widget = widget
        self._wheel_overlay_margin_top = max(0, int(margin_top))
        self._wheel_overlay_margin_right = max(0, int(margin_right))
        widget.setParent(self.view.viewport())
        widget.show()
        qt_runtime.safe_raise(widget)
        widget.installEventFilter(self)
        QtCore.QTimer.singleShot(0, self._position_wheel_overlay_widget)

    def _position_wheel_overlay_widget(self) -> None:
        widget = self._wheel_overlay_widget
        if widget is None:
            return
        viewport = self.view.viewport()
        x = max(0, viewport.width() - widget.width() - self._wheel_overlay_margin_right)
        y = max(0, self._wheel_overlay_margin_top)
        widget.move(x, y)
        qt_runtime.safe_raise(widget)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent):
        if obj is self.view.viewport() and event.type() in (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
            QtCore.QEvent.LayoutRequest,
        ):
            QtCore.QTimer.singleShot(0, self._position_wheel_overlay_widget)
        elif obj is self._wheel_overlay_widget and event.type() in (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
        ):
            QtCore.QTimer.singleShot(0, self._position_wheel_overlay_widget)
        return super().eventFilter(obj, event)

    @contextmanager
    def _suspend_list_signals(self):
        blockers = [
            QtCore.QSignalBlocker(self.names),
            QtCore.QSignalBlocker(self.names.model()),
        ]
        prev = self._suppress_state_signal
        self._suppress_state_signal = True
        try:
            yield prev
        finally:
            del blockers
            self._suppress_state_signal = prev

    def set_language(self, lang: str):
        """Reapply translated labels for the current wheel."""
        super().set_language(lang)
        self._default_spin_label = i18n.t("wheel.spin_role")
        if self.toggle:
            self.toggle.setText(i18n.t("wheel.pairs_toggle"))
        if self.chk_subroles:
            self.chk_subroles.setText(i18n.t("wheel.subroles_toggle"))
            hint = i18n.t("wheel.subroles_hint_generic")
            if len(self.subrole_labels) >= 2:
                hint = i18n.t(
                    "wheel.subroles_hint_labels",
                    a=self.subrole_labels[0],
                    b=self.subrole_labels[1],
                )
            self.chk_subroles.setToolTip(hint)
        if self.chk_show_names:
            self.chk_show_names.setText(i18n.t("wheel.show_names"))
        if hasattr(self, "btn_reset_segments"):
            self.btn_reset_segments.setToolTip(i18n.t("wheel.reset_disabled_tooltip"))
        self.btn_clear_result.setToolTip(i18n.t("wheel.clear_result_tooltip"))
        self.btn_include_in_all.setToolTip(i18n.t("wheel.include_tooltip"))
        if self._custom_spin_label is None:
            self.set_spin_button_text(None)
        self._apply_placeholder()
        self._apply_result_state()
        self._apply_fixed_widths()

    def _refit_view(self):
        """Reicht Größenanpassung an das WheelWidget weiter."""
        if hasattr(self, "view") and hasattr(self.view, "_refit_view"):
            self.view._refit_view()

    def _apply_result_state(self):
        """Render the current result state with translated labels."""
        if self._result_state == "value" and self._result_value is not None:
            self.result.setText(i18n.t("wheel.result_prefix", result=self._result_value))
        elif self._result_state == "too_few":
            self.result.setText(i18n.t("wheel.result_too_few"))
        else:
            self.result.setText("–")
        self._update_clear_button_enabled()

    def _apply_fixed_widths(self):
        """Set fixed widths based on max translation to avoid layout jumps."""
        super()._apply_fixed_widths()
        if self.toggle:
            ui_helpers.set_fixed_width_from_translations(
                self.toggle,
                ["wheel.pairs_toggle"],
                padding=30,
            )
        if self.chk_subroles:
            ui_helpers.set_fixed_width_from_translations(
                self.chk_subroles,
                ["wheel.subroles_toggle"],
                padding=30,
            )
        if self.chk_show_names:
            ui_helpers.set_fixed_width_from_translations(
                self.chk_show_names,
                ["wheel.show_names"],
                padding=30,
            )

    def apply_theme(self, theme: theme_util.Theme) -> None:
        """Apply color palette for the active theme to this wheel."""
        if self._applied_theme_key_local == theme.key:
            return
        super().apply_theme(theme)
        self.result.setStyleSheet(_wheel_result_style(theme))
        # Indicator styling stays aligned with the active theme colors.
        self.setStyleSheet(_wheel_indicator_style(theme))
        if hasattr(self, "btn_reset_segments"):
            self.btn_reset_segments.setStyleSheet(_reset_button_style(theme))
        self._applied_theme_key_local = theme.key

    def set_result_value(self, value: str):
        self._result_state = "value"
        self._result_value = value
        self._apply_result_state()

    def set_result_too_few(self):
        self._result_state = "too_few"
        self._result_value = None
        self._apply_result_state()

    def clear_result(self):
        self._result_state = "empty"
        self._result_value = None
        self._apply_result_state()

    def get_result_value(self) -> Optional[str]:
        return self._result_value if self._result_state == "value" else None

    def tooltip_revision(self) -> int:
        """Monotonic revision for tooltip cache invalidation."""
        return self._tooltip_rev

    def is_anim_running(self) -> bool:
        return hasattr(self, "anim") and self.anim.state() == QtCore.QAbstractAnimation.Running
    def hard_stop(self):
        if hasattr(self, "anim"):
            try:
                if self.is_anim_running(): self.anim.stop()
            finally:
                self.anim.deleteLater(); delattr(self, "anim")
        self._is_spinning = False
    def spin(self, duration_ms: int = 2500):
        if self._is_spinning and self.is_anim_running():
            return None
        
        # Sobald ein neues Spin startet, alte Auswahl löschen
        self.clear_result()

        base_entries = self._entries_for_spin()
        names = self._effective_names_from(base_entries, include_disabled=True)
        enabled_indices = self._wheel_state.enabled_indices(names)
        if (self.pair_mode and len(base_entries) < 2) or not enabled_indices:
            self.set_result_too_few()
            return None
        duration_ms = max(1, int(duration_ms))
        return wheel_spin_ops.spin_to_label(
            self,
            names,
            enabled_indices,
            duration_ms=duration_ms,
        )
    def spin_to_name(self, target_name: str, duration_ms: int = 2500):
        """Spinnt das Rad gezielt auf einen bestimmten Namen.

        Falls der Name im aktuellen Rad nicht vorkommt, fällt die Methode auf
        das normale Zufalls-Spin zurück.
        """
        if self._is_spinning and self.is_anim_running():
            return None

        # Sobald ein neues Spin startet, alte Auswahl löschen
        self.clear_result()

        base_entries = self._entries_for_spin()
        names = self._effective_names_from(base_entries, include_disabled=True)
        enabled_indices = self._wheel_state.enabled_indices(names)
        if (self.pair_mode and len(base_entries) < 2) or not enabled_indices:
            self.set_result_too_few()
            return None
        duration_ms = max(1, int(duration_ms))
        return wheel_spin_ops.spin_to_label(
            self,
            names,
            enabled_indices,
            duration_ms=duration_ms,
            target_label=target_name,
        )


    def _emit_result(self):
        if hasattr(self, "_pending_result"):
            self.set_result_value(str(self._pending_result))
            self.spun.emit(self._pending_result)
            delattr(self, "_pending_result")

        if hasattr(self, "anim"):
            self.anim.deleteLater()
            delattr(self, "anim")
        self._is_spinning = False

    # --- Added resize behaviour ---

    # wheel resizing handled by WheelWidget
