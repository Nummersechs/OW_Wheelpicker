from __future__ import annotations

import unittest

from PySide6 import QtWidgets

from utils import theme as theme_util
from view import style_helpers


class StyleHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_apply_theme_role_button_primary_sets_cached_key(self):
        btn = QtWidgets.QPushButton("Spin")
        theme = theme_util.get_theme("light")

        style_helpers.apply_theme_role(btn, theme, "button.primary")

        self.assertEqual(btn.property("_ow_style_cache_key"), "button:primary:light")
        self.assertIn(theme.primary, btn.styleSheet())

    def test_apply_theme_role_label_summary_uses_muted_color(self):
        label = QtWidgets.QLabel("Summary")
        theme = theme_util.get_theme("dark")

        style_helpers.apply_theme_role(label, theme, "label.summary")

        self.assertEqual(label.property("_ow_style_cache_key"), "label:summary:dark")
        self.assertIn(theme.muted_text, label.styleSheet())

    def test_apply_theme_roles_ignores_none_widgets(self):
        theme = theme_util.get_theme("light")
        btn = QtWidgets.QPushButton("A")

        style_helpers.apply_theme_roles(
            theme,
            (
                (None, "button.primary"),
                (btn, "button.danger"),
            ),
        )

        self.assertEqual(btn.property("_ow_style_cache_key"), "button:danger:light")

    def test_apply_theme_role_unknown_raises(self):
        label = QtWidgets.QLabel("X")
        theme = theme_util.get_theme("light")

        with self.assertRaises(ValueError):
            style_helpers.apply_theme_role(label, theme, "label.unknown_variant")


if __name__ == "__main__":
    unittest.main()
