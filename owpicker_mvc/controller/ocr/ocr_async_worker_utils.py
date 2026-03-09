from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore

from . import ocr_runtime_trace as _ocr_runtime_trace


class _OCRExtractWorker(QtCore.QObject):
    finished = QtCore.Signal(list, str, object)
    failed = QtCore.Signal(str)

    def __init__(self, paths: list[Path], cfg: dict, *, extract_names_fn):
        super().__init__()
        self._paths = [Path(p) for p in paths]
        self._cfg = dict(cfg)
        self._extract_names_fn = extract_names_fn
        self._cancel_requested = False

    @QtCore.Slot()
    def cancel(self) -> None:
        self._cancel_requested = True

    def _is_cancelled(self) -> bool:
        if self._cancel_requested:
            return True
        thread = self.thread()
        if thread is None:
            return False
        try:
            return bool(thread.isInterruptionRequested())
        except Exception:
            return False

    @QtCore.Slot()
    def run(self) -> None:
        _ocr_runtime_trace.trace(
            "ocr_extract_worker:start",
            files=len(list(self._paths or [])),
            lang=self._cfg.get("easyocr_lang"),
        )

        if self._is_cancelled():
            _ocr_runtime_trace.trace("ocr_extract_worker:cancelled_before_start")
            self.failed.emit("cancelled")
            return

        try:
            names, raw_text, error = self._extract_names_fn(
                self._paths,
                ocr_cmd="",
                cfg=self._cfg,
                cancel_check=self._is_cancelled,   # neu
            )
        except TypeError:
            # Fallback, falls noch nicht überall umgestellt
            try:
                names, raw_text, error = self._extract_names_fn(
                    self._paths,
                    ocr_cmd="",
                    cfg=self._cfg,
                )
            except Exception as exc:
                _ocr_runtime_trace.trace("ocr_extract_worker:error", error=repr(exc))
                self.failed.emit(repr(exc))
                return
        except Exception as exc:
            _ocr_runtime_trace.trace("ocr_extract_worker:error", error=repr(exc))
            self.failed.emit(repr(exc))
            return

        if self._is_cancelled():
            _ocr_runtime_trace.trace("ocr_extract_worker:cancelled_after_extract")
            self.failed.emit("cancelled")
            return

        _ocr_runtime_trace.trace(
            "ocr_extract_worker:done",
            names=len(list(names or [])),
            has_error=bool(error),
            error=str(error or ""),
        )
        self.finished.emit(names, raw_text, error)


class _OCRResultRelay(QtCore.QObject):
    """Relay worker results into the GUI thread."""

    result = QtCore.Signal(list, str, object)
    error = QtCore.Signal(str)

    @QtCore.Slot(list, str, object)
    def forward_result(self, names: list[str], raw_text: str, ocr_error: object) -> None:
        self.result.emit(names, raw_text, ocr_error)

    @QtCore.Slot(str)
    def forward_error(self, reason: str) -> None:
        self.error.emit(reason)
