import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets
from utils import qt_runtime
from view.name_list import NameRowWidget, NamesListPanel


class TestNamesListPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        qt_runtime.apply_preferred_app_font(cls._app)

    def _add_names(self, panel: NamesListPanel, names: list[str]) -> None:
        for name in names:
            panel.names.add_name(name, active=True)

    def _name_texts(self, panel: NamesListPanel) -> list[str]:
        values: list[str] = []
        for i in range(panel.names.count()):
            item = panel.names.item(i)
            if item is None:
                continue
            widget = panel.names.itemWidget(item)
            if isinstance(widget, NameRowWidget):
                values.append(widget.edit.text().strip())
            else:
                values.append(item.text().strip())
        return values

    def _confirm_marked_delete(self, panel: NamesListPanel) -> None:
        panel.btn_delete_marked.click()
        QtWidgets.QApplication.processEvents()

    def test_trash_button_enabled_only_with_marked_rows(self):
        panel = NamesListPanel(subrole_labels=["HS", "FDPS"])
        self._add_names(panel, ["Alpha", "Beta"])
        QtWidgets.QApplication.processEvents()

        self.assertFalse(panel.btn_delete_marked.isEnabled())
        item0 = panel.names.item(0)
        widget0 = panel.names.itemWidget(item0)
        self.assertIsInstance(widget0, NameRowWidget)
        widget0.chk_mark_for_delete.setChecked(True)
        QtWidgets.QApplication.processEvents()
        self.assertTrue(panel.btn_delete_marked.isEnabled())

        widget0.chk_mark_for_delete.setChecked(False)
        QtWidgets.QApplication.processEvents()
        self.assertFalse(panel.btn_delete_marked.isEnabled())
        panel.close()

    def test_trash_button_deletes_all_marked_names(self):
        panel = NamesListPanel(subrole_labels=["HS", "FDPS"])
        self._add_names(panel, ["Alpha", "Beta", "Gamma"])
        QtWidgets.QApplication.processEvents()

        for row in (0, 2):
            item = panel.names.item(row)
            widget = panel.names.itemWidget(item)
            self.assertIsInstance(widget, NameRowWidget)
            widget.chk_mark_for_delete.setChecked(True)
        QtWidgets.QApplication.processEvents()

        self.assertTrue(panel.btn_delete_marked.isEnabled())
        self._confirm_marked_delete(panel)

        self.assertEqual(self._name_texts(panel), ["Beta"])
        self.assertFalse(panel.btn_delete_marked.isEnabled())
        panel.close()

    def test_trash_button_keeps_single_empty_row_when_all_removed(self):
        panel = NamesListPanel(subrole_labels=["HS", "FDPS"])
        self._add_names(panel, ["Solo"])
        QtWidgets.QApplication.processEvents()

        item0 = panel.names.item(0)
        widget0 = panel.names.itemWidget(item0)
        self.assertIsInstance(widget0, NameRowWidget)
        widget0.chk_mark_for_delete.setChecked(True)
        QtWidgets.QApplication.processEvents()

        self._confirm_marked_delete(panel)

        self.assertEqual(panel.names.count(), 1)
        self.assertEqual(self._name_texts(panel), [""])
        self.assertFalse(panel.btn_delete_marked.isEnabled())
        panel.close()

    def test_enter_in_line_edit_inserts_row(self):
        panel = NamesListPanel(subrole_labels=["HS", "FDPS"])
        self._add_names(panel, ["Alpha"])
        QtWidgets.QApplication.processEvents()

        item0 = panel.names.item(0)
        widget0 = panel.names.itemWidget(item0)
        self.assertIsInstance(widget0, NameRowWidget)

        widget0.edit.newRowRequested.emit()
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.processEvents()

        self.assertEqual(panel.names.count(), 2)
        inserted_item = panel.names.item(1)
        inserted_widget = panel.names.itemWidget(inserted_item)
        self.assertIsInstance(inserted_widget, NameRowWidget)
        self.assertEqual(inserted_widget.edit.text().strip(), "")
        panel.close()

    def test_bulk_delete_then_enter_inserts_new_row(self):
        panel = NamesListPanel(subrole_labels=["HS", "FDPS"])
        self._add_names(panel, ["Alpha", "Beta", "Gamma"])
        QtWidgets.QApplication.processEvents()

        for row in (0, 2):
            item = panel.names.item(row)
            widget = panel.names.itemWidget(item)
            self.assertIsInstance(widget, NameRowWidget)
            widget.chk_mark_for_delete.setChecked(True)
        QtWidgets.QApplication.processEvents()
        self._confirm_marked_delete(panel)

        self.assertEqual(self._name_texts(panel), ["Beta"])

        remaining_item = panel.names.item(0)
        remaining_widget = panel.names.itemWidget(remaining_item)
        self.assertIsInstance(remaining_widget, NameRowWidget)
        remaining_widget.edit.newRowRequested.emit()
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.processEvents()

        self.assertEqual(panel.names.count(), 2)
        self.assertEqual(self._name_texts(panel), ["Beta", ""])
        panel.close()

    def test_marked_delete_waits_for_external_confirmation(self):
        panel = NamesListPanel(subrole_labels=["HS", "FDPS"])
        self._add_names(panel, ["Alpha", "Beta"])
        QtWidgets.QApplication.processEvents()

        requested_counts: list[int] = []
        panel.set_delete_confirm_handler(lambda count: requested_counts.append(int(count)) or True)

        item0 = panel.names.item(0)
        widget0 = panel.names.itemWidget(item0)
        self.assertIsInstance(widget0, NameRowWidget)
        widget0.chk_mark_for_delete.setChecked(True)
        QtWidgets.QApplication.processEvents()

        panel.btn_delete_marked.click()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(requested_counts, [1])

        self.assertEqual(self._name_texts(panel), ["Alpha", "Beta"])
        self.assertTrue(panel.btn_delete_marked.isEnabled())
        panel.confirm_delete_marked()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self._name_texts(panel), ["Beta"])
        panel.close()

    def test_subrole_rows_can_hide_delete_mark_checkbox(self):
        panel = NamesListPanel(
            subrole_labels=["HS", "FDPS"],
            enable_mark_for_delete=False,
        )
        self._add_names(panel, ["Alpha"])
        QtWidgets.QApplication.processEvents()

        item0 = panel.names.item(0)
        widget0 = panel.names.itemWidget(item0)
        self.assertIsInstance(widget0, NameRowWidget)
        self.assertEqual(len(widget0.subrole_checks), 2)
        self.assertIsNone(widget0.chk_mark_for_delete)
        self.assertFalse(panel.btn_delete_marked.isVisible())
        panel.close()

    def test_sort_keeps_name_field_width_stable_for_subrole_rows(self):
        panel = NamesListPanel(subrole_labels=["Tank", "DPS", "Support", "Main", "Flex"])
        self._add_names(panel, [f"Player{i:02d}" for i in range(14)])
        panel.resize(340, 380)
        panel.layout().activate()
        QtWidgets.QApplication.processEvents()

        first_item_before = panel.names.item(0)
        first_widget_before = panel.names.itemWidget(first_item_before)
        self.assertIsInstance(first_widget_before, NameRowWidget)
        self.assertIsNotNone(first_widget_before.chk_mark_for_delete)
        width_before = first_widget_before.edit.width()

        panel.names.sort_alphabetically()
        QtWidgets.QApplication.processEvents()

        first_item_after = panel.names.item(0)
        first_widget_after = panel.names.itemWidget(first_item_after)
        self.assertIsInstance(first_widget_after, NameRowWidget)
        self.assertIsNotNone(first_widget_after.chk_mark_for_delete)
        width_after = first_widget_after.edit.width()

        self.assertEqual(width_after, width_before)
        panel.close()


if __name__ == "__main__":
    unittest.main()
