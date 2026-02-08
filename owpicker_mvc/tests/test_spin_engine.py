import unittest
from unittest.mock import patch

from logic.spin_engine import _turns_for_duration, plan_spin


class TestSpinEngine(unittest.TestCase):
    def test_turns_for_duration_minimum(self):
        with patch("logic.spin_engine.random.choice", return_value=0):
            self.assertEqual(_turns_for_duration(0), 3)

    def test_turns_for_duration_clamps_upper_bound(self):
        with patch("logic.spin_engine.random.choice", return_value=1):
            # Very large duration must still clamp to max 12 turns.
            self.assertEqual(_turns_for_duration(60_000), 12)

    def test_plan_spin_uses_pointer_alignment_and_turns(self):
        with patch("logic.spin_engine._turns_for_duration", return_value=4):
            plan = plan_spin(current_deg=10.0, slice_center_deg=90.0, duration_ms=3000)
        self.assertEqual(plan.start_deg, 10.0)
        self.assertEqual(plan.end_deg, 1800.0)
        self.assertEqual(plan.duration_ms, 3000)

    def test_plan_spin_normalizes_negative_current_angle(self):
        with patch("logic.spin_engine._turns_for_duration", return_value=3):
            plan = plan_spin(current_deg=-45.0, slice_center_deg=180.0, duration_ms=1200)
        self.assertEqual(plan.start_deg, 315.0)
        self.assertEqual(plan.duration_ms, 1200)
        # End must always be strictly larger than start due to at least 3 turns.
        self.assertGreater(plan.end_deg, plan.start_deg)


if __name__ == "__main__":
    unittest.main()
