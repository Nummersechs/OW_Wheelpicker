import unittest

from controller.main_window import MainWindow
from controller.ocr.ocr_role_import import PendingOCRImport


class _FakeWheel:
    def __init__(self, names=None, subrole_labels=None):
        self.entries = [
            {"name": str(value).strip(), "subroles": [], "active": True}
            for value in (names or [])
            if str(value).strip()
        ]
        self.subrole_labels = [str(value).strip() for value in (subrole_labels or []) if str(value).strip()]

    def get_current_names(self):
        return [str(entry.get("name", "")).strip() for entry in self.entries if str(entry.get("name", "")).strip()]

    def add_name(self, name: str, active: bool = True, subroles=None) -> bool:
        value = str(name or "").strip()
        if not value:
            return False
        existing = {str(entry.get("name", "")).strip() for entry in self.entries}
        if value in existing:
            return False
        self.entries.append(
            {
                "name": value,
                "subroles": [str(v).strip() for v in list(subroles or []) if str(v).strip()],
                "active": bool(active),
            }
        )
        return True

    def load_entries(self, entries):
        self.entries = []
        for entry in entries or []:
            name = str((entry or {}).get("name", "")).strip()
            if not name:
                continue
            self.entries.append(
                {
                    "name": name,
                    "subroles": [
                        str(value).strip()
                        for value in list((entry or {}).get("subroles", []) or [])
                        if str(value).strip()
                    ],
                    "active": bool((entry or {}).get("active", True)),
                }
            )


class _FakeStateSync:
    def __init__(self) -> None:
        self.save_calls = 0

    def save_state(self, *args, **kwargs):
        self.save_calls += 1


class TestMainWindowOCRImport(unittest.TestCase):
    def _make_window(self) -> MainWindow:
        mw = MainWindow.__new__(MainWindow)
        mw.settings = {}
        mw.tank = _FakeWheel(subrole_labels=["MT", "OT"])
        mw.dps = _FakeWheel(subrole_labels=["HS", "FDPS"])
        mw.support = _FakeWheel(subrole_labels=["MS", "FS"])
        mw.state_sync = _FakeStateSync()
        mw._spin_all_updates = 0
        mw._update_spin_all_enabled = lambda: setattr(mw, "_spin_all_updates", mw._spin_all_updates + 1)
        return mw

    def test_apply_ocr_name_hints_maps_noisy_tokens_to_hint_names(self):
        mw = self._make_window()
        mw.settings.update(
            {
                "OCR_USE_NAME_HINTS": True,
                "OCR_EXPECTED_CANDIDATES": 5,
                "OCR_NAME_HINTS": ["Aero", "AJAR", "Massith", "Mika", "Nikeos"],
                "OCR_HINT_CORRECTION_MIN_SCORE": 0.62,
                "OCR_HINT_CORRECTION_LOW_CONF_MIN_SCORE": 0.28,
            }
        )

        corrected = MainWindow._apply_ocr_name_hints(
            mw,
            "dps",
            ["Aero", "BAO", "Rew", "MNKE"],
        )

        self.assertEqual(len(corrected), 5)
        self.assertEqual(set(corrected), {"Aero", "AJAR", "Massith", "Mika", "Nikeos"})
        self.assertEqual(corrected[0], "Aero")

    def test_selected_entries_for_pending_maps_role_assignments(self):
        mw = self._make_window()
        pending = PendingOCRImport(
            role_key="all",
            candidates=["Alpha", "Bravo", "Charlie", "Delta"],
            option_labels=["Tank", "DPS", "Support", "Main", "Flex"],
            option_assignment_by_label_key={
                "tank": "tank",
                "dps": "dps",
                "support": "support",
            },
            option_subrole_code_by_label_key={
                "main": "main",
                "flex": "flex",
            },
            hint_key="ocr.pick_hint_all_roles",
            hint_kwargs={},
        )
        payload = [
            {"name": "Bravo", "subroles": ["DPS", "Flex"]},
            {"name": "Alpha", "subroles": ["Tank", "Support", "Main"]},
            {"name": "Delta", "subroles": ["Main"]},
        ]

        entries = MainWindow._selected_ocr_entries_for_pending(mw, pending, payload)

        self.assertEqual([entry["name"] for entry in entries], ["Alpha", "Bravo", "Delta"])
        self.assertEqual(set(entries[0]["assignments"]), {"tank", "support"})
        self.assertEqual(entries[1]["assignments"], ["dps"])
        self.assertEqual(entries[2]["assignments"], [])
        self.assertEqual(entries[0]["subroles_by_role"], {"tank": ["MT"], "support": ["MS"]})
        self.assertEqual(entries[1]["subroles_by_role"], {"dps": ["FDPS"]})
        self.assertEqual(entries[2]["subrole_codes"], ["main"])

    def test_selected_entries_for_pending_keeps_duplicate_candidates_until_import(self):
        mw = self._make_window()
        pending = PendingOCRImport(
            role_key="all",
            candidates=["Alpha", "Alpha", "Bravo"],
            option_labels=["Tank", "DPS", "Support", "Main", "Flex"],
            option_assignment_by_label_key={
                "tank": "tank",
                "dps": "dps",
                "support": "support",
            },
            option_subrole_code_by_label_key={
                "main": "main",
                "flex": "flex",
            },
            hint_key="ocr.pick_hint_all_roles",
            hint_kwargs={},
        )
        payload = [
            {"name": "Alpha", "subroles": ["Tank"]},
            {"name": "Alpha", "subroles": ["Support"]},
            {"name": "Bravo", "subroles": ["DPS"]},
        ]

        entries = MainWindow._selected_ocr_entries_for_pending(mw, pending, payload)

        self.assertEqual([entry["name"] for entry in entries], ["Alpha", "Alpha", "Bravo"])
        self.assertEqual(entries[0]["assignments"], ["tank"])
        self.assertEqual(entries[1]["assignments"], ["support"])
        self.assertEqual(entries[2]["assignments"], ["dps"])

    def test_add_distributed_respects_explicit_roles_and_round_robin(self):
        mw = self._make_window()
        entries = [
            {"name": "MarkedDPS", "assignments": ["dps"], "subrole_codes": ["main"], "subroles_by_role": {}, "active": True},
            {"name": "UnmarkedA", "assignments": [], "active": True},
            {"name": "UnmarkedB", "assignments": [], "subrole_codes": ["flex"], "active": True},
            {
                "name": "MarkedMulti",
                "assignments": ["tank", "support"],
                "subrole_codes": ["main"],
                "subroles_by_role": {},
                "active": True,
            },
        ]

        added, counts = MainWindow._add_ocr_entries_distributed(mw, entries)

        self.assertEqual(added, 5)
        self.assertEqual(counts, {"tank": 2, "dps": 2, "support": 1})
        self.assertEqual(mw.tank.get_current_names(), ["UnmarkedA", "MarkedMulti"])
        self.assertEqual(mw.dps.get_current_names(), ["MarkedDPS", "UnmarkedB"])
        self.assertEqual(mw.support.get_current_names(), ["MarkedMulti"])
        self.assertEqual(mw.tank.entries[0]["subroles"], [])
        self.assertEqual(mw.tank.entries[1]["subroles"], ["MT"])
        self.assertEqual(mw.dps.entries[0]["subroles"], ["HS"])
        self.assertEqual(mw.dps.entries[1]["subroles"], ["FDPS"])
        self.assertEqual(mw.support.entries[0]["subroles"], ["MS"])
        self.assertEqual(mw.state_sync.save_calls, 1)
        self.assertEqual(mw._spin_all_updates, 1)

    def test_add_for_single_role_only_targets_that_role(self):
        mw = self._make_window()
        added = MainWindow._add_ocr_entries_for_role(
            mw,
            "support",
            [
                {"name": "Alpha", "assignments": ["tank"], "subroles_by_role": {"support": ["MS"]}, "subrole_codes": [], "active": True},
                {"name": "Alpha", "assignments": [], "active": True},
                {"name": "Bravo", "assignments": [], "subrole_codes": ["flex"], "active": True},
            ],
        )

        self.assertEqual(added, 2)
        self.assertEqual(mw.support.get_current_names(), ["Alpha", "Bravo"])
        self.assertEqual(mw.support.entries[0]["subroles"], ["MS"])
        self.assertEqual(mw.support.entries[1]["subroles"], ["FS"])
        self.assertEqual(mw.tank.get_current_names(), [])
        self.assertEqual(mw.dps.get_current_names(), [])
        self.assertEqual(mw.state_sync.save_calls, 1)
        self.assertEqual(mw._spin_all_updates, 1)

    def test_replace_distributed_respects_explicit_roles_for_all_roles_flow(self):
        mw = self._make_window()
        total, counts = MainWindow._replace_ocr_entries_distributed(
            mw,
            [
                {"name": "Alpha", "assignments": ["tank"], "subroles_by_role": {"tank": ["MT"]}, "subrole_codes": [], "active": True},
                {"name": "Bravo", "assignments": [], "active": True},
                {
                    "name": "Charlie",
                    "assignments": ["support", "dps"],
                    "subroles_by_role": {},
                    "subrole_codes": ["main"],
                    "active": True,
                },
            ],
        )

        self.assertEqual(total, 4)
        self.assertEqual(counts, {"tank": 2, "dps": 1, "support": 1})
        self.assertEqual(mw.tank.get_current_names(), ["Alpha", "Bravo"])
        self.assertEqual(mw.dps.get_current_names(), ["Charlie"])
        self.assertEqual(mw.support.get_current_names(), ["Charlie"])
        self.assertEqual(mw.tank.entries[0]["subroles"], ["MT"])
        self.assertEqual(mw.tank.entries[1]["subroles"], [])
        self.assertEqual(mw.dps.entries[0]["subroles"], ["HS"])
        self.assertEqual(mw.support.entries[0]["subroles"], ["MS"])
        self.assertEqual(mw.state_sync.save_calls, 1)
        self.assertEqual(mw._spin_all_updates, 1)

    def test_all_role_assignment_options_provide_exact_five_checkboxes(self):
        mw = self._make_window()
        labels, assignment_map, subrole_code_map, hint_key = MainWindow._ocr_assignment_options(mw, "all")
        self.assertEqual(labels, ["Tank", "DPS", "Support", "Main", "Flex"])
        self.assertEqual(hint_key, "ocr.pick_hint_all_roles")
        self.assertEqual(
            assignment_map,
            {
                "tank": "tank",
                "dps": "dps",
                "support": "support",
            },
        )
        self.assertEqual(
            subrole_code_map,
            {
                "main": "main",
                "flex": "flex",
            },
        )

    def test_release_ocr_runtime_cache_defers_while_spin_is_active(self):
        class _FakeTimer:
            def __init__(self):
                self.started: list[int] = []

            def start(self, timeout_ms):
                self.started.append(int(timeout_ms))

        mw = self._make_window()
        fake_timer = _FakeTimer()
        mw.pending = 1
        traces: list[tuple[str, dict]] = []
        mw._cfg = lambda key, default=None: 777 if key == "OCR_IDLE_CACHE_RELEASE_BUSY_RETRY_MS" else default
        mw._ensure_ocr_cache_release_timer = lambda: fake_timer
        mw._trace_event = lambda name, **extra: traces.append((name, extra))

        MainWindow._release_ocr_runtime_cache(mw)

        self.assertEqual(fake_timer.started, [777])
        self.assertTrue(any(name == "ocr_cache_release_deferred_busy" for name, _extra in traces))

    def test_release_ocr_runtime_cache_for_spin_can_be_disabled(self):
        mw = self._make_window()
        cancel_calls = {"count": 0}
        schedule_calls = {"count": 0}
        mw._cfg = lambda key, default=None: False if key == "OCR_RELEASE_CACHE_ON_SPIN" else default
        mw._cancel_ocr_runtime_cache_release = lambda: cancel_calls.__setitem__("count", cancel_calls["count"] + 1)
        mw._schedule_ocr_runtime_cache_release = lambda: schedule_calls.__setitem__("count", schedule_calls["count"] + 1)
        mw._ocr_async_job = None

        MainWindow._release_ocr_runtime_cache_for_spin(mw)

        self.assertEqual(cancel_calls["count"], 1)
        self.assertEqual(schedule_calls["count"], 1)


if __name__ == "__main__":
    unittest.main()
