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

    from PySide6 import QtWidgets  # nach Quiet-Setup laden
    from controller import MainWindow

    app = QtWidgets.QApplication([])
    win = MainWindow()
    win.show()
    app.exec()

if __name__ == "__main__":
    main()
