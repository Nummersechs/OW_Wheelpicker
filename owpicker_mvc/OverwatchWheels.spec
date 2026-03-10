# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_data_files,
)


block_cipher = None

def _spec_root() -> Path:
    specpath = globals().get("SPECPATH") or globals().get("specpath")
    if specpath:
        path = Path(specpath)
        return path.parent if path.suffix == ".spec" else path
    spec_file = globals().get("__file__")
    if spec_file:
        return Path(spec_file).resolve().parent
    return Path.cwd()

project_root = _spec_root()
app_name = "OW_Wheelpicker"


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


BUILD_PROFILE = (os.environ.get("OW_BUILD_PROFILE") or "full").strip().lower()
MIN_SIZE_BUILD = BUILD_PROFILE in {"minsize", "min", "lite"}
RELEASE_BUILD = BUILD_PROFILE in {"release", "prod", "shipping"}
DIST_MODE_DEFAULT = "onedir" if os.name == "nt" else "onefile"
DIST_MODE = (os.environ.get("OW_DIST_MODE") or DIST_MODE_DEFAULT).strip().lower()
if DIST_MODE not in {"onefile", "onedir"}:
    raise SystemExit(
        "OW_DIST_MODE must be one of: onefile, onedir "
        f"(got: {DIST_MODE!r})"
    )
STRIP_BINARIES = _env_flag("OW_STRIP", (RELEASE_BUILD or MIN_SIZE_BUILD) and os.name != "nt")
if STRIP_BINARIES and shutil.which("strip") is None:
    print("[spec] strip requested but no 'strip' tool was found; disabling strip.")
    STRIP_BINARIES = False
# UPX can cause runtime instability with large torch/cv2 bundles in onefile builds.
# Keep it opt-in via OW_UPX=1.
ENABLE_UPX = _env_flag("OW_UPX", False)
INCLUDE_QT_MULTIMEDIA = not MIN_SIZE_BUILD
# Requests is optional (online sync only). Disable by default to keep runtime lean.
INCLUDE_REQUESTS = _env_flag("OW_INCLUDE_REQUESTS", False)
PRUNE_QT_RUNTIME = _env_flag("OW_PRUNE_QT", True)
OCR_ENGINE = (os.environ.get("OW_OCR_ENGINE") or "easyocr").strip().lower()
if OCR_ENGINE in {"easy", "easy-ocr", "easy_ocr"}:
    OCR_ENGINE = "easyocr"
if OCR_ENGINE != "easyocr":
    print(f"[spec] Unsupported OW_OCR_ENGINE={OCR_ENGINE!r}; forcing 'easyocr'.")
    OCR_ENGINE = "easyocr"
INCLUDE_EASYOCR = _env_flag("OW_INCLUDE_EASYOCR", True)
EASYOCR_HIDDENIMPORT_PROFILE = (os.environ.get("OW_EASYOCR_HIDDENIMPORT_PROFILE") or "minimal").strip().lower()
if EASYOCR_HIDDENIMPORT_PROFILE not in {"minimal", "full"}:
    EASYOCR_HIDDENIMPORT_PROFILE = "minimal"
LEGACY_OCR_BUNDLE_REQUESTED = _env_flag("OW_INCLUDE_OCR_BUNDLE", False)
if LEGACY_OCR_BUNDLE_REQUESTED:
    print("[spec] OW_INCLUDE_OCR_BUNDLE is obsolete and ignored (EasyOCR-only build).")
try:
    PY_OPTIMIZE_LEVEL = int(str(os.environ.get("OW_PY_OPTIMIZE", "0")).strip())
except Exception:
    PY_OPTIMIZE_LEVEL = 0
if PY_OPTIMIZE_LEVEL < 0:
    PY_OPTIMIZE_LEVEL = 0
if PY_OPTIMIZE_LEVEL > 2:
    PY_OPTIMIZE_LEVEL = 2
# Torch/EasyOCR can break under optimized bytecode in frozen builds
# (e.g. docstring/circular import issues). Force safe mode.
if INCLUDE_EASYOCR and PY_OPTIMIZE_LEVEL > 0:
    print(
        f"[spec] OW_PY_OPTIMIZE={PY_OPTIMIZE_LEVEL} is unsafe with EasyOCR/torch; "
        "forcing 0."
    )
    PY_OPTIMIZE_LEVEL = 0

_AUDIO_EXTENSIONS = {".wav", ".ogg", ".mp3"}
_EASYOCR_MODEL_HINTS = (
    Path("EasyOCR/model"),
    Path("easyocr/model"),
    Path("OCR/EasyOCR/model"),
    Path("ocr/easyocr/model"),
)


def _audio_datas(folder_name: str, target_name: str) -> list[tuple[str, str]]:
    folder = project_root / folder_name
    if not folder.exists() or not folder.is_dir():
        return []
    files = [
        p
        for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix.lower() in _AUDIO_EXTENSIONS
    ]
    if MIN_SIZE_BUILD:
        # In minsize builds we rely on QApplication.beep() fallback to keep the binary lean.
        files = []
    return [(str(p), target_name) for p in files]


def _unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.resolve()).lower()
        except Exception:
            key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _target_dir_for_relative(base_dir: Path, file_path: Path, root_target: str) -> str:
    try:
        rel_parent = file_path.relative_to(base_dir).parent
    except Exception:
        return root_target
    if str(rel_parent) in {"", "."}:
        return root_target
    return f"{root_target}/{rel_parent.as_posix()}"


def _easyocr_model_candidate_dirs() -> list[Path]:
    candidates: list[Path] = []
    env_path = str(os.environ.get("OW_EASYOCR_MODEL_DIR", "")).strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())

    for root in (project_root, project_root.parent):
        for rel in _EASYOCR_MODEL_HINTS:
            candidate = root / rel
            if candidate.exists() and candidate.is_dir():
                candidates.append(candidate)

    home_default = Path.home() / ".EasyOCR" / "model"
    if home_default.exists() and home_default.is_dir():
        candidates.append(home_default)
    return _unique_paths(candidates)


def _pick_easyocr_model_source_dir() -> Path | None:
    candidates = _easyocr_model_candidate_dirs()
    if not candidates:
        return None
    for candidate in candidates:
        try:
            if any(
                path.is_file() and path.suffix.lower() in {".pth", ".pt"}
                for path in candidate.rglob("*")
            ):
                return candidate
        except Exception:
            continue
    return None


def _collect_easyocr_model_datas(source_dir: Path) -> tuple[list[tuple[str, str]], int, int]:
    datas_local: list[tuple[str, str]] = []
    file_count = 0
    total_bytes = 0
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        target_dir = _target_dir_for_relative(source_dir, path, "EasyOCR/model")
        datas_local.append((str(path), target_dir))
        file_count += 1
        try:
            total_bytes += int(path.stat().st_size)
        except Exception:
            pass
    return datas_local, file_count, total_bytes


def _append_unique_toc_entries(target: list, entries: list) -> None:
    seen: set[tuple[str, str, str]] = set()
    for current in target:
        try:
            key = (
                str(current[0]),
                str(current[1]),
                str(current[2]) if len(current) > 2 else "",
            )
        except Exception:
            key = (str(current), "", "")
        seen.add(key)
    for entry in entries:
        try:
            key = (
                str(entry[0]),
                str(entry[1]),
                str(entry[2]) if len(entry) > 2 else "",
            )
        except Exception:
            key = (str(entry), "", "")
        if key in seen:
            continue
        seen.add(key)
        target.append(entry)


def _append_unique_strings(target: list[str], entries: list[str]) -> None:
    seen = {str(item).strip() for item in target if str(item).strip()}
    for entry in entries:
        value = str(entry).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        target.append(value)


datas = []
datas.extend(_audio_datas("Spin", "Spin"))
datas.extend(_audio_datas("Ding", "Ding"))
extra_binaries: list = []
extra_hiddenimports: list[str] = []

if INCLUDE_EASYOCR:
    print("[spec] EasyOCR bundle enabled.")
    if EASYOCR_HIDDENIMPORT_PROFILE == "full":
        easyocr_imports = [
            "easyocr",
            "easyocr.cli",
            "easyocr.config",
            "easyocr.craft_utils",
            "easyocr.detection",
            "easyocr.export",
            "easyocr.imgproc",
            "easyocr.model.model",
            "easyocr.model.vgg_model",
            "easyocr.recognition",
            "easyocr.utils",
            "torch",
            "torchvision",
            "cv2",
            "numpy",
            "PIL",
            "scipy",
            "skimage",
        ]
    else:
        # Minimal profile: rely on PyInstaller hooks (easyocr/torch/cv2/scipy).
        easyocr_imports = [
            "easyocr",
        ]
    _append_unique_strings(extra_hiddenimports, easyocr_imports)

    try:
        _append_unique_toc_entries(datas, list(collect_data_files("easyocr", include_py_files=False)))
    except Exception as exc:
        print(f"[spec] WARNING: failed to collect easyocr package data: {exc}")

    easyocr_model_source = _pick_easyocr_model_source_dir()
    if easyocr_model_source is not None:
        model_datas, model_count, model_bytes = _collect_easyocr_model_datas(easyocr_model_source)
        _append_unique_toc_entries(datas, model_datas)
        model_mb = model_bytes / (1024 * 1024)
        print(
            "[spec] EasyOCR model source: "
            f"{easyocr_model_source} ({model_count} files, ~{model_mb:.1f} MB)"
        )
    else:
        print(
            "[spec] WARNING: no EasyOCR model directory found. "
            "Set OW_EASYOCR_MODEL_DIR to bundle offline models."
        )

print(
    "[spec] Build profile="
    f"{BUILD_PROFILE} | dist_mode={DIST_MODE} | strip={STRIP_BINARIES} | upx={ENABLE_UPX} | "
    f"qt_multimedia={INCLUDE_QT_MULTIMEDIA} | requests={INCLUDE_REQUESTS} | "
    f"ocr_engine={OCR_ENGINE} | include_easyocr={INCLUDE_EASYOCR} | "
    f"easyocr_hiddenimports={EASYOCR_HIDDENIMPORT_PROFILE} | py_optimize={PY_OPTIMIZE_LEVEL}"
)

hiddenimports = [
    *(
        [
            "PySide6.QtMultimedia",
        ]
        if INCLUDE_QT_MULTIMEDIA
        else []
    ),
    *(
        [
            "requests",
        ]
        if INCLUDE_REQUESTS
        else []
    ),
]
_append_unique_strings(hiddenimports, extra_hiddenimports)

excludes = [
    "PySide6.QtConcurrent",
    "PySide6.QtDBus",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtGrpc",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtNetworkAuth",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtOpcUa",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtProtobuf",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQmlModels",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuick3DAssetImport",
    "PySide6.QtQuick3DAssetUtils",
    "PySide6.QtQuick3DEffects",
    "PySide6.QtQuick3DHelpers",
    "PySide6.QtQuick3DIblBaker",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtScript",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtStateMachineQml",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
    "PySide6.QtXml",
    "PySide6.QtXmlPatterns",
    # Optional ecosystems that are not needed for EasyOCR runtime.
    # Excluding these reduces noisy build warnings and avoids unnecessary baggage.
    "torch.utils.tensorboard",
    "tensorboard",
    "tensorflow",
    "tensorflow_estimator",
    "fsspec.conftest",
    "tkinter",
    "_tkinter",
    # Torch compile/ONNX stacks are not used by runtime OCR inference here.
    # Excluding them reduces hook probing noise and avoids unnecessary baggage.
    "torch._inductor",
    "torch._inductor.codecache",
    "torch._dynamo",
    "torch.onnx",
    "triton",
    "onnxruntime",
]
if MIN_SIZE_BUILD:
    excludes.append("PySide6.QtMultimedia")


_PRUNE_TOC_FRAGMENTS = (
    "/pyside6/qt/qml/",
    "/pyside6/qt/lib/qtwebengine",
    "/pyside6/qt/lib/qtpdf",
    "/pyside6/qt/lib/qtqml",
    "/pyside6/qt/lib/qtquick",
    "/pyside6/qt/lib/qtdesigner",
    "/pyside6/qt/lib/qt3d",
    "/pyside6/qt/lib/qtquick3d",
    "/pyside6/qt/plugins/qmltooling/",
    "/pyside6/qt/plugins/qmllint/",
    "/pyside6/qt/plugins/renderers/",
    "/pyside6/qt/plugins/sceneparsers/",
    "/pyside6/qt/plugins/assetimporters/",
    "/pyside6/qt/plugins/designer/",
    "/pyside6/qt/plugins/geoservices/",
    "/pyside6/qt/plugins/position/",
    "/pyside6/qt/plugins/canbus/",
    "/pyside6/qt/plugins/sensors/",
    "/pyside6/qt/plugins/texttospeech/",
    "/pyside6/qt/plugins/webview/",
    "/pyside6/qt/plugins/scxmldatamodel/",
    "/pyside6/qt/plugins/networkinformation/",
    "/pyside6/qt/plugins/renderplugins/",
)


def _norm_path(value) -> str:
    return str(value or "").replace("\\", "/").lower()


def _keep_toc_entry(entry) -> bool:
    candidates = []
    try:
        if len(entry) > 0:
            candidates.append(_norm_path(entry[0]))
        if len(entry) > 1:
            candidates.append(_norm_path(entry[1]))
    except Exception:
        return True
    for path in candidates:
        if any(fragment in path for fragment in _PRUNE_TOC_FRAGMENTS):
            return False
    return True

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=extra_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
    optimize=PY_OPTIMIZE_LEVEL,
)
if PRUNE_QT_RUNTIME:
    a.binaries[:] = [entry for entry in a.binaries if _keep_toc_entry(entry)]
    a.datas[:] = [entry for entry in a.datas if _keep_toc_entry(entry)]
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
if DIST_MODE == "onedir":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=app_name,
        debug=False,
        strip=STRIP_BINARIES,
        upx=ENABLE_UPX,
        console=False,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=STRIP_BINARIES,
        upx=ENABLE_UPX,
        name=app_name,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        name=app_name,
        debug=False,
        strip=STRIP_BINARIES,
        upx=ENABLE_UPX,
        console=False,
    )
