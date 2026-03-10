import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets
from unittest.mock import patch

import i18n
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
        wheel.layout().activate()
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
        wheel.layout().activate()
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

    def test_add_name_reuses_empty_placeholder_row(self):
        wheel = WheelView("Test", [])
        QtWidgets.QApplication.processEvents()

        self.assertEqual(wheel.names.count(), 1)
        self.assertEqual(wheel.get_current_names(), [])

        changed = wheel.add_name("Alpha", active=True)
        QtWidgets.QApplication.processEvents()

        self.assertTrue(changed)
        self.assertEqual(wheel.names.count(), 1)
        self.assertEqual(wheel.get_current_names(), ["Alpha"])
        self.assertEqual(list(getattr(wheel.wheel, "names", [])), ["Alpha"])
        wheel.close()

    def test_spin_button_tooltip_explains_disabled_state_when_no_names(self):
        wheel = WheelView("Test", [])
        QtWidgets.QApplication.processEvents()

        self.assertFalse(wheel.btn_local_spin.isEnabled())
        self.assertEqual(
            wheel.btn_local_spin.toolTip(),
            i18n.t("wheel.spin_button_disabled_no_names_tooltip"),
        )

        wheel.add_name("Alpha", active=True)
        QtWidgets.QApplication.processEvents()

        self.assertTrue(wheel.btn_local_spin.isEnabled())
        self.assertEqual(
            wheel.btn_local_spin.toolTip(),
            i18n.t("wheel.spin_button_tooltip"),
        )
        wheel.close()

    def test_disabled_spin_button_hover_shows_tooltip_via_card_event_filter(self):
        wheel = WheelView("Test", [])
        if not qt_runtime.is_headless_qpa():
            wheel.show()
        QtWidgets.QApplication.processEvents()
        self.assertFalse(wheel.btn_local_spin.isEnabled())

        pos_global = wheel.btn_local_spin.mapToGlobal(QtCore.QPoint(4, 4))
        pos_local = wheel.card.mapFromGlobal(pos_global)
        evt = QtGui.QHelpEvent(QtCore.QEvent.ToolTip, pos_local, pos_global)

        with patch("view.base_panel.QtWidgets.QToolTip.showText") as show_text:
            handled = wheel.eventFilter(wheel.card, evt)
            self.assertTrue(handled)
            if qt_runtime.is_headless_qpa():
                show_text.assert_not_called()
            else:
                show_text.assert_called_once()
        wheel.close()

    def test_pair_mode_falls_back_to_single_when_only_one_active_name_remains(self):
        wheel = WheelView(
            "Test",
            ["Alpha", "Beta"],
            allow_pair_toggle=True,
        )
        QtWidgets.QApplication.processEvents()

        wheel.toggle.setChecked(True)
        QtWidgets.QApplication.processEvents()
        self.assertTrue(wheel.pair_mode)

        changed = wheel.set_names_active({"Beta"}, False)
        self.assertTrue(changed)
        QtWidgets.QApplication.processEvents()

        self.assertFalse(wheel.pair_mode)
        self.assertFalse(wheel.toggle.isChecked())
        self.assertEqual(list(getattr(wheel.wheel, "names", [])), ["Alpha"])
        wheel.close()

    def test_pair_toggle_cannot_force_pair_mode_with_single_name(self):
        wheel = WheelView(
            "Test",
            ["Solo"],
            allow_pair_toggle=True,
        )
        QtWidgets.QApplication.processEvents()
        self.assertFalse(wheel.toggle.isEnabled())

        wheel.toggle.setChecked(True)
        QtWidgets.QApplication.processEvents()

        self.assertFalse(wheel.pair_mode)
        self.assertFalse(wheel.toggle.isChecked())
        self.assertEqual(list(getattr(wheel.wheel, "names", [])), ["Solo"])
        wheel.close()


if __name__ == "__main__":
    unittest.main()
