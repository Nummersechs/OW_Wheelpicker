from __future__ import annotations

import os
import sys
from pathlib import Path


def _resolve_model_dir(project_root: Path) -> str:
    env_value = str(os.environ.get("OW_EASYOCR_MODEL_DIR", "")).strip()
    if env_value:
        return env_value
    return str(project_root / "EasyOCR" / "model")


def _resolve_lang_value(config_module) -> str:
    env_value = str(os.environ.get("OW_EASYOCR_LANG", "")).strip()
    if env_value:
        return env_value
    return str(getattr(config_module, "OCR_EASYOCR_LANG", "en") or "en")


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    import config  # pylint: disable=import-error
    from controller.ocr import ocr_import  # pylint: disable=import-error
    import easyocr  # type: ignore

    model_dir = _resolve_model_dir(project_root)
    Path(model_dir).mkdir(parents=True, exist_ok=True)

    lang_value = _resolve_lang_value(config)
    langs = ocr_import._parse_easyocr_langs(lang_value)
    groups = ocr_import._build_easyocr_lang_groups(langs)

    print(f"Configured OCR langs: {','.join(langs)}")
    print(f"EasyOCR preload groups: {groups}")
    print(f"Model dir: {model_dir}")

    for group in groups:
        print(f"Preloading group: {group}")
        easyocr.Reader(
            list(group),
            gpu=False,
            model_storage_directory=model_dir,
            download_enabled=True,
            verbose=False,
        )

    print("EasyOCR model preload complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
