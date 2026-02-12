import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from utils import qt_runtime
from view.wheel_view import WheelView


class TestWheelViewRenderToggle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        qt_runtime.apply_preferred_app_font(cls._app)

    def test_reenable_restores_names_after_render_suppression(self):
        wheel = WheelView("Test", ["Alpha", "Beta", "Gamma"])
        QtWidgets.QApplication.processEvents()

        self.assertEqual(list(getattr(wheel.wheel, "names", [])), ["Alpha", "Beta", "Gamma"])

        wheel.set_wheel_render_enabled(False)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(list(getattr(wheel.wheel, "names", [])), [])

        wheel.set_wheel_render_enabled(True)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(list(getattr(wheel.wheel, "names", [])), ["Alpha", "Beta", "Gamma"])
        wheel.close()


if __name__ == "__main__":
    unittest.main()
