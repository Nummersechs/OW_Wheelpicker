import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from controller.ocr_capture_ops import capture_region_for_ocr
import controller.ocr_capture_ops as ocr_capture_ops
import controller.ocr_import as real_ocr_import


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
            patch("controller.ocr_capture_ops.select_region_from_primary_screen", return_value=("pix", None)) as select_mock,
            patch("controller.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
            patch("controller.ocr_capture_ops.qt_runtime.safe_raise") as raise_mock,
            patch("controller.ocr_capture_ops.qt_runtime.safe_activate_window") as activate_mock,
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
            patch("controller.ocr_capture_ops.select_region_from_primary_screen", return_value=("pix", None)) as select_mock,
            patch("controller.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
            patch("controller.ocr_capture_ops.qt_runtime.safe_raise") as raise_mock,
            patch("controller.ocr_capture_ops.qt_runtime.safe_activate_window") as activate_mock,
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
            patch("controller.ocr_capture_ops.select_region_from_primary_screen", return_value=("pix", None)),
            patch("controller.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
            patch("controller.ocr_capture_ops.qt_runtime.safe_raise") as raise_mock,
            patch("controller.ocr_capture_ops.qt_runtime.safe_activate_window") as activate_mock,
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
            patch("controller.ocr_capture_ops.sys.platform", "win32"),
            patch("controller.ocr_capture_ops.select_region_from_primary_screen", return_value=("pix", None)) as select_mock,
            patch("controller.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
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
            patch("controller.ocr_capture_ops.sys.platform", "win32"),
            patch("controller.ocr_capture_ops.select_region_from_primary_screen", return_value=("pix", None)) as select_mock,
            patch("controller.ocr_capture_ops.QtWidgets.QApplication.processEvents"),
        ):
            result = capture_region_for_ocr(mw)

        self.assertEqual(result, ("pix", None))
        self.assertFalse(select_mock.call_args.kwargs.get("auto_accept_on_release"))

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

    def test_extract_names_runs_retry_when_fast_mode_finds_too_few(self):
        calls: list[dict] = []
        outputs = [
            "A\nB\nC\nD",
            "A\nB\nC\nD\nE",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_tesseract_multi(
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

        with patch("controller.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
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
            def run_tesseract_multi(
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

        with patch("controller.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=self._ocr_cfg(),
            )

        self.assertEqual(names, ["Alpha", "Bravo", "Charlie", "Delta", "Echo"])
        self.assertIn("Echo", merged_text)
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
            def run_tesseract_multi(
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

        with patch("controller.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=self._ocr_cfg(),
            )

        self.assertEqual(names, ["A", "B", "C", "D", "Massith"])
        self.assertIn("D", merged_text)
        self.assertIsNone(error)
        self.assertEqual(len(calls), 2)

    def test_extract_names_prefers_retry_when_primary_has_too_many_candidates(self):
        calls: list[dict] = []
        outputs = [
            "Aero\nBAO\nBar\nMNKE\nHOY\nPw\nHO\nB w\nHD",
            "Aero\nAJAR\nMassith\nMika\nMoonbrew",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_tesseract_multi(
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

        with patch("controller.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
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
            def run_tesseract_multi(
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

        with patch("controller.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
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
            def run_tesseract_multi(
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

        with patch("controller.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
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
            def run_tesseract_multi(
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
            patch("controller.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()),
            patch(
                "controller.ocr_capture_ops._run_row_segmentation_pass",
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

    def test_extract_names_filters_low_confidence_singletons(self):
        outputs = [
            "Aero\nAJAR\nMassith\nMika\nMNKE",
        ]

        class _StubOCRImport:
            @staticmethod
            def run_tesseract_multi(
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

        with patch("controller.ocr_capture_ops._ocr_import_module", return_value=_StubOCRImport()):
            names, merged_text, error = ocr_capture_ops._extract_names_from_ocr_files(
                [Path("dummy.png")],
                ocr_cmd="auto",
                cfg=cfg,
            )

        self.assertEqual(names, ["Aero", "AJAR", "Massith", "Mika"])
        self.assertIn("MNKE", merged_text)
        self.assertIsNone(error)

    def test_append_ocr_debug_log_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            settings = {
                "OCR_DEBUG_LOG_TO_FILE": True,
                "OCR_DEBUG_LOG_FILE": "ocr_debug.log",
                "OCR_DEBUG_LOG_MAX_CHARS": 0,
            }
            mw = SimpleNamespace(
                _cfg=lambda key, default=None: settings.get(key, default),
                _state_dir=state_dir,
            )
            log_path = ocr_capture_ops._append_ocr_debug_log(
                mw,
                role="dps",
                names=["Aero", "Massith"],
                raw_text="[OCR Debug Report]\nparsed-candidates: Aero, Massith",
                ocr_error=None,
            )
            self.assertEqual(log_path, state_dir / "ocr_debug.log")
            self.assertTrue((state_dir / "ocr_debug.log").exists())
            content = (state_dir / "ocr_debug.log").read_text(encoding="utf-8")
            self.assertIn("role=DPS", content)
            self.assertIn("candidates=2", content)
            self.assertIn("[OCR Debug Report]", content)

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
            "controller.ocr_capture_ops.i18n.t",
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
            "controller.ocr_capture_ops.i18n.t",
            side_effect=lambda key, **kwargs: "OCR in progress" if key == "ocr.progress_title" else key,
        ):
            ocr_capture_ops._hide_ocr_busy_overlay(mw, active=True)

        self.assertEqual(overlay.enabled_values, [True])
        self.assertEqual(overlay.hide_calls, 1)


if __name__ == "__main__":
    unittest.main()
