from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class FocusPolicyManager:
    """Centralizes startup focus policy handling to avoid refocus flicker."""

    def __init__(self, root: QtWidgets.QWidget) -> None:
        self._root = root

    def apply_defaults(self) -> None:
        for w in self._root.findChildren(QtWidgets.QWidget):
            try:
                policy = w.focusPolicy()
            except Exception:
                continue
            if isinstance(w, QtWidgets.QAbstractButton):
                try:
                    w.setFocusPolicy(QtCore.Qt.NoFocus)
                except Exception:
                    pass
                continue
            if policy == QtCore.Qt.NoFocus:
                continue
            if policy in (QtCore.Qt.TabFocus, QtCore.Qt.StrongFocus):
                try:
                    w.setFocusPolicy(QtCore.Qt.ClickFocus)
                except Exception:
                    pass

    def schedule_clear_focus(self) -> None:
        QtCore.QTimer.singleShot(0, self.clear_focus_now)
        QtCore.QTimer.singleShot(150, self.clear_focus_now)
        QtCore.QTimer.singleShot(400, self.clear_focus_now)

    def clear_focus_now(self) -> None:
        try:
            app = QtWidgets.QApplication.instance()
            if app:
                fw = app.focusWidget()
                if fw:
                    fw.clearFocus()
        except Exception:
            pass
        try:
            self._root.clearFocus()
        except Exception:
            pass
