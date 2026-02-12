import unittest
from unittest.mock import patch

from controller.ocr_capture_ops import capture_region_for_ocr


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


if __name__ == "__main__":
    unittest.main()
