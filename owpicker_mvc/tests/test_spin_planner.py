import unittest
from unittest.mock import patch
from logic import spin_planner


class TestSpinPlanner(unittest.TestCase):
    def test_empty_input(self):
        self.assertIsNone(spin_planner.plan_assignments([]))

    def test_single_role(self):
        result = spin_planner.plan_assignments([[("Alice", ["Alice"])]])
        self.assertEqual(result, ["Alice"])

    def test_two_roles_conflict(self):
        # Beide Rollen hätten nur denselben Spieler → keine Lösung
        candidates = [
            [("A", ["P1"])],
            [("B", ["P1"])],
        ]
        self.assertIsNone(spin_planner.plan_assignments(candidates))

    def test_three_roles_non_conflicting(self):
        candidates = [
            [("A", ["P1"]), ("A2", ["P2"])],
            [("B", ["P2"]), ("B2", ["P3"])],
            [("C", ["P3"]), ("C2", ["P1"])],
        ]
        result = spin_planner.plan_assignments(candidates)
        self.assertIsNotNone(result)
        # Keine doppelten Spieler in der Auswahl
        used = []
        for idx, label in enumerate(result):
            if label is None:
                continue
            players = [p.strip() for p in label.split("+") if p.strip()]
            used.extend(players)
        self.assertEqual(len(used), len(set(used)))

    def test_role_with_no_candidates_returns_none(self):
        candidates = [
            [("A", ["P1"])],
            [],
        ]
        self.assertIsNone(spin_planner.plan_assignments(candidates))

    def test_pair_candidate_conflict(self):
        candidates = [
            [("P1 + P2", ["P1", "P2"])],
            [("P2 + P3", ["P2", "P3"]), ("P4", ["P4"])],
        ]
        with patch("logic.spin_planner.random.shuffle", lambda seq: None):
            result = spin_planner.plan_assignments(candidates)
        self.assertEqual(result, ["P1 + P2", "P4"])


if __name__ == "__main__":
    unittest.main()
