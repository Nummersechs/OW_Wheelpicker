import os
import sys
import config


def _apply_quiet_mode():
    """Leitet Ausgabe um, bevor Qt geladen wird."""
    if not getattr(config, "QUIET", False):
        return
    os.environ.setdefault("QT_LOGGING_RULES", "*=false")
    os.environ.setdefault("QT_LOGGING_TO_CONSOLE", "0")
    devnull = open(os.devnull, "w")
    sys.stdout = devnull
    sys.stderr = devnull
    try:
        os.dup2(devnull.fileno(), 1)
        os.dup2(devnull.fileno(), 2)
    except Exception:
        # Falls dup2 nicht erlaubt ist, wenigstens Python-Streams stummschalten
        pass


def main():
    # Quiet-Modus so früh wie möglich aktivieren (vor Qt-Imports)
    _apply_quiet_mode()

    from PySide6 import QtCore, QtGui, QtWidgets  # nach Quiet-Setup laden
    from controller.main_window import MainWindow
    from utils.qt_runtime import apply_preferred_app_font

    app = QtWidgets.QApplication([])
    apply_preferred_app_font(app)

    splash = None
    try:
        pixmap = QtGui.QPixmap(520, 180)
        pixmap.fill(QtGui.QColor("#1f232a"))
        painter = QtGui.QPainter(pixmap)
        painter.setPen(QtGui.QColor("#ffffff"))
        font = QtGui.QFont(app.font())
        font.setPointSize(max(10, int(font.pointSize()) + 2))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCore.Qt.AlignCenter, "Overwatch Wheel Picker\nStarting...")
        painter.end()
        splash = QtWidgets.QSplashScreen(pixmap)
        splash.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        splash.show()
        app.processEvents()
    except Exception:
        splash = None

    win = MainWindow()
    win.show()
    if splash is not None:
        splash.finish(win)
        splash.deleteLater()
    app.exec()

if __name__ == "__main__":
    main()
