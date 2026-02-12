# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path


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

BUILD_PROFILE = (os.environ.get("OW_BUILD_PROFILE") or "full").strip().lower()
MIN_SIZE_BUILD = BUILD_PROFILE in {"minsize", "min", "lite"}
STRIP_BINARIES = str(os.environ.get("OW_STRIP", "0")).strip().lower() in {"1", "true", "yes", "on"}
ENABLE_UPX = str(os.environ.get("OW_UPX", "1")).strip().lower() not in {"0", "false", "no", "off"}
INCLUDE_QT_MULTIMEDIA = not MIN_SIZE_BUILD
INCLUDE_REQUESTS = str(os.environ.get("OW_INCLUDE_REQUESTS", "1")).strip().lower() not in {"0", "false", "no", "off"}
PRUNE_QT_RUNTIME = str(os.environ.get("OW_PRUNE_QT", "1")).strip().lower() not in {"0", "false", "no", "off"}
INCLUDE_OCR_BUNDLE = str(os.environ.get("OW_INCLUDE_OCR_BUNDLE", "1")).strip().lower() not in {"0", "false", "no", "off"}

_AUDIO_EXTENSIONS = {".wav", ".ogg", ".mp3"}
_OCR_FOLDER_NAMES = ("OCR", "ocr", "Tesseract-OCR", "Tesseract", "tesseract")
_OCR_EXECUTABLE_NAMES = ("tesseract.exe", "tesseract")
_OCR_EXTERNAL_DIR_ENV_VARS = ("OW_TESSERACT_DIR", "TESSERACT_ROOT")
_WINDOWS_TESSERACT_DIR_CANDIDATES = (
    Path("C:/Program Files/Tesseract-OCR"),
    Path("C:/Program Files (x86)/Tesseract-OCR"),
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


def _external_ocr_candidate_dirs() -> list[Path]:
    candidates: list[Path] = []
    for env_name in _OCR_EXTERNAL_DIR_ENV_VARS:
        value = str(os.environ.get(env_name, "")).strip()
        if value:
            candidates.append(Path(value).expanduser())
    if os.name == "nt":
        candidates.extend(_WINDOWS_TESSERACT_DIR_CANDIDATES)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except Exception:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _existing_external_ocr_dirs() -> list[Path]:
    return [candidate for candidate in _external_ocr_candidate_dirs() if candidate.exists() and candidate.is_dir()]


def _append_ocr_source(
    datas_local: list[tuple[str, str]],
    source_dirs: list[Path],
    seen_sources: set[str],
    folder: Path,
    target_name: str,
) -> None:
    if not folder.exists() or not folder.is_dir():
        return
    try:
        key = str(folder.resolve()).lower()
    except Exception:
        key = str(folder).lower()
    if key in seen_sources:
        return
    seen_sources.add(key)
    datas_local.append((str(folder), target_name))
    source_dirs.append(folder)


def _collect_ocr_datas() -> tuple[list[tuple[str, str]], list[Path]]:
    datas_local: list[tuple[str, str]] = []
    source_dirs: list[Path] = []
    seen_sources: set[str] = set()
    # Accept both locations:
    # - alongside this spec (owpicker_mvc/)
    # - repo root (parent of owpicker_mvc/)
    candidate_roots = [project_root, project_root.parent]
    for root in candidate_roots:
        for folder_name in _OCR_FOLDER_NAMES:
            folder = root / folder_name
            _append_ocr_source(datas_local, source_dirs, seen_sources, folder, folder_name)

    # Allow bundling directly from system install folders on Windows, so a local OCR copy is optional.
    for folder in _existing_external_ocr_dirs():
        _append_ocr_source(datas_local, source_dirs, seen_sources, folder, "OCR")
    return datas_local, source_dirs


def _bundle_contains_tesseract_executable(source_dirs: list[Path]) -> bool:
    for src in source_dirs:
        for name in _OCR_EXECUTABLE_NAMES:
            try:
                if any(candidate.is_file() for candidate in src.rglob(name)):
                    return True
            except Exception:
                continue
    return False


def _bundle_contains_traineddata(source_dirs: list[Path]) -> bool:
    for src in source_dirs:
        try:
            if any(candidate.is_file() for candidate in src.rglob("*.traineddata")):
                return True
        except Exception:
            continue
    return False


def _ocr_bundle_stats(source_dirs: list[Path]) -> tuple[int, int, list[str]]:
    file_count = 0
    total_bytes = 0
    traineddata_files: list[str] = []
    for src in source_dirs:
        try:
            for candidate in src.rglob("*"):
                if not candidate.is_file():
                    continue
                file_count += 1
                try:
                    total_bytes += int(candidate.stat().st_size)
                except Exception:
                    pass
                if candidate.suffix.lower() == ".traineddata":
                    traineddata_files.append(candidate.name)
        except Exception:
            continue
    traineddata_files = sorted(set(traineddata_files))
    return file_count, total_bytes, traineddata_files


datas = []
datas.extend(_audio_datas("Spin", "Spin"))
datas.extend(_audio_datas("Ding", "Ding"))
if INCLUDE_OCR_BUNDLE:
    ocr_datas, ocr_source_dirs = _collect_ocr_datas()
    if not ocr_datas:
        roots = [str(project_root), str(project_root.parent)]
        external_candidates = [str(p) for p in _external_ocr_candidate_dirs()]
        expected = ", ".join(_OCR_FOLDER_NAMES)
        raise SystemExit(
            "OW_INCLUDE_OCR_BUNDLE=1 but no OCR bundle folder was found.\n"
            f"Searched roots: {roots}\n"
            f"Searched external dirs: {external_candidates}\n"
            f"Expected one of: {expected}"
        )
    if not _bundle_contains_tesseract_executable(ocr_source_dirs):
        raise SystemExit(
            "OW_INCLUDE_OCR_BUNDLE=1 but no tesseract executable was found in OCR bundle.\n"
            f"Searched dirs: {[str(p) for p in ocr_source_dirs]}"
        )
    if not _bundle_contains_traineddata(ocr_source_dirs):
        raise SystemExit(
            "OW_INCLUDE_OCR_BUNDLE=1 but no tessdata (*.traineddata) was found in OCR bundle.\n"
            f"Searched dirs: {[str(p) for p in ocr_source_dirs]}"
        )
    datas.extend(ocr_datas)
    print("[spec] OCR bundle enabled. Included source dirs:")
    for src in ocr_source_dirs:
        print(f"[spec]   - {src}")
    file_count, total_bytes, traineddata_files = _ocr_bundle_stats(ocr_source_dirs)
    size_mb = total_bytes / (1024 * 1024)
    print(f"[spec] OCR bundle files: {file_count} (total ~{size_mb:.1f} MB)")
    if traineddata_files:
        print(f"[spec] OCR languages: {', '.join(traineddata_files)}")
else:
    print("[spec] OCR bundle disabled (OW_INCLUDE_OCR_BUNDLE=0)")

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
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
    optimize=2,
)
if PRUNE_QT_RUNTIME:
    a.binaries[:] = [entry for entry in a.binaries if _keep_toc_entry(entry)]
    a.datas[:] = [entry for entry in a.datas if _keep_toc_entry(entry)]
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
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
