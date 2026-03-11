import os
import sys
from pathlib import Path
from typing import Any

_QUIET_QT_MESSAGE_HANDLER = None
_SINGLE_INSTANCE_LOCK = None


def _apply_quiet_mode(settings: Any):
    """Leitet Ausgabe so früh wie möglich in den Quiet-Modus um."""
    if not bool(settings.runtime.quiet):
        return
    os.environ.setdefault("QT_LOGGING_RULES", "*=false")
    os.environ.setdefault("QT_LOGGING_TO_CONSOLE", "0")
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    import logging
    import warnings

    warnings.simplefilter("ignore")
    logging.disable(logging.CRITICAL)
    devnull = open(os.devnull, "w")
    sys.stdout = devnull
    sys.stderr = devnull
    try:
        os.dup2(devnull.fileno(), 1)
        os.dup2(devnull.fileno(), 2)
    except OSError:
        # Falls dup2 nicht erlaubt ist, wenigstens Python-Streams stummschalten
        pass


def _install_quiet_qt_handler(QtCore, settings: Any):
    """Unterdrückt Qt Runtime-Messages zusätzlich zum Env-Filter."""
    if not bool(settings.runtime.quiet):
        return
    global _QUIET_QT_MESSAGE_HANDLER

    def _quiet_handler(_msg_type, _context, _message):
        return

    _QUIET_QT_MESSAGE_HANDLER = _quiet_handler
    try:
        QtCore.qInstallMessageHandler(_QUIET_QT_MESSAGE_HANDLER)
    except (AttributeError, RuntimeError, TypeError):
        pass


def _acquire_single_instance_lock(QtCore, settings: Any) -> bool:
    """Prevent duplicate app launches on Windows double-click."""
    if not sys.platform.startswith("win"):
        return True
    if not bool(settings.runtime.windows_single_instance):
        return True
    lock_name = str(settings.runtime.windows_single_instance_lock_name).strip()
    if not lock_name:
        lock_name = "ow_wheelpicker_instance"
    try:
        temp_dir = QtCore.QDir.tempPath() or "."
    except (AttributeError, RuntimeError):
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
        except (AttributeError, RuntimeError, OSError):
            return False
    global _SINGLE_INSTANCE_LOCK
    _SINGLE_INSTANCE_LOCK = lock
    return True


def _show_boot_splash(app, QtCore, QtGui, QtWidgets, text: str):
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
        painter.drawText(pixmap.rect(), QtCore.Qt.AlignCenter, str(text or "Starting..."))
        painter.end()
        splash = QtWidgets.QSplashScreen(pixmap)
        splash.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        splash.show()
        app.processEvents()
    except (RuntimeError, TypeError, ValueError):
        splash = None
    return splash


def _update_boot_splash(splash, app, QtCore, QtGui, text: str) -> None:
    if splash is None:
        return
    try:
        splash.showMessage(
            str(text or ""),
            QtCore.Qt.AlignCenter | QtCore.Qt.AlignBottom,
            QtGui.QColor("#ffffff"),
        )
        app.processEvents(QtCore.QEventLoop.AllEvents, 50)
    except (RuntimeError, TypeError, ValueError):
        pass


def main():
    # First visible feedback as early as possible for slower systems.
    from PySide6 import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication([])
    splash = _show_boot_splash(app, QtCore, QtGui, QtWidgets, "Overwatch Wheel Picker\nStarting...")
    app.setQuitOnLastWindowClosed(True)
    _update_boot_splash(splash, app, QtCore, QtGui, "Overwatch Wheel Picker\nLoading settings...")

    # Defer heavy imports until after splash is visible.
    from services.app_settings import AppSettings
    from services import settings_provider
    import config

    settings = settings_provider.set_settings(AppSettings.from_module(config))
    _update_boot_splash(splash, app, QtCore, QtGui, "Overwatch Wheel Picker\nApplying startup checks...")
    _apply_quiet_mode(settings)
    _install_quiet_qt_handler(QtCore, settings)
    if not _acquire_single_instance_lock(QtCore, settings):
        if splash is not None:
            splash.close()
            splash.deleteLater()
        return

    _update_boot_splash(splash, app, QtCore, QtGui, "Overwatch Wheel Picker\nLoading UI modules...")

    # Erst nach sichtbarem Splash laden, damit "Klick -> sichtbares Feedback"
    # schneller passiert, auch wenn MainWindow-Module länger importieren.
    from utils.qt_runtime import apply_preferred_app_font
    apply_preferred_app_font(app)
    from controller.main_window import MainWindow

    _update_boot_splash(splash, app, QtCore, QtGui, "Overwatch Wheel Picker\nBuilding main window...")
    win = MainWindow(settings=settings)
    _update_boot_splash(splash, app, QtCore, QtGui, "Overwatch Wheel Picker\nFinalizing...")
    win.show()
    if splash is not None:
        splash.finish(win)
        splash.deleteLater()
    app.exec()

if __name__ == "__main__":
    main()
