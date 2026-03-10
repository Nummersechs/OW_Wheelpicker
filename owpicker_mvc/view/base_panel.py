from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

import i18n
from utils import qt_runtime, theme as theme_util, ui_helpers
from view import style_helpers, ui_tokens
from view.name_list import NamesListPanel


class BasePanel(QtWidgets.QWidget):
    stateChanged = QtCore.Signal()
    request_spin = QtCore.Signal()

    def __init__(
        self,
        title: str,
        spin_label: str,
        names_hint_text: str | None = None,
        names_hint_key: str | None = None,
        subrole_labels: list[str] | None = None,
        title_key: str | None = None,
        header_mode: str = "simple",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title_key = title_key
        self._title_fallback = title
        self._names_hint_key = names_hint_key
        self.subrole_labels = subrole_labels or []
        self._applied_theme_key: str | None = None

        self.card = QtWidgets.QFrame()
        self.card.setObjectName("card")
        self._disabled_spin_hover_active = False

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.card)

        self._inner_layout = QtWidgets.QVBoxLayout(self.card)
        self._inner_layout.setContentsMargins(
            ui_tokens.PANEL_CONTENT_MARGIN_H,
            ui_tokens.PANEL_CONTENT_MARGIN_V,
            ui_tokens.PANEL_CONTENT_MARGIN_H,
            ui_tokens.PANEL_CONTENT_MARGIN_V,
        )
        self._inner_layout.setSpacing(ui_tokens.PANEL_LAYOUT_SPACING)

        self.header_layout = QtWidgets.QHBoxLayout()
        self.header_layout.setContentsMargins(0, 0, 0, 0)

        self.label = QtWidgets.QLabel()
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet("font-size:18px; font-weight:800; letter-spacing:0.3px;")
        self._apply_title()

        if header_mode == "simple":
            self.header_layout.addStretch(1)
            self.header_layout.addWidget(self.label)
            self.header_layout.addStretch(1)
        self._inner_layout.addLayout(self.header_layout)

        self.btn_local_spin = QtWidgets.QPushButton(spin_label)
        self.btn_local_spin.setFixedHeight(ui_tokens.BUTTON_HEIGHT_MD)
        self.btn_local_spin.setToolTip(i18n.t("wheel.spin_button_tooltip"))
        self.btn_local_spin.clicked.connect(self.request_spin.emit)

        self.btn_include_in_all = QtWidgets.QPushButton()
        self.btn_include_in_all.setCheckable(True)
        self.btn_include_in_all.setChecked(True)
        self.btn_include_in_all.setFixedHeight(ui_tokens.BUTTON_HEIGHT_MD)
        self.btn_include_in_all.setToolTip(i18n.t("wheel.include_tooltip"))
        self.btn_include_in_all.toggled.connect(self._on_include_in_all_toggled)
        self._on_include_in_all_toggled(self.btn_include_in_all.isChecked())

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(ui_tokens.SECTION_SPACING)
        btn_row.addWidget(self.btn_local_spin, 1)
        btn_row.addWidget(self.btn_include_in_all, 0)

        self._controls_insert_index = self._inner_layout.count()
        self._inner_layout.addLayout(btn_row)
        self.setMouseTracking(True)
        self.card.setMouseTracking(True)
        self._interaction_filters_installed = False
        QtCore.QTimer.singleShot(0, self._install_interaction_filters)

        hint = names_hint_text
        if hint is None and names_hint_key:
            hint = i18n.t(names_hint_key)
        self.names_hint = QtWidgets.QLabel(hint or "")
        self.names_hint.setStyleSheet("font-size:12px; padding:2px;")
        self._inner_layout.addWidget(self.names_hint)

        self.names_panel = NamesListPanel(subrole_labels=self.subrole_labels)
        self.names_panel.set_fixed_visible_rows(4)
        self.names_panel.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.names = self.names_panel.names
        self.btn_sort_names = self.names_panel.btn_sort_names
        self.btn_toggle_all_names = self.names_panel.btn_toggle_all_names
        self._inner_layout.addWidget(self.names_panel)

        self._apply_fixed_widths_base()

    def add_body_widget(self, widget: QtWidgets.QWidget, stretch: int = 0) -> None:
        if widget is None:
            return
        self._inner_layout.insertWidget(self._controls_insert_index, widget, stretch)
        self._controls_insert_index += 1

    def _apply_title(self) -> None:
        text = self._title_fallback
        if self._title_key:
            text = i18n.t(self._title_key)
        self.label.setText(text)

    def _include_label(self) -> str:
        prefix = "☑" if self.btn_include_in_all.isChecked() else "☐"
        return f"{prefix} {i18n.t('wheel.include_prefix')}"

    def _install_interaction_filters(self) -> None:
        if self._interaction_filters_installed:
            return
        self.installEventFilter(self)
        self.card.installEventFilter(self)
        self._interaction_filters_installed = True

    def _on_include_in_all_toggled(self, _checked: bool) -> None:
        self.btn_include_in_all.setText(self._include_label())
        self.stateChanged.emit()

    def _apply_fixed_widths_base(self) -> None:
        ui_helpers.set_fixed_width_from_translations(
            self.btn_local_spin,
            ["wheel.spin_role", "wheel.spin_map", "wheel.spin_single_map"],
            padding=22,
        )
        ui_helpers.set_fixed_width_from_translations(
            self.btn_include_in_all,
            ["wheel.include_prefix"],
            padding=48,
            prefixes=["☑ ", "☐ "],
        )
        if hasattr(self, "names_panel"):
            self.names_panel.apply_fixed_widths()
        self.btn_include_in_all.setText(self._include_label())

    def _apply_fixed_widths(self) -> None:
        self._apply_fixed_widths_base()

    def set_spin_button_text(self, text: str) -> None:
        if text is None:
            return
        self.btn_local_spin.setText(text)
        self.btn_local_spin.setToolTip(i18n.t("wheel.spin_button_tooltip"))
        self._apply_fixed_widths()

    def set_language(self, lang: str) -> None:
        i18n.set_language(lang)
        self._apply_title()
        if self._names_hint_key:
            self.names_hint.setText(i18n.t(self._names_hint_key))
        if hasattr(self, "names_panel"):
            self.names_panel.set_language(lang)
        self.btn_local_spin.setToolTip(i18n.t("wheel.spin_button_tooltip"))
        self.btn_include_in_all.setToolTip(i18n.t("wheel.include_tooltip"))
        self.btn_include_in_all.setText(self._include_label())
        self._apply_fixed_widths()

    def set_interactive_enabled(self, enabled: bool) -> None:
        self.names.setEnabled(enabled)
        self.btn_local_spin.setEnabled(enabled)
        self.btn_include_in_all.setEnabled(enabled)
        if hasattr(self, "btn_sort_names"):
            self.btn_sort_names.setEnabled(enabled)
        if hasattr(self, "btn_toggle_all_names"):
            self.btn_toggle_all_names.setEnabled(enabled)
        if hasattr(self, "names_panel"):
            self.names_panel.set_interactive_enabled(enabled)

    def _sync_disabled_spin_tooltip(
        self,
        global_pos: QtCore.QPoint,
        *,
        force_show: bool = False,
    ) -> bool:
        btn = self.btn_local_spin
        if btn is None:
            return False
        if btn.isEnabled():
            if self._disabled_spin_hover_active:
                QtWidgets.QToolTip.hideText()
                self._disabled_spin_hover_active = False
            return False
        tip = str(btn.toolTip() or "").strip()
        if not tip:
            return False
        top_left = btn.mapToGlobal(QtCore.QPoint(0, 0))
        inside = QtCore.QRect(top_left, btn.size()).contains(global_pos)
        if not inside:
            if self._disabled_spin_hover_active:
                QtWidgets.QToolTip.hideText()
                self._disabled_spin_hover_active = False
            return False
        shown = False
        if force_show or not self._disabled_spin_hover_active:
            if not qt_runtime.is_headless_qpa():
                QtWidgets.QToolTip.showText(global_pos, tip, btn, btn.rect())
                shown = True
        self._disabled_spin_hover_active = shown
        return True

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj in (self, self.card):
            etype = event.type()
            if etype == QtCore.QEvent.ToolTip:
                if isinstance(event, QtGui.QHelpEvent):
                    if self._sync_disabled_spin_tooltip(event.globalPos(), force_show=True):
                        return True
            elif etype == QtCore.QEvent.MouseMove:
                if isinstance(event, QtGui.QMouseEvent):
                    self._sync_disabled_spin_tooltip(event.globalPosition().toPoint())
                else:
                    self._sync_disabled_spin_tooltip(QtGui.QCursor.pos())
            elif etype in (QtCore.QEvent.Leave, QtCore.QEvent.Hide):
                if self._disabled_spin_hover_active:
                    QtWidgets.QToolTip.hideText()
                    self._disabled_spin_hover_active = False
        return super().eventFilter(obj, event)

    def apply_theme(self, theme: theme_util.Theme) -> None:
        if self._applied_theme_key == theme.key:
            return
        style_helpers.apply_theme_roles(
            theme,
            (
                (self.card, "frame.card"),
                (self.label, "label.panel_title"),
                (self.names_hint, "label.hint"),
                (self.btn_local_spin, "button.primary"),
                (self.btn_include_in_all, "button.include"),
            ),
        )
        if hasattr(self, "names_panel"):
            self.names_panel.apply_theme(theme)
        self._applied_theme_key = theme.key
