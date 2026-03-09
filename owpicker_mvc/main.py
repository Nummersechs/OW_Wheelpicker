import os
import sys
from pathlib import Path
import config

_QUIET_QT_MESSAGE_HANDLER = None
_SINGLE_INSTANCE_LOCK = None


def _apply_quiet_mode():
    """Leitet Ausgabe um, bevor Qt geladen wird."""
    if not getattr(config, "QUIET", False):
        return
    os.environ.setdefault("QT_LOGGING_RULES", "*=false")
    os.environ.setdefault("QT_LOGGING_TO_CONSOLE", "0")
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    try:
        import logging
        import warnings

        warnings.simplefilter("ignore")
        logging.disable(logging.CRITICAL)
    except Exception:
        pass
    devnull = open(os.devnull, "w")
    sys.stdout = devnull
    sys.stderr = devnull
    try:
        os.dup2(devnull.fileno(), 1)
        os.dup2(devnull.fileno(), 2)
    except Exception:
        # Falls dup2 nicht erlaubt ist, wenigstens Python-Streams stummschalten
        pass


def _install_quiet_qt_handler(QtCore):
    """Unterdrückt Qt Runtime-Messages zusätzlich zum Env-Filter."""
    if not getattr(config, "QUIET", False):
        return
    global _QUIET_QT_MESSAGE_HANDLER

    def _quiet_handler(_msg_type, _context, _message):
        return

    _QUIET_QT_MESSAGE_HANDLER = _quiet_handler
    try:
        QtCore.qInstallMessageHandler(_QUIET_QT_MESSAGE_HANDLER)
    except Exception:
        pass


def _acquire_single_instance_lock(QtCore) -> bool:
    """Prevent duplicate app launches on Windows double-click."""
    if not sys.platform.startswith("win"):
        return True
    if not bool(getattr(config, "WINDOWS_SINGLE_INSTANCE", True)):
        return True
    lock_name = str(getattr(config, "WINDOWS_SINGLE_INSTANCE_LOCK_NAME", "ow_wheelpicker_instance")).strip()
    if not lock_name:
        lock_name = "ow_wheelpicker_instance"
    try:
        temp_dir = QtCore.QDir.tempPath() or "."
    except Exception:
        temp_dir = "."
    lock_path = str(Path(str(temp_dir)).resolve() / f"{lock_name}.lock")
    lock = QtCore.QLockFile(lock_path)
    # Keep stale timeout short so stale locks from crashes do not block restarts.
    lock.setStaleLockTime(10_000)
    if not lock.tryLock(0):
        try:
            if lock.removeStaleLockFile() and lock.tryLock(0):
                pass
            else:
                return False
        except Exception:
            return False
    global _SINGLE_INSTANCE_LOCK
    _SINGLE_INSTANCE_LOCK = lock
    return True


def main():
    # Quiet-Modus so früh wie möglich aktivieren (vor Qt-Imports)
    _apply_quiet_mode()

    from PySide6 import QtCore, QtGui, QtWidgets  # nach Quiet-Setup laden
    from utils.qt_runtime import apply_preferred_app_font
    _install_quiet_qt_handler(QtCore)
    if not _acquire_single_instance_lock(QtCore):
        return

    app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(True)
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

    # Erst nach sichtbarem Splash laden, damit "Klick -> sichtbares Feedback"
    # schneller passiert, auch wenn MainWindow-Module länger importieren.
    from controller.main_window import MainWindow

    win = MainWindow()
    win.show()
    if splash is not None:
        splash.finish(win)
        splash.deleteLater()
    app.exec()

if __name__ == "__main__":
    main()
