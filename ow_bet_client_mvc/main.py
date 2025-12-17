from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtWidgets

from controller.app_controller import AppController


def main():
    app = QtWidgets.QApplication(sys.argv)
    base_dir = Path(__file__).resolve().parent
    controller = AppController(base_dir=base_dir)
    controller.view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
