from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore


class _OCRExtractWorker(QtCore.QObject):
    finished = QtCore.Signal(list, str, object)
    failed = QtCore.Signal(str)

    def __init__(self, paths: list[Path], cfg: dict, *, extract_names_fn):
        super().__init__()
        self._paths = [Path(p) for p in paths]
        self._cfg = dict(cfg)
        self._extract_names_fn = extract_names_fn

    @QtCore.Slot()
    def run(self) -> None:
        try:
            names, raw_text, error = self._extract_names_fn(
                self._paths,
                ocr_cmd="",
                cfg=self._cfg,
            )
        except Exception as exc:
            self.failed.emit(repr(exc))
            return
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
