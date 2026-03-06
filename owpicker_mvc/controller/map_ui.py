from __future__ import annotations

from typing import Dict
from PySide6 import QtCore, QtWidgets
import config
import i18n
from utils import qt_runtime, theme as theme_util, ui_helpers
from view import style_helpers, ui_tokens
from view.wheel_view import WheelView
from view.list_panel import ListPanel

_MAP_TYPE_LIST_STYLE_CACHE: dict[str, str] = {}
_MAP_NAMES_HINT_STYLE_CACHE: dict[str, str] = {}


def _map_type_list_style(theme: theme_util.Theme) -> str:
    cached = _MAP_TYPE_LIST_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QListWidget {"
        f" background:{theme.base}; color:{theme.text};"
        f" border:1px solid {theme.border}; border-radius:8px; padding:2px;"
        "}"
        f"QListWidget::item {{ color:{theme.text}; padding:4px 6px; border-radius:6px; }}"
        f"QListWidget::item:selected {{ background:{theme.primary}; color:{theme.button_text}; }}"
        f"QListWidget::item:hover {{ background:{theme.alt_base}; color:{theme.text}; }}"
        "QListWidget QLineEdit {"
        f" background:{theme.base}; color:{theme.text};"
        f" border:1px solid {theme.border}; border-radius:4px; padding:1px 4px;"
        "}"
    )
    _MAP_TYPE_LIST_STYLE_CACHE[theme.key] = cached
    return cached


def _map_names_hint_style(theme: theme_util.Theme) -> str:
    cached = _MAP_NAMES_HINT_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        f"color:{theme.muted_text};"
        " font-size:12px; padding:2px;"
        f" background:{theme.card_bg}; border:none;"
    )
    _MAP_NAMES_HINT_STYLE_CACHE[theme.key] = cached
    return cached


def _default_map_role_state() -> dict:
    return {"entries": [], "pair_mode": False, "use_subroles": False}


class MapUI(QtCore.QObject):
    """
    Kapselt die komplette Map-UI (Listen + zentrales Rad) aus MainWindow heraus.
    Stellt kombinierte Namen, State-Load/Save und Theme/Language-Hooks bereit.
    """

    stateChanged = QtCore.Signal()
    requestSpinCategory = QtCore.Signal(str)
    listsBuilt = QtCore.Signal()

    def __init__(self, state_store, language: str, theme_key: str, role_widgets: tuple, defer_lists: bool = False):
        super().__init__()
        self.state_store = state_store
        self.language = language
        self.theme_key = theme_key
        self._role_widgets = role_widgets  # (tank, dps, support)
        self._defer_list_build = bool(defer_lists)

        self.map_categories = list(getattr(config, "MAP_CATEGORIES", [])) or list(config.DEFAULT_MAPS.keys())
        self.map_lists: Dict[str, ListPanel] = {}
        self._map_combined: list[str] = []
        self._map_override_entries: list[dict] = []
        self._map_override_signature: tuple[str, ...] | None = None
        self._map_result_text = "–"
        self._active = True
        self._pending_rebuild = False
        self._pending_state_emit = False
        self._pending_wheel_refresh = False
        self._pending_list_categories: list[str] = []
        self._pending_list_state: dict = {}
        self._list_build_timer: QtCore.QTimer | None = None
        self._update_delay_ms = 140
        self._theme_apply_signature: tuple[str, int, bool] | None = None
        self._update_timer = QtCore.QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._flush_updates)
        self.container = self._build_ui()

    # ----- Build UI -----
    def _build_ui(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # --- Sidebar ---
        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("mapSidebar")
        sb_layout = QtWidgets.QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(
            ui_tokens.PANEL_CONTENT_MARGIN_H,
            ui_tokens.PANEL_CONTENT_MARGIN_V,
            ui_tokens.PANEL_CONTENT_MARGIN_H,
            ui_tokens.PANEL_CONTENT_MARGIN_V,
        )
        sb_layout.setSpacing(ui_tokens.PANEL_LAYOUT_SPACING)
        self.lbl_map_types = QtWidgets.QLabel(i18n.t("map.types"))
        style_helpers.apply_theme_roles(
            theme_util.get_theme(self.theme_key),
            ((self.lbl_map_types, "label.map_types"),),
        )
        sb_layout.addWidget(self.lbl_map_types)
        self.map_type_checks: dict[str, QtWidgets.QCheckBox] = {}
        self._map_type_list_layout = QtWidgets.QVBoxLayout()
        self._map_type_list_layout.setContentsMargins(0, 2, 0, 0)
        self._map_type_list_layout.setSpacing(ui_tokens.SECTION_SPACING)
        sb_layout.addLayout(self._map_type_list_layout)
        sb_layout.addSpacing(ui_tokens.SECTION_SPACING)
        self.btn_edit_map_types = QtWidgets.QPushButton(i18n.t("map.edit_types"))
        self.btn_edit_map_types.setToolTip(i18n.t("map.edit_types_tooltip"))
        self.btn_edit_map_types.clicked.connect(lambda: self._show_map_type_editor(container))
        self.btn_edit_map_types.setFocusPolicy(QtCore.Qt.ClickFocus)
        self._apply_map_control_widths()
        sb_layout.addWidget(self.btn_edit_map_types, 0, QtCore.Qt.AlignLeft)
        sb_layout.addStretch(1)
        self.map_sidebar = sidebar

        # --- Listen-Gitter rechts ---
        self.map_grid_container = QtWidgets.QWidget()
        self.map_grid_container.setObjectName("mapGridContainer")
        self.map_grid = QtWidgets.QVBoxLayout(self.map_grid_container)
        # Make only the inner right-side map canvas 10px narrower.
        self.map_grid.setContentsMargins(4, 4, 14, 4)
        self.map_grid.setSpacing(8)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.map_grid_container)
        scroll.setObjectName("mapListScroll")
        scroll.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.map_lists_frame = scroll
        right_wrap = QtWidgets.QWidget()
        right_wrap.setObjectName("mapListsWrapper")
        right_wrap_layout = QtWidgets.QVBoxLayout(right_wrap)
        right_wrap_layout.setSpacing(0)
        right_wrap_layout.addWidget(scroll)
        self.map_lists_wrapper = right_wrap

        # Listen initial erstellen
        map_state = self.state_store.get_mode_state("maps") or {}
        if self._defer_list_build:
            self._pending_list_state = map_state
            QtCore.QTimer.singleShot(0, self._start_list_build)
        else:
            self._build_map_lists(map_state)

        # zentrales Map-Rad
        self.map_main = WheelView("Map-Rad", [], pair_mode=False, allow_pair_toggle=False, title_key="map.wheel_title")
        self.map_main.set_header_controls_visible(False)
        self.map_main.set_subrole_controls_visible(False)
        self.map_main.set_show_names_visible(True)
        self.map_main.btn_include_in_all.setVisible(False)
        self.map_main.btn_local_spin.setText(i18n.t("wheel.spin_map"))
        self.map_main.names_hint.setVisible(False)
        if hasattr(self.map_main, "names_panel"):
            self.map_main.names_panel.setVisible(False)
        else:
            self.map_main.names.setVisible(False)
        self.map_main.result_widget.setVisible(False)
        self.map_main.btn_local_spin.setVisible(False)

        base_canvas = max(200, int(2 * config.WHEEL_RADIUS + 80))
        self.map_main.view.setMinimumSize(base_canvas, base_canvas)
        self.map_main.view.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.map_main.view.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.map_main.btn_local_spin.setFocusPolicy(QtCore.Qt.ClickFocus)

        # Gesamt-Layout
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(sidebar, 0)
        row.addWidget(self.map_main, 0, QtCore.Qt.AlignCenter)
        row.addWidget(right_wrap, 1)
        row.setStretch(0, 1)
        row.setStretch(1, 9)
        row.setStretch(2, 9)
        layout.addLayout(row, 1)
        layout.setStretchFactor(row, 1)
        QtCore.QTimer.singleShot(0, self._cap_heights)
        if not self._defer_list_build:
            QtCore.QTimer.singleShot(0, lambda: self.rebuild_combined(emit_state=False, force_wheel=True))
        return container

    # ----- Map lists -----
    def _clear_map_lists(self) -> None:
        # Clear existing list panels
        while self.map_grid.count():
            item = self.map_grid.takeAt(0)
            w = item.widget()
            if w:
                # Disconnect dynamic height callbacks first so no stale callbacks
                # keep removed panels alive or refresh deleted widgets.
                names_canvas = getattr(w, "names", None)
                callback = getattr(names_canvas, "_map_dynamic_height_callback", None)
                if isinstance(names_canvas, QtWidgets.QListWidget) and callable(callback):
                    model = names_canvas.model()
                    if model is not None:
                        for sig_name in ("rowsInserted", "rowsRemoved", "modelReset"):
                            sig = getattr(model, sig_name, None)
                            if sig is None:
                                continue
                            try:
                                sig.disconnect(callback)
                            except Exception:
                                pass
                    try:
                        setattr(names_canvas, "_map_dynamic_height_callback", None)
                    except Exception:
                        pass
                try:
                    w.hide()
                except Exception:
                    pass
                w.deleteLater()
            del item
        self.map_lists.clear()
        # Clear sidebar checks
        while self._map_type_list_layout.count():
            item = self._map_type_list_layout.takeAt(0)
            w = item.widget()
            if w:
                try:
                    w.hide()
                except Exception:
                    pass
                w.deleteLater()
            del item
        self.map_type_checks.clear()

    def _map_list_target_names_height(self, wheel: ListPanel) -> int | None:
        names_canvas = getattr(wheel, "names", None)
        if not isinstance(names_canvas, QtWidgets.QListWidget):
            return None
        try:
            row_height = int(names_canvas.sizeHintForRow(0))
        except Exception:
            row_height = 0
        if row_height <= 0:
            row_height = max(18, int(getattr(names_canvas, "_row_height", 20)))
        row_count = max(1, int(names_canvas.count()))
        min_rows = max(1, int(getattr(config, "MAP_LIST_NAMES_MIN_VISIBLE_ROWS", 2)))
        max_rows = max(min_rows, int(getattr(config, "MAP_LIST_NAMES_MAX_VISIBLE_ROWS", 6)))
        visible_rows = max(min_rows, min(row_count, max_rows))
        frame = max(0, int(names_canvas.frameWidth()) * 2)
        extra_padding = max(0, int(getattr(config, "MAP_LIST_NAMES_EXTRA_PADDING_PX", 8)))
        target = int((visible_rows * row_height) + frame + extra_padding)
        return max(40, target)

    def _apply_dynamic_map_list_height(self, wheel: ListPanel) -> None:
        names_canvas = getattr(wheel, "names", None)
        if not isinstance(names_canvas, QtWidgets.QListWidget):
            return
        target_height = self._map_list_target_names_height(wheel)
        if target_height is None:
            return
        names_canvas.setMinimumHeight(target_height)
        names_canvas.setMaximumHeight(target_height)

    def _bind_dynamic_map_list_height(self, wheel: ListPanel) -> None:
        names_canvas = getattr(wheel, "names", None)
        if not isinstance(names_canvas, QtWidgets.QListWidget):
            return
        if bool(getattr(names_canvas, "_map_dynamic_height_bound", False)):
            return
        setattr(names_canvas, "_map_dynamic_height_bound", True)

        def _schedule_resize(*_args, _wheel=wheel):
            QtCore.QTimer.singleShot(0, lambda w=_wheel: self._apply_dynamic_map_list_height(w))

        setattr(names_canvas, "_map_dynamic_height_callback", _schedule_resize)
        model = names_canvas.model()
        if model is not None:
            model.rowsInserted.connect(_schedule_resize)
            model.rowsRemoved.connect(_schedule_resize)
            model.modelReset.connect(_schedule_resize)
        _schedule_resize()

    def _add_map_list(self, cat: str, role_state: dict) -> None:
        include_checked = role_state.get("include_in_all", True)
        parent = getattr(self, "map_grid_container", None)
        w = ListPanel(cat, role_state.get("entries", []), parent=parent)
        w.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self._bind_dynamic_map_list_height(w)
        w.set_spin_button_text(i18n.t("wheel.spin_single_map"))
        w.set_language(self.language)
        w.set_interactive_enabled(include_checked)
        w.setVisible(include_checked)
        w.btn_include_in_all.setChecked(include_checked)
        w.btn_include_in_all.setVisible(False)
        if hasattr(w, "names_panel"):
            w.names_panel.set_auto_focus_enabled(False)
            if hasattr(w.names_panel, "set_compact_vertical"):
                try:
                    w.names_panel.set_compact_vertical(True)
                except Exception:
                    pass
        w.btn_local_spin.setFocusPolicy(QtCore.Qt.ClickFocus)
        w.btn_include_in_all.setFocusPolicy(QtCore.Qt.ClickFocus)
        if hasattr(w, "names"):
            w.names.setFocusPolicy(QtCore.Qt.ClickFocus)
        if hasattr(w, "btn_sort_names"):
            w.btn_sort_names.setFocusPolicy(QtCore.Qt.ClickFocus)
        if hasattr(w, "btn_toggle_all_names"):
            w.btn_toggle_all_names.setFocusPolicy(QtCore.Qt.ClickFocus)
        w.btn_include_in_all.toggled.connect(lambda checked, c=cat: self._on_list_include_toggled(c, checked))
        w.stateChanged.connect(self._schedule_update)
        w.request_spin.connect(lambda _=None, c=cat: self.requestSpinCategory.emit(c))
        self.map_lists[cat] = w
        self.map_grid.addWidget(w, 0, QtCore.Qt.AlignTop)

        cb = QtWidgets.QCheckBox(cat)
        cb.setChecked(include_checked)
        cb.setFocusPolicy(QtCore.Qt.ClickFocus)
        cb.toggled.connect(lambda checked, c=cat: self._on_map_type_toggled(c, checked))
        self.map_type_checks[cat] = cb
        self._map_type_list_layout.addWidget(cb)

    def _build_map_lists(self, map_state: dict):
        self._clear_map_lists()
        for cat in self.map_categories:
            role_state = map_state.get(cat) or _default_map_role_state()
            self._add_map_list(cat, role_state)
        self.map_grid.addStretch(1)
        self._map_type_list_layout.addStretch(1)
        self._theme_apply_signature = None
        self.apply_theme(theme_util.get_theme(self.theme_key))
        self.listsBuilt.emit()

    def _start_list_build(self):
        self._clear_map_lists()
        self._pending_list_categories = list(self.map_categories)
        if self._list_build_timer is None:
            self._list_build_timer = QtCore.QTimer(self)
            self._list_build_timer.setSingleShot(True)
            self._list_build_timer.timeout.connect(self._build_list_step)
        self._list_build_timer.start(0)

    def _build_list_step(self):
        if not self._pending_list_categories:
            self.map_grid.addStretch(1)
            self._map_type_list_layout.addStretch(1)
            self.rebuild_combined(emit_state=False, force_wheel=True)
            self._theme_apply_signature = None
            self.apply_theme(theme_util.get_theme(self.theme_key))
            self.listsBuilt.emit()
            return
        # Build one category per tick to keep UI responsive
        cat = self._pending_list_categories.pop(0)
        role_state = self._pending_list_state.get(cat) or _default_map_role_state()
        self._add_map_list(cat, role_state)
        if self._list_build_timer is not None:
            self._list_build_timer.start(0)

    def _on_map_type_toggled(self, category: str, checked: bool):
        wheel = self.map_lists.get(category)
        if wheel:
            wheel.btn_include_in_all.setChecked(checked)
            wheel.setVisible(checked)
            wheel.set_interactive_enabled(checked)
        # Rebuild kommt über stateChanged des ListPanels.

    def _on_list_include_toggled(self, category: str, checked: bool):
        if cb := self.map_type_checks.get(category):
            if cb.isChecked() != checked:
                blocker = QtCore.QSignalBlocker(cb)
                cb.setChecked(checked)
                del blocker
        wheel = self.map_lists.get(category)
        if wheel:
            wheel.setVisible(checked)
            wheel.set_interactive_enabled(checked)

    # ----- Map-Type-Editor -----
    def _show_map_type_editor(self, parent_widget: QtWidgets.QWidget):
        if not hasattr(self, "_map_type_editor"):
            self._map_type_editor = QtWidgets.QFrame(parent_widget)
            self._map_type_editor.setFixedSize(360, 320)
            layout = QtWidgets.QVBoxLayout(self._map_type_editor)
            layout.setContentsMargins(
                ui_tokens.PANEL_CONTENT_MARGIN_H,
                ui_tokens.PANEL_CONTENT_MARGIN_V,
                ui_tokens.PANEL_CONTENT_MARGIN_H,
                ui_tokens.PANEL_CONTENT_MARGIN_V,
            )
            layout.setSpacing(ui_tokens.PANEL_LAYOUT_SPACING)
            self._map_type_editor_title = QtWidgets.QLabel(i18n.t("map.editor.title"))
            layout.addWidget(self._map_type_editor_title)

            self._map_type_list_widget = QtWidgets.QListWidget()
            self._map_type_list_widget.setEditTriggers(
                QtWidgets.QAbstractItemView.SelectedClicked
                | QtWidgets.QAbstractItemView.EditKeyPressed
            )
            self._map_type_list_widget.itemClicked.connect(self._start_map_type_edit)
            layout.addWidget(self._map_type_list_widget, 1)

            btn_grid = QtWidgets.QGridLayout()
            btn_grid.setContentsMargins(16, ui_tokens.SECTION_SPACING + 2, 16, 8)
            btn_grid.setHorizontalSpacing(16)
            self._map_type_btn_add = QtWidgets.QPushButton(i18n.t("map.editor.add"))
            self._map_type_btn_del = QtWidgets.QPushButton(i18n.t("map.editor.delete"))
            self._map_type_btn_add.setToolTip(i18n.t("map.editor.add_tooltip"))
            self._map_type_btn_del.setToolTip(i18n.t("map.editor.delete_tooltip"))
            self._map_type_btn_add.clicked.connect(self._add_map_type_row)
            self._map_type_btn_del.clicked.connect(self._del_map_type_row)
            btn_grid.addWidget(self._map_type_btn_add, 0, 0, QtCore.Qt.AlignLeft)
            btn_grid.addWidget(self._map_type_btn_del, 0, 1, QtCore.Qt.AlignRight)
            btn_grid.setColumnStretch(0, 1)
            btn_grid.setColumnStretch(1, 1)
            layout.addLayout(btn_grid)

            confirm_row = QtWidgets.QHBoxLayout()
            confirm_row.setContentsMargins(16, ui_tokens.SECTION_SPACING + 2, 16, 8)
            self._map_type_btn_ok = QtWidgets.QPushButton(i18n.t("map.editor.apply"))
            self._map_type_btn_cancel = QtWidgets.QPushButton(i18n.t("map.editor.cancel"))
            self._map_type_btn_ok.setToolTip(i18n.t("map.editor.apply_tooltip"))
            self._map_type_btn_cancel.setToolTip(i18n.t("map.editor.cancel_tooltip"))
            self._map_type_btn_ok.clicked.connect(self._confirm_map_types)
            self._map_type_btn_cancel.clicked.connect(lambda: self._map_type_editor.hide())
            confirm_row.addWidget(self._map_type_btn_ok)
            confirm_row.addStretch(1)
            confirm_row.addWidget(self._map_type_btn_cancel)
            layout.addLayout(confirm_row)
            self._apply_map_editor_widths()

        self._apply_theme_to_map_controls(theme_util.get_theme(self.theme_key))

        # Inhalte aktualisieren
        self._map_type_list_widget.clear()
        for cat in self.map_categories:
            item = QtWidgets.QListWidgetItem(cat)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
            self._map_type_list_widget.addItem(item)

        # Frame mittig im Parent platzieren
        if parent_widget:
            pw = parent_widget.width()
            ph = parent_widget.height()
            w = self._map_type_editor.width()
            h = self._map_type_editor.height()
            self._map_type_editor.move(max(0, (pw - w) // 2), max(0, (ph - h) // 2))
        self._map_type_editor.show()
        qt_runtime.safe_raise(self._map_type_editor)

    def _add_map_type_row(self):
        if hasattr(self, "_map_type_list_widget"):
            item = QtWidgets.QListWidgetItem(i18n.t("map.editor.new_type"))
            item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
            self._map_type_list_widget.addItem(item)
            self._map_type_list_widget.setCurrentItem(item)
            self._start_map_type_edit(item)

    def _del_map_type_row(self):
        if hasattr(self, "_map_type_list_widget"):
            row = self._map_type_list_widget.currentRow()
            if row >= 0:
                self._map_type_list_widget.takeItem(row)

    def _confirm_map_types(self):
        if not hasattr(self, "_map_type_list_widget"):
            return
        new_types = []
        for i in range(self._map_type_list_widget.count()):
            text = self._map_type_list_widget.item(i).text().strip()
            if text and text not in new_types:
                new_types.append(text)
        if not new_types:
            self._map_type_editor.hide()
            return
        QtCore.QTimer.singleShot(0, lambda: self._apply_map_types(new_types))
        self._map_type_editor.hide()

    def _start_map_type_edit(self, item: QtWidgets.QListWidgetItem):
        if not item:
            return
        self._map_type_list_widget.editItem(item)
        QtCore.QTimer.singleShot(0, lambda: self._focus_editor_end())

    def _focus_editor_end(self):
        editors = self._map_type_list_widget.findChildren(QtWidgets.QLineEdit)
        if not editors:
            return
        editor = editors[-1]
        # Kein erzwungener Fokus
        editor.deselect()
        editor.setCursorPosition(len(editor.text()))

    def _apply_map_types(self, new_types: list[str]):
        current_states = {}
        include_map = {}
        for cat, wheel in getattr(self, "map_lists", {}).items():
            current_states[cat] = {
                "entries": wheel.get_current_entries(),
                "pair_mode": False,
                "use_subroles": False,
            }
            include_map[cat] = wheel.btn_include_in_all.isChecked()

        saved_state = self.state_store.get_mode_state("maps") or {}

        new_state = {}
        new_include_map = {}
        old_categories = list(self.map_categories)
        for idx, cat in enumerate(new_types):
            if cat in current_states:
                new_state[cat] = current_states[cat]
                new_include_map[cat] = include_map.get(cat, True)
            elif cat in saved_state:
                new_state[cat] = saved_state[cat]
                new_include_map[cat] = True
            elif idx < len(old_categories):
                old_cat = old_categories[idx]
                st = current_states.get(old_cat) or saved_state.get(old_cat)
                if st:
                    new_state[cat] = st
                    new_include_map[cat] = include_map.get(old_cat, True)
                else:
                    new_state[cat] = _default_map_role_state()
                    new_include_map[cat] = True
            else:
                new_state[cat] = _default_map_role_state()
                new_include_map[cat] = True

        self.map_categories = list(new_types)
        self._build_map_lists(new_state)
        for cat, wheel in self.map_lists.items():
            wheel.btn_include_in_all.setChecked(new_include_map.get(cat, True))
            wheel.set_interactive_enabled(wheel.btn_include_in_all.isChecked())
            wheel.setVisible(wheel.btn_include_in_all.isChecked())
            if cb := self.map_type_checks.get(cat):
                cb.setChecked(wheel.btn_include_in_all.isChecked())
        self.rebuild_combined(emit_state=True, force_wheel=True)

    # ----- State / Language / Theme -----
    def set_language(self, lang: str):
        self.language = lang
        i18n.set_language(lang)
        self.lbl_map_types.setText(i18n.t("map.types"))
        if hasattr(self, "btn_edit_map_types"):
            self.btn_edit_map_types.setText(i18n.t("map.edit_types"))
            self.btn_edit_map_types.setToolTip(i18n.t("map.edit_types_tooltip"))
        self._apply_map_control_widths()
        for w in self.map_lists.values():
            w.set_language(lang)
            w.set_spin_button_text(i18n.t("wheel.spin_single_map"))
        self.map_main.set_language(lang)
        self.map_main.set_spin_button_text(i18n.t("wheel.spin_map"))
        # Editor-Texte aktualisieren
        if hasattr(self, "_map_type_editor_title"):
            self._map_type_editor_title.setText(i18n.t("map.editor.title"))
        if hasattr(self, "_map_type_btn_add"):
            self._map_type_btn_add.setText(i18n.t("map.editor.add"))
            self._map_type_btn_add.setToolTip(i18n.t("map.editor.add_tooltip"))
        if hasattr(self, "_map_type_btn_del"):
            self._map_type_btn_del.setText(i18n.t("map.editor.delete"))
            self._map_type_btn_del.setToolTip(i18n.t("map.editor.delete_tooltip"))
        if hasattr(self, "_map_type_btn_ok"):
            self._map_type_btn_ok.setText(i18n.t("map.editor.apply"))
            self._map_type_btn_ok.setToolTip(i18n.t("map.editor.apply_tooltip"))
        if hasattr(self, "_map_type_btn_cancel"):
            self._map_type_btn_cancel.setText(i18n.t("map.editor.cancel"))
            self._map_type_btn_cancel.setToolTip(i18n.t("map.editor.cancel_tooltip"))
        self._apply_map_editor_widths()

    def _apply_map_control_widths(self) -> None:
        ui_helpers.set_fixed_width_from_translations([self.lbl_map_types], ["map.types"], padding=30)
        if hasattr(self, "btn_edit_map_types"):
            ui_helpers.set_fixed_width_from_translations([self.btn_edit_map_types], ["map.edit_types"], padding=48)

    def _apply_map_editor_widths(self) -> None:
        if hasattr(self, "_map_type_editor_title"):
            ui_helpers.set_fixed_width_from_translations([self._map_type_editor_title], ["map.editor.title"], padding=28)
        if hasattr(self, "_map_type_btn_add") and hasattr(self, "_map_type_btn_del"):
            ui_helpers.set_fixed_width_from_translations(
                [self._map_type_btn_add, self._map_type_btn_del],
                ["map.editor.add", "map.editor.delete"],
                padding=40,
            )
        if hasattr(self, "_map_type_btn_ok") and hasattr(self, "_map_type_btn_cancel"):
            ui_helpers.set_fixed_width_from_translations(
                [self._map_type_btn_ok, self._map_type_btn_cancel],
                ["map.editor.apply", "map.editor.cancel"],
                padding=44,
            )

    def _apply_theme_to_map_controls(self, theme: theme_util.Theme):
        style_helpers.apply_theme_roles(
            theme,
            (
                (self.lbl_map_types, "label.map_types"),
                (getattr(self, "btn_edit_map_types", None), "button.primary"),
            ),
        )
        if hasattr(self, "_map_type_editor"):
            style_helpers.apply_theme_roles(
                theme,
                (
                    (self._map_type_editor, "frame.editor_dialog"),
                    (getattr(self, "_map_type_editor_title", None), "label.editor_title"),
                ),
            )
            style_helpers.set_stylesheet_if_needed(
                getattr(self, "_map_type_list_widget", None),
                f"map_editor_list:{theme.key}",
                _map_type_list_style(theme),
            )
            style_helpers.apply_theme_roles(
                theme,
                (
                    (getattr(self, "_map_type_btn_add", None), "button.primary"),
                    (getattr(self, "_map_type_btn_del", None), "button.danger"),
                    (getattr(self, "_map_type_btn_ok", None), "button.success"),
                    (getattr(self, "_map_type_btn_cancel", None), "button.primary"),
                ),
            )

    def apply_theme(self, theme: theme_util.Theme):
        signature = (theme.key, len(self.map_lists), bool(hasattr(self, "_map_type_editor")))
        if self._theme_apply_signature == signature:
            return
        self.theme_key = theme.key
        if hasattr(self, "map_main") and hasattr(self.map_main, "apply_theme"):
            self.map_main.apply_theme(theme)
        for w in self.map_lists.values():
            w.apply_theme(theme)
            style_helpers.set_stylesheet_if_needed(
                getattr(w, "names_hint", None),
                f"map_names_hint:{theme.key}",
                _map_names_hint_style(theme),
            )
        self._apply_theme_to_map_controls(theme)
        self._refresh_palette_backed_widgets()
        self._theme_apply_signature = signature

    def _refresh_palette_backed_widgets(self) -> None:
        """Force repolish for widgets that depend on global palette(...) rules."""
        targets: list[QtWidgets.QWidget] = [
            getattr(self, "container", None),
            getattr(self, "map_sidebar", None),
            getattr(self, "map_grid_container", None),
            getattr(self, "map_lists_wrapper", None),
            getattr(self, "map_lists_frame", None),
        ]
        targets.extend(self.map_type_checks.values())
        for widget in targets:
            if not isinstance(widget, QtWidgets.QWidget):
                continue
            style = widget.style()
            if style is None:
                widget.update()
                continue
            try:
                style.unpolish(widget)
                style.polish(widget)
            except Exception:
                pass
            widget.update()

    def load_state(self):
        state = self.state_store.get_mode_state("maps") or {}
        for cat, wheel in self.map_lists.items():
            role_state = state.get(cat) or self.state_store.default_role_state(cat, "maps")
            wheel.load_entries(role_state.get("entries", []))
            wheel.btn_include_in_all.setChecked(role_state.get("include_in_all", True))
            wheel.set_interactive_enabled(wheel.btn_include_in_all.isChecked())
            wheel.setVisible(wheel.btn_include_in_all.isChecked())
            if cb := self.map_type_checks.get(cat):
                cb.setChecked(wheel.btn_include_in_all.isChecked())
        self.rebuild_combined(emit_state=False, force_wheel=True)

    def capture_state(self):
        payload = {}
        for cat, wheel in self.map_lists.items():
            payload[cat] = {
                "entries": wheel.get_current_entries(),
                "pair_mode": False,
                "use_subroles": False,
                "include_in_all": wheel.btn_include_in_all.isChecked(),
            }
        self.state_store.set_mode_state("maps", payload)

    # ----- Data helpers -----
    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        if self._active:
            if self._pending_rebuild or self._pending_wheel_refresh:
                emit_state = bool(self._pending_state_emit)
                self.rebuild_combined(emit_state=emit_state, force_wheel=True)
            self._pending_rebuild = False
            self._pending_state_emit = False
        else:
            if self._update_timer.isActive():
                self._update_timer.stop()

    def shutdown(self) -> None:
        """Stop internal timers and prevent further wheel updates."""
        self.set_active(False)
        if self._update_timer.isActive():
            self._update_timer.stop()
        if self._list_build_timer is not None and self._list_build_timer.isActive():
            self._list_build_timer.stop()
        self._pending_list_categories = []
        self._pending_rebuild = False
        self._pending_state_emit = False

    def resource_snapshot(self) -> dict:
        update_timer_active = False
        list_build_timer_active = False
        try:
            update_timer_active = bool(self._update_timer.isActive())
        except Exception:
            pass
        if self._list_build_timer is not None:
            try:
                list_build_timer_active = bool(self._list_build_timer.isActive())
            except Exception:
                pass
        return {
            "active": bool(self._active),
            "map_lists": len(self.map_lists),
            "pending_rebuild": bool(self._pending_rebuild),
            "pending_state_emit": bool(self._pending_state_emit),
            "pending_wheel_refresh": bool(self._pending_wheel_refresh),
            "pending_list_categories": len(self._pending_list_categories),
            "update_timer_active": update_timer_active,
            "list_build_timer_active": list_build_timer_active,
        }

    def _schedule_update(self):
        if not self._active:
            # Defer expensive merge work while maps mode is inactive.
            self._pending_rebuild = True
            self._pending_wheel_refresh = True
            self._pending_state_emit = True
            return
        self._pending_rebuild = True
        self._pending_state_emit = True
        if not self._update_timer.isActive():
            self._update_timer.start(self._update_delay_ms)

    def _flush_updates(self):
        if not self._pending_rebuild:
            return
        emit_state = self._pending_state_emit
        self._pending_rebuild = False
        self._pending_state_emit = False
        self._apply_combined_update(emit_state=emit_state, force_wheel=False)

    def _apply_combined_update(self, emit_state: bool, force_wheel: bool):
        combined: list[str] = []
        for wheel in self.map_lists.values():
            if not wheel.btn_include_in_all.isChecked():
                continue
            for entry in wheel.get_active_entries():
                name = entry.get("name", "").strip()
                if name:
                    combined.append(name)
        changed = combined != self._map_combined
        if changed:
            self._map_combined = combined
            self._map_override_entries = [
                {"name": name, "subroles": [], "active": True}
                for name in combined
            ]
        combined_sig = tuple(self._map_combined)
        if changed or force_wheel or self._pending_wheel_refresh:
            if hasattr(self, "map_main") and (self._active or force_wheel):
                needs_push = (
                    force_wheel
                    or
                    changed
                    or self._pending_wheel_refresh
                    or self._map_override_signature != combined_sig
                )
                if needs_push:
                    self.map_main.set_override_entries(self._map_override_entries)
                    self._map_override_signature = combined_sig
                self._pending_wheel_refresh = False
            else:
                self._pending_wheel_refresh = True
        if emit_state:
            self.stateChanged.emit()

    def rebuild_combined(self, emit_state: bool = True, force_wheel: bool = False):
        if self._update_timer.isActive():
            self._update_timer.stop()
        self._pending_rebuild = False
        self._pending_state_emit = False
        self._apply_combined_update(emit_state=emit_state, force_wheel=force_wheel)

    def combined_names(self) -> list[str]:
        return list(self._map_combined)

    def names_for_category(self, category: str) -> list[str]:
        wheel = self.map_lists.get(category)
        if not wheel:
            return []
        return [e.get("name", "").strip() for e in wheel.get_active_entries() if e.get("name", "").strip()]

    # ----- Sizing -----
    def _cap_heights(self):
        if not self._role_widgets or not isinstance(self._role_widgets, tuple):
            return
        tank, dps, support = self._role_widgets
        ref_h = max(
            200,
            tank.height() or tank.sizeHint().height(),
            dps.height() or dps.sizeHint().height(),
            support.height() or support.sizeHint().height(),
        )
        ref_w = max(
            self.map_main.view.minimumWidth(),
            self.map_main.view.sizeHint().width() or 0,
            int(2 * config.WHEEL_RADIUS + 80),
        )
        self.map_main.view.setMinimumHeight(ref_h)
        self.map_main.view.setMinimumWidth(ref_w)
        self.map_main.view.setMaximumWidth(ref_w + 200)
        self.map_main.view.setMaximumHeight(ref_h + 80)
        self.map_main.setMinimumHeight(ref_h)
        self.map_main.setMinimumWidth(ref_w)
        self.map_main.setMaximumHeight(ref_h + 80)
        self.map_main.setMaximumWidth(ref_w + 200)
        if hasattr(self, "map_lists_frame"):
            adj = max(100, ref_h - 20)
            self.map_lists_frame.setMinimumHeight(adj)
            self.map_lists_frame.setMaximumHeight(ref_h + 80)
        if hasattr(self, "map_lists_wrapper"):
            adj = max(100, ref_h - 20)
            self.map_lists_wrapper.setMinimumHeight(adj)
            self.map_lists_wrapper.setMaximumHeight(ref_h + 80)
        if hasattr(self, "map_sidebar"):
            adj = max(100, ref_h - 20)
            self.map_sidebar.setMinimumHeight(adj)
            self.map_sidebar.setMaximumHeight(ref_h + 80)

    def set_interactive_enabled(self, en: bool):
        for wheel in self.map_lists.values():
            wheel.set_interactive_enabled(en)
        if hasattr(self, "map_main"):
            self.map_main.set_interactive_enabled(en)
