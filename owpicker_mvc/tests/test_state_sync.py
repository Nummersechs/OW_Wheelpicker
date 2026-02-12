import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6 import QtCore

from controller.state_sync import StateSyncController


class DummySlider:
    def __init__(self, value: int = 100):
        self._value = int(value)

    def value(self) -> int:
        return int(self._value)

    def set_value(self, value: int) -> None:
        self._value = int(value)


class DummyWheel:
    def __init__(self, names):
        self._names = list(names)
        self.pair_mode = False

    def get_current_names(self):
        return list(self._names)


class DummyStore:
    def __init__(self):
        self.capture_calls = []
        self.payload_version = 0

    def capture_mode_from_wheels(self, mode, wheels, hero_ban_active=False):
        self.capture_calls.append(
            {
                "mode": mode,
                "hero_ban_active": bool(hero_ban_active),
                "roles": sorted(list(wheels.keys())),
            }
        )

    def to_saved(self, volume: int):
        return {
            "players": {"version": self.payload_version},
            "heroes": {},
            "maps": {},
            "volume": int(volume),
        }


class DummyMapMode:
    def __init__(self):
        self.capture_calls = 0

    def capture_state(self):
        self.capture_calls += 1


class DummyMainWindow(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self._state_store = DummyStore()
        self.map_mode = DummyMapMode()
        self.volume_slider = DummySlider(100)
        self.tank = DummyWheel(["T1"])
        self.dps = DummyWheel(["D1"])
        self.support = DummyWheel(["S1"])
        self.current_mode = "players"
        self.last_non_hero_mode = "players"
        self.hero_ban_active = False
        self.map_lists = None
        self.language = "en"
        self.theme = "light"
        self.online_mode = False
        self._restoring_state = False
        self._closing = False
        self.hero_ban_rebuild_calls = 0

    def _update_hero_ban_wheel(self):
        self.hero_ban_rebuild_calls += 1


class TestStateSyncController(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])

    def _make_controller(self):
        tmp = tempfile.TemporaryDirectory()
        state_file = Path(tmp.name) / "saved_state.json"
        mw = DummyMainWindow()
        controller = StateSyncController(mw, state_file)
        return tmp, mw, controller

    def test_gather_state_uses_last_non_hero_mode_for_maps(self):
        tmp, mw, controller = self._make_controller()
        try:
            mw.current_mode = "maps"
            mw.last_non_hero_mode = "heroes"
            state = controller.gather_state()
            self.assertIn("volume", state)
            self.assertTrue(mw._state_store.capture_calls)
            self.assertEqual(mw._state_store.capture_calls[-1]["mode"], "heroes")
        finally:
            controller.shutdown(flush=False)
            tmp.cleanup()

    def test_immediate_save_deduplicates_identical_state(self):
        tmp, _mw, controller = self._make_controller()
        try:
            with patch.object(StateSyncController, "_save_state", return_value=True) as save_mock:
                controller.save_state(sync=False, immediate=True)
                controller.save_state(sync=False, immediate=True)
                self.assertEqual(save_mock.call_count, 1)
        finally:
            controller.shutdown(flush=False)
            tmp.cleanup()

    def test_debounced_save_flushes_latest_state(self):
        tmp, mw, controller = self._make_controller()
        try:
            with patch.object(StateSyncController, "_save_state", return_value=True) as save_mock:
                mw.volume_slider.set_value(11)
                mw._state_store.payload_version = 1
                controller.save_state(sync=False, immediate=False)
                mw.volume_slider.set_value(22)
                mw._state_store.payload_version = 2
                controller.save_state(sync=False, immediate=False)
                self.assertEqual(save_mock.call_count, 0)
                controller._flush_pending_save()
                self.assertEqual(save_mock.call_count, 1)
                saved_payload = save_mock.call_args.args[1]
                self.assertEqual(saved_payload["volume"], 22)
                self.assertEqual(saved_payload["players"]["version"], 2)
        finally:
            controller.shutdown(flush=False)
            tmp.cleanup()

    def test_debounced_save_gathers_state_only_on_flush(self):
        tmp, _mw, controller = self._make_controller()
        try:
            with (
                patch.object(controller, "gather_state", wraps=controller.gather_state) as gather_mock,
                patch.object(StateSyncController, "_save_state", return_value=True),
            ):
                controller.save_state(sync=False, immediate=False)
                controller.save_state(sync=False, immediate=False)
                self.assertEqual(gather_mock.call_count, 0)
                controller._flush_pending_save()
                self.assertEqual(gather_mock.call_count, 1)
        finally:
            controller.shutdown(flush=False)
            tmp.cleanup()

    def test_pending_sync_is_merged_until_save_flush(self):
        tmp, mw, controller = self._make_controller()
        try:
            mw.online_mode = True
            with (
                patch.object(StateSyncController, "_save_state", return_value=True),
                patch.object(controller, "sync_all_roles") as sync_mock,
            ):
                controller.save_state(sync=False, immediate=False)
                controller.save_state(sync=True, immediate=False)
                controller._flush_pending_save()
                sync_mock.assert_called_once()
        finally:
            controller.shutdown(flush=False)
            tmp.cleanup()

    def test_shutdown_flush_persists_pending_state(self):
        tmp, _mw, controller = self._make_controller()
        try:
            with patch.object(StateSyncController, "_save_state", return_value=True) as save_mock:
                controller.save_state(sync=False, immediate=False)
                controller.shutdown(flush=True)
                self.assertEqual(save_mock.call_count, 1)
        finally:
            tmp.cleanup()

    def test_shutdown_without_flush_discards_pending_state(self):
        tmp, _mw, controller = self._make_controller()
        try:
            with patch.object(StateSyncController, "_save_state", return_value=True) as save_mock:
                controller.save_state(sync=False, immediate=False)
                controller.shutdown(flush=False)
                self.assertEqual(save_mock.call_count, 0)
        finally:
            tmp.cleanup()

    def test_split_pair_label(self):
        self.assertEqual(StateSyncController._split_pair_label("Ana", False), ("Ana", ""))
        self.assertEqual(StateSyncController._split_pair_label("Ana + Bap", True), ("Ana", "Bap"))
        self.assertEqual(
            StateSyncController._split_pair_label("Ana + Bap + Kiriko", True),
            ("Ana", "Bap + Kiriko"),
        )
        self.assertEqual(StateSyncController._split_pair_label("  ", True), ("", ""))

    def test_send_spin_result_offline_is_noop(self):
        tmp, mw, controller = self._make_controller()
        try:
            mw.online_mode = False
            with patch.object(controller, "_send_spin_result") as send_mock:
                controller.send_spin_result("T", "D", "S")
                send_mock.assert_not_called()
        finally:
            controller.shutdown(flush=False)
            tmp.cleanup()

    def test_sync_all_roles_offline_clears_pending(self):
        tmp, mw, controller = self._make_controller()
        try:
            mw.online_mode = False
            controller._pending_sync_payload = [{"role": "Tank", "names": ["A"]}]
            controller._pending_sync_dirty = True
            controller._sync_timer.start(1_000)
            controller.sync_all_roles()
            self.assertIsNone(controller._pending_sync_payload)
            self.assertFalse(controller._pending_sync_dirty)
            self.assertFalse(controller._sync_timer.isActive())
        finally:
            controller.shutdown(flush=False)
            tmp.cleanup()

    def test_sync_all_roles_online_sets_payload(self):
        tmp, mw, controller = self._make_controller()
        try:
            mw.online_mode = True
            controller.sync_all_roles()
            self.assertTrue(controller._pending_sync_dirty)
            self.assertIsNone(controller._pending_sync_payload)
            self.assertTrue(controller._sync_timer.isActive())
        finally:
            controller.shutdown(flush=False)
            tmp.cleanup()

    def test_executor_is_lazy_until_first_network_post(self):
        tmp, _mw, controller = self._make_controller()
        try:
            self.assertIsNone(controller._executor)
            with (
                patch.object(controller, "_get_requests_module", return_value=None),
                patch.object(controller, "_ensure_executor", wraps=controller._ensure_executor) as ensure_mock,
            ):
                controller._post_json_async(
                    endpoint="/roles-sync",
                    payload={"roles": []},
                    payload_log="SYNC →",
                    success_log="SYNC OK:",
                    error_log="Fehler beim Rollen-Sync:",
                    missing_requests_log="Requests not available – roles not synced.",
                )
                ensure_mock.assert_not_called()
            self.assertIsNone(controller._executor)
        finally:
            controller.shutdown(flush=False)
            tmp.cleanup()

    def test_flush_role_sync_dispatches_payload(self):
        tmp, mw, controller = self._make_controller()
        try:
            mw.online_mode = True
            controller._pending_sync_payload = [{"role": "Tank", "names": ["A"]}]
            with patch.object(controller, "_sync_roles") as sync_mock:
                controller._flush_role_sync()
                sync_mock.assert_called_once_with([{"role": "Tank", "names": ["A"]}])
                self.assertIsNone(controller._pending_sync_payload)
        finally:
            controller.shutdown(flush=False)
            tmp.cleanup()

    def test_flush_role_sync_skips_identical_payloads(self):
        tmp, mw, controller = self._make_controller()
        try:
            mw.online_mode = True
            with patch.object(controller, "_sync_roles") as sync_mock:
                controller._pending_sync_payload = [{"role": "Tank", "names": ["A"]}]
                controller._flush_role_sync()
                controller._pending_sync_payload = [{"role": "Tank", "names": ["A"]}]
                controller._flush_role_sync()
                sync_mock.assert_called_once_with([{"role": "Tank", "names": ["A"]}])
        finally:
            controller.shutdown(flush=False)
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
