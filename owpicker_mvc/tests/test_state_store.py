import unittest
from services.state_store import ModeStateStore
import config


class DummyBtn:
    def __init__(self, checked=True):
        self._checked = checked

    def isChecked(self):
        return self._checked


class DummyWheel:
    def __init__(self, entries, include=True, pair_mode=False, use_subroles=False):
        self._entries = entries
        self.btn_include_in_all = DummyBtn(include)
        self.pair_mode = pair_mode
        self.use_subrole_filter = use_subroles

    def get_current_entries(self):
        return self._entries


class TestStateStore(unittest.TestCase):
    def test_defaults_from_config(self):
        store = ModeStateStore.from_saved({})
        heroes = store.get_mode_state("heroes")
        self.assertTrue(heroes)
        self.assertEqual(
            len(heroes["Damage"]["entries"]), len(config.DEFAULT_HEROES["Damage"])
        )

    def test_capture_mode_from_wheels(self):
        store = ModeStateStore.from_saved({})
        wheels = {
            "Tank": DummyWheel([{"name": "Rein", "active": True, "subroles": []}], include=False),
            "Damage": DummyWheel([{"name": "Echo", "active": True, "subroles": []}], pair_mode=True),
            "Support": DummyWheel([{"name": "Ana", "active": True, "subroles": []}], use_subroles=True),
        }
        store.capture_mode_from_wheels("players", wheels, hero_ban_active=False)
        players = store.get_mode_state("players")
        self.assertFalse(players["Tank"]["include_in_all"])
        self.assertTrue(players["Damage"]["pair_mode"])
        self.assertTrue(players["Support"]["use_subroles"])
        self.assertEqual(players["Damage"]["entries"][0]["name"], "Echo")

    def test_to_saved_structure(self):
        store = ModeStateStore.from_saved({})
        saved = store.to_saved(volume=42)
        self.assertIn("players", saved)
        self.assertIn("heroes", saved)
        self.assertEqual(saved["volume"], 42)


if __name__ == "__main__":
    unittest.main()
