import unittest

from controller import shutdown_manager


class _FakeTimer:
    def __init__(self, *, active: bool = False, raise_runtime: bool = False):
        self._active = bool(active)
        self._raise_runtime = bool(raise_runtime)

    def isActive(self) -> bool:
        if self._raise_runtime:
            raise RuntimeError("timer failure")
        return self._active


class _SnapshotSource:
    def __init__(self, payload=None, error: Exception | None = None):
        self._payload = payload if payload is not None else {}
        self._error = error

    def resource_snapshot(self):
        if self._error is not None:
            raise self._error
        return dict(self._payload)


class _DummyMainWindow:
    def __init__(self, *, trace_shutdown: bool = False):
        self._trace_shutdown = bool(trace_shutdown)
        self._events: list[tuple[str, dict]] = []
        self._qt_timers = []
        self._timers = None
        self.state_sync = None
        self._tooltip_manager = None
        self.sound = None
        self.player_list_panel = None
        self.map_ui = None

    def _cfg(self, key: str, default=None):
        if key == "TRACE_SHUTDOWN":
            return self._trace_shutdown
        return default

    def _trace_event(self, name: str, **payload):
        self._events.append((name, dict(payload)))

    def findChildren(self, _cls):
        return list(self._qt_timers)


class _CfgRaiser:
    def _cfg(self, _key: str, _default=None):
        raise RuntimeError("cfg failure")


class _StepTracer:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def _trace_event(self, name: str, **payload):
        self.events.append((name, dict(payload)))


class TestShutdownManager(unittest.TestCase):
    def test_merge_shutdown_snapshot_prefixes_keys(self):
        target = {"keep": 1}
        shutdown_manager.merge_shutdown_snapshot("state_sync", {"active": 2, "pending": True}, target)
        self.assertEqual(
            target,
            {
                "keep": 1,
                "state_sync_active": 2,
                "state_sync_pending": True,
            },
        )

    def test_shutdown_resource_snapshot_merges_component_payloads(self):
        mw = _DummyMainWindow(trace_shutdown=False)
        mw._qt_timers = [_FakeTimer(active=True), _FakeTimer(active=False)]
        mw._timers = _SnapshotSource({"registered": 3, "active": 1})
        mw.state_sync = _SnapshotSource({"closed": False})
        mw._tooltip_manager = _SnapshotSource({"enabled": True})

        snapshot = shutdown_manager.shutdown_resource_snapshot(mw)

        self.assertEqual(snapshot["qt_timers_total"], 2)
        self.assertEqual(snapshot["qt_timers_active"], 1)
        self.assertEqual(snapshot["registry_registered"], 3)
        self.assertEqual(snapshot["registry_active"], 1)
        self.assertEqual(snapshot["state_sync_closed"], False)
        self.assertEqual(snapshot["tooltip_enabled"], True)

    def test_shutdown_resource_snapshot_traces_snapshot_errors_when_enabled(self):
        mw = _DummyMainWindow(trace_shutdown=True)
        mw._qt_timers = [_FakeTimer(raise_runtime=True)]
        mw.state_sync = _SnapshotSource(error=RuntimeError("snapshot failure"))

        snapshot = shutdown_manager.shutdown_resource_snapshot(mw)

        self.assertIn("qt_timers_total", snapshot)
        error_events = [payload for name, payload in mw._events if name == "shutdown_snapshot:error"]
        self.assertTrue(error_events)
        components = {str(payload.get("component")) for payload in error_events}
        self.assertIn("qt_timer", components)
        self.assertIn("state_sync", components)

    def test_cfg_falls_back_to_default_when_main_window_cfg_fails(self):
        mw = _CfgRaiser()
        self.assertEqual(shutdown_manager._cfg(mw, "DEBUG", False), False)
        self.assertEqual(shutdown_manager._cfg(mw, "MISSING", "x"), "x")

    def test_run_shutdown_step_traces_success_and_error(self):
        tracer = _StepTracer()
        shutdown_manager.run_shutdown_step(tracer, "ok_step", lambda: None)

        def _explode():
            raise RuntimeError("boom")

        shutdown_manager.run_shutdown_step(tracer, "bad_step", _explode)

        names = [name for name, _ in tracer.events]
        self.assertEqual(
            names,
            [
                "shutdown_step:start",
                "shutdown_step:ok",
                "shutdown_step:start",
                "shutdown_step:error",
            ],
        )


if __name__ == "__main__":
    unittest.main()
