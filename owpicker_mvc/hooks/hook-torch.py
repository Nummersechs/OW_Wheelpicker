"""Project-local PyInstaller hook for torch.

This replaces the contrib hook for our build so we can keep EasyOCR runtime
support while avoiding optional torch compile stacks (inductor) that trigger
noisy build-time warnings on Windows.
"""

from __future__ import annotations

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

_EXCLUDED_PREFIXES = [
    "torch.utils.tensorboard",
]

# Torch 2.x can call inspect.getsource() while importing internals.
# Frozen pyz-only modules can cause "could not get source code" on Windows.
# Keep source files alongside bytecode for torch/torchvision to avoid that.
module_collection_mode = {
    "torch": "pyz+py",
    "torchvision": "pyz+py",
}


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
    "torch.nn",
    "torch.nn.modules",
    "torch.distributed",
    "torch.distributed.rpc",
    "torch.backends.cudnn",
    "torch.utils.data",
    "torch.nn.functional",
    "torch.autograd",
    "torch._dynamo",
    "torch._dynamo.polyfills",
    "torch._dynamo.polyfills.fx",
    # Some torch versions import these dynamically during startup.
    "torch._inductor",
    "torch._inductor.test_operators",
]

# Frozen Windows builds can miss dynamic torch namespace imports if they are
# reached only through lazy runtime paths. Pull relevant trees proactively.
hiddenimports += collect_submodules("torch._dynamo")
hiddenimports += collect_submodules("torch._dynamo.polyfills")
hiddenimports += collect_submodules("torch._inductor")

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
