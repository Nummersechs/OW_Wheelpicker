"""Project-local PyInstaller hook for torchvision.

Keeps runtime-safe OCR dependencies for EasyOCR by ensuring torchvision source
files are available and ONNX registration helpers are present.
"""

from __future__ import annotations

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

datas = copy_metadata("torchvision")
datas += collect_data_files("torchvision", include_py_files=False)
binaries = collect_dynamic_libs("torchvision")

hiddenimports = [
    "torchvision._C",
    "torchvision.extension",
    "torchvision.transforms",
    "torchvision.ops",
    "torchvision.ops._register_onnx_ops",
    "torchvision.io.image",
    "torch.onnx",
    "torch.onnx.symbolic_helper",
    "torch.onnx.symbolic_opset11",
]

module_collection_mode = {
    "torchvision": "pyz+py",
}
