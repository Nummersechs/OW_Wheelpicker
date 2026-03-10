import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.qt_test_guard import import_qt
QtGui, = import_qt("QtGui")
from controller.ocr.ocr_capture_ops import capture_region_for_ocr
import controller.ocr.ocr_capture_ops as ocr_capture_ops
import controller.ocr.ocr_import as real_ocr_import


class _DummyMainWindow:
    def __init__(self, settings: dict | None = None, *, visible: bool = True, minimized: bool = False) -> None:
        self._settings = settings or {}
        self._visible = bool(visible)
        self._minimized = bool(minimized)
        self._closing = False
        self.hide_calls = 0
        self.show_calls = 0
        self.show_minimized_calls = 0

    def _cfg(self, key: str, default=None):
        return self._settings.get(key, default)

    def isVisible(self) -> bool:
        return self._visible

    def isMinimized(self) -> bool:
        return self._minimized

    def hide(self) -> None:
        self.hide_calls += 1
        self._visible = False

    def show(self) -> None:
        self.show_calls += 1
        self._visible = True
        self._minimized = False

    def showMinimized(self) -> None:
        self.show_minimized_calls += 1
        self._visible = True
        self._minimized = True


class TestOCRCaptureOps(unittest.TestCase):
    def test_non_macos_capture_hides_and_restores_window(self):
        mw = _DummyMainWindow(
            {
                "OCR_USE_NATIVE_MAC_CAPTURE": False,
                "OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE": True,
                "OCR_CAPTURE_PREPARE_DELAY_MS": 0,
            }
        )
        with (
            patch("controller.ocr.ocr_capture_ops.select_region_from_primary_screen", return_value=("pix", None)) as select_mock,
            patch("controller.ocr.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
            patch("controller.ocr.ocr_capture_ops.qt_runtime.safe_raise") as raise_mock,
            patch("controller.ocr.ocr_capture_ops.qt_runtime.safe_activate_window") as activate_mock,
        ):
            result = capture_region_for_ocr(mw)

        self.assertEqual(result, ("pix", None))
        self.assertEqual(mw.hide_calls, 1)
        self.assertEqual(mw.show_calls, 1)
        self.assertEqual(mw.show_minimized_calls, 0)
        self.assertEqual(select_mock.call_args.kwargs.get("parent"), None)
        raise_mock.assert_called_once_with(mw)
        activate_mock.assert_called_once_with(mw)

    def test_non_macos_capture_keeps_window_when_disabled(self):
        mw = _DummyMainWindow(
            {
                "OCR_USE_NATIVE_MAC_CAPTURE": False,
                "OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE": False,
                "OCR_CAPTURE_PREPARE_DELAY_MS": 0,
            }
        )
        with (
            patch("controller.ocr.ocr_capture_ops.select_region_from_primary_screen", return_value=("pix", None)) as select_mock,
            patch("controller.ocr.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
            patch("controller.ocr.ocr_capture_ops.qt_runtime.safe_raise") as raise_mock,
            patch("controller.ocr.ocr_capture_ops.qt_runtime.safe_activate_window") as activate_mock,
        ):
            result = capture_region_for_ocr(mw)

        self.assertEqual(result, ("pix", None))
        self.assertEqual(mw.hide_calls, 0)
        self.assertEqual(mw.show_calls, 0)
        self.assertEqual(mw.show_minimized_calls, 0)
        self.assertIs(select_mock.call_args.kwargs.get("parent"), mw)
        raise_mock.assert_not_called()
        activate_mock.assert_not_called()

    def test_non_macos_capture_restores_minimized_state(self):
        mw = _DummyMainWindow(
            {
                "OCR_USE_NATIVE_MAC_CAPTURE": False,
                "OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE": True,
                "OCR_CAPTURE_PREPARE_DELAY_MS": 0,
            },
            visible=True,
            minimized=True,
        )
        with (
            patch("controller.ocr.ocr_capture_ops.select_region_from_primary_screen", return_value=("pix", None)),
            patch("controller.ocr.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
            patch("controller.ocr.ocr_capture_ops.qt_runtime.safe_raise") as raise_mock,
            patch("controller.ocr.ocr_capture_ops.qt_runtime.safe_activate_window") as activate_mock,
        ):
            result = capture_region_for_ocr(mw)

        self.assertEqual(result, ("pix", None))
        self.assertEqual(mw.hide_calls, 1)
        self.assertEqual(mw.show_calls, 0)
        self.assertEqual(mw.show_minimized_calls, 1)
        raise_mock.assert_not_called()
        activate_mock.assert_not_called()

    def test_qt_selector_auto_accept_enabled_by_default_on_windows(self):
        mw = _DummyMainWindow(
            {
                "OCR_USE_NATIVE_MAC_CAPTURE": False,
                "OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE": False,
                "OCR_CAPTURE_PREPARE_DELAY_MS": 0,
                "OCR_CAPTURE_PREPARE_DELAY_MS_WINDOWS": 0,
            }
        )
        with (
            patch("controller.ocr.ocr_capture_ops.sys.platform", "win32"),
            patch("controller.ocr.ocr_capture_ops.select_region_from_primary_screen", return_value=("pix", None)) as select_mock,
            patch("controller.ocr.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
        ):
            result = capture_region_for_ocr(mw)

        self.assertEqual(result, ("pix", None))
        self.assertTrue(select_mock.call_args.kwargs.get("auto_accept_on_release"))

    def test_qt_selector_auto_accept_can_be_disabled(self):
        mw = _DummyMainWindow(
            {
                "OCR_USE_NATIVE_MAC_CAPTURE": False,
                "OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE": False,
                "OCR_QT_SELECTOR_AUTO_ACCEPT_ON_RELEASE": False,
                "OCR_CAPTURE_PREPARE_DELAY_MS": 0,
                "OCR_CAPTURE_PREPARE_DELAY_MS_WINDOWS": 0,
            }
        )
        with (
            patch("controller.ocr.ocr_capture_ops.sys.platform", "win32"),
            patch("controller.ocr.ocr_capture_ops.select_region_from_primary_screen", return_value=("pix", None)) as select_mock,
            patch("controller.ocr.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
        ):
            result = capture_region_for_ocr(mw)

        self.assertEqual(result, ("pix", None))
        self.assertFalse(select_mock.call_args.kwargs.get("auto_accept_on_release"))

    def test_macos_native_capture_minimizes_then_hides_window(self):
        mw = _DummyMainWindow(
            {
                "OCR_USE_NATIVE_MAC_CAPTURE": True,
                "OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE": True,
                "OCR_CAPTURE_PREPARE_DELAY_MS": 0,
                "OCR_CAPTURE_TIMEOUT_S": 1.0,
            },
            visible=True,
            minimized=False,
        )
        with (
            patch("controller.ocr.ocr_capture_ops.sys.platform", "darwin"),
            patch("controller.ocr.ocr_capture_ops.QtWidgets.QMessageBox.information"),
            patch("controller.ocr.ocr_capture_ops.select_region_with_macos_screencapture", return_value=("pix", None)),
            patch("controller.ocr.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
            patch("controller.ocr.ocr_capture_ops.qt_runtime.safe_raise") as raise_mock,
            patch("controller.ocr.ocr_capture_ops.qt_runtime.safe_activate_window") as activate_mock,
        ):
            result = capture_region_for_ocr(mw)

        self.assertEqual(result, ("pix", None))
        self.assertEqual(mw.show_minimized_calls, 1)
        self.assertEqual(mw.hide_calls, 1)
        self.assertEqual(mw.show_calls, 1)
        raise_mock.assert_called_once_with(mw)
        activate_mock.assert_called_once_with(mw)

    def test_macos_native_capture_respects_hide_setting_false(self):
        mw = _DummyMainWindow(
            {
                "OCR_USE_NATIVE_MAC_CAPTURE": True,
                "OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE": False,
                "OCR_CAPTURE_PREPARE_DELAY_MS": 0,
                "OCR_CAPTURE_TIMEOUT_S": 1.0,
            },
            visible=True,
            minimized=False,
        )
        with (
            patch("controller.ocr.ocr_capture_ops.sys.platform", "darwin"),
            patch("controller.ocr.ocr_capture_ops.QtWidgets.QMessageBox.information"),
            patch("controller.ocr.ocr_capture_ops.select_region_with_macos_screencapture", return_value=("pix", None)),
            patch("controller.ocr.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
            patch("controller.ocr.ocr_capture_ops.qt_runtime.safe_raise") as raise_mock,
            patch("controller.ocr.ocr_capture_ops.qt_runtime.safe_activate_window") as activate_mock,
        ):
            result = capture_region_for_ocr(mw)

        self.assertEqual(result, ("pix", None))
        self.assertEqual(mw.show_minimized_calls, 0)
        self.assertEqual(mw.hide_calls, 0)
        self.assertEqual(mw.show_calls, 0)
        raise_mock.assert_not_called()
        activate_mock.assert_not_called()

    def _ocr_cfg(self) -> dict:
        return {
            "fast_mode": True,
            "max_variants": 1,
            "stop_after_variant_success": True,
            "psm_primary": 6,
            "psm_fallback": 11,
            "psm_values": (6,),
            "timeout_s": 1.0,
            "recall_retry_enabled": True,
            "recall_retry_min_candidates": 5,
            "recall_retry_max_candidates": 7,
            "recall_retry_short_name_max_ratio": 0.34,
            "recall_retry_max_variants": 1,
            "recall_retry_use_fallback_psm": True,
            "recall_retry_timeout_scale": 1.5,
            "recall_relax_support_on_low_count": True,
            "expected_candidates": 5,
            "row_pass_enabled": False,
            "row_pass_min_candidates": 5,
        }

    def test_runtime_cfg_enables_single_name_per_row_by_default(self):
        mw = _DummyMainWindow({})
        cfg = ocr_capture_ops._ocr_runtime_cfg_snapshot(mw)
        self.assertTrue(bool(cfg.get("row_pass_single_name_per_row")))

    def test_select_row_names_from_ranked_votes_single_when_best_vote_low(self):
        cfg = {}
        ranked = [
            {"display": "Rontarou", "count": 1, "conf_sum": 80.0, "conf_weight": 1.0},
            {"display": "The Bookseller", "count": 1, "conf_sum": 79.0, "conf_weight": 1.0},
        ]
        result = ocr_capture_ops._select_row_names_from_ranked_votes(
            ranked,
            cfg=cfg,
            best_vote_count=1,
        )
        self.assertEqual(result, ["Rontarou"])

    def test_select_row_names_from_ranked_votes_allows_multiline_candidates(self):
        cfg = {
            "row_pass_single_name_per_row": False,
            "row_pass_multiline_min_vote_count": 2,
            "row_pass_max_names_per_row": 5,
            "row_pass_multiline_min_avg_conf": 30.0,
        }
        ranked = [
            {"display": "Mogojyan The Lacie Lover", "count": 2, "conf_sum": 170.0, "conf_weight": 2.0},
            {"display": "Rontarou", "count": 2, "conf_sum": 168.0, "conf_weight": 2.0},
            {"display": "The Bookseller", "count": 2, "conf_sum": 160.0, "conf_weight": 2.0},
            {"display": "FWMC", "count": 1, "conf_sum": 95.0, "conf_weight": 1.0},
        ]
        result = ocr_capture_ops._select_row_names_from_ranked_votes(
            ranked,
            cfg=cfg,
            best_vote_count=2,
        )
        self.assertEqual(
            result,
            ["Mogojyan The Lacie Lover", "Rontarou", "The Bookseller"],
        )

    def test_select_row_names_from_ranked_votes_single_name_per_row_when_enabled(self):
        cfg = {"row_pass_single_name_per_row": True}
        ranked = [
            {"display": "Mogojyan The Lacie Lover", "count": 2, "conf_sum": 170.0, "conf_weight": 2.0},
            {"display": "Rontarou", "count": 2, "conf_sum": 168.0, "conf_weight": 2.0},
            {"display": "The Bookseller", "count": 2, "conf_sum": 160.0, "conf_weight": 2.0},
        ]
        result = ocr_capture_ops._select_row_names_from_ranked_votes(
            ranked,
            cfg=cfg,
            best_vote_count=2,
        )
        self.assertEqual(result, ["Mogojyan The Lacie Lover"])

    def test_should_run_row_pass_skips_when_primary_is_stable_and_clean(self):
        cfg = self._ocr_cfg()
        cfg.update(
            {
                "row_pass_enabled": True,
                "row_pass_always_run": True,
                "row_pass_skip_when_primary_stable": True,
                "expected_candidates": 5,
            }
        )
        stable_names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
        self.assertFalse(ocr_capture_ops._should_run_row_pass(cfg, stable_names))

    def test_should_run_row_pass_still_runs_when_primary_looks_noisy(self):
        cfg = self._ocr_cfg()
        cfg.update(
            {
                "row_pass_enabled": True,
                "row_pass_always_run": True,
                "row_pass_skip_when_primary_stable": True,
                "expected_candidates": 5,
            }
        )
        noisy_names = ["A", "B", "C", "D", "E"]
        self.assertTrue(ocr_capture_ops._should_run_row_pass(cfg, noisy_names))

    def test_should_run_row_pass_skips_when_relaxed_gap_and_primary_confidence_are_good(self):
        cfg = self._ocr_cfg()
        cfg.update(
            {
                "row_pass_enabled": True,
                "row_pass_always_run": True,
                "row_pass_skip_when_primary_stable": True,
                "expected_candidates": 7,
                "primary_candidate_count": 4,
                "primary_line_avg_conf": 82.0,
                "row_pass_primary_stable_relaxed_expected_gap": 3,
                "row_pass_primary_stable_relaxed_min_avg_conf": 76.0,
            }
        )
        clean_primary_names = [
            "Jockie Music 1 (ml)",
            "Mogojyan The Lacie Lover FWMC",
            "Rontorou {Gest Cojo Moin} 1OOK",
            "The Gookseller {The Food lover}",
        ]
        self.assertFalse(ocr_capture_ops._should_run_row_pass(cfg, clean_primary_names))

    def test_should_run_recall_retry_skips_when_primary_is_clean_and_shortfall_is_small(self):
        cfg = self._ocr_cfg()
        cfg.update(
            {
                "fast_mode": True,
                "recall_retry_enabled": True,
                "recall_retry_min_candidates": 5,
                "recall_retry_skip_when_primary_clean": True,
                "recall_retry_skip_primary_clean_min_count": 4,
                "recall_retry_skip_primary_clean_max_shortfall": 1,
                "recall_retry_skip_primary_clean_min_avg_conf": 78.0,
                "primary_line_avg_conf": 82.0,
            }
        )
        clean_primary_names = [
            "Jockie Music 1 (ml)",
            "Mogojyan The Lacie Lover FWMC",
            "Rontorou {Gest Cojo Moin} 1OOK",
            "The Gookseller {The Food lover}",
        ]
        self.assertFalse(ocr_capture_ops._should_run_recall_retry(cfg, clean_primary_names))

    def test_should_run_recall_retry_keeps_running_when_primary_confidence_is_low(self):
        cfg = self._ocr_cfg()
        cfg.update(
            {
                "fast_mode": True,
                "recall_retry_enabled": True,
                "recall_retry_min_candidates": 5,
                "recall_retry_skip_when_primary_clean": True,
                "recall_retry_skip_primary_clean_min_count": 4,
                "recall_retry_skip_primary_clean_max_shortfall": 1,
                "recall_retry_skip_primary_clean_min_avg_conf": 78.0,
                "primary_line_avg_conf": 64.0,
            }
        )
        clean_primary_names = [
            "Jockie Music 1 (ml)",
            "Mogojyan The Lacie Lover FWMC",
            "Rontorou {Gest Cojo Moin} 1OOK",
            "The Gookseller {The Food lover}",
        ]
        self.assertTrue(ocr_capture_ops._should_run_recall_retry(cfg, clean_primary_names))

    def test_should_run_row_pass_skips_when_expected_gap_is_small_and_primary_is_clean(self):
        cfg = self._ocr_cfg()
        cfg.update(
            {
                "row_pass_enabled": True,
                "row_pass_always_run": True,
                "row_pass_skip_when_primary_stable": True,
                "expected_candidates": 7,
                "primary_candidate_count": 5,
                "row_pass_primary_stable_relaxed_expected_gap": 2,
            }
        )
        clean_primary_names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
        self.assertFalse(ocr_capture_ops._should_run_row_pass(cfg, clean_primary_names))

    def test_prefer_row_candidates_keeps_primary_when_row_has_fewer_and_primary_is_clean(self):
        cfg = self._ocr_cfg()
        cfg.update(
            {
                "expected_candidates": 8,
                "precount_rows_primary_stable": 7,
            }
        )
        primary = ["Rhug", "flatiqz", "Kylo", "mikix", "Pxssesive", "rqlled", "yukino"]
        row = ["Rhug", "tlatiaz", "Kylo", "mikix", "Pxssesive", "ralled"]
        self.assertFalse(ocr_capture_ops._prefer_row_candidates(primary, row, cfg))

    def test_prefer_row_candidates_can_replace_short_noisy_primary_even_if_row_has_fewer(self):
        cfg = self._ocr_cfg()
        cfg.update(
            {
                "expected_candidates": 5,
                "precount_rows_primary_stable": 0,
            }
        )
        primary = ["A", "B", "C", "D", "E", "F", "G"]
        row = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]
        self.assertTrue(ocr_capture_ops._prefer_row_candidates(primary, row, cfg))

    def test_candidate_stats_counts_only_one_candidate_per_line(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(line_text):
                text = str(line_text or "").strip()
                if text == "Player Player2":
                    return ["Player", "Player2"]
                return [text] if text else []

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "lines": [
                        {"text": "Player Player2", "conf": 80.0},
                    ]
                }
            ],
            _ParseCtx(),
        )
        self.assertEqual(len(stats), 1)
        self.assertTrue("player" in stats or "player2" in stats)

    def test_candidate_stats_prefers_stronger_line_candidate_over_short_noise(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(_line_text):
                return ["TK", "The Bookseller"]

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "lines": [
                        {"text": "dummy", "conf": 80.0},
                    ]
                }
            ],
            _ParseCtx(),
        )
        self.assertEqual(len(stats), 1)
        self.assertIn("thebookseller", stats)
        self.assertNotIn("tk", stats)

    def test_candidate_stats_uses_preparsed_candidates_hint_without_reparsing(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(_line_text):
                raise AssertionError("should not reparse when parsed_candidates is provided")

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "pass": "row",
                    "image": "src#1[0:0]/name.base",
                    "lines": [
                        {
                            "text": "ignored-raw",
                            "conf": 80.0,
                            "parsed_candidates": ["Alpha"],
                        }
                    ],
                }
            ],
            _ParseCtx(),
        )
        self.assertEqual(len(stats), 1)
        self.assertIn("alpha", stats)

    def test_candidate_stats_skips_marked_lines_without_reparsing(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(_line_text):
                raise AssertionError("should not reparse skipped row lines")

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "pass": "row",
                    "image": "src#1[0:0]/name.base",
                    "lines": [
                        {
                            "text": "ignored-raw",
                            "conf": 10.0,
                            "skip_candidate_stats": True,
                            "skip_reason": "row-low-conf",
                            "parsed_candidates_locked": True,
                            "parsed_candidates": [],
                        }
                    ],
                }
            ],
            _ParseCtx(),
        )
        self.assertEqual(stats, {})

    def test_candidate_stats_respects_locked_empty_candidates(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(_line_text):
                raise AssertionError("should not reparse locked parsed_candidates")

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "pass": "row",
                    "image": "src#1[0:0]/name.base",
                    "lines": [
                        {
                            "text": "ignored-raw",
                            "conf": 55.0,
                            "parsed_candidates_locked": True,
                            "parsed_candidates": [],
                        }
                    ],
                }
            ],
            _ParseCtx(),
        )
        self.assertEqual(stats, {})

    def test_candidate_stats_uses_alternate_candidate_when_primary_already_seen(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(line_text):
                text = str(line_text or "").strip()
                if text == "line1":
                    return ["Aero", "AJAR"]
                if text == "line2":
                    return ["Aero", "Massith"]
                return []

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "lines": [
                        {"text": "line1", "conf": 80.0},
                        {"text": "line2", "conf": 79.0},
                    ]
                }
            ],
            _ParseCtx(),
        )
        self.assertEqual(len(stats), 2)
        self.assertIn("aero", stats)
        self.assertIn("massith", stats)

    def test_candidate_stats_trace_entries_include_drop_and_selection(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(line_text):
                text = str(line_text or "").strip()
                if text == "line1":
                    return ["Aero", "AJAR"]
                if text == "line2":
                    return ["Aero", "Massith"]
                return []

            @staticmethod
            def extract_debug_for_text(line_text):
                text = str(line_text or "").strip()
                if text == "line3":
                    return [], [{"status": "dropped", "reason": "failed-name-heuristics", "cleaned": text}]
                return [], [{"status": "accepted", "reason": "-", "cleaned": text}]

        trace: list[dict] = []
        _stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "pass": "primary",
                    "image": "tmp.png",
                    "lines": [
                        {"text": "line1", "conf": 80.0},
                        {"text": "line2", "conf": 79.0},
                        {"text": "line3", "conf": 20.0},
                    ],
                }
            ],
            _ParseCtx(),
            trace_entries=trace,
            include_debug_meta=True,
        )
        self.assertEqual(len(trace), 3)
        self.assertEqual(trace[0].get("selection_reason"), "best")
        self.assertEqual(trace[1].get("selection_reason"), "alternate-after-duplicate")
        self.assertEqual(trace[2].get("drop_reason"), "no-line-candidates")
        self.assertEqual(trace[2].get("strict_reason"), "failed-name-heuristics")

    def test_candidate_stats_counts_only_one_support_for_same_primary_line_across_runs(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(line_text):
                value = str(line_text or "").strip()
                return [value] if value else []

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "pass": "primary",
                    "image": "a.png",
                    "lines": [{"text": "funnyName", "conf": 70.0}],
                },
                {
                    "pass": "primary",
                    "image": "b.png",
                    "lines": [{"text": "funnyName2", "conf": 92.0}],
                },
            ],
            _ParseCtx(),
        )
        support_sum = int(stats.get("funnyname", {}).get("support", 0)) + int(
            stats.get("funnyname2", {}).get("support", 0)
        )
        self.assertEqual(support_sum, 1)
        self.assertLessEqual(int(stats.get("funnyname", {}).get("support", 0)), 1)
        self.assertLessEqual(int(stats.get("funnyname2", {}).get("support", 0)), 1)

    def test_candidate_stats_keeps_two_names_when_they_come_from_two_row_slots(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(line_text):
                value = str(line_text or "").strip()
                return [value] if value else []

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "pass": "row",
                    "image": "src#1[10:20]/name.base",
                    "lines": [{"text": "funnyName2", "conf": 62.0}],
                },
                {
                    "pass": "row",
                    "image": "src#1[10:20]/name.scaled_x4",
                    "lines": [{"text": "funnyName2", "conf": 88.0}],
                },
                {
                    "pass": "row",
                    "image": "src#2[24:34]/name.base",
                    "lines": [{"text": "funnyName", "conf": 91.0}],
                },
            ],
            _ParseCtx(),
        )
        self.assertEqual(int(stats.get("funnyname", {}).get("support", 0)), 1)
        self.assertEqual(int(stats.get("funnyname2", {}).get("support", 0)), 1)

    def test_candidate_stats_row_slot_prefers_clean_name_over_short_high_conf_variant(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(line_text):
                value = str(line_text or "").strip()
                return [value] if value else []

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "pass": "row",
                    "image": "src#2[10:20]/name.base",
                    "lines": [{"text": "AJAR", "conf": 77.5}],
                },
                {
                    "pass": "row",
                    "image": "src#2[10:20]/name.scaled_x4",
                    "lines": [{"text": "AR", "conf": 98.1}],
                },
            ],
            _ParseCtx(),
        )
        self.assertEqual(int(stats.get("ajar", {}).get("support", 0)), 1)
        self.assertEqual(int(stats.get("ar", {}).get("support", 0)), 0)

    def test_candidate_stats_row_slot_prefers_letter_only_variant_over_digit_noise(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(line_text):
                value = str(line_text or "").strip()
                return [value] if value else []

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "pass": "row",
                    "image": "src#4[30:40]/name.base",
                    "lines": [{"text": "Mika Moonbrcw", "conf": 65.1}],
                },
                {
                    "pass": "row",
                    "image": "src#4[30:40]/name.mono",
                    "lines": [{"text": "liliil 1 Vjhru", "conf": 49.5}],
                },
            ],
            _ParseCtx(),
        )
        self.assertEqual(int(stats.get("mikamoonbrcw", {}).get("support", 0)), 1)
        self.assertEqual(int(stats.get("liliil1vjhru", {}).get("support", 0)), 0)

    def test_candidate_stats_row_conflict_does_not_add_extra_support_line(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(line_text):
                value = str(line_text or "").strip()
                return [value] if value else []

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "pass": "primary",
                    "image": "a.png",
                    "lines": [
                        {"text": "Line1", "conf": 92.0},
                        {"text": "Line2", "conf": 90.0},
                        {"text": "Line3", "conf": 88.0},
                        {"text": "Line4", "conf": 86.0},
                    ],
                },
                # OCR row-pass misread for row #4: variant from another row.
                {
                    "pass": "row",
                    "image": "src#4[40:50]/name.base",
                    "lines": [{"text": "Line3", "conf": 31.0}],
                },
            ],
            _ParseCtx(),
        )
        # The conflicting row-pass variant must not create an additional
        # supported line candidate.
        self.assertEqual(int(stats.get("line1", {}).get("support", 0)), 1)
        self.assertEqual(int(stats.get("line2", {}).get("support", 0)), 1)
        self.assertEqual(int(stats.get("line3", {}).get("support", 0)), 1)
        self.assertEqual(int(stats.get("line4", {}).get("support", 0)), 1)

    def test_candidate_stats_primary_keeps_slot_even_when_row_variant_looks_cleaner(self):
        class _ParseCtx:
            @staticmethod
            def extract_line_candidates(line_text):
                value = str(line_text or "").strip()
                return [value] if value else []

        stats = ocr_capture_ops._candidate_stats_from_runs(
            [
                {
                    "pass": "primary",
                    "image": "a.png",
                    "lines": [
                        {"text": "Line1", "conf": 91.0},
                        {"text": "Line2", "conf": 90.0},
                        {"text": "Line3", "conf": 88.0},
                        {"text": "Line4", "conf": 70.0},
                    ],
                },
                {
                    "pass": "row",
                    "image": "src#4[40:50]/name.base",
                    "lines": [{"text": "Line3", "conf": 99.0}],
                },
            ],
            _ParseCtx(),
        )
        # Even a strong row variant for slot #4 should not override an
        # existing primary line winner for that slot.
        self.assertEqual(int(stats.get("line4", {}).get("support", 0)), 1)
        self.assertEqual(int(stats.get("line3", {}).get("support", 0)), 1)

    def test_extract_names_from_texts_adds_missing_line_fallback_candidate(self):
        class _Import:
            @staticmethod
            def extract_candidate_names_multi(_texts, **_kwargs):
                return [
                    "Teste bitte nochmal genau den 7-Zeilen",
                    "nachsten Schritt eine Debug-Ausgabe",
                ]

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                line = str(text or "").strip()
                if not line:
                    return []
                words = [tok for tok in line.replace(";", " ").replace(",", " ").split() if tok]
                max_words = int(kwargs.get("max_words", 2))
                if len(words) > max_words:
                    return []
                return [line]

        texts = [
            "\n".join(
                [
                    "Teste bitte nochmal genau den 7-Zeilen",
                    "Case. Wenn es noch fehlt; baue ich dir als",
                    "nachsten Schritt eine Debug-Ausgabe",
                ]
            )
        ]
        names = ocr_capture_ops._extract_names_from_texts(
            _Import(),
            texts,
            {
                "name_min_chars": 2,
                "name_max_chars": 64,
                "name_max_words": 8,
                "name_max_digit_ratio": 0.45,
                "name_special_char_constraint": False,
                "line_relaxed_fallback": True,
                "line_recall_max_additions": 2,
                "single_name_per_line": False,
                "name_min_support": 1,
                "name_high_count_threshold": 8,
                "name_high_count_min_support": 2,
                "name_max_candidates": 12,
                "name_near_dup_min_chars": 8,
                "name_near_dup_max_len_delta": 1,
                "name_near_dup_similarity": 0.90,
                "name_near_dup_tail_min_chars": 3,
                "name_near_dup_tail_head_similarity": 0.70,
            },
        )
        self.assertIn("Case. Wenn es noch fehlt; baue ich dir als", names)

    def test_build_final_names_without_stats_prefers_preferred_sequence(self):
        names = ocr_capture_ops._build_final_names_from_runs(
            cfg={"expected_candidates": 5},
            stats={},
            preferred_names=["Bravo", "Alpha"],
            primary_names=["Alpha", "Bravo"],
            retry_names=["Charlie"],
            row_names=["Charlie", "Alpha"],
            row_preferred=False,
        )
        self.assertEqual(names, ["Bravo", "Alpha", "Charlie"])

    def test_build_final_names_remerges_seeded_near_duplicates(self):
        stats = {
            "thebookseller": {
                "display": "The Bookseller",
                "support": 3,
                "occurrences": 3,
                "best_conf": 86.0,
            }
        }
        names = ocr_capture_ops._build_final_names_from_runs(
            cfg={
                "expected_candidates": 5,
                "name_min_support": 1,
                "name_min_confidence": 0.0,
                "name_low_confidence_min_support": 1,
                "name_near_dup_min_chars": 8,
                "name_near_dup_max_len_delta": 1,
                "name_near_dup_similarity": 0.90,
            },
            stats=stats,
            preferred_names=["The Bookselier", "The Bookseller"],
            primary_names=["The Bookseller"],
            retry_names=["The Bookselier"],
            row_names=["The Bookselier"],
            row_preferred=False,
        )
        self.assertEqual(names, ["The Bookseller"])

    def test_build_final_names_row_preferred_keeps_fuzzy_matched_preferred_key(self):
        stats = {
            "aero": {"display": "Aero", "support": 5, "occurrences": 5, "best_conf": 98.0},
            "ajar": {"display": "AJAR", "support": 5, "occurrences": 5, "best_conf": 99.0},
            "massithmarcdu": {
                "display": "Massith Marc #Du",
                "support": 5,
                "occurrences": 5,
                "best_conf": 85.0,
            },
            "mikamoonbrcw4w": {
                "display": "Mika Moonbrcw \"0 ^",
                "support": 6,
                "occurrences": 6,
                "best_conf": 81.0,
            },
            "nikeosmnke": {
                "display": "NIKEOS MNKE",
                "support": 5,
                "occurrences": 5,
                "best_conf": 96.0,
            },
        }
        names = ocr_capture_ops._build_final_names_from_runs(
            cfg={
                "expected_candidates": 5,
                "name_min_support": 1,
                "name_min_confidence": 43.0,
                "name_low_confidence_min_support": 2,
            },
            stats=stats,
            preferred_names=[
                "Aero",
                "AJAR",
                "Massith Marc #Du",
                "Mika Moonbrcw \"0 ^",
                "NIKEOS MNKE",
            ],
            primary_names=[
                "Aero",
                "AJAR",
                "Massith Marc #DW",
                "Mika | Moonbrcw 4 W ^",
                "NIKEOS MNKE",
            ],
            retry_names=[],
            row_names=[
                "Aero",
                "AJAR",
                "Massith Marc #Du",
                "Mika Moonbrcw \"0 ^",
                "NIKEOS MNKE",
            ],
            row_preferred=True,
        )
        name_keys = {ocr_capture_ops._simple_name_key(name) for name in names}
        self.assertEqual(len(names), 5)
        self.assertIn("aero", name_keys)
        self.assertIn("ajar", name_keys)
        self.assertIn("massithmarcdu", name_keys)
        self.assertIn("nikeosmnke", name_keys)
        self.assertTrue(any(key.startswith("mikamoonbrcw") for key in name_keys))

    def test_merge_near_duplicate_candidate_stats_merges_low_support_variants(self):
        stats = {
            "thebookseller": {
                "display": "The Bookseller",
                "support": 3,
                "occurrences": 3,
                "best_conf": 86.0,
            },
            "thebookselier": {
                "display": "The Bookselier",
                "support": 1,
                "occurrences": 1,
                "best_conf": 59.0,
            },
        }
        merged = ocr_capture_ops._merge_near_duplicate_candidate_stats(stats, self._ocr_cfg())
        self.assertEqual(len(merged), 1)
        bucket = next(iter(merged.values()))
        self.assertEqual(int(bucket.get("support", 0)), 4)
        self.assertEqual(int(bucket.get("occurrences", 0)), 4)

    def test_merge_prefix_candidate_stats_merges_truncated_multiword_variant(self):
        stats = {
            "casewennesnochfehltbaueichdirals": {
                "display": "Case. Wenn es noch fehlt; baue ich dir als",
                "support": 2,
                "occurrences": 2,
                "best_conf": 84.0,
            },
            "casewennesnochfehltbaueic": {
                "display": "Case_ Wenn es noch fehlt, baue ic",
                "support": 3,
                "occurrences": 3,
                "best_conf": 82.0,
            },
        }
        merged = ocr_capture_ops._merge_prefix_candidate_stats(stats)
        self.assertEqual(len(merged), 1)
        bucket = next(iter(merged.values()))
        self.assertEqual(int(bucket.get("support", 0)), 5)
        self.assertEqual(int(bucket.get("occurrences", 0)), 5)

    def test_merge_prefix_candidate_stats_keeps_numeric_suffix_variant(self):
        stats = {
            "player": {
                "display": "Player",
                "support": 2,
                "occurrences": 2,
                "best_conf": 80.0,
            },
            "player2": {
                "display": "Player2",
                "support": 2,
                "occurrences": 2,
                "best_conf": 81.0,
            },
        }
        merged = ocr_capture_ops._merge_prefix_candidate_stats(stats)
        self.assertEqual(len(merged), 2)
        self.assertIn("player", merged)
        self.assertIn("player2", merged)

    def test_name_display_quality_prefers_clean_variant_over_noisy_tail(self):
        clean = ocr_capture_ops._name_display_quality("Mika Moonbrcw")
        noisy = ocr_capture_ops._name_display_quality("Mika Moonbrcw \"0 ^")
        self.assertLess(clean, noisy)

    def test_merge_prefix_candidate_stats_prefers_clean_short_when_suffix_is_noise(self):
        stats = {
            "mikamoonbrcw": {
                "display": "Mika Moonbrcw",
                "support": 3,
                "occurrences": 3,
                "best_conf": 80.9,
            },
            "mikamoonbrcw4w": {
                "display": "Mika | Moonbrcw 4 W ^",
                "support": 1,
                "occurrences": 1,
                "best_conf": 77.9,
            },
        }
        merged = ocr_capture_ops._merge_prefix_candidate_stats(stats)
        self.assertEqual(len(merged), 1)
        self.assertIn("mikamoonbrcw", merged)
        bucket = merged["mikamoonbrcw"]
        self.assertEqual(bucket.get("display"), "Mika Moonbrcw")
        self.assertEqual(int(bucket.get("support", 0)), 4)

    def test_merge_near_duplicate_candidate_stats_keeps_distinct_strong_names(self):
        stats = {
            "massith": {
                "display": "Massith",
                "support": 2,
                "occurrences": 2,
                "best_conf": 84.0,
            },
            "mossith": {
                "display": "Mossith",
                "support": 2,
                "occurrences": 2,
                "best_conf": 83.0,
            },
        }
        merged = ocr_capture_ops._merge_near_duplicate_candidate_stats(stats, self._ocr_cfg())
        self.assertEqual(len(merged), 2)

    def test_merge_near_duplicate_candidate_stats_keeps_numeric_suffix_variants(self):
        stats = {
            "player": {
                "display": "Player",
                "support": 2,
                "occurrences": 2,
                "best_conf": 84.0,
            },
            "player2": {
                "display": "Player2",
                "support": 1,
                "occurrences": 1,
                "best_conf": 79.0,
            },
        }
        merged = ocr_capture_ops._merge_near_duplicate_candidate_stats(stats, self._ocr_cfg())
        self.assertEqual(len(merged), 2)
        self.assertIn("player", merged)
        self.assertIn("player2", merged)

    def test_order_names_by_line_trace_uses_primary_line_order(self):
        names = ["Charlie", "Alpha", "Bravo"]
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "alpha",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "bravo",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 3,
                "selected_key": "charlie",
                "support_incremented": True,
            },
        ]
        ordered = ocr_capture_ops._order_names_by_line_trace(names, trace, row_preferred=False)
        self.assertEqual(ordered, ["Alpha", "Bravo", "Charlie"])

    def test_order_names_by_line_trace_prefers_row_order_when_row_preferred(self):
        names = ["Charlie", "Alpha", "Bravo"]
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "charlie",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "alpha",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 3,
                "selected_key": "bravo",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 2,
                "line_index": 1,
                "selected_key": "alpha",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 2,
                "line_index": 2,
                "selected_key": "bravo",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 2,
                "line_index": 3,
                "selected_key": "charlie",
                "support_incremented": True,
            },
        ]
        ordered = ocr_capture_ops._order_names_by_line_trace(names, trace, row_preferred=True)
        self.assertEqual(ordered, ["Alpha", "Bravo", "Charlie"])

    def test_order_names_by_line_trace_row_preferred_keeps_primary_only_key_in_slot(self):
        names = ["Aero", "AJAR", "Mika Moonbrcw", "NIKEOS MNKE", "Massith Marc #QW"]
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "aero",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "ajar",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 3,
                "selected_key": "massithmarcqw",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 4,
                "selected_key": "mikamoonbrcw",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 5,
                "selected_key": "nikeosmnke",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 10,
                "line_index": 1,
                "image": "src#1[0:0]/name.base",
                "selected_key": "aero",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 11,
                "line_index": 1,
                "image": "src#2[0:0]/name.base",
                "selected_key": "ajar",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 12,
                "line_index": 1,
                "image": "src#4[0:0]/name.base",
                "selected_key": "mikamoonbrcw",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 13,
                "line_index": 1,
                "image": "src#5[0:0]/name.base",
                "selected_key": "nikeosmnke",
                "support_incremented": True,
            },
        ]
        ordered = ocr_capture_ops._order_names_by_line_trace(
            names,
            trace,
            row_preferred=True,
        )
        self.assertEqual(
            ordered,
            ["Aero", "AJAR", "Massith Marc #QW", "Mika Moonbrcw", "NIKEOS MNKE"],
        )

    def test_order_names_by_line_trace_reorders_known_subset_and_appends_unknown(self):
        names = ["Noise", "Charlie", "Alpha", "Bravo"]
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "alpha",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "bravo",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 3,
                "selected_key": "charlie",
                "support_incremented": True,
            },
        ]
        ordered = ocr_capture_ops._order_names_by_line_trace(names, trace, row_preferred=False)
        self.assertEqual(ordered, ["Alpha", "Bravo", "Charlie", "Noise"])

    def test_order_names_by_line_trace_aliases_row_only_variant_to_primary_position(self):
        names = [
            "Mogojyan The Lacie Lover FWMC",
            "The Gookseller {The Food lover}",
            "Jockie Music 1 (ml) 66",
            "Rontorou {Best Cojo Moin} 10OK",
        ]
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "jockiemusic1ml",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "mogojyanthelacieloverfwmc",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 3,
                "selected_key": "rontorougestgojomoin1ook",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 4,
                "selected_key": "thegooksellerthefoodlover",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 5,
                "line_index": 1,
                "selected_key": "jockiemusic1ml66",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 13,
                "line_index": 1,
                "selected_key": "rontoroubestcojomoin10ok",
                "support_incremented": True,
            },
        ]

        ordered = ocr_capture_ops._order_names_by_line_trace(names, trace, row_preferred=False)
        self.assertEqual(
            ordered,
            [
                "Jockie Music 1 (ml) 66",
                "Mogojyan The Lacie Lover FWMC",
                "Rontorou {Best Cojo Moin} 10OK",
                "The Gookseller {The Food lover}",
            ],
        )

    def test_order_names_by_line_trace_keeps_slot_for_ambiguous_primary_aliases(self):
        names = [
            "Alpha",
            "Bravo",
            "Charlie",
            "Echo",
            "Foxtrot",
            "II welche Zeile wurde auf welchen Kandidaten",
        ]
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "alpha",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "bravo",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 3,
                "selected_key": "charlie",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 4,
                "selected_key": "welchezeilewurdeaufwelchenkandidaten",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 5,
                "selected_key": "echo",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 6,
                "selected_key": "foxtrot",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 2,
                "line_index": 4,
                "selected_key": "iwelchezeilewurdeaufwelchenkandidaten",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 5,
                "line_index": 4,
                "selected_key": "iiwelchezeilewurdeaufwelchenkandidaten",
                "support_incremented": True,
                "image": "full.base",
            },
        ]

        ordered = ocr_capture_ops._order_names_by_line_trace(
            names,
            trace,
            row_preferred=False,
        )
        self.assertEqual(
            ordered,
            [
                "Alpha",
                "Bravo",
                "Charlie",
                "II welche Zeile wurde auf welchen Kandidaten",
                "Echo",
                "Foxtrot",
            ],
        )

    def test_order_names_by_line_trace_does_not_swap_two_row_variants_when_only_one_aliases(self):
        names = ["HIDE & SEEK funktionie", "Das DUMMSTE VERST"]
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "dasdummsteversteckin",
                "support_incremented": True,
                "occurrence_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "hideseekfunktioniert",
                "support_incremented": True,
                "occurrence_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 7,
                "line_index": 1,
                "image": "name.base",
                "selected_key": "dasdummsteverst",
                "support_incremented": False,
                "occurrence_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 8,
                "line_index": 2,
                "image": "name.scaled_x4",
                "selected_key": "hideseekfunktionie",
                "support_incremented": False,
                "occurrence_incremented": True,
            },
        ]

        ordered = ocr_capture_ops._order_names_by_line_trace(
            names,
            trace,
            row_preferred=False,
        )
        self.assertEqual(
            ordered,
            ["Das DUMMSTE VERST", "HIDE & SEEK funktionie"],
        )

    def test_order_names_by_line_trace_uses_occurrence_when_support_missing(self):
        names = ["Aero", "Mika Moonbrcw", "NIKEOS MNKE", "AJAR", "Massith Marc #Ou"]
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "aero",
                "occurrence_incremented": True,
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "ajar",
                "occurrence_incremented": True,
                "support_incremented": False,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 3,
                "selected_key": "massithmarcou",
                "occurrence_incremented": True,
                "support_incremented": False,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 4,
                "selected_key": "mikamoonbrcw",
                "occurrence_incremented": True,
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 5,
                "selected_key": "nikeosmnke",
                "occurrence_incremented": True,
                "support_incremented": True,
            },
        ]

        ordered = ocr_capture_ops._order_names_by_line_trace(
            names,
            trace,
            row_preferred=False,
        )
        self.assertEqual(
            ordered,
            ["Aero", "AJAR", "Massith Marc #Ou", "Mika Moonbrcw", "NIKEOS MNKE"],
        )

    def test_collapse_names_by_trace_slots_removes_duplicate_variant_at_tail(self):
        names = [
            "Jockie Music 1 (ml)",
            "Mogojyan The Lacie Lover FWMC",
            "Rontorou {Gest Gojo Moin} 1OOK",
            "The Gookseller {The Foodlover}",
            "The Bookseller {The FoodIover}",
        ]
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "jockiemusic1ml",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "mogojyanthelacieloverfwmc",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 3,
                "selected_key": "rontorougestgojomoin1ook",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 4,
                "selected_key": "thegooksellerthefoodlover",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 3,
                "line_index": 1,
                "image": "name.base",
                "selected_key": "jockiemusic1ml",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 6,
                "line_index": 1,
                "image": "name.base",
                "selected_key": "mogojyanthelacieloverfwmc",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 10,
                "line_index": 1,
                "image": "name.base",
                "selected_key": "rontoroubestcojomoin10ok",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 14,
                "line_index": 1,
                "image": "name.base",
                "selected_key": "thebooksellerthefoodiover",
                "support_incremented": True,
            },
        ]
        stats = {
            "jockiemusic1ml": {"display": "Jockie Music 1 (ml)", "support": 3, "occurrences": 3, "best_conf": 90.0},
            "mogojyanthelacieloverfwmc": {
                "display": "Mogojyan The Lacie Lover FWMC",
                "support": 3,
                "occurrences": 3,
                "best_conf": 90.0,
            },
            "rontorougestgojomoin1ook": {
                "display": "Rontorou {Gest Gojo Moin} 1OOK",
                "support": 2,
                "occurrences": 2,
                "best_conf": 81.0,
            },
            "thegooksellerthefoodlover": {
                "display": "The Gookseller {The Foodlover}",
                "support": 2,
                "occurrences": 2,
                "best_conf": 75.0,
            },
            "thebooksellerthefoodiover": {
                "display": "The Bookseller {The FoodIover}",
                "support": 1,
                "occurrences": 1,
                "best_conf": 75.0,
            },
        }
        collapsed = ocr_capture_ops._collapse_names_by_trace_slots(
            names,
            trace_entries=trace,
            row_preferred=False,
            candidate_stats=stats,
            cfg=self._ocr_cfg(),
        )
        self.assertEqual(
            collapsed,
            [
                "Jockie Music 1 (ml)",
                "Mogojyan The Lacie Lover FWMC",
                "Rontorou {Gest Gojo Moin} 1OOK",
                "The Gookseller {The Foodlover}",
            ],
        )

    def test_collapse_names_by_trace_slots_keeps_similar_names_on_different_lines(self):
        names = ["funnyName", "funnyName2"]
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "funnyname",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "funnyname2",
                "support_incremented": True,
            },
        ]
        stats = {
            "funnyname": {"display": "funnyName", "support": 2, "occurrences": 2, "best_conf": 84.0},
            "funnyname2": {"display": "funnyName2", "support": 2, "occurrences": 2, "best_conf": 83.0},
        }
        collapsed = ocr_capture_ops._collapse_names_by_trace_slots(
            names,
            trace_entries=trace,
            row_preferred=False,
            candidate_stats=stats,
            cfg=self._ocr_cfg(),
        )
        self.assertEqual(collapsed, ["funnyName", "funnyName2"])

    def test_collapse_names_by_trace_slots_merges_one_char_prefix_drift_in_same_slot(self):
        names = ["Line1", "flatiqz", "Line3", "Line4", "Line5", "yukino", "vukino"]
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "line1",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "flatiqz",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 3,
                "selected_key": "line3",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 4,
                "selected_key": "line4",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 5,
                "selected_key": "line5",
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 6,
                "selected_key": "yukino",
                "support_incremented": True,
            },
            {
                "pass": "row",
                "run_index": 7,
                "line_index": 1,
                "image": "src#6[0:0]/name.base",
                "selected_key": "vukino",
                "support_incremented": True,
            },
        ]
        stats = {
            "line1": {"display": "Line1", "support": 2, "occurrences": 2, "best_conf": 90.0},
            "flatiqz": {"display": "flatiqz", "support": 1, "occurrences": 1, "best_conf": 61.0},
            "line3": {"display": "Line3", "support": 2, "occurrences": 2, "best_conf": 90.0},
            "line4": {"display": "Line4", "support": 2, "occurrences": 2, "best_conf": 90.0},
            "line5": {"display": "Line5", "support": 2, "occurrences": 2, "best_conf": 90.0},
            "yukino": {"display": "yukino", "support": 2, "occurrences": 2, "best_conf": 94.0},
            "vukino": {"display": "vukino", "support": 1, "occurrences": 3, "best_conf": 97.0},
        }
        collapsed = ocr_capture_ops._collapse_names_by_trace_slots(
            names,
            trace_entries=trace,
            row_preferred=False,
            candidate_stats=stats,
            cfg=self._ocr_cfg(),
        )
        self.assertEqual(collapsed, ["Line1", "flatiqz", "Line3", "Line4", "Line5", "yukino"])

    def test_refill_names_to_target_prefers_trace_alternative_for_missing_line(self):
        names = ["Aero", "Mika Moonbrcw", "NIKEOS MNKE"]
        stats = {
            "aero": {"display": "Aero", "support": 4, "occurrences": 4, "best_conf": 95.0},
            "ajar": {"display": "AJAR", "support": 1, "occurrences": 1, "best_conf": 60.0},
            "mikamoonbrcw": {
                "display": "Mika Moonbrcw",
                "support": 4,
                "occurrences": 4,
                "best_conf": 84.0,
            },
            "nikeosmnke": {
                "display": "NIKEOS MNKE",
                "support": 4,
                "occurrences": 4,
                "best_conf": 92.0,
            },
            "zzztopnoise": {
                "display": "ZZZ TOP NOISE",
                "support": 9,
                "occurrences": 9,
                "best_conf": 99.0,
            },
        }
        trace = [
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 1,
                "selected_key": "aero",
                "occurrence_incremented": True,
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 2,
                "selected_key": "ajar",
                "occurrence_incremented": True,
                "support_incremented": False,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 3,
                "selected_key": "mikamoonbrcw",
                "occurrence_incremented": True,
                "support_incremented": True,
            },
            {
                "pass": "primary",
                "run_index": 1,
                "line_index": 4,
                "selected_key": "nikeosmnke",
                "occurrence_incremented": True,
                "support_incremented": True,
            },
        ]

        refilled = ocr_capture_ops._refill_names_to_target(
            names,
            refill_target=4,
            candidate_stats=stats,
            cfg=self._ocr_cfg(),
            trace_entries=trace,
            row_preferred=False,
        )
        ordered = ocr_capture_ops._order_names_by_line_trace(
            refilled,
            trace,
            row_preferred=False,
        )
        self.assertEqual(
            ordered,
            ["Aero", "AJAR", "Mika Moonbrcw", "NIKEOS MNKE"],
        )

    def test_resolve_effective_precount_rows_prefers_stable_primary_on_visual_overcount(self):
        primary_runs = [
            {
                "lines": [
                    {"text": "A", "conf": 90.0},
                    {"text": "B", "conf": 90.0},
                    {"text": "C", "conf": 90.0},
                    {"text": "D", "conf": 90.0},
                    {"text": "E", "conf": 90.0},
                    {"text": "F", "conf": 90.0},
                ]
            },
            {
                "lines": [
                    {"text": "A", "conf": 90.0},
                    {"text": "B", "conf": 90.0},
                    {"text": "C", "conf": 90.0},
                    {"text": "D", "conf": 90.0},
                    {"text": "E", "conf": 90.0},
                    {"text": "F", "conf": 90.0},
                ]
            },
        ]
        effective = ocr_capture_ops._resolve_effective_precount_rows(7, primary_runs)
        self.assertEqual(effective, 6)

    def test_estimate_expected_rows_fast_probe_reduces_detection_calls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = Path(tmpdir) / "a.png"
            path_b = Path(tmpdir) / "b.png"
            image = QtGui.QImage(32, 32, QtGui.QImage.Format_Grayscale8)
            image.fill(255)
            self.assertTrue(image.save(str(path_a), "PNG"))
            self.assertTrue(image.save(str(path_b), "PNG"))

            calls: list[int] = []

            def _fake_detect(_gray, cfg):
                calls.append(int(cfg.get("expected_candidates", 0)))
                return [(3, 6)]

            cfg = self._ocr_cfg()
            cfg.update(
                {
                    "max_variants": 2,
                    "fast_mode": True,
                    "expected_candidates": 5,
                    "precount_fast_probe_enabled": True,
                    "precount_fast_probe_single_expected": True,
                    "precount_fast_probe_max_variants": 1,
                }
            )
            with patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", side_effect=_fake_detect):
                estimated = ocr_capture_ops._estimate_expected_rows_from_paths(
                    [path_a, path_b],
                    cfg,
                )

            self.assertEqual(estimated, 1)
            self.assertEqual(calls, [5])

    def test_resolve_effective_precount_rows_keeps_visual_when_primary_unstable(self):
        primary_runs = [
            {
                "lines": [
                    {"text": "A", "conf": 90.0},
                    {"text": "B", "conf": 90.0},
                    {"text": "C", "conf": 90.0},
                    {"text": "D", "conf": 90.0},
                    {"text": "E", "conf": 90.0},
                    {"text": "F", "conf": 90.0},
                ]
            },
            {
                "lines": [
                    {"text": "A", "conf": 90.0},
                    {"text": "B", "conf": 90.0},
                    {"text": "C", "conf": 90.0},
                    {"text": "D", "conf": 90.0},
                    {"text": "E", "conf": 90.0},
                ]
            },
        ]
        effective = ocr_capture_ops._resolve_effective_precount_rows(7, primary_runs)
        self.assertEqual(effective, 7)

    def test_resolve_effective_precount_rows_uses_primary_when_visual_undercounts_single_run(self):
        primary_runs = [
            {
                "lines": [
                    {"text": "A", "conf": 90.0},
                    {"text": "B", "conf": 90.0},
                    {"text": "C", "conf": 90.0},
                    {"text": "D", "conf": 90.0},
                    {"text": "E", "conf": 90.0},
                    {"text": "F", "conf": 90.0},
                ]
            }
        ]
        effective = ocr_capture_ops._resolve_effective_precount_rows(1, primary_runs)
        self.assertEqual(effective, 6)

    def test_resolve_effective_precount_rows_keeps_visual_on_single_run_overcount(self):
        primary_runs = [
            {
                "lines": [
                    {"text": "A", "conf": 90.0},
                    {"text": "B", "conf": 90.0},
                    {"text": "C", "conf": 90.0},
                    {"text": "D", "conf": 90.0},
                    {"text": "E", "conf": 90.0},
                    {"text": "F", "conf": 90.0},
                ]
            }
        ]
        effective = ocr_capture_ops._resolve_effective_precount_rows(9, primary_runs)
        self.assertEqual(effective, 9)

    def test_resolve_precount_row_bounds_locks_upper_bound_when_primary_stable(self):
        minimum, maximum, refill_target = ocr_capture_ops._resolve_precount_row_bounds(
            effective_precount_rows=6,
            stable_primary_rows=6,
        )
        self.assertEqual((minimum, maximum, refill_target), (5, 6, 6))

    def test_resolve_precount_row_bounds_allows_soft_upper_without_stable_primary(self):
        minimum, maximum, refill_target = ocr_capture_ops._resolve_precount_row_bounds(
            effective_precount_rows=6,
            stable_primary_rows=None,
        )
        self.assertEqual((minimum, maximum, refill_target), (5, 7, 6))

    def test_precount_extra_allowance_ignores_weak_singleton_extra(self):
        stats: dict[str, dict[str, float | int | str]] = {}
        for idx in range(1, 8):
            name = f"Line{idx}"
            key = ocr_capture_ops._simple_name_key(name)
            if not key:
                continue
            stats[key] = {
                "display": name,
                "support": 2 if idx <= 6 else 1,
                "occurrences": 2 if idx <= 6 else 1,
                "best_conf": 80.0 if idx <= 6 else 33.0,
            }
        allowance = ocr_capture_ops._precount_extra_allowance_from_stats(
            base_max_rows=6,
            stats=stats,
            cfg=self._ocr_cfg(),
        )
        self.assertEqual(allowance, 0)

    def test_precount_extra_allowance_accepts_strong_extra(self):
        stats: dict[str, dict[str, float | int | str]] = {}
        for idx in range(1, 8):
            name = f"Line{idx}"
            key = ocr_capture_ops._simple_name_key(name)
            if not key:
                continue
            stats[key] = {
                "display": name,
                "support": 2,
                "occurrences": 2,
                "best_conf": 80.0,
            }
        allowance = ocr_capture_ops._precount_extra_allowance_from_stats(
            base_max_rows=6,
            stats=stats,
            cfg=self._ocr_cfg(),
        )
        self.assertEqual(allowance, 1)

    def test_build_final_names_respects_preferred_order_when_row_not_preferred(self):
        stats = {
            "charlie": {"display": "Charlie", "support": 3, "occurrences": 3, "best_conf": 90.0},
            "alpha": {"display": "Alpha", "support": 3, "occurrences": 3, "best_conf": 89.0},
            "bravo": {"display": "Bravo", "support": 3, "occurrences": 3, "best_conf": 88.0},
        }
        names = ocr_capture_ops._build_final_names_from_runs(
            cfg={
                "expected_candidates": 5,
                "name_min_support": 1,
                "name_min_confidence": 0.0,
                "name_low_confidence_min_support": 1,
            },
            stats=stats,
            preferred_names=["Alpha", "Bravo", "Charlie"],
            primary_names=["Alpha", "Bravo", "Charlie"],
            retry_names=[],
            row_names=["Charlie", "Alpha", "Bravo"],
            row_preferred=False,
        )
        self.assertEqual(names, ["Alpha", "Bravo", "Charlie"])

    def test_extract_names_runs_retry_when_fast_mode_finds_too_few(self):
        calls: list[dict] = []
        outputs = [
            "A\nB\nC\nD",
            "A\nB\nC\nD\nE",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                calls.append(
                    {
                        "path": str(image_path),
                        "cmd": cmd,
                        "psm_values": tuple(psm_values),
                        "timeout_s": timeout_s,
                        "lang": lang,
                        "stop_on_first_success": bool(stop_on_first_success),
                    }
                )
                text = outputs.pop(0) if outputs else ""
                return SimpleNamespace(text=text, error=None)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                seen: set[str] = set()
                names: list[str] = []
                for text in texts:
                    for line in str(text or "").splitlines():
                        value = line.strip()
                        if not value or value in seen:
                            continue
                        seen.add(value)
                        names.append(value)
                return names

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=self._ocr_cfg(),
            )

        self.assertEqual(names, ["A", "B", "C", "D", "E"])
        self.assertIn("E", merged_text)
        self.assertIsNone(error)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["psm_values"], (6,))
        self.assertTrue(calls[0]["stop_on_first_success"])
        self.assertEqual(calls[1]["psm_values"], (6, 11))
        self.assertFalse(calls[1]["stop_on_first_success"])
        self.assertGreater(calls[1]["timeout_s"], calls[0]["timeout_s"])

    def test_extract_names_skips_retry_when_threshold_is_met(self):
        calls: list[dict] = []
        outputs = [
            "Alpha\nBravo\nCharlie\nDelta\nEcho",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                calls.append(
                    {
                        "path": str(image_path),
                        "cmd": cmd,
                        "psm_values": tuple(psm_values),
                        "timeout_s": timeout_s,
                        "lang": lang,
                        "stop_on_first_success": bool(stop_on_first_success),
                    }
                )
                text = outputs.pop(0) if outputs else ""
                return SimpleNamespace(text=text, error=None)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                seen: set[str] = set()
                names: list[str] = []
                for text in texts:
                    for line in str(text or "").splitlines():
                        value = line.strip()
                        if not value or value in seen:
                            continue
                        seen.add(value)
                        names.append(value)
                return names

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=self._ocr_cfg(),
            )

        self.assertEqual(names, ["Alpha", "Bravo", "Charlie", "Delta", "Echo"])
        self.assertIn("Echo", merged_text)
        self.assertIsNone(error)
        self.assertEqual(len(calls), 1)

    def test_extract_names_fast_mode_confident_primary_short_circuit_skips_second_variant(self):
        calls: list[dict] = []
        outputs = [
            "Alpha\nBravo\nCharlie\nDelta\nEcho\nFoxtrot",
            "NOISE\nTAIL\nSHOULD\nNOT\nRUN",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                calls.append(
                    {
                        "path": str(image_path),
                        "cmd": cmd,
                        "psm_values": tuple(psm_values),
                        "timeout_s": timeout_s,
                        "lang": lang,
                        "stop_on_first_success": bool(stop_on_first_success),
                    }
                )
                text = outputs.pop(0) if outputs else ""
                return SimpleNamespace(text=text, error=None)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                seen: set[str] = set()
                names: list[str] = []
                for text in texts:
                    for line in str(text or "").splitlines():
                        value = line.strip()
                        if not value or value in seen:
                            continue
                        seen.add(value)
                        names.append(value)
                return names

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "max_variants": 2,
                "fast_mode": True,
                "stop_after_variant_success": False,
                "fast_mode_confident_line_stop": True,
                "fast_mode_confident_line_min_lines": 5,
                "expected_candidates": 5,
                "recall_retry_enabled": False,
                "row_pass_enabled": False,
            }
        )

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy-a.png"), Path("dummy-b.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(
            names,
            ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"],
        )
        self.assertIn("Foxtrot", merged_text)
        self.assertNotIn("SHOULD", merged_text)
        self.assertIsNone(error)
        self.assertEqual(len(calls), 1)

    def test_extract_names_relaxes_support_filter_when_result_stays_too_small(self):
        calls: list[dict] = []
        outputs = [
            "A\nB\nC\nD",
            "A\nB\nC\nD",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                calls.append(
                    {
                        "path": str(image_path),
                        "cmd": cmd,
                        "psm_values": tuple(psm_values),
                        "timeout_s": timeout_s,
                        "lang": lang,
                        "stop_on_first_success": bool(stop_on_first_success),
                    }
                )
                text = outputs.pop(0) if outputs else ""
                return SimpleNamespace(text=text, error=None)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                if int(kwargs.get("high_count_min_support", 2)) <= 1:
                    return ["A", "B", "C", "D", "Massith"]
                return ["A", "B", "C", "D"]

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=self._ocr_cfg(),
            )

        self.assertEqual(names, ["A", "B", "C", "D", "Massith"])
        self.assertIn("D", merged_text)
        self.assertIsNone(error)
        self.assertEqual(len(calls), 2)

    def test_extract_names_confident_line_stop_allows_one_missing_line_with_high_conf(self):
        calls: list[dict] = []
        outputs = [
            {
                "text": "Alpha\nBravo\nCharlie\nDelta",
                "lines": [
                    {"text": "Alpha", "conf": 92.0},
                    {"text": "Bravo", "conf": 88.0},
                    {"text": "Charlie", "conf": 85.0},
                    {"text": "Delta", "conf": 81.0},
                ],
            },
            {
                "text": "NOISE\nTAIL\nSHOULD\nNOT\nRUN",
                "lines": [
                    {"text": "NOISE", "conf": 42.0},
                    {"text": "TAIL", "conf": 41.0},
                    {"text": "SHOULD", "conf": 40.0},
                    {"text": "NOT", "conf": 39.0},
                    {"text": "RUN", "conf": 38.0},
                ],
            },
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                **kwargs,
            ):
                calls.append(
                    {
                        "path": str(image_path),
                        "engine": engine,
                        "cmd": cmd,
                        "psm_values": tuple(psm_values),
                        "timeout_s": timeout_s,
                        "lang": lang,
                        "stop_on_first_success": bool(stop_on_first_success),
                    }
                )
                payload = outputs.pop(0) if outputs else {"text": "", "lines": []}
                return SimpleNamespace(
                    text=str(payload.get("text", "")),
                    error=None,
                    lines=list(payload.get("lines", [])),
                )

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                seen: set[str] = set()
                names: list[str] = []
                for text in texts:
                    for line in str(text or "").splitlines():
                        value = line.strip()
                        if not value or value in seen:
                            continue
                        seen.add(value)
                        names.append(value)
                return names

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "max_variants": 2,
                "fast_mode": True,
                "stop_after_variant_success": False,
                "fast_mode_confident_line_stop": True,
                "fast_mode_confident_line_min_lines": 0,
                "fast_mode_confident_line_missing_tolerance": 1,
                "fast_mode_confident_line_min_avg_conf": 68.0,
                "fast_mode_confident_line_min_avg_conf_tolerant": 78.0,
                "expected_candidates": 5,
                "recall_retry_enabled": False,
                "row_pass_enabled": False,
            }
        )

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy-a.png"), Path("dummy-b.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, ["Alpha", "Bravo", "Charlie", "Delta"])
        self.assertNotIn("SHOULD", merged_text)
        self.assertIsNone(error)
        self.assertEqual(len(calls), 1)

    def test_extract_names_prefers_retry_when_primary_has_too_many_candidates(self):
        calls: list[dict] = []
        outputs = [
            "Aero\nBAO\nBar\nMNKE\nHOY\nPw\nHO\nB w\nHD",
            "Aero\nAJAR\nMassith\nMika\nMoonbrew",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                calls.append(
                    {
                        "path": str(image_path),
                        "cmd": cmd,
                        "psm_values": tuple(psm_values),
                        "timeout_s": timeout_s,
                        "lang": lang,
                        "stop_on_first_success": bool(stop_on_first_success),
                    }
                )
                text = outputs.pop(0) if outputs else ""
                return SimpleNamespace(text=text, error=None)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                seen: set[str] = set()
                names: list[str] = []
                for text in texts:
                    for line in str(text or "").splitlines():
                        value = line.strip()
                        if not value or value in seen:
                            continue
                        seen.add(value)
                        names.append(value)
                return names

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=self._ocr_cfg(),
            )

        self.assertEqual(names, ["Aero", "AJAR", "Massith", "Mika", "Moonbrew"])
        self.assertIn("Massith", merged_text)
        self.assertIsNone(error)
        self.assertEqual(len(calls), 2)

    def test_extract_names_applies_strict_filter_for_noisy_large_candidate_set(self):
        outputs = [
            "Aero\nBAO\nBar\nMNKE\nHOY\nPw\nHO\nB w\nHD",
            "Aero\nBAO\nBar\nMNKE\nHOY\nPw\nHO\nB w\nHD",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                text = outputs.pop(0) if outputs else ""
                return SimpleNamespace(text=text, error=None)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                min_chars = int(kwargs.get("min_chars", 2))
                if min_chars >= 3:
                    return ["Aero", "BAO", "Bar", "MNKE", "HOY"]
                return ["Aero", "BAO", "Bar", "MNKE", "HOY", "Pw", "HO", "B w", "HD"]

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=self._ocr_cfg(),
            )

        self.assertEqual(names, ["Aero", "BAO", "Bar", "MNKE", "HOY"])
        self.assertIn("Aero", merged_text)
        self.assertIsNone(error)

    def test_extract_names_debug_report_includes_line_analysis(self):
        outputs = [
            "Massith | Marc みのり\nAero\nAero",
            "Massith | Marc みのり\nAero\nAero",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                text = outputs.pop(0) if outputs else ""
                return SimpleNamespace(text=text, error=None)

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                return real_ocr_import.extract_candidate_names(text, **kwargs)

            @staticmethod
            def extract_candidate_names_debug(text, **kwargs):
                return real_ocr_import.extract_candidate_names_debug(text, **kwargs)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                return real_ocr_import.extract_candidate_names_multi(texts, **kwargs)

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "debug_show_report": True,
                "debug_include_report_text": True,
                "debug_line_analysis": True,
                "debug_line_max_entries_per_run": 10,
            }
        )

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, debug_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, ["Massith", "Aero"])
        self.assertIn("[OCR Debug Report]", debug_text)
        self.assertIn("line-analysis:", debug_text)
        self.assertIn("duplicate-key", debug_text)
        self.assertIsNone(error)

    def test_extract_names_prefers_row_pass_when_better(self):
        outputs = [
            "Aero\nHOY\nPw\nMNKE",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                text = outputs.pop(0) if outputs else ""
                return SimpleNamespace(text=text, error=None)

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                return real_ocr_import.extract_candidate_names(text, **kwargs)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                return real_ocr_import.extract_candidate_names_multi(texts, **kwargs)

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": True,
                "row_pass_min_candidates": 5,
                "expected_candidates": 5,
            }
        )
        row_names = ["Aero", "AJAR", "Massith", "Mika", "NIKEOS"]
        row_texts = ["Aero\nAJAR\nMassith\nMika\nNIKEOS"]
        row_runs = [
            {
                "pass": "row",
                "image": "dummy.png#1[0:20]",
                "psm_values": [7, 6, 13],
                "timeout_s": 1.0,
                "lang": "eng",
                "fast_mode": False,
                "text": "Aero",
                "error": "",
            }
        ]

        with (
            patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
            patch(
                "controller.ocr.ocr_capture_ops._run_row_segmentation_pass",
                return_value=(row_names, row_texts, row_runs),
            ),
        ):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, row_names)
        self.assertIn("NIKEOS", merged_text)
        self.assertIsNone(error)

    def test_extract_names_row_preferred_does_not_reinflate_with_extra_candidates(self):
        outputs = [
            "Music\nJockie Music 1\nMogojyan The Lacie Lover\nRontarou\nThe Bookseller\nTK\nFWMC",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                text = outputs.pop(0) if outputs else ""
                return SimpleNamespace(text=text, error=None)

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                return real_ocr_import.extract_candidate_names(text, **kwargs)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                return real_ocr_import.extract_candidate_names_multi(texts, **kwargs)

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": True,
                "row_pass_min_candidates": 5,
                "expected_candidates": 5,
            }
        )
        row_names = ["Jockie Music 1", "Mogojyan The Lacie Lover", "Rontarou", "The Bookseller"]
        row_texts = ["\n".join(row_names)]
        row_runs = [
            {
                "pass": "row",
                "image": "dummy.png#1[0:20]",
                "psm_values": [7, 6, 13],
                "timeout_s": 1.0,
                "lang": "eng",
                "fast_mode": False,
                "text": row_texts[0],
                "error": "",
            }
        ]

        with (
            patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
            patch(
                "controller.ocr.ocr_capture_ops._run_row_segmentation_pass",
                return_value=(row_names, row_texts, row_runs),
            ),
        ):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, row_names)
        self.assertIn("The Bookseller", merged_text)
        self.assertIsNone(error)

    def test_extract_names_row_preferred_primary_stabilization_fixes_single_shifted_line(self):
        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                del image_path, cmd, psm_values, timeout_s, lang, stop_on_first_success
                return SimpleNamespace(text="", error=None)

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                return real_ocr_import.extract_candidate_names(text, **kwargs)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                return real_ocr_import.extract_candidate_names_multi(texts, **kwargs)

        primary_names = [
            "Jockie Music 1 (ml)",
            "Mogojyan The Lacie Lover FWMC",
            "Rontorou {Gest Cojo Moin} 1OOK",
            "The Gookseller {The Foodlover}",
        ]
        primary_runs = [
            {
                "pass": "primary",
                "image": "a.png",
                "lines": [
                    {"text": primary_names[0], "conf": 92.0},
                    {"text": primary_names[1], "conf": 90.0},
                    {"text": primary_names[2], "conf": 88.0},
                    {"text": primary_names[3], "conf": 86.0},
                ],
                "text": "\n".join(primary_names),
            },
            {
                "pass": "primary",
                "image": "b.png",
                "lines": [
                    {"text": primary_names[0], "conf": 93.0},
                    {"text": primary_names[1], "conf": 91.0},
                    {"text": primary_names[2], "conf": 89.0},
                    {"text": primary_names[3], "conf": 87.0},
                ],
                "text": "\n".join(primary_names),
            },
        ]
        row_names = [
            "Fa 4",
            "Lenj LCCiits 4aai n e",
            "Mogojyan The Lacie Lover FWMC",
            "Rontorou {Gest Cojo Moin} 10OH %",
            "Tk? pacLSSIS_ tks Fc3A Ic",
        ]
        row_texts = ["\n".join(row_names)]
        row_runs = [
            {
                "pass": "row",
                "image": "dummy.png#1[0:20]",
                "psm_values": [7, 6, 13],
                "timeout_s": 1.0,
                "lang": "eng",
                "fast_mode": False,
                "text": row_texts[0],
                "error": "",
            }
        ]
        stats: dict[str, dict[str, float | int | str]] = {}
        for text in primary_names + row_names:
            key = ocr_capture_ops._simple_name_key(text)
            if not key or key in stats:
                continue
            stats[key] = {"display": text, "support": 1, "occurrences": 1, "best_conf": 90.0}

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": True,
                "row_pass_min_candidates": 5,
                "expected_candidates": 5,
            }
        )

        def _candidate_stats_with_trace(_runs, _parse_ctx, *, trace_entries=None, include_debug_meta=False):
            del _runs, _parse_ctx, include_debug_meta
            if trace_entries is not None:
                for idx, text in enumerate(primary_names, start=1):
                    trace_entries.append(
                        {
                            "pass": "primary",
                            "run_index": 1,
                            "line_index": idx,
                            "selected_key": ocr_capture_ops._simple_name_key(text),
                            "support_incremented": True,
                            "occurrence_incremented": True,
                        }
                    )
                trace_entries.extend(
                    [
                        {
                            "pass": "row",
                            "run_index": 5,
                            "line_index": 1,
                            "image": "src#1[0:0]/name.base",
                            "selected_key": ocr_capture_ops._simple_name_key(row_names[0]),
                            "support_incremented": True,
                            "occurrence_incremented": True,
                        },
                        {
                            "pass": "row",
                            "run_index": 9,
                            "line_index": 1,
                            "image": "src#2[0:0]/name.base",
                            "selected_key": ocr_capture_ops._simple_name_key(row_names[1]),
                            "support_incremented": True,
                            "occurrence_incremented": True,
                        },
                        {
                            "pass": "row",
                            "run_index": 23,
                            "line_index": 1,
                            "image": "src#3[0:0]/name.base",
                            "selected_key": ocr_capture_ops._simple_name_key(row_names[2]),
                            "support_incremented": True,
                            "occurrence_incremented": True,
                        },
                        {
                            "pass": "row",
                            "run_index": 29,
                            "line_index": 1,
                            "image": "src#4[0:0]/name.base",
                            "selected_key": ocr_capture_ops._simple_name_key(row_names[3]),
                            "support_incremented": True,
                            "occurrence_incremented": True,
                        },
                    ]
                )
            return dict(stats)

        with (
            patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
            patch("controller.ocr.ocr_capture_ops._estimate_expected_rows_from_paths", return_value=5),
            patch(
                "controller.ocr.ocr_capture_ops._run_ocr_pass",
                return_value=(["\n".join(primary_names)], [], primary_runs),
            ),
            patch(
                "controller.ocr.ocr_capture_ops._run_row_segmentation_pass",
                return_value=(row_names, row_texts, row_runs),
            ),
            patch("controller.ocr.ocr_capture_ops._extract_names_from_texts", return_value=list(primary_names)),
            patch("controller.ocr.ocr_capture_ops._prefer_row_candidates", return_value=True),
            patch(
                "controller.ocr.ocr_capture_ops._candidate_stats_from_runs",
                side_effect=_candidate_stats_with_trace,
            ),
            patch(
                "controller.ocr.ocr_capture_ops._build_final_names_from_runs",
                return_value=[
                    primary_names[0],
                    primary_names[2],
                    primary_names[3],
                    primary_names[1],
                ],
            ),
            patch(
                "controller.ocr.ocr_capture_ops._filter_low_confidence_candidates",
                side_effect=lambda names, *_args, **_kwargs: list(names),
            ),
            patch(
                "controller.ocr.ocr_capture_ops._expand_config_identifier_prefixes",
                side_effect=lambda names: list(names),
            ),
        ):
            names, _merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(
            names,
            [
                "Jockie Music 1 (ml)",
                "Mogojyan The Lacie Lover FWMC",
                "Rontorou {Gest Cojo Moin} 1OOK",
                "The Gookseller {The Foodlover}",
            ],
        )
        self.assertIsNone(error)

    def test_extract_names_row_preferred_restores_missing_primary_slot_from_overflow_tail(self):
        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                del image_path, cmd, psm_values, timeout_s, lang, stop_on_first_success
                return SimpleNamespace(text="", error=None)

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                return real_ocr_import.extract_candidate_names(text, **kwargs)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                return real_ocr_import.extract_candidate_names_multi(texts, **kwargs)

        primary_names = [
            "[+] Rhug TLC",
            "flatiqz",
            "Kylo BMTH",
            "mikix TLC",
            "Pxssesive",
            "rqlled AIM",
            "yukino",
        ]
        row_names = [
            "[+] Rhug TLC",
            "tlatiaz",
            "Kylo BMTH",
            "mikix TLC",
            "pxssesive",
            "ralled AIM",
            "vukino",
        ]
        primary_runs = [
            {
                "pass": "primary",
                "image": "a.png",
                "lines": [
                    {"text": primary_names[0], "conf": 99.0},
                    {"text": primary_names[1], "conf": 92.0},
                    {"text": primary_names[2], "conf": 99.0},
                    {"text": primary_names[3], "conf": 99.0},
                    {"text": primary_names[4], "conf": 99.0},
                    {"text": primary_names[5], "conf": 79.0},
                    {"text": primary_names[6], "conf": 99.0},
                ],
                "text": "\n".join(primary_names),
            },
            {
                "pass": "primary",
                "image": "b.png",
                "lines": [
                    {"text": primary_names[0], "conf": 82.0},
                    {"text": primary_names[1], "conf": 82.0},
                    {"text": primary_names[2], "conf": 99.0},
                    {"text": primary_names[3], "conf": 99.0},
                    {"text": primary_names[4], "conf": 68.0},
                    {"text": primary_names[5], "conf": 62.0},
                    {"text": primary_names[6], "conf": 99.0},
                ],
                "text": "\n".join(primary_names),
            },
        ]
        row_texts = ["\n".join(row_names)]
        row_runs = [
            {
                "pass": "row",
                "image": "src#8[0:0]/name.base",
                "psm_values": [7, 6, 13],
                "timeout_s": 1.0,
                "lang": "eng",
                "fast_mode": False,
                "text": "vukino",
                "error": "",
            }
        ]
        stats: dict[str, dict[str, float | int | str]] = {
            "rhugtlc": {"display": "[+] Rhug TLC", "support": 2, "occurrences": 5, "best_conf": 99.0},
            "flatiqz": {"display": "flatiqz", "support": 2, "occurrences": 2, "best_conf": 92.0},
            "kylobmth": {"display": "Kylo BMTH", "support": 2, "occurrences": 2, "best_conf": 99.0},
            "mikixtlc": {"display": "mikix TLC", "support": 2, "occurrences": 2, "best_conf": 99.0},
            "pxssesive": {"display": "Pxssesive", "support": 2, "occurrences": 2, "best_conf": 99.0},
            "rqlledaim": {"display": "rqlled AIM", "support": 1, "occurrences": 2, "best_conf": 79.0},
            "yukino": {"display": "yukino", "support": 1, "occurrences": 2, "best_conf": 99.0},
            "vukino": {"display": "vukino", "support": 1, "occurrences": 3, "best_conf": 91.0},
        }

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": True,
                "row_pass_min_candidates": 5,
                "expected_candidates": 7,
            }
        )

        def _candidate_stats_with_trace(_runs, _parse_ctx, *, trace_entries=None, include_debug_meta=False):
            del _runs, _parse_ctx, include_debug_meta
            if trace_entries is not None:
                for idx, name in enumerate(primary_names, start=1):
                    trace_entries.append(
                        {
                            "pass": "primary",
                            "run_index": 1,
                            "line_index": idx,
                            "selected_key": ocr_capture_ops._simple_name_key(name),
                            "support_incremented": True,
                            "occurrence_incremented": True,
                        }
                    )
                trace_entries.append(
                    {
                        "pass": "row",
                        "run_index": 29,
                        "line_index": 1,
                        "image": "src#8[0:0]/name.base",
                        "selected_key": "vukino",
                        "support_incremented": True,
                        "occurrence_incremented": True,
                    }
                )
            return dict(stats)

        with (
            patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
            patch("controller.ocr.ocr_capture_ops._estimate_expected_rows_from_paths", return_value=7),
            patch(
                "controller.ocr.ocr_capture_ops._run_ocr_pass",
                return_value=(["\n".join(primary_names)], [], primary_runs),
            ),
            patch(
                "controller.ocr.ocr_capture_ops._run_row_segmentation_pass",
                return_value=(row_names, row_texts, row_runs),
            ),
            patch("controller.ocr.ocr_capture_ops._extract_names_from_texts", return_value=list(primary_names)),
            patch("controller.ocr.ocr_capture_ops._prefer_row_candidates", return_value=True),
            patch(
                "controller.ocr.ocr_capture_ops._candidate_stats_from_runs",
                side_effect=_candidate_stats_with_trace,
            ),
            patch(
                "controller.ocr.ocr_capture_ops._build_final_names_from_runs",
                return_value=[
                    "[+] Rhug TLC",
                    "flatiqz",
                    "Kylo BMTH",
                    "mikix TLC",
                    "Pxssesive",
                    "yukino",
                    "vukino",
                ],
            ),
            patch(
                "controller.ocr.ocr_capture_ops._filter_low_confidence_candidates",
                side_effect=lambda names, *_args, **_kwargs: list(names),
            ),
            patch(
                "controller.ocr.ocr_capture_ops._expand_config_identifier_prefixes",
                side_effect=lambda names: list(names),
            ),
        ):
            names, _merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(
            names,
            [
                "[+] Rhug TLC",
                "flatiqz",
                "Kylo BMTH",
                "mikix TLC",
                "Pxssesive",
                "rqlled AIM",
                "yukino",
            ],
        )
        self.assertIsNone(error)

    def test_row_pass_retries_full_width_when_right_edge_looks_clipped(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                if call_no["n"] == 1:
                    text = "Mogojyan The"
                else:
                    text = "Mogojyan The Lacie Lover"
                return SimpleNamespace(
                    text=text,
                    error=None,
                    lines=[SimpleNamespace(text=text, confidence=80.0)],
                )

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 1,
                "row_pass_include_mono": False,
                "row_pass_psm_values": (7,),
                "row_pass_full_only_when_name_uncertain": False,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(180, 24, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = ocr_capture_ops._OCRLineParseContext(_StubOCRImport(), cfg)
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=[(2, 20)]),
                patch("controller.ocr.ocr_capture_ops._build_row_image_variants", side_effect=lambda row_img, _cfg: [("base", row_img)]),
                patch("controller.ocr.ocr_capture_ops._row_image_looks_right_clipped", return_value=True),
            ):
                names, row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(call_no["n"], 2)
        self.assertEqual(names, ["Mogojyan The Lacie Lover"])
        self.assertIn("Mogojyan The Lacie Lover", row_texts)
        self.assertEqual(len(runs), 2)
        self.assertIn("/full.base", str(runs[1].get("image", "")))

    def test_row_pass_skips_full_width_when_name_crop_stays_empty(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                return SimpleNamespace(text="", error=None, lines=[])

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 2,
                "row_pass_include_mono": False,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": True,
                "row_pass_full_width_edge_only": False,
                "row_pass_skip_full_when_name_empty": True,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(180, 24, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = ocr_capture_ops._OCRLineParseContext(_StubOCRImport(), cfg)
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=[(2, 20)]),
                patch("controller.ocr.ocr_capture_ops._row_image_looks_right_clipped", return_value=True),
            ):
                names, _row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(call_no["n"], 2)
        self.assertEqual(names, [])
        self.assertEqual(len(runs), 2)
        self.assertTrue(all("/full." not in str(run.get("image", "")) for run in runs))

    def test_row_pass_skips_full_width_when_name_crop_only_has_low_conf_noise(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                return SimpleNamespace(
                    text="low conf noise",
                    error=None,
                    lines=[SimpleNamespace(text="low conf noise", confidence=4.0)],
                )

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 2,
                "row_pass_include_mono": False,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": True,
                "row_pass_full_width_edge_only": False,
                "row_pass_skip_full_when_name_empty": False,
                "row_pass_skip_full_when_name_low_conf": True,
                "row_pass_skip_full_when_name_low_conf_max_conf": 12.0,
                "row_pass_line_stats_min_conf": 8.0,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(180, 24, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = ocr_capture_ops._OCRLineParseContext(_StubOCRImport(), cfg)
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=[(2, 20)]),
                patch("controller.ocr.ocr_capture_ops._row_image_looks_right_clipped", return_value=True),
            ):
                names, _row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(call_no["n"], 2)
        self.assertEqual(names, [])
        self.assertEqual(len(runs), 2)
        self.assertTrue(all("/full." not in str(run.get("image", "")) for run in runs))

    def test_row_pass_stops_early_after_vote_target_without_full_width_retry(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                text = "Mogojyan The Lacie Lover"
                return SimpleNamespace(
                    text=text,
                    error=None,
                    lines=[SimpleNamespace(text=text, confidence=82.0)],
                )

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 2,
                "row_pass_include_mono": False,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": True,
                "row_pass_vote_target_single_name": 2,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(180, 24, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = ocr_capture_ops._OCRLineParseContext(_StubOCRImport(), cfg)
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=[(2, 20)]),
            ):
                names, row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(call_no["n"], 2)
        self.assertEqual(names, ["Mogojyan The Lacie Lover"])
        self.assertIn("Mogojyan The Lacie Lover", row_texts)
        self.assertEqual(len(runs), 2)
        self.assertTrue(all("/full." not in str(run.get("image", "")) for run in runs))

    def test_row_pass_confident_single_vote_stops_after_first_variant(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                text = "Mogojyan The Lacie Lover"
                return SimpleNamespace(
                    text=text,
                    error=None,
                    lines=[SimpleNamespace(text=text, confidence=99.0)],
                )

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 2,
                "row_pass_include_mono": False,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": True,
                "row_pass_vote_target_single_name": 2,
                "row_pass_confident_single_vote_stop": True,
                "row_pass_confident_single_vote_min_conf": 98.0,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(180, 24, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = ocr_capture_ops._OCRLineParseContext(_StubOCRImport(), cfg)
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=[(2, 20)]),
            ):
                names, row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(call_no["n"], 1)
        self.assertEqual(names, ["Mogojyan The Lacie Lover"])
        self.assertIn("Mogojyan The Lacie Lover", row_texts)
        self.assertEqual(len(runs), 1)

    def test_row_pass_stops_after_consecutive_empty_rows_when_enough_names_collected(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                if call_no["n"] <= 5:
                    text = f"Name{call_no['n']}"
                    return SimpleNamespace(
                        text=text,
                        error=None,
                        lines=[SimpleNamespace(text=text, confidence=80.0)],
                    )
                return SimpleNamespace(text="", error=None, lines=[])

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "fast_mode": True,
                "expected_candidates": 5,
                "row_pass_max_rows": 12,
                "row_pass_adaptive_max_rows": True,
                "row_pass_adaptive_extra_rows": 4,
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 1,
                "row_pass_include_mono": False,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": False,
                "row_pass_vote_target_single_name": 1,
                "row_pass_consecutive_empty_row_stop": 2,
                "row_pass_empty_row_stop_min_collected": 5,
                "row_pass_stop_when_expected_reached": False,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(220, 320, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = ocr_capture_ops._OCRLineParseContext(_StubOCRImport(), cfg)
            row_ranges = [(2 + i * 20, 10 + i * 20) for i in range(10)]
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=row_ranges),
            ):
                names, _row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(names, ["Name1", "Name2", "Name3", "Name4", "Name5"])
        self.assertEqual(call_no["n"], 7)
        self.assertEqual(len(runs), 7)

    def test_row_pass_prefilter_skips_obvious_noise_before_parser(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                return SimpleNamespace(
                    text="1\n(\nAlpha",
                    error=None,
                    lines=[
                        SimpleNamespace(text="1", confidence=1.0),
                        SimpleNamespace(text="(", confidence=2.0),
                        SimpleNamespace(text="Alpha", confidence=82.0),
                    ],
                )

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        class _ParseCtx:
            def __init__(self):
                self.calls: list[str] = []

            def extract_line_candidates(self, line_text):
                text = str(line_text or "").strip()
                self.calls.append(text)
                return [text] if text else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 1,
                "row_pass_include_mono": False,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": False,
                "row_pass_vote_target_single_name": 1,
                "row_pass_line_prefilter_enabled": True,
                "row_pass_line_prefilter_low_conf": 22.0,
                "row_pass_line_prefilter_high_conf_bypass": 72.0,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(180, 24, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = _ParseCtx()
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=[(2, 20)]),
            ):
                names, _row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(call_no["n"], 1)
        self.assertEqual(names, ["Alpha"])
        self.assertEqual(parse_ctx.calls, ["Alpha"])
        self.assertEqual(len(runs), 1)

    def test_row_pass_reuses_cached_candidate_for_duplicate_raw_line(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                return SimpleNamespace(
                    text="Alpha",
                    error=None,
                    lines=[SimpleNamespace(text="Alpha", confidence=84.0)],
                )

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        class _ParseCtx:
            def __init__(self):
                self.calls: list[str] = []

            def extract_line_candidates(self, line_text):
                text = str(line_text or "").strip()
                self.calls.append(text)
                return [text] if text else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 2,
                "row_pass_include_mono": False,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": False,
                "row_pass_vote_target_single_name": 2,
                "row_pass_line_prefilter_enabled": True,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(180, 24, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = _ParseCtx()
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=[(2, 20)]),
            ):
                names, _row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(call_no["n"], 2)
        self.assertEqual(names, ["Alpha"])
        self.assertEqual(parse_ctx.calls, ["Alpha"])
        self.assertEqual(len(runs), 2)

    def test_row_pass_reuses_cached_candidate_across_rows(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                return SimpleNamespace(
                    text="Alpha",
                    error=None,
                    lines=[SimpleNamespace(text="Alpha", confidence=84.0)],
                )

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        class _ParseCtx:
            def __init__(self):
                self.calls: list[str] = []

            def extract_line_candidates(self, line_text):
                text = str(line_text or "").strip()
                self.calls.append(text)
                return [text] if text else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 1,
                "row_pass_include_mono": False,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": False,
                "row_pass_vote_target_single_name": 1,
                "row_pass_line_prefilter_enabled": True,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(200, 80, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = _ParseCtx()
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=[(2, 12), (24, 34)]),
            ):
                names, _row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(call_no["n"], 2)
        self.assertEqual(names, ["Alpha"])
        self.assertEqual(parse_ctx.calls, ["Alpha"])
        self.assertEqual(len(runs), 2)

    def test_row_pass_skips_mono_retry_when_row_candidate_is_already_confident(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                if call_no["n"] == 1:
                    return SimpleNamespace(
                        text="Alpha",
                        error=None,
                        lines=[SimpleNamespace(text="Alpha", confidence=85.0)],
                    )
                return SimpleNamespace(text="", error=None, lines=[])

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 2,
                "row_pass_include_mono": True,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": False,
                "row_pass_vote_target_single_name": 3,
                "row_pass_confident_single_vote_stop": False,
                "row_pass_mono_retry_only_when_uncertain": True,
                "row_pass_mono_retry_min_conf": 70.0,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(180, 24, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = ocr_capture_ops._OCRLineParseContext(_StubOCRImport(), cfg)
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=[(2, 20)]),
            ):
                names, _row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        # base + scaled only (mono variants skipped due confident first vote)
        self.assertEqual(call_no["n"], 2)
        self.assertEqual(names, ["Alpha"])
        self.assertEqual(len(runs), 2)

    def test_row_pass_skips_mono_retry_when_non_mono_signal_is_only_low_conf_noise(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                if call_no["n"] == 1:
                    return SimpleNamespace(
                        text="Lt",
                        error=None,
                        lines=[SimpleNamespace(text="Lt", confidence=0.3)],
                    )
                if call_no["n"] == 2:
                    return SimpleNamespace(
                        text="n",
                        error=None,
                        lines=[SimpleNamespace(text="n", confidence=1.2)],
                    )
                return SimpleNamespace(text="", error=None, lines=[])

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 2,
                "row_pass_include_mono": True,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": False,
                "row_pass_vote_target_single_name": 3,
                "row_pass_skip_mono_when_non_mono_empty": False,
                "row_pass_skip_mono_when_non_mono_low_conf": True,
                "row_pass_skip_mono_when_non_mono_low_conf_max_conf": 12.0,
                "row_pass_line_stats_min_conf": 8.0,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(180, 24, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = ocr_capture_ops._OCRLineParseContext(_StubOCRImport(), cfg)
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=[(2, 20)]),
            ):
                names, _row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(call_no["n"], 2)
        self.assertEqual(names, [])
        self.assertEqual(len(runs), 2)
        self.assertTrue(all("/mono" not in str(run.get("image", "")) for run in runs))

    def test_row_pass_extra_rows_light_mode_reduces_tail_variant_calls(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                if call_no["n"] <= 5:
                    text = f"Name{call_no['n']}"
                    return SimpleNamespace(
                        text=text,
                        error=None,
                        lines=[SimpleNamespace(text=text, confidence=82.0)],
                    )
                return SimpleNamespace(text="", error=None, lines=[])

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "fast_mode": True,
                "expected_candidates": 5,
                "row_pass_max_rows": 12,
                "row_pass_adaptive_max_rows": True,
                "row_pass_adaptive_extra_rows": 2,
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 2,
                "row_pass_include_mono": True,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": True,
                "row_pass_full_width_edge_only": False,
                "row_pass_vote_target_single_name": 1,
                "row_pass_confident_single_vote_stop": False,
                "row_pass_mono_retry_only_when_uncertain": False,
                "row_pass_extra_rows_light_mode": True,
                "row_pass_extra_rows_light_mode_min_collected": 5,
                "row_pass_consecutive_empty_row_stop": 2,
                "row_pass_empty_row_stop_min_collected": 5,
                "row_pass_stop_when_expected_reached": False,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(220, 220, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = ocr_capture_ops._OCRLineParseContext(_StubOCRImport(), cfg)
            row_ranges = [(2 + i * 20, 10 + i * 20) for i in range(10)]
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=row_ranges),
            ):
                names, _row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        # First 5 rows succeed in one call each (vote_target=1).
        # Extra rows 6 and 7 run in light mode: name crop + non-mono variants.
        self.assertEqual(names, ["Name1", "Name2", "Name3", "Name4", "Name5"])
        self.assertEqual(call_no["n"], 9)
        self.assertEqual(len(runs), 9)

    def test_row_pass_stops_when_expected_rows_are_already_collected(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                text = f"Name{call_no['n']}"
                return SimpleNamespace(
                    text=text,
                    error=None,
                    lines=[SimpleNamespace(text=text, confidence=82.0)],
                )

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "expected_candidates": 5,
                "row_pass_max_rows": 12,
                "row_pass_adaptive_max_rows": False,
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 1,
                "row_pass_include_mono": False,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": False,
                "row_pass_vote_target_single_name": 1,
                "row_pass_stop_when_expected_reached": True,
                "row_pass_consecutive_empty_row_stop": 0,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(220, 260, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = ocr_capture_ops._OCRLineParseContext(_StubOCRImport(), cfg)
            row_ranges = [(2 + i * 20, 10 + i * 20) for i in range(10)]
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=row_ranges),
            ):
                names, _row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(names, ["Name1", "Name2", "Name3", "Name4", "Name5"])
        self.assertEqual(call_no["n"], 5)
        self.assertEqual(len(runs), 5)

    def test_row_pass_adaptive_max_rows_limits_processed_rows_in_fast_mode(self):
        call_no = {"n": 0}

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                engine,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
                easyocr_model_dir,
                easyocr_user_network_dir,
                easyocr_gpu,
                easyocr_download_enabled,
                easyocr_quiet,
            ):
                del (
                    image_path,
                    engine,
                    cmd,
                    psm_values,
                    timeout_s,
                    lang,
                    stop_on_first_success,
                    easyocr_model_dir,
                    easyocr_user_network_dir,
                    easyocr_gpu,
                    easyocr_download_enabled,
                    easyocr_quiet,
                )
                call_no["n"] += 1
                text = "RowCandidate"
                return SimpleNamespace(
                    text=text,
                    error=None,
                    lines=[SimpleNamespace(text=text, confidence=80.0)],
                )

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                del kwargs
                value = str(text or "").strip()
                return [value] if value else []

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "engine": "easyocr",
                "lang": "en",
                "fast_mode": True,
                "expected_candidates": 5,
                "row_pass_max_rows": 12,
                "row_pass_adaptive_max_rows": True,
                "row_pass_adaptive_extra_rows": 2,
                "row_pass_name_x_ratio": 0.58,
                "row_pass_brightness_threshold": 145,
                "row_pass_scale_factor": 1,
                "row_pass_include_mono": False,
                "row_pass_psm_values": (7,),
                "row_pass_full_width_fallback": False,
                "name_special_char_constraint": False,
            }
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            img = QtGui.QImage(200, 260, QtGui.QImage.Format_Grayscale8)
            img.fill(0)
            self.assertTrue(img.save(str(image_path), "PNG"))

            parse_ctx = ocr_capture_ops._OCRLineParseContext(_StubOCRImport(), cfg)
            row_ranges = [(2 + i * 20, 10 + i * 20) for i in range(10)]
            with (
                patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
                patch("controller.ocr.ocr_capture_ops._detect_text_row_ranges", return_value=row_ranges),
            ):
                _names, _row_texts, runs = ocr_capture_ops._run_row_segmentation_pass(
                    [image_path],
                    cfg=cfg,
                    parse_ctx=parse_ctx,
                )
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(call_no["n"], 7)
        self.assertEqual(len(runs), 7)

    def test_expand_config_identifier_prefixes_completes_unique_prefixes(self):
        names = [
            "TOOLTIP_CACHE_ON_STA",
            "SOUND_WARMUP_LAZY_ST",
            "MAP_PREBUILD_ON_ST",
            "SOUND WARMUP ON ST",
        ]
        with patch(
            "controller.ocr.ocr_capture_ops._config_identifier_hints",
            return_value=(
                "TOOLTIP_CACHE_ON_START",
                "SOUND_WARMUP_LAZY_STEP_MS",
                "MAP_PREBUILD_ON_START",
                "SOUND_WARMUP_ON_START",
            ),
        ):
            resolved = ocr_capture_ops._expand_config_identifier_prefixes(names)
        self.assertEqual(
            resolved,
            [
                "TOOLTIP_CACHE_ON_START",
                "SOUND_WARMUP_LAZY_STEP_MS",
                "MAP_PREBUILD_ON_START",
                "SOUND_WARMUP_ON_START",
            ],
        )

    def test_extract_names_filters_low_confidence_singletons(self):
        outputs = [
            "Aero\nAJAR\nMassith\nMika\nMNKE",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                text = outputs.pop(0) if outputs else ""
                lines = [
                    SimpleNamespace(text="Aero", confidence=88.0),
                    SimpleNamespace(text="AJAR", confidence=77.0),
                    SimpleNamespace(text="Massith", confidence=74.0),
                    SimpleNamespace(text="Mika", confidence=72.0),
                    SimpleNamespace(text="MNKE", confidence=12.0),
                ]
                return SimpleNamespace(text=text, error=None, lines=lines)

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                return real_ocr_import.extract_candidate_names(text, **kwargs)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                return real_ocr_import.extract_candidate_names_multi(texts, **kwargs)

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": False,
                "name_confidence_filter_noisy_only": False,
                "name_min_confidence": 43.0,
                "name_low_confidence_min_support": 2,
            }
        )

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, ["Aero", "AJAR", "Massith", "Mika"])
        self.assertIn("MNKE", merged_text)
        self.assertIsNone(error)

    def test_extract_names_keeps_expected_count_in_noisy_only_mode(self):
        outputs = [
            "Aero\nAJAR\nMassith\nMika\nMNKE",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                text = outputs.pop(0) if outputs else ""
                lines = [
                    SimpleNamespace(text="Aero", confidence=88.0),
                    SimpleNamespace(text="AJAR", confidence=77.0),
                    SimpleNamespace(text="Massith", confidence=74.0),
                    SimpleNamespace(text="Mika", confidence=72.0),
                    SimpleNamespace(text="MNKE", confidence=12.0),
                ]
                return SimpleNamespace(text=text, error=None, lines=lines)

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                return real_ocr_import.extract_candidate_names(text, **kwargs)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                return real_ocr_import.extract_candidate_names_multi(texts, **kwargs)

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": False,
                "name_confidence_filter_noisy_only": True,
                "name_min_confidence": 43.0,
                "name_low_confidence_min_support": 2,
                "expected_candidates": 5,
            }
        )

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, ["Aero", "AJAR", "Massith", "Mika", "MNKE"])
        self.assertIn("MNKE", merged_text)
        self.assertIsNone(error)

    def test_extract_names_precount_rows_soft_cap_allows_plus_one_without_stable_primary(self):
        outputs = [
            "Alpha\nBravo\nCharlie\nDelta",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                text = outputs.pop(0) if outputs else ""
                lines = [
                    SimpleNamespace(text="Alpha", confidence=88.0),
                    SimpleNamespace(text="Bravo", confidence=84.0),
                    SimpleNamespace(text="Charlie", confidence=82.0),
                    SimpleNamespace(text="Delta", confidence=80.0),
                ]
                return SimpleNamespace(text=text, error=None, lines=lines)

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                return real_ocr_import.extract_candidate_names(text, **kwargs)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                return real_ocr_import.extract_candidate_names_multi(texts, **kwargs)

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": False,
                "name_confidence_filter_noisy_only": False,
                "name_min_confidence": 0.0,
                "name_low_confidence_min_support": 1,
                "expected_candidates": 5,
            }
        )

        with (
            patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
            patch("controller.ocr.ocr_capture_ops._estimate_expected_rows_from_paths", return_value=3),
        ):
            names, _merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, ["Alpha", "Bravo", "Charlie", "Delta"])
        self.assertIsNone(error)

    def test_extract_names_precount_stable_rows_do_not_refill_duplicate_tail(self):
        primary_names = [
            "Line1",
            "Line2",
            "Line3",
            "Line4",
            "Line5",
            "Line6",
            "NoiseTail",
        ]
        line_entries = [
            {"text": "Line1", "conf": 90.0},
            {"text": "Line2", "conf": 90.0},
            {"text": "Line3", "conf": 90.0},
            {"text": "Line4", "conf": 90.0},
            {"text": "Line5", "conf": 90.0},
            {"text": "Line6", "conf": 90.0},
        ]
        primary_runs = [
            {"pass": "primary", "image": "a.png", "lines": list(line_entries), "text": "\n".join(primary_names[:6])},
            {"pass": "primary", "image": "b.png", "lines": list(line_entries), "text": "\n".join(primary_names[:6])},
        ]
        stats: dict[str, dict[str, float | int | str]] = {}
        for idx, name in enumerate(primary_names, start=1):
            key = ocr_capture_ops._simple_name_key(name)
            if not key:
                continue
            stats[key] = {
                "display": name,
                "support": 2 if idx <= 6 else 1,
                "occurrences": 2 if idx <= 6 else 1,
                "best_conf": 80.0 if idx <= 6 else 35.0,
            }

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": False,
                "name_confidence_filter_noisy_only": True,
            }
        )

        with (
            patch("controller.ocr.ocr_capture_ops._estimate_expected_rows_from_paths", return_value=7),
            patch(
                "controller.ocr.ocr_capture_ops._run_ocr_pass",
                return_value=(["\n".join(primary_names[:6])], [], primary_runs),
            ),
            patch("controller.ocr.ocr_capture_ops._extract_names_from_texts", return_value=list(primary_names)),
            patch("controller.ocr.ocr_capture_ops._candidate_stats_from_runs", return_value=dict(stats)),
            patch("controller.ocr.ocr_capture_ops._build_final_names_from_runs", return_value=list(primary_names)),
            patch(
                "controller.ocr.ocr_capture_ops._filter_low_confidence_candidates",
                side_effect=lambda names, *_args, **_kwargs: list(names),
            ),
            patch(
                "controller.ocr.ocr_capture_ops._order_names_by_line_trace",
                side_effect=lambda names, *_args, **_kwargs: list(names),
            ),
            patch(
                "controller.ocr.ocr_capture_ops._expand_config_identifier_prefixes",
                side_effect=lambda names: list(names),
            ),
        ):
            names, _merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, primary_names[:6])
        self.assertNotIn("NoiseTail", names)
        self.assertIsNone(error)

    def test_extract_names_refill_reorders_by_trace_instead_of_appending_tail(self):
        primary_names = ["Line1", "Line2", "Line3", "Line4", "Line5", "Line6"]
        primary_runs = [
            {
                "pass": "primary",
                "image": "a.png",
                "lines": [
                    {"text": "Line1", "conf": 95.0},
                    {"text": "Line2", "conf": 95.0},
                    {"text": "Line3", "conf": 95.0},
                    {"text": "Line4", "conf": 95.0},
                    {"text": "Line5", "conf": 95.0},
                    {"text": "Line6", "conf": 95.0},
                ],
                "text": "\n".join(primary_names),
            },
            {
                "pass": "primary",
                "image": "b.png",
                "lines": [
                    {"text": "Line1", "conf": 95.0},
                    {"text": "Line2", "conf": 95.0},
                    {"text": "Line3", "conf": 95.0},
                    {"text": "Line4", "conf": 95.0},
                    {"text": "Line5", "conf": 95.0},
                    {"text": "Line6", "conf": 95.0},
                ],
                "text": "\n".join(primary_names),
            },
        ]
        stats: dict[str, dict[str, float | int | str]] = {}
        for name in primary_names:
            key = ocr_capture_ops._simple_name_key(name)
            if not key:
                continue
            stats[key] = {
                "display": name,
                "support": 2,
                "occurrences": 2,
                "best_conf": 90.0,
            }

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": False,
                "name_confidence_filter_noisy_only": True,
                "expected_candidates": 6,
            }
        )

        def _candidate_stats_with_trace(_runs, _parse_ctx, *, trace_entries=None, include_debug_meta=False):
            del _runs, _parse_ctx, include_debug_meta
            if trace_entries is not None:
                for idx, name in enumerate(primary_names, start=1):
                    trace_entries.append(
                        {
                            "pass": "primary",
                            "run_index": 1,
                            "line_index": idx,
                            "selected_key": ocr_capture_ops._simple_name_key(name),
                            "support_incremented": True,
                        }
                    )
            return dict(stats)

        with (
            patch("controller.ocr.ocr_capture_ops._estimate_expected_rows_from_paths", return_value=6),
            patch(
                "controller.ocr.ocr_capture_ops._run_ocr_pass",
                return_value=(["\n".join(primary_names)], [], primary_runs),
            ),
            patch("controller.ocr.ocr_capture_ops._extract_names_from_texts", return_value=list(primary_names)),
            patch(
                "controller.ocr.ocr_capture_ops._candidate_stats_from_runs",
                side_effect=_candidate_stats_with_trace,
            ),
            patch(
                "controller.ocr.ocr_capture_ops._build_final_names_from_runs",
                return_value=["Line1", "Line3", "Line4", "Line5", "Line6"],
            ),
            patch(
                "controller.ocr.ocr_capture_ops._filter_low_confidence_candidates",
                side_effect=lambda names, *_args, **_kwargs: list(names),
            ),
            patch(
                "controller.ocr.ocr_capture_ops._expand_config_identifier_prefixes",
                side_effect=lambda names: list(names),
            ),
        ):
            names, _merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, ["Line1", "Line2", "Line3", "Line4", "Line5", "Line6"])
        self.assertIsNone(error)

    def test_extract_names_precount_clamp_keeps_middle_line_after_slot_duplicate_collapse(self):
        primary_names = ["Line1", "flatiqz", "Line3", "Line4", "Line5", "Line6", "yukino"]
        primary_runs = [
            {
                "pass": "primary",
                "image": "a.png",
                "lines": [
                    {"text": "Line1", "conf": 95.0},
                    {"text": "flatiqz", "conf": 60.0},
                    {"text": "Line3", "conf": 95.0},
                    {"text": "Line4", "conf": 95.0},
                    {"text": "Line5", "conf": 95.0},
                    {"text": "Line6", "conf": 95.0},
                    {"text": "yukino", "conf": 95.0},
                ],
                "text": "\n".join(primary_names),
            },
            {
                "pass": "primary",
                "image": "b.png",
                "lines": [
                    {"text": "Line1", "conf": 95.0},
                    {"text": "flatiqz", "conf": 60.0},
                    {"text": "Line3", "conf": 95.0},
                    {"text": "Line4", "conf": 95.0},
                    {"text": "Line5", "conf": 95.0},
                    {"text": "Line6", "conf": 95.0},
                    {"text": "yukino", "conf": 95.0},
                ],
                "text": "\n".join(primary_names),
            },
        ]
        stats: dict[str, dict[str, float | int | str]] = {
            "line1": {"display": "Line1", "support": 2, "occurrences": 2, "best_conf": 95.0},
            "flatiqz": {"display": "flatiqz", "support": 1, "occurrences": 2, "best_conf": 60.0},
            "line3": {"display": "Line3", "support": 2, "occurrences": 2, "best_conf": 95.0},
            "line4": {"display": "Line4", "support": 2, "occurrences": 2, "best_conf": 95.0},
            "line5": {"display": "Line5", "support": 2, "occurrences": 2, "best_conf": 95.0},
            "line6": {"display": "Line6", "support": 2, "occurrences": 2, "best_conf": 95.0},
            "yukino": {"display": "yukino", "support": 2, "occurrences": 2, "best_conf": 95.0},
            "vukino": {"display": "vukino", "support": 1, "occurrences": 3, "best_conf": 97.0},
        }

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": False,
                "name_confidence_filter_noisy_only": True,
                "expected_candidates": 7,
            }
        )

        def _candidate_stats_with_trace(_runs, _parse_ctx, *, trace_entries=None, include_debug_meta=False):
            del _runs, _parse_ctx, include_debug_meta
            if trace_entries is not None:
                for idx, name in enumerate(primary_names, start=1):
                    trace_entries.append(
                        {
                            "pass": "primary",
                            "run_index": 1,
                            "line_index": idx,
                            "selected_key": ocr_capture_ops._simple_name_key(name),
                            "support_incremented": True,
                            "occurrence_incremented": True,
                        }
                    )
                trace_entries.append(
                    {
                        "pass": "row",
                        "run_index": 30,
                        "line_index": 1,
                        "image": "src#7[0:0]/name.base",
                        "selected_key": "vukino",
                        "support_incremented": True,
                        "occurrence_incremented": True,
                    }
                )
            return dict(stats)

        with (
            patch("controller.ocr.ocr_capture_ops._estimate_expected_rows_from_paths", return_value=7),
            patch(
                "controller.ocr.ocr_capture_ops._run_ocr_pass",
                return_value=(["\n".join(primary_names)], [], primary_runs),
            ),
            patch("controller.ocr.ocr_capture_ops._extract_names_from_texts", return_value=list(primary_names)),
            patch(
                "controller.ocr.ocr_capture_ops._candidate_stats_from_runs",
                side_effect=_candidate_stats_with_trace,
            ),
            patch(
                "controller.ocr.ocr_capture_ops._build_final_names_from_runs",
                return_value=["Line1", "flatiqz", "Line3", "Line4", "Line5", "Line6", "yukino", "vukino"],
            ),
            patch(
                "controller.ocr.ocr_capture_ops._filter_low_confidence_candidates",
                side_effect=lambda names, *_args, **_kwargs: list(names),
            ),
            patch(
                "controller.ocr.ocr_capture_ops._expand_config_identifier_prefixes",
                side_effect=lambda names: list(names),
            ),
        ):
            names, _merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, ["Line1", "flatiqz", "Line3", "Line4", "Line5", "Line6", "yukino"])
        self.assertIsNone(error)

    def test_extract_names_without_precount_rows_keeps_all_detected(self):
        outputs = [
            "Alpha\nBravo\nCharlie\nDelta",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                text = outputs.pop(0) if outputs else ""
                lines = [
                    SimpleNamespace(text="Alpha", confidence=88.0),
                    SimpleNamespace(text="Bravo", confidence=84.0),
                    SimpleNamespace(text="Charlie", confidence=82.0),
                    SimpleNamespace(text="Delta", confidence=80.0),
                ]
                return SimpleNamespace(text=text, error=None, lines=lines)

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                return real_ocr_import.extract_candidate_names(text, **kwargs)

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                return real_ocr_import.extract_candidate_names_multi(texts, **kwargs)

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": False,
                "name_confidence_filter_noisy_only": False,
                "name_min_confidence": 0.0,
                "name_low_confidence_min_support": 1,
                "expected_candidates": 5,
            }
        )

        with (
            patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
            patch("controller.ocr.ocr_capture_ops._estimate_expected_rows_from_paths", return_value=None),
        ):
            names, _merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, ["Alpha", "Bravo", "Charlie", "Delta"])
        self.assertIsNone(error)

    def test_extract_names_relaxed_line_fallback_recovers_missing_line(self):
        outputs = [
            "Aero\nAJAR\nMassith\nMika\nZeta | meta",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                text = outputs.pop(0) if outputs else ""
                lines = [
                    SimpleNamespace(text="Aero", confidence=88.0),
                    SimpleNamespace(text="AJAR", confidence=87.0),
                    SimpleNamespace(text="Massith", confidence=86.0),
                    SimpleNamespace(text="Mika", confidence=85.0),
                    SimpleNamespace(text="Zeta | meta", confidence=72.0),
                ]
                return SimpleNamespace(text=text, error=None, lines=lines)

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                value = str(text or "").strip()
                enforce_special = bool(kwargs.get("enforce_special_char_constraint", True))
                if value == "Zeta | meta":
                    return [] if enforce_special else ["Zeta"]
                if value:
                    return [value]
                return []

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                del kwargs
                # Simulate a multi-pass miss of the last line.
                return ["Aero", "AJAR", "Massith", "Mika"]

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": False,
                "line_relaxed_fallback": True,
                "expected_candidates": 5,
            }
        )

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertIn("Zeta", names)
        self.assertEqual(len(names), 5)
        self.assertIn("Zeta | meta", merged_text)
        self.assertIsNone(error)

    def test_extract_names_relaxed_line_fallback_when_strict_only_returns_noise(self):
        outputs = [
            "Aero\nAJAR\nMassith\nMika\nZeta | meta",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_ocr_multi(
                image_path,
                *,
                cmd,
                psm_values,
                timeout_s,
                lang,
                stop_on_first_success,
            ):
                text = outputs.pop(0) if outputs else ""
                lines = [
                    SimpleNamespace(text="Aero", confidence=88.0),
                    SimpleNamespace(text="AJAR", confidence=87.0),
                    SimpleNamespace(text="Massith", confidence=86.0),
                    SimpleNamespace(text="Mika", confidence=85.0),
                    SimpleNamespace(text="Zeta | meta", confidence=72.0),
                ]
                return SimpleNamespace(text=text, error=None, lines=lines)

            @staticmethod
            def extract_candidate_names(text, **kwargs):
                value = str(text or "").strip()
                enforce_special = bool(kwargs.get("enforce_special_char_constraint", True))
                if value == "Zeta | meta":
                    return ["TK"] if enforce_special else ["Zeta"]
                if value:
                    return [value]
                return []

            @staticmethod
            def extract_candidate_names_multi(texts, **kwargs):
                del kwargs
                return ["Aero", "AJAR", "Massith", "Mika"]

        cfg = self._ocr_cfg()
        cfg.update(
            {
                "recall_retry_enabled": False,
                "row_pass_enabled": False,
                "line_relaxed_fallback": True,
                "expected_candidates": 5,
            }
        )

        with patch("controller.ocr.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertIn("Zeta", names)
        self.assertEqual(len(names), 5)
        self.assertIn("Zeta | meta", merged_text)
        self.assertIsNone(error)

    def test_append_ocr_debug_log_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            settings = {
                "OCR_DEBUG_LOG_TO_FILE": True,
                "OCR_DEBUG_LOG_FILE": "ocr_debug.log",
                "LOG_OUTPUT_DIR": "logs",
                "OCR_DEBUG_LOG_MAX_CHARS": 0,
            }
            mw = SimpleNamespace(
                _cfg=lambda key, default=None: settings.get(key, default),
                _state_dir=state_dir,
                _log_dir=state_dir / "logs",
            )
            log_path = ocr_capture_ops._append_ocr_debug_log(
                mw,
                role="dps",
                names=["Aero", "Massith"],
                raw_text="[OCR Debug Report]\nparsed-candidates: Aero, Massith",
                ocr_error=None,
            )
            self.assertEqual(log_path, state_dir / "logs" / "ocr_debug.log")
            self.assertTrue((state_dir / "logs" / "ocr_debug.log").exists())
            content = (state_dir / "logs" / "ocr_debug.log").read_text(encoding="utf-8")
            self.assertIn("role=DPS", content)
            self.assertIn("candidates=2", content)
            self.assertIn("[OCR Debug Report]", content)

    def test_on_role_ocr_import_reenables_buttons_when_capture_is_cancelled(self):
        class _DummyButton:
            def __init__(self) -> None:
                self.enabled = True
                self.states: list[bool] = []

            def setEnabled(self, enabled: bool) -> None:
                self.enabled = bool(enabled)
                self.states.append(self.enabled)

        btn = _DummyButton()
        update_calls = {"count": 0}

        def _update_all_buttons() -> None:
            update_calls["count"] += 1
            btn.setEnabled(True)

        mw = SimpleNamespace(
            _role_ocr_import_available=lambda role_key: True,
            _ocr_async_job=None,
            _update_role_ocr_button_enabled=lambda role_key: btn.setEnabled(True),
            _update_role_ocr_buttons_enabled=_update_all_buttons,
            _role_ocr_buttons={"dps": btn},
        )

        with (
            patch("controller.ocr.ocr_capture_ops._mark_ocr_runtime_activated"),
            patch("controller.ocr.ocr_capture_ops._cancel_ocr_cache_release"),
            patch("controller.ocr.ocr_capture_ops.capture_region_for_ocr", return_value=(None, "cancelled")),
            patch("controller.ocr.ocr_capture_ops._handle_ocr_selection_error", return_value=True),
            patch("controller.ocr.ocr_capture_ops._schedule_ocr_cache_release") as schedule_mock,
        ):
            ocr_capture_ops.on_role_ocr_import_clicked(mw, "dps")

        self.assertIn(False, btn.states)
        self.assertTrue(btn.enabled)
        self.assertEqual(update_calls["count"], 1)
        schedule_mock.assert_called_once_with(mw)

    def test_show_ocr_busy_overlay_uses_status_message_style(self):
        class _DummyOverlay:
            def __init__(self) -> None:
                self.status_calls: list[tuple[str, list[str]]] = []
                self.enabled_values: list[bool] = []
                self._last_view = {}

            def show_status_message(self, title, lines):
                payload = (str(title), list(lines))
                self.status_calls.append(payload)
                self._last_view = {"type": "status_message", "data": payload}

            def setEnabled(self, enabled: bool):
                self.enabled_values.append(bool(enabled))

            def hide(self):
                return None

        overlay = _DummyOverlay()
        mw = SimpleNamespace(
            overlay=overlay,
            _ocr_role_display_name=lambda role_key: "DPS" if role_key == "dps" else role_key.upper(),
        )
        with patch(
            "controller.ocr.ocr_capture_ops.i18n.t",
            side_effect=lambda key, **kwargs: {
                "ocr.progress_title": "OCR in progress",
                "ocr.progress_line_wait": "Please wait...",
                "ocr.progress_line_all": "All roles",
                "ocr.progress_line_role": f"Role {kwargs.get('role', '')}",
            }.get(key, key),
        ):
            shown = ocr_capture_ops._show_ocr_busy_overlay(mw, "dps")

        self.assertTrue(shown)
        self.assertEqual(len(overlay.status_calls), 1)
        self.assertEqual(overlay.status_calls[0][0], "OCR in progress")
        self.assertEqual(overlay.enabled_values, [False])

    def test_hide_ocr_busy_overlay_hides_only_matching_status_view(self):
        class _DummyOverlay:
            def __init__(self) -> None:
                self.enabled_values: list[bool] = []
                self.hide_calls = 0
                self._last_view = {
                    "type": "status_message",
                    "data": ("OCR in progress", ["line1", "line2"]),
                }

            def setEnabled(self, enabled: bool):
                self.enabled_values.append(bool(enabled))

            def hide(self):
                self.hide_calls += 1

        overlay = _DummyOverlay()
        mw = SimpleNamespace(overlay=overlay)
        with patch(
            "controller.ocr.ocr_capture_ops.i18n.t",
            side_effect=lambda key, **kwargs: "OCR in progress" if key == "ocr.progress_title" else key,
        ):
            ocr_capture_ops._hide_ocr_busy_overlay(mw, active=True)

        self.assertEqual(overlay.enabled_values, [True])
        self.assertEqual(overlay.hide_calls, 1)


if __name__ == "__main__":
    unittest.main()
