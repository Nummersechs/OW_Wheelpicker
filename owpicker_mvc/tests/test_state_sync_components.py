import tempfile
import unittest
from pathlib import Path

from controller.state_sync_components import (
    LocalStatePersistenceQueue,
    RoleSyncPayloadBuilder,
    StateFilePersistence,
    StateSnapshotBuilder,
)


class DummySlider:
    def __init__(self, value: int = 100):
        self._value = int(value)

    def value(self) -> int:
        return int(self._value)


class DummyWheel:
    def __init__(self, names, *, pair_mode: bool = False):
        self._names = list(names)
        self.pair_mode = bool(pair_mode)

    def get_current_names(self):
        return list(self._names)


class DummyStore:
    def __init__(self):
        self.capture_calls = []

    def capture_mode_from_wheels(self, mode, wheels, hero_ban_active=False):
        self.capture_calls.append(
            {
                "mode": str(mode),
                "hero_ban_active": bool(hero_ban_active),
                "roles": sorted(list(wheels.keys())),
            }
        )

    def to_saved(self, volume: int):
        return {"players": {}, "heroes": {}, "maps": {}, "volume": int(volume)}


class DummyMapMode:
    def __init__(self):
        self.capture_calls = 0

    def capture_state(self):
        self.capture_calls += 1


class DummyMainWindow:
    def __init__(self):
        self._state_store = DummyStore()
        self.map_mode = DummyMapMode()
        self.volume_slider = DummySlider(75)
        self.tank = DummyWheel(["TankA"], pair_mode=True)
        self.dps = DummyWheel(["DpsA"])
        self.support = DummyWheel(["SupA", "SupB"], pair_mode=False)
        self.current_mode = "players"
        self.last_non_hero_mode = "heroes"
        self.hero_ban_active = False
        self.map_lists = None
        self.language = "de"
        self.theme = "dark"


class TestStateFilePersistence(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "saved_state.json"
            payload = {"players": {"Tank": ["A"]}, "volume": 42}
            self.assertTrue(StateFilePersistence.save_state(path, payload))
            loaded = StateFilePersistence.load_state(path)
            self.assertEqual(loaded, payload)

    def test_signature_none_for_unserializable(self):
        signature = StateFilePersistence.state_signature({"bad": set([1, 2, 3])})
        self.assertIsNone(signature)


class TestRoleSyncPayloadBuilder(unittest.TestCase):
    def setUp(self):
        self.mw = DummyMainWindow()
        self.builder = RoleSyncPayloadBuilder()

    def test_pair_modes(self):
        modes = self.builder.pair_modes(self.mw)
        self.assertEqual(modes.get("Tank"), True)
        self.assertEqual(modes.get("Damage"), False)
        self.assertEqual(modes.get("Support"), False)

    def test_roles_payload(self):
        payload = self.builder.roles_payload(self.mw)
        by_role = {entry["role"]: entry["names"] for entry in payload}
        self.assertEqual(by_role.get("Tank"), ["TankA"])
        self.assertEqual(by_role.get("Damage"), ["DpsA"])
        self.assertEqual(by_role.get("Support"), ["SupA", "SupB"])

    def test_split_pair_label(self):
        self.assertEqual(self.builder.split_pair_label("Ana", False), ("Ana", ""))
        self.assertEqual(self.builder.split_pair_label("Ana + Bap", True), ("Ana", "Bap"))
        self.assertEqual(self.builder.split_pair_label(" Ana + Bap + Kiri ", True), ("Ana", "Bap + Kiri"))
        self.assertEqual(self.builder.split_pair_label(" ", True), ("", ""))

    def test_spin_result_payload(self):
        payload = self.builder.spin_result_payload(
            tank="Rein + Zarya",
            damage="Soj",
            support="Ana + Lucio",
            pair_modes={"Tank": True, "Damage": False, "Support": True},
        )
        self.assertEqual(payload["tank1"], "Rein")
        self.assertEqual(payload["tank2"], "Zarya")
        self.assertEqual(payload["dps1"], "Soj")
        self.assertEqual(payload["dps2"], "")
        self.assertEqual(payload["support1"], "Ana")
        self.assertEqual(payload["support2"], "Lucio")


class TestLocalStatePersistenceQueue(unittest.TestCase):
    def test_consume_pending_uses_gather_when_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "saved_state.json"
            queue = LocalStatePersistenceQueue(
                state_file=path,
                load_state_fn=StateFilePersistence.load_state,
                save_state_fn=StateFilePersistence.save_state,
                state_signature_fn=StateFilePersistence.state_signature,
            )
            queue.queue_save(sync=True)
            gather_calls = {"count": 0}

            def _gather():
                gather_calls["count"] += 1
                return {"volume": 88}

            state, sync = queue.consume_pending(gather_state_fn=_gather)
            self.assertEqual(gather_calls["count"], 1)
            self.assertEqual(state, {"volume": 88})
            self.assertTrue(sync)
            self.assertFalse(queue.pending_state_dirty)
            self.assertFalse(queue.pending_save_sync)

    def test_persist_state_deduplicates_by_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "saved_state.json"
            queue = LocalStatePersistenceQueue(
                state_file=path,
                load_state_fn=StateFilePersistence.load_state,
                save_state_fn=StateFilePersistence.save_state,
                state_signature_fn=StateFilePersistence.state_signature,
            )
            payload = {"players": {"Tank": ["A"]}, "volume": 50}
            saved_first = queue.persist_state(payload)
            saved_second = queue.persist_state(payload)
            self.assertTrue(saved_first)
            self.assertFalse(saved_second)


class TestStateSnapshotBuilder(unittest.TestCase):
    def test_gather_state_maps_mode_uses_last_non_hero_mode(self):
        mw = DummyMainWindow()
        mw.current_mode = "maps"
        mw.last_non_hero_mode = "heroes"
        mw.hero_ban_active = True
        mw.map_lists = {"Control": ["Busan"]}
        builder = StateSnapshotBuilder(mw)

        state = builder.gather_state()

        self.assertEqual(state["volume"], 75)
        self.assertEqual(state["language"], "de")
        self.assertEqual(state["theme"], "dark")
        self.assertEqual(mw.map_mode.capture_calls, 1)
        self.assertTrue(mw._state_store.capture_calls)
        last_call = mw._state_store.capture_calls[-1]
        self.assertEqual(last_call["mode"], "heroes")
        self.assertEqual(last_call["hero_ban_active"], True)


if __name__ == "__main__":
    unittest.main()
