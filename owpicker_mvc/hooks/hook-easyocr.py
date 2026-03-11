"""Project-local PyInstaller hook for easyocr.

Goal: keep OCR runtime stable on frozen Windows builds by collecting
transitive EasyOCR modules and forcing source availability for modules that
rely on inspect/getsource style introspection.
"""

from __future__ import annotations

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

datas = copy_metadata("easyocr")
datas += collect_data_files("easyocr", include_py_files=False)

# EasyOCR imports several modules dynamically (including model backends).
# Collect submodules defensively to avoid runtime misses in frozen builds.
hiddenimports = collect_submodules("easyocr")
hiddenimports += [
    "bidi",
    "bidi.algorithm",
    "yaml",
    "yaml.loader",
    "yaml.dumper",
    "cv2",
    "numpy",
    "scipy",
    "scipy.ndimage",
    "PIL",
    "PIL.Image",
]

module_collection_mode = {
    "easyocr": "pyz+py",
}
