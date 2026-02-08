import unittest
from logic import hero_ban_merge


class DummyWheel:
    def __init__(self, entries):
        self._entries = entries

    def get_current_entries(self):
        return self._entries


class TestHeroBanMerge(unittest.TestCase):
    def test_merge_skips_inactive_and_dedupes(self):
        wheels = {
            "Tank": DummyWheel(
                [
                    {"name": "Rein", "active": True, "subroles": []},
                    {"name": "D.Va", "active": False, "subroles": []},
                ]
            ),
            "Damage": DummyWheel(
                [
                    {"name": "Rein", "active": True, "subroles": []},
                    {"name": "Echo", "active": True, "subroles": []},
                ]
            ),
        }
        merged = hero_ban_merge.merge_selected_roles(["Tank", "Damage"], wheels)
        names = [m["name"] for m in merged]
        self.assertIn("Rein", names)
        self.assertIn("Echo", names)
        # D.Va inaktiv → nicht enthalten
        self.assertNotIn("D.Va", names)
        # Rein nur einmal
        self.assertEqual(names.count("Rein"), 1)


if __name__ == "__main__":
    unittest.main()
