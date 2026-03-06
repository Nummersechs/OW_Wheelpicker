from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from utils import theme as theme_util
from view import ui_tokens

_TOGGLE_FRAME_STYLE_CACHE: dict[str, str] = {}
_THUMB_STYLE_CACHE: dict[tuple[str, bool], str] = {}
_LABEL_STYLE_CACHE: dict[tuple[str, str], str] = {}


def _frame_style(theme: theme_util.Theme) -> str:
    cached = _TOGGLE_FRAME_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "#spinModeToggle { "
        f"background-color: {theme.frame_bg}; "
        f"border: 1px solid {theme.border}; "
        "border-radius: 12px; "
        "}"
        "#spinModeToggle:disabled { "
        f"background-color: {theme.disabled_bg}; "
        f"border: 1px solid {theme.border}; "
        "}"
    )
    _TOGGLE_FRAME_STYLE_CACHE[theme.key] = cached
    return cached


def _thumb_style(theme: theme_util.Theme, enabled: bool) -> str:
    cache_key = (theme.key, bool(enabled))
    cached = _THUMB_STYLE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if enabled:
        bg = theme.primary
        border = theme.primary_hover
    else:
        bg = theme.disabled_bg
        border = theme.border
    cached = f"background-color: {bg}; border: 1px solid {border}; border-radius: 10px;"
    _THUMB_STYLE_CACHE[cache_key] = cached
    return cached


def _label_style(theme: theme_util.Theme, mode: str) -> str:
    cache_key = (theme.key, mode)
    cached = _LABEL_STYLE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if mode == "disabled":
        cached = f"color:{theme.disabled_text}; font-weight:600;"
    elif mode == "active":
        cached = f"color:{theme.button_text}; font-weight:600;"
    else:
        cached = f"color:{theme.muted_text}; font-weight:600;"
    _LABEL_STYLE_CACHE[cache_key] = cached
    return cached


class SpinModeToggle(QtWidgets.QFrame):
    valueChanged = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("spinModeToggle")
        self._value = 0
        self._left_text = ""
        self._right_text = ""
        self._theme = theme_util.app_theme("light")
        self._applied_theme_key: str | None = None
        self._thumb_anim: QtCore.QPropertyAnimation | None = None

        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setFixedHeight(ui_tokens.BUTTON_HEIGHT_XL)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)

        self._thumb = QtWidgets.QFrame(self)
        self._thumb.setObjectName("spinModeThumb")
        self._thumb.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self._thumb.setAttribute(QtCore.Qt.WA_StyledBackground, True)

        self._left_label = QtWidgets.QLabel(self)
        self._right_label = QtWidgets.QLabel(self)
        for lab in (self._left_label, self._right_label):
            lab.setAlignment(QtCore.Qt.AlignCenter)
            lab.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        self.apply_theme(self._theme)
        self._sync_layout()

    def value(self) -> int:
        return int(self._value)

    def setValue(self, value: int) -> None:
        next_value = 1 if int(value) else 0
        if next_value == self._value:
            return
        self._value = next_value
        self._sync_layout(animate=True)
        self._update_label_styles()
        self.valueChanged.emit(self._value)

    def set_texts(self, left: str, right: str) -> None:
        self._left_text = str(left or "")
        self._right_text = str(right or "")
        self._left_label.setText(self._left_text)
        self._right_label.setText(self._right_text)
        self._update_fixed_width()
        self._sync_layout(animate=False)
        self._update_label_styles()

    def apply_theme(self, theme: theme_util.Theme) -> None:
        if self._applied_theme_key == theme.key:
            return
        self._theme = theme
        self.setStyleSheet(_frame_style(theme))
        self._update_thumb_style()
        self._update_label_styles()
        self._applied_theme_key = theme.key

    def mousePressEvent(self, ev: QtGui.QMouseEvent) -> None:
        if ev.button() == QtCore.Qt.LeftButton:
            if not self.isEnabled():
                ev.accept()
                return
            self.setValue(0 if self._value else 1)
            ev.accept()
            return
        super().mousePressEvent(ev)

    def keyPressEvent(self, ev: QtGui.QKeyEvent) -> None:
        key = ev.key()
        if key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_A):
            self.setValue(0)
            ev.accept()
            return
        if key in (QtCore.Qt.Key_Right, QtCore.Qt.Key_D):
            self.setValue(1)
            ev.accept()
            return
        if key in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.setValue(0 if self._value else 1)
            ev.accept()
            return
        super().keyPressEvent(ev)

    def resizeEvent(self, ev: QtGui.QResizeEvent) -> None:
        super().resizeEvent(ev)
        self._sync_layout(animate=False)

    def changeEvent(self, ev: QtCore.QEvent) -> None:
        if ev.type() == QtCore.QEvent.EnabledChange:
            self._update_thumb_style()
            self._update_label_styles()
        super().changeEvent(ev)

    def _update_fixed_width(self) -> None:
        fm = QtGui.QFontMetrics(self.font())
        left_w = fm.horizontalAdvance(self._left_text)
        right_w = fm.horizontalAdvance(self._right_text)
        half = max(left_w, right_w) + 20
        width = (half * 2) + 8
        self.setMinimumWidth(width)
        self.setMaximumWidth(width)

    def _update_label_styles(self) -> None:
        if not self._theme:
            return
        if not self.isEnabled():
            style = _label_style(self._theme, "disabled")
            self._left_label.setStyleSheet(style)
            self._right_label.setStyleSheet(style)
            return
        if self._value == 0:
            self._left_label.setStyleSheet(_label_style(self._theme, "active"))
            self._right_label.setStyleSheet(_label_style(self._theme, "inactive"))
        else:
            self._left_label.setStyleSheet(_label_style(self._theme, "inactive"))
            self._right_label.setStyleSheet(_label_style(self._theme, "active"))

    def _update_thumb_style(self) -> None:
        if not self._theme:
            return
        self._thumb.setStyleSheet(_thumb_style(self._theme, self.isEnabled()))

    def _thumb_rect(self, value: int) -> QtCore.QRect:
        margin = 4
        width = max(1, self.width() - (margin * 2))
        height = max(1, self.height() - (margin * 2))
        left_w = width // 2
        right_w = width - left_w
        left_x = margin
        right_x = margin + left_w
        if value == 0:
            return QtCore.QRect(left_x, margin, left_w, height)
        return QtCore.QRect(right_x, margin, right_w, height)

    def _sync_layout(self, animate: bool = False) -> None:
        margin = 4
        width = max(1, self.width() - (margin * 2))
        height = max(1, self.height() - (margin * 2))
        left_w = width // 2
        right_w = width - left_w
        left_x = margin
        right_x = margin + left_w

        self._left_label.setGeometry(left_x, margin, left_w, height)
        self._right_label.setGeometry(right_x, margin, right_w, height)
        target = self._thumb_rect(self._value)
        if not animate:
            self._thumb.setGeometry(target)
            return
        self._animate_thumb(target)

    def _animate_thumb(self, target: QtCore.QRect) -> None:
        anim = getattr(self, "_thumb_anim", None)
        if anim:
            anim.stop()
            anim.deleteLater()
        self._thumb_anim = QtCore.QPropertyAnimation(self._thumb, b"geometry", self)
        self._thumb_anim.setDuration(180)
        self._thumb_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._thumb_anim.setStartValue(self._thumb.geometry())
        self._thumb_anim.setEndValue(target)
        self._thumb_anim.start()
