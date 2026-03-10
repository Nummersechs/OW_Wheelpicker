from __future__ import annotations

from typing import Callable
from PySide6 import QtCore, QtWidgets

import i18n
from utils import qt_runtime
from view import ui_tokens

from .categories import unique_non_empty_labels


class MapTypeEditorController:
    """Owns map-type editor widget lifecycle and user actions."""

    def __init__(
        self,
        *,
        on_confirm_types: Callable[[list[str]], None],
        apply_editor_widths: Callable[[], None] | None = None,
    ) -> None:
        self._on_confirm_types = on_confirm_types
        self._apply_editor_widths = apply_editor_widths
        self._frame: QtWidgets.QFrame | None = None
        self._title: QtWidgets.QLabel | None = None
        self._list_widget: QtWidgets.QListWidget | None = None
        self._btn_add: QtWidgets.QPushButton | None = None
        self._btn_del: QtWidgets.QPushButton | None = None
        self._btn_ok: QtWidgets.QPushButton | None = None
        self._btn_cancel: QtWidgets.QPushButton | None = None

    def exists(self) -> bool:
        return self._frame is not None

    def widgets(
        self,
    ) -> tuple[
        QtWidgets.QFrame | None,
        QtWidgets.QLabel | None,
        QtWidgets.QListWidget | None,
        QtWidgets.QPushButton | None,
        QtWidgets.QPushButton | None,
        QtWidgets.QPushButton | None,
        QtWidgets.QPushButton | None,
    ]:
        return (
            self._frame,
            self._title,
            self._list_widget,
            self._btn_add,
            self._btn_del,
            self._btn_ok,
            self._btn_cancel,
        )

    def _ensure(self, parent_widget: QtWidgets.QWidget) -> None:
        if self._frame is not None:
            return
        frame = QtWidgets.QFrame(parent_widget)
        frame.setFixedSize(360, 320)
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(
            ui_tokens.PANEL_CONTENT_MARGIN_H,
            ui_tokens.PANEL_CONTENT_MARGIN_V,
            ui_tokens.PANEL_CONTENT_MARGIN_H,
            ui_tokens.PANEL_CONTENT_MARGIN_V,
        )
        layout.setSpacing(ui_tokens.PANEL_LAYOUT_SPACING)

        title = QtWidgets.QLabel(i18n.t("map.editor.title"))
        layout.addWidget(title)

        list_widget = QtWidgets.QListWidget()
        list_widget.setEditTriggers(
            QtWidgets.QAbstractItemView.SelectedClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        list_widget.itemClicked.connect(self.start_edit)
        layout.addWidget(list_widget, 1)

        btn_grid = QtWidgets.QGridLayout()
        btn_grid.setContentsMargins(16, ui_tokens.SECTION_SPACING + 2, 16, 8)
        btn_grid.setHorizontalSpacing(16)
        btn_add = QtWidgets.QPushButton(i18n.t("map.editor.add"))
        btn_del = QtWidgets.QPushButton(i18n.t("map.editor.delete"))
        btn_add.setToolTip(i18n.t("map.editor.add_tooltip"))
        btn_del.setToolTip(i18n.t("map.editor.delete_tooltip"))
        btn_add.clicked.connect(self.add_row)
        btn_del.clicked.connect(self.delete_row)
        btn_grid.addWidget(btn_add, 0, 0, QtCore.Qt.AlignLeft)
        btn_grid.addWidget(btn_del, 0, 1, QtCore.Qt.AlignRight)
        btn_grid.setColumnStretch(0, 1)
        btn_grid.setColumnStretch(1, 1)
        layout.addLayout(btn_grid)

        confirm_row = QtWidgets.QHBoxLayout()
        confirm_row.setContentsMargins(16, ui_tokens.SECTION_SPACING + 2, 16, 8)
        btn_ok = QtWidgets.QPushButton(i18n.t("map.editor.apply"))
        btn_cancel = QtWidgets.QPushButton(i18n.t("map.editor.cancel"))
        btn_ok.setToolTip(i18n.t("map.editor.apply_tooltip"))
        btn_cancel.setToolTip(i18n.t("map.editor.cancel_tooltip"))
        btn_ok.clicked.connect(self.confirm)
        btn_cancel.clicked.connect(self.hide)
        confirm_row.addWidget(btn_ok)
        confirm_row.addStretch(1)
        confirm_row.addWidget(btn_cancel)
        layout.addLayout(confirm_row)

        self._frame = frame
        self._title = title
        self._list_widget = list_widget
        self._btn_add = btn_add
        self._btn_del = btn_del
        self._btn_ok = btn_ok
        self._btn_cancel = btn_cancel
        if callable(self._apply_editor_widths):
            self._apply_editor_widths()

    def show(self, parent_widget: QtWidgets.QWidget, categories: list[str]) -> None:
        self._ensure(parent_widget)
        if self._list_widget is None or self._frame is None:
            return
        self._list_widget.clear()
        for category in categories:
            item = QtWidgets.QListWidgetItem(category)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
            self._list_widget.addItem(item)

        if parent_widget:
            pw = parent_widget.width()
            ph = parent_widget.height()
            w = self._frame.width()
            h = self._frame.height()
            self._frame.move(max(0, (pw - w) // 2), max(0, (ph - h) // 2))
        self._frame.show()
        qt_runtime.safe_raise(self._frame)

    def hide(self) -> None:
        if self._frame is not None:
            self._frame.hide()

    def add_row(self) -> None:
        if self._list_widget is None:
            return
        item = QtWidgets.QListWidgetItem(i18n.t("map.editor.new_type"))
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        self._list_widget.addItem(item)
        self._list_widget.setCurrentItem(item)
        self.start_edit(item)

    def delete_row(self) -> None:
        if self._list_widget is None:
            return
        row = self._list_widget.currentRow()
        if row >= 0:
            self._list_widget.takeItem(row)

    def confirm(self) -> None:
        if self._list_widget is None:
            return
        labels = [self._list_widget.item(i).text() for i in range(self._list_widget.count())]
        new_types = unique_non_empty_labels(labels)
        if not new_types:
            self.hide()
            return
        QtCore.QTimer.singleShot(0, lambda: self._on_confirm_types(new_types))
        self.hide()

    def start_edit(self, item: QtWidgets.QListWidgetItem) -> None:
        if item is None or self._list_widget is None:
            return
        self._list_widget.editItem(item)
        QtCore.QTimer.singleShot(0, self.focus_editor_end)

    def focus_editor_end(self) -> None:
        if self._list_widget is None:
            return
        editors = self._list_widget.findChildren(QtWidgets.QLineEdit)
        if not editors:
            return
        editor = editors[-1]
        editor.deselect()
        editor.setCursorPosition(len(editor.text()))
