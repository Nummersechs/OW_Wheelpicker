import unittest

import i18n
from view.overlay import ResultOverlay


class _FakeButton:
    def __init__(self) -> None:
        self._enabled = True
        self.tooltip = ""

    def setEnabled(self, value: bool) -> None:
        self._enabled = bool(value)

    def isEnabled(self) -> bool:
        return bool(self._enabled)

    def setToolTip(self, value: str) -> None:
        self.tooltip = str(value or "")


class TestOverlayChoiceTooltips(unittest.TestCase):
    def _make_overlay(self) -> ResultOverlay:
        overlay = ResultOverlay.__new__(ResultOverlay)
        overlay.btn_online = _FakeButton()
        overlay.btn_offline = _FakeButton()
        overlay._choice_buttons_loading = False
        return overlay

    def test_set_choice_enabled_false_uses_loading_tooltip(self):
        overlay = self._make_overlay()

        ResultOverlay.set_choice_enabled(overlay, False)

        self.assertFalse(overlay.btn_online.isEnabled())
        self.assertFalse(overlay.btn_offline.isEnabled())
        self.assertEqual(overlay.btn_online.tooltip, i18n.t("overlay.choice_loading_tooltip"))
        self.assertEqual(overlay.btn_offline.tooltip, i18n.t("overlay.choice_loading_tooltip"))

    def test_set_choice_enabled_true_restores_default_tooltips(self):
        overlay = self._make_overlay()
        ResultOverlay.set_choice_enabled(overlay, False)

        ResultOverlay.set_choice_enabled(overlay, True)

        self.assertTrue(overlay.btn_online.isEnabled())
        self.assertTrue(overlay.btn_offline.isEnabled())
        self.assertEqual(overlay.btn_online.tooltip, i18n.t("overlay.button_online_tooltip"))
        self.assertEqual(overlay.btn_offline.tooltip, i18n.t("overlay.button_offline_tooltip"))

    def test_loading_flag_keeps_loading_tooltip_until_explicitly_cleared(self):
        overlay = self._make_overlay()
        overlay.btn_online.setEnabled(True)
        overlay.btn_offline.setEnabled(True)
        overlay._choice_buttons_loading = True

        ResultOverlay._apply_choice_button_tooltips(overlay)

        self.assertEqual(overlay.btn_online.tooltip, i18n.t("overlay.choice_loading_tooltip"))
        self.assertEqual(overlay.btn_offline.tooltip, i18n.t("overlay.choice_loading_tooltip"))


if __name__ == "__main__":
    unittest.main()
