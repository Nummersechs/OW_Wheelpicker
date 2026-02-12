import unittest

from model.wheel_state import WheelState


class TestWheelState(unittest.TestCase):
    def test_single_mode_returns_base_names(self):
        state = WheelState(pair_mode=False, use_subrole_filter=True, subrole_labels=["A", "B"])
        entries = [
            {"name": "Alpha", "subroles": ["A"]},
            {"name": "Bravo", "subroles": ["B"]},
        ]
        self.assertEqual(state.effective_names_from(entries), ["Alpha", "Bravo"])

    def test_pair_mode_without_subrole_filter_ignores_subroles(self):
        state = WheelState(pair_mode=True, use_subrole_filter=False, subrole_labels=["A", "B"])
        entries = [
            {"name": "Alpha", "subroles": ["A"]},
            {"name": "Bravo", "subroles": []},
            {"name": "Charlie", "subroles": ["B"]},
        ]
        self.assertEqual(
            state.effective_names_from(entries),
            ["Alpha + Bravo", "Alpha + Charlie", "Bravo + Charlie"],
        )

    def test_pair_mode_with_subrole_filter_requires_cross_match(self):
        state = WheelState(pair_mode=True, use_subrole_filter=True, subrole_labels=["Main", "Off"])
        entries = [
            {"name": "Alpha", "subroles": ["Main"]},
            {"name": "Bravo", "subroles": ["Off"]},
            {"name": "Charlie", "subroles": ["Main"]},
        ]
        self.assertEqual(
            state.effective_names_from(entries),
            ["Alpha + Bravo", "Bravo + Charlie"],
        )

    def test_pair_mode_with_subrole_filter_and_plain_names_returns_empty(self):
        state = WheelState(pair_mode=True, use_subrole_filter=True, subrole_labels=["Main", "Off"])
        self.assertEqual(state.effective_names_from(["Alpha", "Bravo"]), [])

    def test_include_disabled_false_filters_disabled_indices(self):
        state = WheelState(pair_mode=False)
        names = ["Alpha", "Bravo", "Charlie"]
        state.disabled_indices = {1}
        self.assertEqual(state.effective_names_from(names, include_disabled=False), ["Alpha", "Charlie"])


if __name__ == "__main__":
    unittest.main()
