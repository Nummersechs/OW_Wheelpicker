#!/usr/bin/env python3
"""Preflight probe for OCR runtime dependencies.

Run this before packaging to fail fast when critical OCR import chains are
broken in the current Python environment.
"""

from __future__ import annotations

import importlib
import sys


CRITICAL_MODULES = [
    "easyocr",
    "easyocr.easyocr",
    "easyocr.recognition",
    "easyocr.detection",
    "torch",
    "torch.nn",
    "torch.autograd",
    "torch.onnx",
    "torch.onnx.symbolic_helper",
    "torchvision",
    "torchvision.transforms",
    "torchvision.ops",
    "torchvision.ops._register_onnx_ops",
]


def _version_or_dash(module_name: str) -> str:
    try:
        mod = importlib.import_module(module_name)
    except Exception:
        return "-"
    return str(getattr(mod, "__version__", "-"))


def main() -> int:
    print("[ocr-probe] python:", sys.version.split()[0])
    print("[ocr-probe] easyocr:", _version_or_dash("easyocr"))
    print("[ocr-probe] torch:", _version_or_dash("torch"))
    print("[ocr-probe] torchvision:", _version_or_dash("torchvision"))

    failed: list[tuple[str, str]] = []
    for module_name in CRITICAL_MODULES:
        try:
            importlib.import_module(module_name)
            print(f"[ocr-probe] OK     {module_name}")
        except Exception as exc:  # noqa: BLE001 - probe should continue and report all failures
            failed.append((module_name, repr(exc)))
            print(f"[ocr-probe] FAILED {module_name}: {exc!r}")

    if failed:
        print("[ocr-probe] Result: FAILED")
        return 1
    print("[ocr-probe] Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
