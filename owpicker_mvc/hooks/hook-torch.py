"""Project-local PyInstaller hook for torch.

This replaces the contrib hook for our build so we can keep EasyOCR runtime
support while avoiding optional torch stacks (distributed/onnx/inductor/test)
that trigger noisy build-time warnings on Windows.
"""

from __future__ import annotations

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    copy_metadata,
)

_EXCLUDED_PREFIXES = [
    "torch.distributed",
    "torch.onnx",
    "torch._inductor",
    "torch._dynamo",
    "torch.testing",
    "torch.utils.tensorboard",
]


# Keep torch runtime binaries and package metadata.
binaries = collect_dynamic_libs("torch")
datas = copy_metadata("torch")
datas += collect_data_files(
    "torch",
    excludes=[
        "**/test/**",
        "**/tests/**",
        "**/include/**",
    ],
)

# Keep hidden imports intentionally small. EasyOCR imports these directly.
# Pulling every torch submodule causes large optional import trees and noisy
# PyInstaller warning files without runtime benefit for our use case.
hiddenimports = [
    "torch",
    "torch.backends.cudnn",
    "torch.utils.data",
    "torch.nn.functional",
    "torch.autograd",
    "torchvision",
    "torchvision.transforms",
]

excludedimports = [
    *_EXCLUDED_PREFIXES,
    "tensorboard",
    "tensorflow",
    "onnxruntime",
    "onnxscript",
    "pandas",
    "cupy",
    "cupyx",
    "matplotlib",
    "pytest",
    "psutil",
    "sphinx",
    "uarray",
    "sparse",
    "scikits",
    "sksparse",
    "cffi",
]
