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

    def test_override_clear_restores_base_names_after_load_entries(self):
        wheel = WheelView("Test", ["A", "B", "C"])
        QtWidgets.QApplication.processEvents()

        wheel.load_entries(
            [
                {"name": "A", "subroles": [], "active": True},
                {"name": "B", "subroles": [], "active": True},
                {"name": "C", "subroles": [], "active": True},
            ],
            pair_mode=False,
            include_in_all=True,
            use_subroles=False,
        )
        QtWidgets.QApplication.processEvents()
        self.assertEqual(list(getattr(wheel.wheel, "names", [])), ["A", "B", "C"])

        wheel.set_override_entries(
            [
                {"name": "X", "subroles": [], "active": True},
                {"name": "Y", "subroles": [], "active": True},
            ]
        )
        QtWidgets.QApplication.processEvents()
        self.assertEqual(list(getattr(wheel.wheel, "names", [])), ["X", "Y"])

        wheel.set_override_entries(None)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(list(getattr(wheel.wheel, "names", [])), ["A", "B", "C"])
        wheel.close()

    def test_spin_repaint_callback_is_cleaned_on_hard_stop(self):
        wheel = WheelView("Test", ["A", "B", "C"])
        QtWidgets.QApplication.processEvents()

        started = wheel.spin(duration_ms=1500)
        self.assertTrue(started)
        self.assertTrue(hasattr(wheel, "_anim_repaint_cb"))

        wheel.hard_stop()
        QtWidgets.QApplication.processEvents()
        self.assertFalse(hasattr(wheel, "_anim_repaint_cb"))
        wheel.close()

    def test_subrole_controls_reapply_restores_delete_checkbox_visibility(self):
        wheel = WheelView(
            "Test",
            ["Alpha", "Beta"],
            pair_mode=True,
            allow_pair_toggle=True,
            subrole_labels=["Main", "Off"],
        )
        wheel.show()
        QtWidgets.QApplication.processEvents()

        item0 = wheel.names.item(0)
        row_widget = wheel.names.itemWidget(item0)
        self.assertIsNotNone(row_widget)
        self.assertIsNotNone(getattr(row_widget, "chk_mark_for_delete", None))
        delete_cb = row_widget.chk_mark_for_delete
        delete_cell = delete_cb.parentWidget()

        delete_cb.setVisible(False)
        if delete_cell is not None:
            delete_cell.setVisible(False)
        QtWidgets.QApplication.processEvents()

        wheel.set_subrole_controls_visible(True)
        QtWidgets.QApplication.processEvents()

        self.assertFalse(delete_cb.isHidden())
        if delete_cell is not None:
            self.assertFalse(delete_cell.isHidden())
        wheel.close()

    def test_subrole_controls_hidden_keeps_row_profile_and_delete_checkbox(self):
        wheel = WheelView(
            "Test",
            ["Alpha", "Beta", "Gamma", "Delta"],
            pair_mode=True,
            allow_pair_toggle=True,
            subrole_labels=["Main", "Off"],
        )
        wheel.resize(420, 560)
        wheel.show()
        QtWidgets.QApplication.processEvents()

        row_before = wheel.names.itemWidget(wheel.names.item(0))
        self.assertIsNotNone(row_before)
        x_before = row_before.edit.geometry().x()
        w_before = row_before.edit.geometry().width()
        self.assertIsNotNone(row_before.chk_mark_for_delete)

        wheel.set_subrole_controls_visible(False)
        QtWidgets.QApplication.processEvents()

        row = wheel.names.itemWidget(wheel.names.item(0))
        self.assertIsNotNone(row)
        self.assertLessEqual(abs(row.edit.geometry().x() - x_before), 2)
        self.assertLessEqual(abs(row.edit.geometry().width() - w_before), 2)
        self.assertFalse(row.chk_mark_for_delete.isHidden())
        wheel.close()


if __name__ == "__main__":
    unittest.main()
