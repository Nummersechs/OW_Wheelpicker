import unittest

from controller.timer_registry import TimerRegistry


class FakeTimer:
    def __init__(self, active: bool = False, fail_on_is_active: bool = False, fail_on_stop: bool = False):
        self._active = bool(active)
        self._fail_on_is_active = bool(fail_on_is_active)
        self._fail_on_stop = bool(fail_on_stop)
        self.stop_calls = 0

    def isActive(self) -> bool:
        if self._fail_on_is_active:
            raise RuntimeError("isActive failure")
        return self._active

    def stop(self) -> None:
        self.stop_calls += 1
        if self._fail_on_stop:
            raise RuntimeError("stop failure")
        self._active = False


class TestTimerRegistry(unittest.TestCase):
    def test_register_and_unregister(self):
        reg = TimerRegistry()
        t1 = FakeTimer(active=True)
        self.assertIs(reg.register(t1), t1)
        reg.unregister(t1)
        reg.stop_all()
        self.assertEqual(t1.stop_calls, 0)

    def test_stop_all_stops_active_timers_and_clears_registry(self):
        reg = TimerRegistry()
        active = FakeTimer(active=True)
        inactive = FakeTimer(active=False)
        reg.register(active)
        reg.register(inactive)
        reg.stop_all()
        self.assertEqual(active.stop_calls, 1)
        self.assertEqual(inactive.stop_calls, 0)
        # Second call should do nothing because registry was cleared.
        reg.stop_all()
        self.assertEqual(active.stop_calls, 1)

    def test_stop_all_ignores_timer_errors(self):
        reg = TimerRegistry()
        bad1 = FakeTimer(active=True, fail_on_is_active=True)
        bad2 = FakeTimer(active=True, fail_on_stop=True)
        reg.register(bad1)
        reg.register(bad2)
        reg.stop_all()
        # bad2 attempted stop despite raising; registry still cleared.
        self.assertEqual(bad2.stop_calls, 1)
        reg.stop_all()
        self.assertEqual(bad2.stop_calls, 1)

    def test_stop_all_ignores_non_timer_like_objects(self):
        reg = TimerRegistry()
        reg.register(object())
        reg.stop_all()
        self.assertEqual(reg.snapshot()["registered"], 0)


if __name__ == "__main__":
    unittest.main()
