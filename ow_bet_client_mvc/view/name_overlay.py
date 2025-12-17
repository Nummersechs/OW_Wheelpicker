from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class NameOverlay(QtWidgets.QWidget):
    """
    Halbtransparenter Overlay-Canvas, der wie ein Popup wirkt.
    Fragt nach dem Spielernamen (Username).
    """
    nameConfirmed = QtCore.Signal(str)  # wird mit dem eingegebenen Namen emittiert

    def __init__(self, parent=None, initial_name: str = ""):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)

        self.card = QtWidgets.QFrame(self)
        self.card.setObjectName("nameCard")
        self.card.setStyleSheet(
            "#nameCard { "
            "background: rgba(255,255,255,0.96); "
            "border-radius: 16px; "
            "border: 1px solid rgba(0,0,0,0.08); "
            "}"
        )

        v = QtWidgets.QVBoxLayout(self.card)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)

        title = QtWidgets.QLabel("Spielername festlegen")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-size:22px; font-weight:800; margin-bottom:8px;")
        v.addWidget(title)

        hint = QtWidgets.QLabel(
            "Gib bitte deinen Namen ein, der im Wett-Client verwendet wird."
        )
        hint.setWordWrap(True)
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setStyleSheet("font-size:13px; color:#444; margin-bottom:6px;")
        v.addWidget(hint)

        self.edit_name = QtWidgets.QLineEdit()
        self.edit_name.setPlaceholderText("Dein Name")
        self.edit_name.setText(initial_name)
        self.edit_name.setMinimumWidth(260)
        self.edit_name.returnPressed.connect(self._confirm)
        v.addWidget(self.edit_name, alignment=QtCore.Qt.AlignCenter)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)

        self.btn_ok = QtWidgets.QPushButton("OK")
        self.btn_ok.setFixedHeight(38)
        self.btn_ok.clicked.connect(self._confirm)
        btn_row.addWidget(self.btn_ok)

        btn_row.addStretch(1)
        v.addLayout(btn_row)

        self.hide()

    # Hintergrund dunkel zeichnen
    def paintEvent(self, e: QtGui.QPaintEvent):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 140))
        p.end()
        super().paintEvent(e)

    # Card zentrieren
    def resizeEvent(self, e: QtGui.QResizeEvent):
        super().resizeEvent(e)
        w = max(460, int(self.width() * 0.38))
        h = max(220, int(self.height() * 0.26))
        self.card.setGeometry(
            (self.width() - w) // 2,
            (self.height() - h) // 2,
            w,
            h,
        )

    def _show(self):
        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit_name.setFocus()
        self.edit_name.selectAll()

    def open(self):
        """Von außen aufrufen, um das Overlay zu zeigen."""
        self._show()

    def _confirm(self):
        name = self.edit_name.text().strip()
        if not name:
            # Kurzer visueller Hinweis
            self.edit_name.setStyleSheet(
                "border: 1px solid #d93025; border-radius:6px; padding:4px;"
            )
            QtCore.QTimer.singleShot(
                800,
                lambda: self.edit_name.setStyleSheet(""),
            )
            return
        self.hide()
        self.nameConfirmed.emit(name)
