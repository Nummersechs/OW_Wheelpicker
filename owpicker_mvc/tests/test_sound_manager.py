from __future__ import annotations

import unittest
from pathlib import Path

from services.sound import SoundManager


class _FakeEffect:
    def __init__(self) -> None:
        self.stop_calls = 0
        self.play_calls = 0
        self.volume_calls = []

    def stop(self) -> None:
        self.stop_calls += 1

    def play(self) -> None:
        self.play_calls += 1

    def setVolume(self, value: float) -> None:
        self.volume_calls.append(float(value))


class _MutatingEffect(_FakeEffect):
    def __init__(self, manager: SoundManager, injected_key: Path) -> None:
        super().__init__()
        self._manager = manager
        self._injected_key = injected_key

    def setVolume(self, value: float) -> None:
        super().setVolume(value)
        self._manager.spin_effects[self._injected_key] = _FakeEffect()


class TestSoundManager(unittest.TestCase):
    def test_play_spin_stops_existing_spin_effects_before_new_play(self):
        sm = SoundManager(base_dir=Path("."))
        p1 = Path("a.wav")
        p2 = Path("b.wav")
        e1 = _FakeEffect()
        e2 = _FakeEffect()
        sm.spin_sources = [p1, p2]
        sm.spin_effects = {p1: e1, p2: e2}
        sm._maybe_start_lazy_warmup = lambda: None

        sm.play_spin()

        self.assertGreaterEqual(e1.stop_calls, 1)
        self.assertGreaterEqual(e2.stop_calls, 1)
        self.assertGreaterEqual(e1.play_calls + e2.play_calls, 1)

    def test_apply_volume_handles_cache_mutation_safely(self):
        sm = SoundManager(base_dir=Path("."))
        p1 = Path("a.wav")
        p2 = Path("b.wav")
        sm.spin_effects = {p1: _MutatingEffect(sm, p2)}

        sm._apply_volume(sm.spin_effects.values(), 0.35)

        self.assertIn(p2, sm.spin_effects)

    def test_set_master_volume_rejects_invalid_values_without_throwing(self):
        sm = SoundManager(base_dir=Path("."))
        sm.set_master_volume("invalid")
        self.assertEqual(sm.master_volume, 1.0)


if __name__ == "__main__":
    unittest.main()
