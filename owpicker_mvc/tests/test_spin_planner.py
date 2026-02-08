import unittest
from logic import spin_planner


class TestSpinPlanner(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
