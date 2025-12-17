from __future__ import annotations

from html import escape

from PySide6 import QtCore, QtGui, QtWidgets

from .name_overlay import NameOverlay


class BetMainWindow(QtWidgets.QMainWindow):
    """
    Reine View-Klasse: keine Business-Logik, nur GUI.
    Der Controller ruft die öffentlichen Methoden auf und hängt sich an Signale.
    """

    # Signal: Benutzer möchte den Namen neu setzen
    changeNameRequested = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Overwatch 2 – Wett-Client")
        self.resize(900, 600)

        self._apply_theme()

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.lbl_title = QtWidgets.QLabel("Overwatch 2 – Wett-Client")
        self.lbl_title.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_title.setStyleSheet(
            "font-size:20px; font-weight:700; margin:4px 0 2px 0;"
        )
        root.addWidget(self.lbl_title)

        self.lbl_user = QtWidgets.QLabel("")
        self.lbl_user.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_user.setStyleSheet("font-size:13px; color:#5f6368; margin-bottom:8px;")
        root.addWidget(self.lbl_user)

        # Knopf, um Namen später nochmal zu ändern
        btn_change_name = QtWidgets.QPushButton("Namen ändern")
        btn_change_name.setFixedHeight(30)
        btn_change_name.clicked.connect(self.changeNameRequested)
        root.addWidget(btn_change_name, alignment=QtCore.Qt.AlignCenter)

        self.lbl_status = QtWidgets.QLabel("Nicht verbunden.")
        self.lbl_status.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_status.setStyleSheet("font-size:12px; color:#80868b; margin-bottom:4px;")
        root.addWidget(self.lbl_status)

        cols = QtWidgets.QHBoxLayout()
        root.addLayout(cols, 1)

        self.grp_tank = self._create_role_group("Tank")
        self.grp_dps = self._create_role_group("Damage")
        self.grp_sup = self._create_role_group("Support")

        cols.addWidget(self.grp_tank, 1)
        cols.addWidget(self.grp_dps, 1)
        cols.addWidget(self.grp_sup, 1)

        # Overlay für Namenseingabe
        self.name_overlay = NameOverlay(parent=self.centralWidget(), initial_name="")

    # ---------------- Theme & Layout-Helfer ----------------

    def _apply_theme(self):
        QtWidgets.QApplication.setStyle("Fusion")
        pal = QtGui.QPalette()

        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(245, 246, 248))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor(255, 255, 255))
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(240, 240, 240))
        pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(255, 255, 255))
        pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(32, 33, 36))

        pal.setColor(QtGui.QPalette.Text, QtGui.QColor(32, 33, 36))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(32, 33, 36))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(32, 33, 36))

        pal.setColor(QtGui.QPalette.Button, QtGui.QColor(255, 255, 255))
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(0, 120, 215))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))

        QtWidgets.QApplication.setPalette(pal)

        self.setStyleSheet("""
            QLabel { color:#202124; }
            QGroupBox {
                font-weight:600;
                border:1px solid #dadce0;
                border-radius:10px;
                margin-top:8px;
                padding:6px 8px 10px 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color:#5f6368;
                font-size:12px;
            }
            QScrollArea {
                border:none;
                background:transparent;
            }
            QCheckBox {
                color:#202124;
                font-size:13px;
            }
            QCheckBox::indicator {
                width: 10px;
                height: 10px;
                border: 2px solid black;
                border-radius: 3px;
                background: white;
            }
            QCheckBox::indicator:checked {
                background: black;
            }
            QPushButton {
                color:#ffffff;
                background:#0b57d0;
                border-radius:12px;
                font-weight:600;
                padding:6px 16px;
            }
            QPushButton:hover { background:#0a4fc0; }
            QPushButton:pressed { background:#0946ab; }
            QPushButton:disabled {
                background:#c7c7c7;
                color:#777777;
                border-radius:12px;
                border:1px solid #b0b0b0;
            }
            QLineEdit {
                background:#ffffff;
                color:#202124;
                border:1px solid #e6e6e6;
                border-radius:6px;
                padding:4px 6px;
            }
        """)

    def _create_role_group(self, title: str) -> QtWidgets.QGroupBox:
        grp = QtWidgets.QGroupBox(title)
        layout = QtWidgets.QVBoxLayout(grp)
        layout.setContentsMargins(6, 16, 6, 6)
        layout.setSpacing(4)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        inner = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(inner)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(2)
        scroll.setWidget(inner)

        grp._inner = inner
        grp._inner_layout = v
        return grp

    def resizeEvent(self, e: QtGui.QResizeEvent):
        super().resizeEvent(e)
        if self.name_overlay and self.centralWidget():
            self.name_overlay.setGeometry(self.centralWidget().rect())

    # ---------------- API für den Controller ----------------

    def show_name_overlay(self, initial_name: str):
        self.name_overlay.edit_name.setText(initial_name)
        if self.centralWidget():
            self.name_overlay.setGeometry(self.centralWidget().rect())
        self.name_overlay.open()

    def on_name_confirmed(self, slot):
        self.name_overlay.nameConfirmed.connect(slot)

    def set_username(self, username: str):
        if username:
            self.lbl_user.setText(f"Angemeldet als: <b>{escape(username)}</b>")
        else:
            self.lbl_user.setText("Kein Name gesetzt.")

    def set_status(self, text: str):
        self.lbl_status.setText(text)

    def set_roles(self, roles_map):
        # roles_map = {"Tank":[...], "Damage":[...], "Support":[...]}
        self._rebuild_role_group(self.grp_tank, roles_map.get("Tank", []))
        self._rebuild_role_group(self.grp_dps, roles_map.get("Damage", []))
        self._rebuild_role_group(self.grp_sup, roles_map.get("Support", []))

    def _rebuild_role_group(self, grp: QtWidgets.QGroupBox, names):
        layout: QtWidgets.QVBoxLayout = grp._inner_layout

        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for name in names:
            cb = QtWidgets.QCheckBox(name)
            layout.addWidget(cb)

        layout.addStretch(1)
