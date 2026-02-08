import unittest
from unittest.mock import patch

from controller import spin_service


class DummySound:
    def __init__(self):
        self.stop_spin_calls = 0
        self.stop_ding_calls = 0

    def stop_spin(self):
        self.stop_spin_calls += 1

    def stop_ding(self):
        self.stop_ding_calls += 1


class DummySummary:
    def __init__(self):
        self.value = ""

    def setText(self, value: str):
        self.value = value


class DummyOverlay:
    def __init__(self):
        self.messages = []

    def show_message(self, title, lines):
        self.messages.append((title, list(lines)))


class DummyMW:
    def __init__(self):
        self.sound = DummySound()
        self.summary = DummySummary()
        self.overlay = DummyOverlay()
        self.pending = 2
        self.controls_enabled = None

    def _set_controls_enabled(self, enabled: bool):
        self.controls_enabled = bool(enabled)


class TestSpinServiceHelpers(unittest.TestCase):
    def test_labels_to_candidates_filters_empty_parts(self):
        labels = ["A + B", " C ", " + ", "", "D+E+F"]
        got = spin_service._labels_to_candidates(labels)
        self.assertEqual(
            got,
            [
                ("A + B", ["A", "B"]),
                (" C ", ["C"]),
                ("D+E+F", ["D", "E", "F"]),
            ],
        )

    def test_show_team_impossible_updates_ui_and_state(self):
        mw = DummyMW()
        with patch("controller.spin_service.i18n.t", side_effect=lambda key, **kwargs: key):
            spin_service._show_team_impossible(mw)
        self.assertEqual(mw.sound.stop_spin_calls, 1)
        self.assertEqual(mw.sound.stop_ding_calls, 1)
        self.assertTrue(mw.controls_enabled)
        self.assertEqual(mw.pending, 0)
        self.assertEqual(mw.summary.value, "summary.team_impossible")
        self.assertTrue(mw.overlay.messages)
        title, lines = mw.overlay.messages[-1]
        self.assertEqual(title, "overlay.team_impossible_title")
        self.assertEqual(lines[:2], ["overlay.team_impossible_line1", "overlay.team_impossible_line2"])


if __name__ == "__main__":
    unittest.main()
