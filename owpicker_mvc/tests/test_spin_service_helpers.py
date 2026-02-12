import unittest
from unittest.mock import patch

from controller import spin_service


class DummySound:
    def __init__(self):
        self.stop_spin_calls = 0
        self.stop_ding_calls = 0
        self.play_spin_calls = 0

    def stop_spin(self):
        self.stop_spin_calls += 1

    def stop_ding(self):
        self.stop_ding_calls += 1

    def play_spin(self):
        self.play_spin_calls += 1


class DummySummary:
    def __init__(self):
        self.value = ""

    def setText(self, value: str):
        self.value = value


class DummyOverlay:
    def __init__(self):
        self.messages = []
        self.hidden = False

    def show_message(self, title, lines):
        self.messages.append((title, list(lines)))

    def hide(self):
        self.hidden = True


class DummyWheel:
    def __init__(self):
        self.clear_calls = 0

    def clear_result(self):
        self.clear_calls += 1


class DummyMW:
    def __init__(self):
        self.sound = DummySound()
        self.summary = DummySummary()
        self.overlay = DummyOverlay()
        self.pending = 2
        self.controls_enabled = None
        self.snapshot_calls = 0
        self.stop_all_wheels_calls = 0

    def _set_controls_enabled(self, enabled: bool):
        self.controls_enabled = bool(enabled)

    def _snapshot_results(self):
        self.snapshot_calls += 1

    def _stop_all_wheels(self):
        self.stop_all_wheels_calls += 1


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

    def test_begin_spin_run_stops_existing_sounds_before_play(self):
        mw = DummyMW()
        wheel = DummyWheel()

        spin_service._begin_spin_run(mw, [("tank", wheel)])

        self.assertEqual(mw.snapshot_calls, 1)
        self.assertEqual(wheel.clear_calls, 1)
        self.assertEqual(mw.sound.stop_spin_calls, 1)
        self.assertEqual(mw.sound.stop_ding_calls, 1)
        self.assertEqual(mw.sound.play_spin_calls, 1)
        self.assertEqual(mw.stop_all_wheels_calls, 1)
        self.assertEqual(mw.pending, 0)
        self.assertEqual(mw.summary.value, "")
        self.assertFalse(mw.controls_enabled)
        self.assertTrue(mw.overlay.hidden)


if __name__ == "__main__":
    unittest.main()
