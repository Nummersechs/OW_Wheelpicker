from __future__ import annotations

import i18n
from PySide6 import QtWidgets

from utils import theme as theme_util


class MapUIEditorFlowController:
    def __init__(self, owner, editor_ctrl) -> None:
        self._owner = owner
        self._editor_ctrl = editor_ctrl

    def show_editor(self, parent_widget: QtWidgets.QWidget) -> None:
        owner = self._owner
        owner._styling.apply_theme_to_controls(theme_util.get_theme(owner.theme_key))
        self._editor_ctrl.show(parent_widget, owner.map_categories)

    def add_row(self) -> None:
        self._editor_ctrl.add_row()

    def delete_row(self) -> None:
        self._editor_ctrl.delete_row()

    def confirm(self) -> None:
        self._editor_ctrl.confirm()

    def start_edit(self, item: QtWidgets.QListWidgetItem) -> None:
        self._editor_ctrl.start_edit(item)

    def focus_editor_end(self) -> None:
        self._editor_ctrl.focus_editor_end()

    def update_language(self) -> None:
        (
            _editor_frame,
            editor_title,
            _editor_list,
            editor_add,
            editor_del,
            editor_ok,
            editor_cancel,
        ) = self._editor_ctrl.widgets()
        if editor_title is not None:
            editor_title.setText(i18n.t("map.editor.title"))
        if editor_add is not None:
            editor_add.setText(i18n.t("map.editor.add"))
            editor_add.setToolTip(i18n.t("map.editor.add_tooltip"))
        if editor_del is not None:
            editor_del.setText(i18n.t("map.editor.delete"))
            editor_del.setToolTip(i18n.t("map.editor.delete_tooltip"))
        if editor_ok is not None:
            editor_ok.setText(i18n.t("map.editor.apply"))
            editor_ok.setToolTip(i18n.t("map.editor.apply_tooltip"))
        if editor_cancel is not None:
            editor_cancel.setText(i18n.t("map.editor.cancel"))
            editor_cancel.setToolTip(i18n.t("map.editor.cancel_tooltip"))
        self._owner._styling.apply_map_editor_widths()

