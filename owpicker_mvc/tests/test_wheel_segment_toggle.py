import os
import unittest

# Run the Qt widget test without requiring a macOS window server.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtTest, QtWidgets

from view.wheel_widget import WheelWidget


class TestWheelSegmentToggle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_clicking_same_segment_twice_reenables_it(self):
        view = WheelWidget(["A", "B", "C", "D"])
        view.resize(380, 380)
        view.show()
        QtWidgets.QApplication.processEvents()

        click_pos = view.mapFromScene(QtCore.QPointF(float(view.wheel.radius) * 0.6, 0.0))

        self.assertEqual(len(view.wheel.disabled_indices), 0)

        QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, click_pos)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(len(view.wheel.disabled_indices), 1)

        QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, click_pos)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(len(view.wheel.disabled_indices), 0)

        view.close()

    def test_click_outside_wheel_does_not_toggle_segment(self):
        view = WheelWidget(["A", "B", "C", "D"])
        view.resize(380, 380)
        view.show()
        QtWidgets.QApplication.processEvents()

        outside_scene = QtCore.QPointF(float(view.wheel.radius) + 25.0, 0.0)
        outside_pos = view.mapFromScene(outside_scene)

        self.assertEqual(len(view.wheel.disabled_indices), 0)
        QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, outside_pos)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(len(view.wheel.disabled_indices), 0)

        view.close()


if __name__ == "__main__":
    unittest.main()
