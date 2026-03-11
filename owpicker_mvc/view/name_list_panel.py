from __future__ import annotations

from functools import lru_cache
from typing import Callable, List, Optional
from PySide6 import QtCore, QtGui, QtWidgets
import i18n
from utils import ui_helpers, theme as theme_util
from view import style_helpers, ui_tokens
from view.name_list_support import (
    DELETE_MARK_BUTTON_WIDTH,
    NAME_LIST_ROW_HEIGHT,
    NAMES_PANEL_MAX_WIDTH_DEFAULT,
    NAMES_PANEL_MAX_WIDTH_WITH_SUBROLES,
    NAMES_PANEL_MIN_WIDTH_BASE,
    delete_marked_button_style as _delete_marked_button_style,
    names_action_row_style as _names_action_row_style,
)


@lru_cache(maxsize=1)
def _name_list_types():
    from view.name_list import NameRowWidget, NamesList
    return NameRowWidget, NamesList


def _is_name_row_widget(widget: object) -> bool:
    NameRowWidget, _ = _name_list_types()
    return isinstance(widget, NameRowWidget)


class NamesListPanel(QtWidgets.QWidget):
    """Composite widget: names list with select/deselect and sort actions."""
    def __init__(
        self,
        parent=None,
        subrole_labels: Optional[List[str]] = None,
        *,
        enable_mark_for_delete: bool = True,
    ):
        super().__init__(parent)
        _, NamesList = _name_list_types()
        self.names = NamesList(
            self,
            subrole_labels=subrole_labels,
            enable_mark_for_delete=enable_mark_for_delete,
        )
        self._fixed_visible_rows: int | None = None
        self._enable_mark_for_delete = bool(enable_mark_for_delete)
        self._interaction_enabled = True
        self._delete_confirm_handler: Callable[[int], bool] | None = None
        self._applied_theme_key: str | None = None
        self._applied_theme = None
        self._panel_width_update_pending = False
        self._applied_panel_min_width = -1
        self._applied_panel_max_width = -1
        self._fill_parent_width = False
        self._parent_filter_installed = False
        self._window_filter_installed = False
        self._panel_width_timer = QtCore.QTimer(self)
        self._panel_width_timer.setSingleShot(True)
        self._panel_width_timer.timeout.connect(self._apply_panel_width_constraints)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self.btn_delete_marked = QtWidgets.QToolButton()
        self.btn_delete_marked.setText("🗑")
        self.btn_delete_marked.setFixedSize(DELETE_MARK_BUTTON_WIDTH, ui_tokens.BUTTON_HEIGHT_SM)
        self.btn_delete_marked.setToolTip(i18n.t("names.delete_marked_tooltip"))
        self.btn_delete_marked.clicked.connect(self._on_delete_marked_clicked)
        self.btn_delete_marked.setVisible(self.names.has_subroles and self._enable_mark_for_delete)
        self.btn_delete_marked.setProperty("dangerActive", False)

        self.btn_toggle_all_names = QtWidgets.QPushButton()
        self.btn_toggle_all_names.setFixedHeight(ui_tokens.BUTTON_HEIGHT_SM)
        self.btn_toggle_all_names.clicked.connect(self._on_toggle_all_names_clicked)

        self.btn_sort_names = QtWidgets.QPushButton(i18n.t("wheel.sort_names"))
        self.btn_sort_names.setFixedHeight(ui_tokens.BUTTON_HEIGHT_SM)
        self.btn_sort_names.setToolTip(i18n.t("wheel.sort_names_tooltip"))
        self.btn_sort_names.clicked.connect(self._on_sort_names_clicked)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ui_tokens.NAMES_PANEL_LAYOUT_SPACING)

        layout.addWidget(self.names)

        self._action_row_widget = QtWidgets.QWidget(self)
        self._action_row_widget.setObjectName("namesActionRow")
        action_row = QtWidgets.QHBoxLayout(self._action_row_widget)
        action_row.setContentsMargins(0, ui_tokens.NAMES_PANEL_ACTION_TOP_MARGIN, 0, 0)
        action_row.setSpacing(ui_tokens.SECTION_SPACING)
        action_row.addWidget(self.btn_toggle_all_names, 0, QtCore.Qt.AlignLeft)
        action_row.addStretch(1)
        action_row.addWidget(self.btn_sort_names, 0, QtCore.Qt.AlignRight)
        action_row.addWidget(self.btn_delete_marked, 0, QtCore.Qt.AlignRight)
        self._action_row_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        layout.addWidget(self._action_row_widget)

        self.names.itemChanged.connect(self._update_toggle_all_button_label)
        self.names.model().rowsInserted.connect(self._update_toggle_all_button_label)
        self.names.model().rowsRemoved.connect(self._update_toggle_all_button_label)
        self.names.metaChanged.connect(self._update_toggle_all_button_label)
        self.names.itemChanged.connect(self._update_delete_marked_button_state)
        self.names.model().rowsInserted.connect(self._update_delete_marked_button_state)
        self.names.model().rowsRemoved.connect(self._update_delete_marked_button_state)
        self.names.metaChanged.connect(self._update_delete_marked_button_state)
        self.names.itemChanged.connect(self._schedule_panel_width_update)
        self.names.model().rowsInserted.connect(self._schedule_panel_width_update)
        self.names.model().rowsRemoved.connect(self._schedule_panel_width_update)
        self.names.metaChanged.connect(self._schedule_panel_width_update)
        self._update_toggle_all_button_label()
        self._update_delete_marked_button_state()
        self.apply_fixed_widths()
        self._apply_panel_width_constraints()
        self._ensure_parent_event_filter()

    def _schedule_panel_width_update(self, *_args) -> None:
        if self._panel_width_update_pending:
            self._panel_width_timer.start(20)
            return
        self._panel_width_update_pending = True
        self._panel_width_timer.start(20)

    def _ensure_parent_event_filter(self) -> None:
        if self._parent_filter_installed:
            return
        parent = self.parentWidget()
        if parent is None:
            return
        try:
            parent.installEventFilter(self)
            self._parent_filter_installed = True
        except Exception:
            self._parent_filter_installed = False

    def _ensure_window_event_filter(self) -> None:
        if self._window_filter_installed:
            return
        win = self.window()
        if win is None:
            return
        try:
            win.installEventFilter(self)
            self._window_filter_installed = True
        except Exception:
            self._window_filter_installed = False

    def _available_parent_width(self) -> int | None:
        parent = self.parentWidget()
        if parent is None:
            return None
        try:
            width = int(parent.contentsRect().width())
        except Exception:
            width = int(parent.width())
        if width <= 0:
            return None
        # Leave a tiny safety gap so centered layouts do not push to edge.
        return max(0, width - 2)

    def _list_row_content_width_hint(self) -> int:
        width = 0
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            row_widget = self.names.itemWidget(item)
            if row_widget is not None:
                try:
                    width = max(width, int(row_widget.sizeHint().width()))
                    continue
                except Exception:
                    pass
            try:
                width = max(width, int(self.names.visualItemRect(item).width()))
            except Exception:
                continue
        if width <= 0:
            try:
                width = int(self.names.minimumSizeHint().width())
            except Exception:
                width = int(NAMES_PANEL_MIN_WIDTH_BASE)
        frame = max(0, int(self.names.frameWidth())) * 2
        viewport_margin = max(0, int(getattr(self.names, "_viewport_right_margin", 0)))
        return max(0, width + frame + viewport_margin + 8)

    def _minimum_row_safe_width_hint(self) -> int:
        width = 0
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            row_widget = self.names.itemWidget(item)
            if _is_name_row_widget(row_widget):
                try:
                    width = max(width, int(row_widget.minimum_safe_width_hint()))
                except Exception:
                    continue
        if width <= 0:
            width = 120
        frame = max(0, int(self.names.frameWidth())) * 2
        viewport_margin = max(0, int(getattr(self.names, "_viewport_right_margin", 0)))
        return max(1, width + frame + viewport_margin + 6)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        parent = self.parentWidget()
        win = self.window()
        if obj in (parent, win) and event.type() in (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
            QtCore.QEvent.LayoutRequest,
        ):
            self._schedule_panel_width_update()
        return super().eventFilter(obj, event)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._ensure_parent_event_filter()
        self._ensure_window_event_filter()
        self._schedule_panel_width_update()

    def _row_height_hint(self) -> int:
        row_h = -1
        try:
            row_h = int(self.names.sizeHintForRow(0))
        except Exception:
            row_h = -1
        if row_h <= 0:
            try:
                row_h = int(getattr(self.names, "_row_height", NAME_LIST_ROW_HEIGHT))
            except Exception:
                row_h = NAME_LIST_ROW_HEIGHT
        return max(1, int(row_h))

    def _apply_fixed_visible_rows_height(self) -> None:
        rows = self._fixed_visible_rows
        if rows is None or int(rows) <= 0:
            self.names.setMinimumHeight(0)
            self.names.setMaximumHeight(16777215)
            return
        frame = max(0, int(self.names.frameWidth())) * 2
        target_h = frame + self._row_height_hint() * int(rows)
        self.names.setMinimumHeight(target_h)
        self.names.setMaximumHeight(target_h)

    def set_fixed_visible_rows(self, rows: int | None) -> None:
        if rows is None:
            self._fixed_visible_rows = None
        else:
            self._fixed_visible_rows = max(1, int(rows))
        self._apply_fixed_visible_rows_height()
        self.updateGeometry()

    def set_compact_vertical(self, compact: bool = True) -> None:
        compact_mode = bool(compact)
        if compact_mode:
            self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
            self.names.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self._action_row_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        else:
            self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
            self.names.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self._action_row_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self.updateGeometry()

    def set_fill_parent_width(self, enabled: bool) -> None:
        target = bool(enabled)
        if self._fill_parent_width == target:
            return
        self._fill_parent_width = target
        self._schedule_panel_width_update()

    def set_language(self, _lang: str):
        self.btn_sort_names.setText(i18n.t("wheel.sort_names"))
        self.btn_sort_names.setToolTip(i18n.t("wheel.sort_names_tooltip"))
        self.btn_delete_marked.setToolTip(i18n.t("names.delete_marked_tooltip"))
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            widget = self.names.itemWidget(item)
            if _is_name_row_widget(widget):
                widget.refresh_texts()
        self._update_toggle_all_button_label()
        self._update_delete_marked_button_state()
        self.apply_fixed_widths()
        self._apply_panel_width_constraints()
        self._apply_fixed_visible_rows_height()

    def apply_theme(self, theme):
        theme_key = str(getattr(theme, "key", "light"))
        if self._applied_theme_key == theme_key:
            return
        style_helpers.style_primary_button(self.btn_sort_names, theme)
        style_helpers.style_primary_button(self.btn_toggle_all_names, theme)
        self.btn_delete_marked.setStyleSheet(
            _delete_marked_button_style(
                theme,
                danger_active=bool(self.btn_delete_marked.property("dangerActive")),
            )
        )
        style_helpers.style_names_list(self.names, theme)
        style_helpers.set_stylesheet_if_needed(
            self._action_row_widget,
            f"names_action_row:{theme_key}",
            _names_action_row_style(theme),
        )
        self._applied_theme = theme
        self._applied_theme_key = theme_key

    def apply_fixed_widths(self):
        ui_helpers.set_fixed_width_from_translations(
            self.btn_toggle_all_names,
            ["wheel.select_all", "wheel.deselect_all"],
            # QPushButton styles add substantial horizontal padding; keep enough
            # reserve so longer DE labels do not clip on Windows.
            padding=44,
            prefixes=["☑ ", "☐ "],
        )
        ui_helpers.set_fixed_width_from_translations(
            self.btn_sort_names,
            ["wheel.sort_names"],
            # Same rationale as above; "A→Z sortieren" should always fit.
            padding=44,
        )
        self._apply_panel_width_constraints()
        self._apply_fixed_visible_rows_height()

    def _apply_panel_width_constraints(self) -> None:
        self._panel_width_update_pending = False
        if self._fill_parent_width:
            panel_min = 0
            panel_max = 16777215
            changed = False
            if panel_min != self._applied_panel_min_width:
                self._applied_panel_min_width = panel_min
                self.setMinimumWidth(panel_min)
                changed = True
            if panel_max != self._applied_panel_max_width:
                self._applied_panel_max_width = panel_max
                self.setMaximumWidth(panel_max)
                changed = True
            if changed:
                self.updateGeometry()
            return
        panel_pref_max = (
            int(NAMES_PANEL_MAX_WIDTH_WITH_SUBROLES)
            if self.names.has_subroles
            else int(NAMES_PANEL_MAX_WIDTH_DEFAULT)
        )
        panel_hard_max = panel_pref_max + (220 if self.names.has_subroles else 260)
        spacing = max(0, int(ui_tokens.SECTION_SPACING))
        actions_width = (
            int(self.btn_toggle_all_names.minimumSizeHint().width())
            + int(self.btn_sort_names.minimumSizeHint().width())
            + spacing
            + 20
        )
        if self.btn_delete_marked.isVisible():
            actions_width += int(self.btn_delete_marked.minimumSizeHint().width()) + spacing
        content_target = max(self._list_row_content_width_hint(), actions_width)
        row_safe_floor = max(1, int(self._minimum_row_safe_width_hint()))
        parent_available = self._available_parent_width()
        panel_floor = max(80, min(panel_hard_max, row_safe_floor))
        if parent_available is not None:
            parent_width = max(1, int(parent_available))
            panel_cap = max(1, min(panel_hard_max, parent_width))
            panel_floor = min(panel_floor, panel_cap)
            width_from_parent = min(panel_cap, max(1, int(round(parent_width * 0.90))))
            content_cap = min(panel_cap, max(1, int(content_target)))
            panel_target = max(panel_floor, width_from_parent, content_cap)
        else:
            panel_target = max(panel_floor, min(panel_hard_max, int(content_target)))
        panel_min = max(80, min(panel_floor, panel_target))
        panel_max = max(panel_min, panel_target)
        changed = False
        if panel_min != self._applied_panel_min_width:
            self._applied_panel_min_width = panel_min
            self.setMinimumWidth(panel_min)
            changed = True
        if panel_max != self._applied_panel_max_width:
            self._applied_panel_max_width = panel_max
            self.setMaximumWidth(panel_max)
            changed = True
        if changed:
            self.updateGeometry()

    def set_auto_focus_enabled(self, enabled: bool, require_active_focus: bool | None = None) -> None:
        if hasattr(self, "names"):
            self.names.set_auto_focus_enabled(enabled, require_active_focus=require_active_focus)

    def set_delete_confirm_handler(self, handler: Callable[[int], bool] | None) -> None:
        self._delete_confirm_handler = handler

    def refresh_action_state(self):
        self._update_toggle_all_button_label()
        self._update_delete_marked_button_state()

    def set_interactive_enabled(self, enabled: bool) -> None:
        self._interaction_enabled = bool(enabled)
        self.btn_sort_names.setEnabled(bool(enabled))
        self._update_toggle_all_button_label()
        self._update_delete_marked_button_state()

    def set_aux_controls_visible(self, visible: bool) -> None:
        show = bool(visible)
        if hasattr(self, "_action_row_widget"):
            self._action_row_widget.setVisible(show)

    def _item_text(self, item: QtWidgets.QListWidgetItem) -> str:
        widget = self.names.itemWidget(item)
        if _is_name_row_widget(widget):
            return widget.edit.text().strip()
        return item.text().strip()

    def _named_items(self) -> list[QtWidgets.QListWidgetItem]:
        items: list[QtWidgets.QListWidgetItem] = []
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            if self._item_text(item):
                items.append(item)
        return items

    def _all_named_items_checked(self) -> bool:
        items = self._named_items()
        if not items:
            return False
        return all(self.names.item_state(item) == QtCore.Qt.Checked for item in items)

    def _marked_named_rows(self) -> list[int]:
        rows: list[int] = []
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            if not self._item_text(item):
                continue
            if bool(item.data(self.names.MARK_FOR_DELETE_ROLE)):
                rows.append(i)
        return rows

    def _update_toggle_all_button_label(self):
        items = self._named_items()
        if not items:
            self.btn_toggle_all_names.setEnabled(False)
            self.btn_toggle_all_names.setText(f"☑ {i18n.t('wheel.select_all')}")
            self.btn_toggle_all_names.setToolTip(i18n.t("wheel.select_all_tooltip"))
            return
        self.btn_toggle_all_names.setEnabled(bool(self._interaction_enabled))
        if self._all_named_items_checked():
            self.btn_toggle_all_names.setText(f"☐ {i18n.t('wheel.deselect_all')}")
            self.btn_toggle_all_names.setToolTip(i18n.t("wheel.deselect_all_tooltip"))
        else:
            self.btn_toggle_all_names.setText(f"☑ {i18n.t('wheel.select_all')}")
            self.btn_toggle_all_names.setToolTip(i18n.t("wheel.select_all_tooltip"))

    def _update_delete_marked_button_state(self):
        if not self.names.has_subroles or not self._enable_mark_for_delete:
            self.btn_delete_marked.setEnabled(False)
            self._set_delete_button_danger_state(False)
            return
        marked_count = len(self._marked_named_rows())
        enabled = bool(self._interaction_enabled) and marked_count > 0
        self.btn_delete_marked.setEnabled(enabled)
        self._set_delete_button_danger_state(enabled)
        if marked_count > 0:
            self.btn_delete_marked.setToolTip(i18n.t("names.delete_marked_tooltip_active", count=marked_count))
        else:
            self.btn_delete_marked.setToolTip(i18n.t("names.delete_marked_tooltip"))

    def _set_delete_button_danger_state(self, active: bool) -> None:
        target = bool(active)
        current = bool(self.btn_delete_marked.property("dangerActive"))
        if current == target:
            return
        self.btn_delete_marked.setProperty("dangerActive", target)
        theme = self._applied_theme
        if theme is None:
            theme_key = str(self._applied_theme_key or "light")
            theme = theme_util.get_theme(theme_key)
            self._applied_theme = theme
        self.btn_delete_marked.setStyleSheet(_delete_marked_button_style(theme, danger_active=target))
        self.btn_delete_marked.update()

    def _on_toggle_all_names_clicked(self):
        items = self._named_items()
        if not items:
            return
        target_checked = not self._all_named_items_checked()
        blockers = [
            QtCore.QSignalBlocker(self.names),
            QtCore.QSignalBlocker(self.names.model()),
        ]
        try:
            for item in items:
                widget = self.names.itemWidget(item)
                if _is_name_row_widget(widget):
                    widget.chk_active.setChecked(target_checked)
                else:
                    self.names.set_item_state(
                        item,
                        QtCore.Qt.Checked if target_checked else QtCore.Qt.Unchecked,
                    )
        finally:
            del blockers
        self.names.metaChanged.emit()
        self._update_toggle_all_button_label()

    def _on_sort_names_clicked(self):
        self.names.sort_alphabetically()

    def _on_delete_marked_clicked(self):
        rows = self._marked_named_rows()
        if not rows:
            return
        handler = self._delete_confirm_handler
        if handler is not None:
            try:
                if bool(handler(len(rows))):
                    return
            except Exception:
                pass
        self._confirm_delete_marked()

    def confirm_delete_marked(self):
        self._confirm_delete_marked()

    def _confirm_delete_marked(self):
        rows = self._marked_named_rows()
        if not rows:
            self._update_delete_marked_button_state()
            return
        self.names.remove_rows(rows, ensure_one_empty=True)
        self.names.metaChanged.emit()
        self._update_toggle_all_button_label()
        self._update_delete_marked_button_state()
