from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from utils import qt_runtime
from utils import theme as theme_util

_HEADER_STYLE_CACHE: dict[str, str] = {}
_NAME_EDIT_STYLE_CACHE: dict[str, str] = {}
_TOGGLE_STYLE_CACHE: dict[str, str] = {}
_POPUP_STYLE_CACHE: dict[str, str] = {}
_LIST_STYLE_CACHE: dict[str, str] = {}


def _rgba(color_value: str, alpha: float) -> str:
    color = QtGui.QColor(str(color_value or ""))
    if not color.isValid():
        color = QtGui.QColor("#4080ff")
    alpha_ch = max(0, min(255, int(round(float(alpha) * 255.0))))
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha_ch})"


def _header_style(theme: theme_util.Theme) -> str:
    cached = _HEADER_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QFrame#profileHeader {"
        f" background:{theme.base}; border:1px solid {theme.border}; border-radius:10px;"
        "}"
    )
    _HEADER_STYLE_CACHE[theme.key] = cached
    return cached


def _name_edit_style(theme: theme_util.Theme) -> str:
    cached = _NAME_EDIT_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QLineEdit {"
        " border:0; background:transparent; padding:0 4px 0 2px;"
        f" color:{theme.text}; font-size:13px; font-weight:600;"
        f" selection-background-color: {_rgba(theme.primary, 0.35)};"
        "}"
    )
    _NAME_EDIT_STYLE_CACHE[theme.key] = cached
    return cached


def _toggle_style(theme: theme_util.Theme) -> str:
    cached = _TOGGLE_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QToolButton {"
        f" border:0; border-left:1px solid {theme.border}; background:{theme.base}; padding:0;"
        " border-top-right-radius:10px; border-bottom-right-radius:10px;"
        f" color:{theme.muted_text}; font-size:24px; font-weight:700;"
        "}"
        f"QToolButton:hover {{ background:{theme.frame_bg}; color:{theme.text}; }}"
        f"QToolButton:pressed {{ background:{theme.tool_hover}; color:{theme.text}; }}"
    )
    _TOGGLE_STYLE_CACHE[theme.key] = cached
    return cached


def _popup_style(theme: theme_util.Theme) -> str:
    cached = _POPUP_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QFrame#profilePopup {"
        f" background:{theme.base}; border:1px solid {theme.border}; border-radius:10px;"
        "}"
    )
    _POPUP_STYLE_CACHE[theme.key] = cached
    return cached


def _list_style(theme: theme_util.Theme) -> str:
    cached = _LIST_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QListWidget {"
        f" background:transparent; color:{theme.text}; border:0; border-radius:0; padding:0;"
        "}"
        f"QListWidget::item {{ color:{theme.text}; height:28px; padding:0 8px; }}"
        f"QListWidget::item:selected {{ background:{_rgba(theme.primary, 0.28)}; color:{theme.text}; }}"
    )
    _LIST_STYLE_CACHE[theme.key] = cached
    return cached


class _ProfileListWidget(QtWidgets.QListWidget):
    reorderFinished = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropOverwriteMode(False)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setAutoScroll(True)
        self.setAutoScrollMargin(24)
        self._drag_active = False
        self._drag_row = -1

    def _event_pos(self, event) -> QtCore.QPoint:
        if hasattr(event, "position"):
            try:
                return event.position().toPoint()
            except Exception:
                pass
        return event.pos()

    def _item_order(self) -> list[int]:
        order: list[int] = []
        for row in range(self.count()):
            item = self.item(row)
            if item is None:
                continue
            value = item.data(QtCore.Qt.UserRole)
            if isinstance(value, int):
                order.append(value)
        return order

    def startDrag(self, supportedActions):
        self._drag_active = True
        self._drag_row = self.currentRow()
        super().startDrag(QtCore.Qt.MoveAction)

    def dropEvent(self, event):
        before = self._item_order()
        super().dropEvent(event)
        after = self._item_order()
        moved = before != after
        if not moved and self._drag_row >= 0:
            point = self._event_pos(event)
            target_item = self.itemAt(point)
            target_row = self.row(target_item) if target_item is not None else self.count()
            if target_item is not None:
                rect = self.visualItemRect(target_item)
                if point.y() > rect.center().y():
                    target_row += 1
            source_row = self._drag_row
            if target_row > source_row:
                target_row -= 1
            if 0 <= source_row < self.count() and 0 <= target_row <= self.count() and target_row != source_row:
                item = self.takeItem(source_row)
                if item is not None:
                    self.insertItem(target_row, item)
                    self.setCurrentRow(target_row)
                    moved = True
        self._drag_active = False
        self._drag_row = -1
        if moved:
            self.reorderFinished.emit()

    def dragLeaveEvent(self, event):
        self._drag_active = False
        self._drag_row = -1
        super().dragLeaveEvent(event)


class _ProfileRowDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        theme = theme_util.app_theme("light")
        self._handle_bg = QtGui.QColor(theme.base)
        self._handle_fg = QtGui.QColor(theme.text)
        self._handle_fg_selected = QtGui.QColor(theme.text)
        self._handle_separator = QtGui.QColor(theme.border)
        self._handle_bg_selected = QtGui.QColor(theme.primary)
        self._handle_bg_selected.setAlpha(72)

    def set_theme(self, theme: theme_util.Theme) -> None:
        self._handle_bg = QtGui.QColor(theme.base)
        self._handle_fg = QtGui.QColor(theme.text)
        self._handle_fg_selected = QtGui.QColor(theme.text)
        self._handle_separator = QtGui.QColor(theme.border)
        selected_alpha = 72 if theme.key == "light" else 96
        self._handle_bg_selected = QtGui.QColor(theme.primary)
        self._handle_bg_selected.setAlpha(selected_alpha)

    def paint(self, painter, option, index):
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        handle_w = 22
        handle_rect = QtCore.QRect(opt.rect.right() - handle_w, opt.rect.top(), handle_w, opt.rect.height())
        text_opt = QtWidgets.QStyleOptionViewItem(opt)
        text_opt.rect = opt.rect.adjusted(0, 0, -handle_w, 0)
        super().paint(painter, text_opt, index)
        painter.save()
        try:
            selected = bool(opt.state & QtWidgets.QStyle.State_Selected)
            bg = self._handle_bg_selected if selected else self._handle_bg
            fg = self._handle_fg_selected if selected else self._handle_fg
            painter.fillRect(handle_rect, bg)
            painter.setPen(QtGui.QPen(self._handle_separator))
            painter.drawLine(
                handle_rect.left(),
                handle_rect.top() + 3,
                handle_rect.left(),
                handle_rect.bottom() - 3,
            )
            painter.setPen(QtGui.QPen(fg))
            painter.drawText(handle_rect.adjusted(0, 0, -2, 0), QtCore.Qt.AlignCenter, "↕")
        finally:
            painter.restore()


class _ProfilePopupFrame(QtWidgets.QFrame):
    hidden = QtCore.Signal()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.hidden.emit()


class PlayerProfileDropdown(QtWidgets.QWidget):
    profileActivated = QtCore.Signal(int)
    profileRenamed = QtCore.Signal(int, str)
    orderChanged = QtCore.Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._syncing = False
        self._current_profile_index = -1
        self._expanded = False
        self._app = QtWidgets.QApplication.instance()
        self._app_filter_installed = False
        self._embedded_popup = qt_runtime.is_headless_qpa()
        self._applied_theme_key: str | None = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = QtWidgets.QFrame(self)
        self.header.setObjectName("profileHeader")
        row = QtWidgets.QHBoxLayout(self.header)
        row.setContentsMargins(10, 0, 0, 0)
        row.setSpacing(0)
        self.name_edit = QtWidgets.QLineEdit(self.header)
        self.name_edit.setFrame(False)
        self.name_edit.setClearButtonEnabled(False)
        self.btn_toggle = QtWidgets.QToolButton(self.header)
        self.btn_toggle.setAutoRaise(True)
        self.btn_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_toggle.setText("▾")
        self.btn_toggle.setFixedWidth(44)
        row.addWidget(self.name_edit, 1)
        row.addWidget(self.btn_toggle, 0)
        root.addWidget(self.header)

        popup_flags = QtCore.Qt.FramelessWindowHint
        if not self._embedded_popup:
            popup_flags |= QtCore.Qt.Popup
        self.popup = _ProfilePopupFrame(self, popup_flags)
        self.popup.setObjectName("profilePopup")
        popup_layout = QtWidgets.QVBoxLayout(self.popup)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        popup_layout.setSpacing(0)
        self.list_widget = _ProfileListWidget(self.popup)
        self._row_delegate = _ProfileRowDelegate(self.list_widget)
        self.list_widget.setItemDelegate(self._row_delegate)
        self.list_widget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        popup_layout.addWidget(self.list_widget)
        self.popup.hide()

        self.btn_toggle.clicked.connect(self.toggle_panel)
        self.name_edit.editingFinished.connect(self._emit_rename)
        self.list_widget.currentRowChanged.connect(self._on_current_row_changed)
        self.list_widget.reorderFinished.connect(self._emit_order_changed)
        self.popup.hidden.connect(lambda: self._set_expanded(False, update_popup=False))
        self.name_edit.returnPressed.connect(lambda: self._set_expanded(False))

    def _set_app_filter_enabled(self, enabled: bool) -> None:
        app = self._app
        if app is None:
            return
        if enabled:
            if self._app_filter_installed:
                return
            app.installEventFilter(self)
            self._app_filter_installed = True
            return
        if not self._app_filter_installed:
            return
        try:
            app.removeEventFilter(self)
        except Exception:
            pass
        self._app_filter_installed = False

    def _clear_name_edit_focus(self) -> None:
        if self.name_edit.hasFocus():
            self.name_edit.clearFocus()
        self.name_edit.deselect()

    def _contains_global_point(self, point: QtCore.QPoint) -> bool:
        if self.isVisible():
            local = self.mapFromGlobal(point)
            if self.rect().contains(local):
                return True
        if not self.popup.isVisible():
            return False
        if self._embedded_popup:
            local_popup = self.popup.mapFromGlobal(point)
            return self.popup.rect().contains(local_popup)
        return self.popup.geometry().contains(point)

    def _event_global_pos(self, event) -> QtCore.QPoint | None:
        if hasattr(event, "globalPosition"):
            try:
                return event.globalPosition().toPoint()
            except Exception:
                pass
        if hasattr(event, "globalPos"):
            try:
                return event.globalPos()
            except Exception:
                return None
        return None

    def _popup_target_geometry(self) -> QtCore.QRect:
        anchor = self.header.mapToGlobal(QtCore.QPoint(0, self.header.height()))
        count = max(1, self.list_widget.count())
        visible_rows = min(6, count)
        row_h = self.list_widget.sizeHintForRow(0) if self.list_widget.count() > 0 else 28
        row_h = max(26, row_h)
        popup_h = int(visible_rows * row_h + 8)
        popup_w = max(self.width(), 220)
        target = QtCore.QRect(anchor.x(), anchor.y(), popup_w, popup_h)
        screen = QtGui.QGuiApplication.screenAt(anchor) or QtGui.QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            if target.right() > avail.right():
                target.moveRight(avail.right())
            if target.left() < avail.left():
                target.moveLeft(avail.left())
            if target.bottom() > avail.bottom():
                # Fall back: open upwards if there is more room.
                above_y = self.header.mapToGlobal(QtCore.QPoint(0, 0)).y() - popup_h
                if above_y >= avail.top():
                    target.moveTop(above_y)
                else:
                    target.setHeight(max(80, avail.bottom() - target.top()))
        if self._embedded_popup:
            local_top_left = self.mapFromGlobal(target.topLeft())
            target.moveTopLeft(local_top_left)
        return target

    def _set_expanded(self, expanded: bool, *, update_popup: bool = True) -> None:
        self._expanded = bool(expanded)
        self.btn_toggle.setText("▴" if self._expanded else "▾")
        self._set_app_filter_enabled(self._expanded)
        if not update_popup:
            return
        if self._expanded:
            rect = self._popup_target_geometry()
            self.popup.setGeometry(rect)
            self.popup.show()
            qt_runtime.safe_raise(self.popup)
            qt_runtime.safe_activate_window(self.popup)
            focus_reason = QtCore.Qt.PopupFocusReason if not self._embedded_popup else QtCore.Qt.OtherFocusReason
            self.list_widget.setFocus(focus_reason)
        else:
            self.popup.hide()
            self._clear_name_edit_focus()

    def toggle_panel(self) -> None:
        self._set_expanded(not self._expanded)

    def collapse(self) -> None:
        self._set_expanded(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._expanded:
            self.popup.setGeometry(self._popup_target_geometry())

    def moveEvent(self, event):
        super().moveEvent(event)
        if self._expanded:
            self.popup.setGeometry(self._popup_target_geometry())

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.popup.isVisible():
            self.popup.hide()
        self._clear_name_edit_focus()

    def closeEvent(self, event):
        self._set_app_filter_enabled(False)
        super().closeEvent(event)

    def eventFilter(self, obj, event):
        et = int(event.type())
        if et == int(QtCore.QEvent.MouseButtonPress):
            global_pos = self._event_global_pos(event)
            if global_pos is not None and not self._contains_global_point(global_pos):
                self._clear_name_edit_focus()
                if self._expanded:
                    self._set_expanded(False)
        return super().eventFilter(obj, event)

    def current_profile_index(self) -> int:
        return int(self._current_profile_index)

    def current_profile_name(self) -> str:
        return str(self.name_edit.text()).strip()

    def current_order(self) -> list[int]:
        order: list[int] = []
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item is None:
                continue
            value = item.data(QtCore.Qt.UserRole)
            if isinstance(value, int):
                order.append(value)
        return order

    def set_profiles(self, names: list[str], active_index: int) -> None:
        self._syncing = True
        try:
            self.list_widget.clear()
            for idx, name in enumerate(names):
                item = QtWidgets.QListWidgetItem(str(name or ""))
                item.setData(QtCore.Qt.UserRole, int(idx))
                self.list_widget.addItem(item)
            if names:
                safe_row = max(0, min(len(names) - 1, int(active_index)))
                self.list_widget.setCurrentRow(safe_row)
                item = self.list_widget.item(safe_row)
                self._current_profile_index = int(item.data(QtCore.Qt.UserRole)) if item is not None else safe_row
                self.name_edit.setText(str(names[safe_row]))
            else:
                self._current_profile_index = -1
                self.name_edit.clear()
        finally:
            self._syncing = False

    def set_dropdown_tooltip(self, text: str) -> None:
        self.setToolTip(text)
        self.header.setToolTip(text)
        self.name_edit.setToolTip(text)
        self.btn_toggle.setToolTip(text)
        self.list_widget.setToolTip(text)
        self.popup.setToolTip(text)

    def _on_current_row_changed(self, row: int) -> None:
        if self._syncing or row < 0:
            return
        item = self.list_widget.item(row)
        if item is None:
            return
        value = item.data(QtCore.Qt.UserRole)
        if not isinstance(value, int):
            return
        self._current_profile_index = int(value)
        self.name_edit.setText(item.text())
        if not self.list_widget._drag_active:
            self.profileActivated.emit(self._current_profile_index)

    def _emit_rename(self) -> None:
        if self._syncing:
            return
        idx = self._current_profile_index
        if idx < 0:
            return
        text = self.current_profile_name()
        row = self.list_widget.currentRow()
        if row >= 0:
            item = self.list_widget.item(row)
            if item is not None:
                item.setText(text)
        self.profileRenamed.emit(idx, text)

    def _emit_order_changed(self) -> None:
        if self._syncing:
            return
        order = self.current_order()
        if order:
            self.orderChanged.emit(order)

    def apply_theme(self, theme: theme_util.Theme) -> None:
        if self._applied_theme_key == theme.key:
            return
        self._row_delegate.set_theme(theme)
        self.header.setStyleSheet(_header_style(theme))
        self.name_edit.setStyleSheet(_name_edit_style(theme))
        self.btn_toggle.setStyleSheet(_toggle_style(theme))
        self.popup.setStyleSheet(_popup_style(theme))
        self.list_widget.setStyleSheet(_list_style(theme))
        self.list_widget.viewport().update()
        self._applied_theme_key = theme.key
