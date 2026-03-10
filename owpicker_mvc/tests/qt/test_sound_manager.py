from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from tests.qt_test_guard import require_pyside6
require_pyside6()

from services.app_settings import AppSettings
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


class _PlayingFakeEffect(_FakeEffect):
    def __init__(self, *, playing: bool = False) -> None:
        super().__init__()
        self._playing = bool(playing)

    def stop(self) -> None:
        super().stop()
        self._playing = False

    def play(self) -> None:
        super().play()
        self._playing = True

    def isPlaying(self) -> bool:
        return bool(self._playing)


class _MutatingEffect(_FakeEffect):
    def __init__(self, manager: SoundManager, injected_key: Path) -> None:
        super().__init__()
        self._manager = manager
        self._injected_key = injected_key

    def setVolume(self, value: float) -> None:
        super().setVolume(value)
        self._manager.spin_effects[self._injected_key] = _FakeEffect()


class _FakeWarmupTimer:
    def __init__(self) -> None:
        self.started: list[int] = []
        self.single_shot = False
        self.parent = None

    def setParent(self, parent) -> None:
        self.parent = parent

    def setSingleShot(self, value: bool) -> None:
        self.single_shot = bool(value)

    def start(self, interval_ms: int) -> None:
        self.started.append(int(interval_ms))

    def stop(self) -> None:
        return

    def deleteLater(self) -> None:
        return


class _FakeSpinTimer:
    def __init__(self) -> None:
        self.stop_calls = 0
        self.delete_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1

    def deleteLater(self) -> None:
        self.delete_calls += 1


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

    def test_play_spin_stops_existing_ding_effects_before_new_play(self):
        sm = SoundManager(base_dir=Path("."))
        p_spin = Path("spin.wav")
        p_ding = Path("ding.wav")
        spin_eff = _FakeEffect()
        ding_eff = _FakeEffect()
        sm.spin_sources = [p_spin]
        sm.spin_effects = {p_spin: spin_eff}
        sm.ding_effects = {p_ding: ding_eff}
        sm._maybe_start_lazy_warmup = lambda: None

        sm.play_spin()

        self.assertGreaterEqual(ding_eff.stop_calls, 1)
        self.assertGreaterEqual(spin_eff.play_calls, 1)

    def test_stop_spin_cancels_pending_spin_start_timer(self):
        sm = SoundManager(base_dir=Path("."))
        timer = _FakeSpinTimer()
        sm._pending_spin_timer = timer
        sm._pending_spin_effect = object()

        sm.stop_spin()

        self.assertEqual(timer.stop_calls, 1)
        self.assertEqual(timer.delete_calls, 1)
        self.assertIsNone(sm._pending_spin_timer)
        self.assertIsNone(sm._pending_spin_effect)

    def test_play_spin_windows_profile_low_uses_20ms_gap(self):
        sm = SoundManager(base_dir=Path("."))
        sm._settings = AppSettings(
            values={
                "SOUND_SPIN_RESTART_GAP_MS": -1,
                "SOUND_SPIN_RESTART_GAP_PROFILE": "low",
            }
        )
        p1 = Path("a.wav")
        sm.spin_sources = [p1]
        sm.spin_effects = {p1: _FakeEffect()}
        sm._maybe_start_lazy_warmup = lambda: None
        recorded: list[int] = []
        sm._schedule_spin_start = lambda _eff, delay_ms: recorded.append(int(delay_ms))

        with patch("services.sound.sys.platform", "win32"):
            sm.play_spin()

        self.assertEqual(recorded, [20])

    def test_play_spin_windows_profile_high_uses_40ms_gap(self):
        sm = SoundManager(base_dir=Path("."))
        sm._settings = AppSettings(
            values={
                "SOUND_SPIN_RESTART_GAP_MS": -1,
                "SOUND_SPIN_RESTART_GAP_PROFILE": "high",
            }
        )
        p1 = Path("a.wav")
        sm.spin_sources = [p1]
        sm.spin_effects = {p1: _FakeEffect()}
        sm._maybe_start_lazy_warmup = lambda: None
        recorded: list[int] = []
        sm._schedule_spin_start = lambda _eff, delay_ms: recorded.append(int(delay_ms))

        with patch("services.sound.sys.platform", "win32"):
            sm.play_spin()

        self.assertEqual(recorded, [40])

    def test_play_spin_explicit_gap_overrides_profile(self):
        sm = SoundManager(base_dir=Path("."))
        sm._settings = AppSettings(
            values={
                "SOUND_SPIN_RESTART_GAP_MS": 55,
                "SOUND_SPIN_RESTART_GAP_PROFILE": "low",
            }
        )
        p1 = Path("a.wav")
        sm.spin_sources = [p1]
        sm.spin_effects = {p1: _FakeEffect()}
        sm._maybe_start_lazy_warmup = lambda: None
        recorded: list[int] = []
        sm._schedule_spin_start = lambda _eff, delay_ms: recorded.append(int(delay_ms))

        with patch("services.sound.sys.platform", "win32"):
            sm.play_spin()

        self.assertEqual(recorded, [55])

    def test_play_spin_active_effect_uses_audio_stop_guard_delay(self):
        sm = SoundManager(base_dir=Path("."))
        p1 = Path("a.wav")
        active_eff = _PlayingFakeEffect(playing=True)
        sm.spin_sources = [p1]
        sm.spin_effects = {p1: active_eff}
        sm._maybe_start_lazy_warmup = lambda: None
        sm._resolve_spin_restart_gap_ms = lambda: 20
        sm._resolve_audio_stop_guard_ms = lambda: 80
        recorded: list[int] = []
        sm._schedule_spin_start = lambda _eff, delay_ms: recorded.append(int(delay_ms))

        with patch("services.sound.time.monotonic", return_value=100.0):
            sm.play_spin()

        self.assertEqual(recorded, [80])

    def test_play_spin_inactive_effect_keeps_restart_gap_without_guard(self):
        sm = SoundManager(base_dir=Path("."))
        p1 = Path("a.wav")
        inactive_eff = _PlayingFakeEffect(playing=False)
        sm.spin_sources = [p1]
        sm.spin_effects = {p1: inactive_eff}
        sm._maybe_start_lazy_warmup = lambda: None
        sm._resolve_spin_restart_gap_ms = lambda: 20
        sm._resolve_audio_stop_guard_ms = lambda: 80
        recorded: list[int] = []
        sm._schedule_spin_start = lambda _eff, delay_ms: recorded.append(int(delay_ms))

        with patch("services.sound.time.monotonic", return_value=100.0):
            sm.play_spin()

        self.assertEqual(recorded, [20])

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

    def test_warmup_async_only_queues_uncached_sources(self):
        sm = SoundManager(base_dir=Path("."))
        a = Path("a.wav")
        b = Path("b.wav")
        c = Path("c.wav")
        sm.spin_sources = [a, b]
        sm.ding_sources = [c]
        sm.spin_effects = {a: _FakeEffect()}
        sm.ding_effects = {}
        sm._warmup_timer = _FakeWarmupTimer()

        sm.warmup_async(step_ms=7)

        queued_paths = [path for path, _cache, _volume in sm._warmup_items]
        self.assertEqual(queued_paths, [b, c])
        self.assertEqual(sm._warmup_timer.started, [7])

    def test_warmup_async_does_not_duplicate_existing_queue_entries(self):
        sm = SoundManager(base_dir=Path("."))
        a = Path("a.wav")
        b = Path("b.wav")
        sm.spin_sources = [a, b]
        sm.ding_sources = []
        sm.spin_effects = {}
        sm._warmup_items = [(a, sm.spin_effects, sm.spin_base_volume)]
        sm._warmup_timer = _FakeWarmupTimer()

        sm.warmup_async(step_ms=5)

        queued_paths = [path for path, _cache, _volume in sm._warmup_items]
        self.assertEqual(queued_paths.count(a), 1)
        self.assertIn(b, queued_paths)


if __name__ == "__main__":
    unittest.main()
