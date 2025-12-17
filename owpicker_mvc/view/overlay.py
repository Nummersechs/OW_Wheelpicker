from PySide6 import QtCore, QtGui, QtWidgets
from html import escape

class ResultOverlay(QtWidgets.QWidget):
    closed = QtCore.Signal()
    modeChosen = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)

        self.card = QtWidgets.QFrame(self)
        self.card.setObjectName("resultCard")
        self.card.setStyleSheet(
            "#resultCard { "
            "background: rgba(255,255,255,0.96); "
            "border-radius: 16px; "
            "border: 1px solid rgba(0,0,0,0.08); "
            "}"
        )

        v = QtWidgets.QVBoxLayout(self.card)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(10)

        self.title = QtWidgets.QLabel("Ergebnis")
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        self.title.setStyleSheet("font-size:22px; font-weight:800; margin-bottom:8px;")
        v.addWidget(self.title)

        self.lab_tank = QtWidgets.QLabel("")
        self.lab_dps = QtWidgets.QLabel("")
        self.lab_sup = QtWidgets.QLabel("")
        for lab in (self.lab_tank, self.lab_dps, self.lab_sup):
            lab.setAlignment(QtCore.Qt.AlignCenter)
            lab.setWordWrap(True)
            lab.setStyleSheet("font-size:17px; margin:4px 0;")
            v.addWidget(lab)

        self.btn_close = QtWidgets.QPushButton("OK")
        self.btn_close.setFixedHeight(40)
        self.btn_close.clicked.connect(self._close)
        
        self.btn_online = QtWidgets.QPushButton("Online")
        self.btn_online.setFixedHeight(40)
        self.btn_offline = QtWidgets.QPushButton("Offline")
        self.btn_offline.setFixedHeight(40)

        self.btn_online.clicked.connect(self._choose_online)
        self.btn_offline.clicked.connect(self._choose_offline)

        # Buttons in einer Zeile anordnen
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_offline)
        btn_row.addWidget(self.btn_online)
        btn_row.addWidget(self.btn_close)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        self.hide()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 140))
        p.end()
        super().paintEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w = max(520, int(self.width() * 0.45))
        h = max(280, int(self.height() * 0.30))
        self.card.setGeometry((self.width() - w) // 2, (self.height() - h) // 2, w, h)

    def _show(self):
        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self.activateWindow()

    def show_result(self, tank, dps, sup):
        self.title.setText("Ergebnis")
        self.lab_tank.setText(f"Tank: <b>{escape(tank)}</b>")
        self.lab_dps.setText(f"Damage: <b>{escape(dps)}</b>")
        self.lab_sup.setText(f"Support: <b>{escape(sup)}</b>")
        self.btn_close.show()
        self.btn_online.hide()
        self.btn_offline.hide()
        self._show()

    def show_message(self, title, lines):
        self.title.setText(escape(title))
        texts = list(lines) + ["", "", ""]
        self.lab_tank.setText(escape(texts[0]))
        self.lab_dps.setText(escape(texts[1]))
        self.lab_sup.setText(escape(texts[2]))
        self.btn_close.show()
        self.btn_online.hide()
        self.btn_offline.hide()
        self._show()

    def show_online_choice(self):
        """Overlay zur Wahl von Online/Offline anzeigen."""
        self.title.setText("Verbindungsmodus wählen")

        # Deine drei Zeilen im bekannten Stil
        self.lab_tank.setText("Online- oder Offline-Modus wählen?")
        self.lab_dps.setText(
            "Online: Spins und Spielernamen werden mit dem Server synchronisiert."
        )
        self.lab_sup.setText(
            "Offline: Alles bleibt lokal auf diesem Rechner."
        )

        # Online/Offline-Buttons anzeigen, OK ausblenden
        self.btn_close.hide()
        self.btn_online.show()
        self.btn_offline.show()

        self._show()

    def _choose_online(self):
        self.hide()
        self.modeChosen.emit(True)   # True = Online

    def _choose_offline(self):
        self.hide()
        self.modeChosen.emit(False)  # False = Offline


    def _close(self):
        self.hide()
        self.closed.emit()
