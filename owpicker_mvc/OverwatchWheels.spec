# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
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
# UPX helps size but slows startup due decompression; prefer fast startup for onedir builds.
ENABLE_UPX = _env_flag("OW_UPX", DIST_MODE == "onefile")
INCLUDE_QT_MULTIMEDIA = not MIN_SIZE_BUILD
# Requests is optional (online sync only). Disable by default to keep runtime lean.
INCLUDE_REQUESTS = _env_flag("OW_INCLUDE_REQUESTS", False)
PRUNE_QT_RUNTIME = _env_flag("OW_PRUNE_QT", True)
INCLUDE_OCR_BUNDLE = _env_flag("OW_INCLUDE_OCR_BUNDLE", True)
OCR_BUNDLE_MODE = (os.environ.get("OW_OCR_BUNDLE_MODE") or "minimal").strip().lower()
if OCR_BUNDLE_MODE not in {"minimal", "full"}:
    raise SystemExit(
        "OW_OCR_BUNDLE_MODE must be one of: minimal, full "
        f"(got: {OCR_BUNDLE_MODE!r})"
    )
OCR_BUNDLE_LANGS = str(os.environ.get("OW_OCR_LANGS", "deu+eng")).strip()
OCR_BUNDLE_INCLUDE_OSD = _env_flag("OW_OCR_INCLUDE_OSD", True)

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


def _local_ocr_candidate_dirs() -> list[Path]:
    candidates: list[Path] = []
    for root in (project_root, project_root.parent):
        for folder_name in _OCR_FOLDER_NAMES:
            folder = root / folder_name
            if folder.exists() and folder.is_dir():
                candidates.append(folder)
    return _unique_paths(candidates)


def _candidate_ocr_source_dirs() -> list[Path]:
    return _unique_paths(_local_ocr_candidate_dirs() + _existing_external_ocr_dirs())


def _find_tesseract_executable(folder: Path) -> Path | None:
    candidates: list[Path] = []
    for name in _OCR_EXECUTABLE_NAMES:
        try:
            candidates.extend(path for path in folder.rglob(name) if path.is_file())
        except Exception:
            continue
    if not candidates:
        return None

    def _rank(path: Path) -> tuple[int, int, int]:
        try:
            rel = path.relative_to(folder)
            depth = len(rel.parts)
        except Exception:
            depth = 999
        preferred_name = 0 if path.name.lower() == "tesseract.exe" else 1
        return (depth, preferred_name, len(str(path)))

    candidates.sort(key=_rank)
    return candidates[0]


def _pick_ocr_source_dir() -> Path | None:
    for candidate in _candidate_ocr_source_dirs():
        if _find_tesseract_executable(candidate) is not None:
            return candidate
    return None


def _parse_ocr_langs(raw_value: str) -> list[str]:
    text = str(raw_value or "")
    normalized = text.replace(",", "+").replace(";", "+").replace(" ", "+")
    langs: list[str] = []
    for token in normalized.split("+"):
        value = token.strip().lower()
        if value and value not in langs:
            langs.append(value)
    return langs


def _requested_ocr_langs() -> list[str]:
    langs = _parse_ocr_langs(OCR_BUNDLE_LANGS)
    if not langs:
        langs = ["eng"]
    if OCR_BUNDLE_INCLUDE_OSD and "osd" not in langs:
        langs.append("osd")
    return langs


def _first_tessdata_dir(candidates: list[Path]) -> Path | None:
    for candidate in _unique_paths(candidates):
        if not candidate.exists() or not candidate.is_dir():
            continue
        try:
            if any(p.is_file() and p.suffix.lower() == ".traineddata" for p in candidate.iterdir()):
                return candidate
        except Exception:
            continue
    return None


def _target_dir_for_relative(base_dir: Path, file_path: Path, root_target: str) -> str:
    try:
        rel_parent = file_path.relative_to(base_dir).parent
    except Exception:
        return root_target
    if str(rel_parent) in {"", "."}:
        return root_target
    return f"{root_target}/{rel_parent.as_posix()}"


def _ocr_bundle_stats_from_files(files: list[Path]) -> tuple[int, int, list[str]]:
    file_count = 0
    total_bytes = 0
    traineddata_files: list[str] = []
    for path in files:
        if not path.is_file():
            continue
        file_count += 1
        try:
            total_bytes += int(path.stat().st_size)
        except Exception:
            pass
        if path.suffix.lower() == ".traineddata":
            traineddata_files.append(path.name)
    return file_count, total_bytes, sorted(set(traineddata_files))


def _collect_minimal_ocr_datas(
    source_dir: Path,
    requested_langs: list[str],
) -> tuple[list[tuple[str, str]], list[Path], Path, Path]:
    exe_path = _find_tesseract_executable(source_dir)
    if exe_path is None:
        raise SystemExit(
            "OW_OCR_BUNDLE_MODE=minimal but no tesseract executable was found.\n"
            f"Source dir: {source_dir}"
        )
    runtime_dir = exe_path.parent
    tessdata_dir = _first_tessdata_dir(
        [
            runtime_dir / "tessdata",
            runtime_dir.parent / "tessdata",
            source_dir / "tessdata",
        ]
    )
    if tessdata_dir is None:
        raise SystemExit(
            "OW_OCR_BUNDLE_MODE=minimal but no tessdata folder with *.traineddata was found.\n"
            f"Source dir: {source_dir}"
        )

    datas_local: list[tuple[str, str]] = []
    included_files: list[Path] = []
    seen_sources: set[str] = set()

    def _add_file(path: Path, target_dir: str) -> None:
        if not path.exists() or not path.is_file():
            return
        try:
            key = str(path.resolve()).lower()
        except Exception:
            key = str(path).lower()
        if key in seen_sources:
            return
        seen_sources.add(key)
        datas_local.append((str(path), target_dir))
        included_files.append(path)

    _add_file(exe_path, "OCR")
    if os.name == "nt":
        # Include all runtime DLLs from the full OCR source tree and flatten
        # them next to tesseract.exe. On some Windows bundles, dependent DLLs
        # can live outside the exe folder (e.g. sibling lib dirs) and would
        # otherwise fail at process start with WinError 2.
        for dll in sorted(source_dir.rglob("*.dll")):
            if "tessdata" in {part.lower() for part in dll.parts}:
                continue
            _add_file(dll, "OCR")
    else:
        for pattern in ("*.so", "*.so.*", "*.dylib"):
            for lib in sorted(runtime_dir.rglob(pattern)):
                _add_file(lib, _target_dir_for_relative(runtime_dir, lib, "OCR"))

    missing_langs: list[str] = []
    for lang in requested_langs:
        traineddata_file = tessdata_dir / f"{lang}.traineddata"
        if traineddata_file.exists() and traineddata_file.is_file():
            _add_file(traineddata_file, "OCR/tessdata")
            continue
        missing_langs.append(lang)
    if missing_langs:
        available = sorted(path.stem for path in tessdata_dir.glob("*.traineddata"))
        raise SystemExit(
            "OW_OCR_BUNDLE_MODE=minimal is missing required OCR language packs.\n"
            f"Missing: {missing_langs}\n"
            f"Requested (OW_OCR_LANGS): {requested_langs}\n"
            f"Available in {tessdata_dir}: {available}"
        )

    return datas_local, included_files, exe_path, tessdata_dir


datas = []
datas.extend(_audio_datas("Spin", "Spin"))
datas.extend(_audio_datas("Ding", "Ding"))
if INCLUDE_OCR_BUNDLE:
    ocr_source_dir = _pick_ocr_source_dir()
    if ocr_source_dir is None:
        roots = [str(project_root), str(project_root.parent)]
        external_candidates = [str(p) for p in _external_ocr_candidate_dirs()]
        expected = ", ".join(_OCR_FOLDER_NAMES)
        raise SystemExit(
            "OW_INCLUDE_OCR_BUNDLE=1 but no OCR bundle folder was found.\n"
            f"Searched roots: {roots}\n"
            f"Searched external dirs: {external_candidates}\n"
            f"Expected one of: {expected}"
        )
    if OCR_BUNDLE_MODE == "full":
        if _find_tesseract_executable(ocr_source_dir) is None:
            raise SystemExit(
                "OW_OCR_BUNDLE_MODE=full but no tesseract executable was found.\n"
                f"Source dir: {ocr_source_dir}"
            )
        bundle_files = [path for path in ocr_source_dir.rglob("*") if path.is_file()]
        file_count, total_bytes, traineddata_files = _ocr_bundle_stats_from_files(bundle_files)
        if not traineddata_files:
            raise SystemExit(
                "OW_OCR_BUNDLE_MODE=full but no tessdata (*.traineddata) was found.\n"
                f"Source dir: {ocr_source_dir}"
            )
        datas.append((str(ocr_source_dir), "OCR"))
        print(f"[spec] OCR bundle enabled (mode=full). Source dir: {ocr_source_dir}")
    else:
        requested_langs = _requested_ocr_langs()
        ocr_datas, included_files, exe_path, tessdata_dir = _collect_minimal_ocr_datas(
            ocr_source_dir,
            requested_langs,
        )
        datas.extend(ocr_datas)
        file_count, total_bytes, traineddata_files = _ocr_bundle_stats_from_files(included_files)
        print(f"[spec] OCR bundle enabled (mode=minimal). Source dir: {ocr_source_dir}")
        print(f"[spec] OCR executable: {exe_path}")
        print(f"[spec] OCR tessdata dir: {tessdata_dir}")
        print(f"[spec] OCR requested langs: {', '.join(requested_langs)}")

    size_mb = total_bytes / (1024 * 1024)
    print(f"[spec] OCR bundle files: {file_count} (total ~{size_mb:.1f} MB)")
    if traineddata_files:
        print(f"[spec] OCR languages: {', '.join(traineddata_files)}")
else:
    print("[spec] OCR bundle disabled (OW_INCLUDE_OCR_BUNDLE=0)")

print(
    "[spec] Build profile="
    f"{BUILD_PROFILE} | dist_mode={DIST_MODE} | strip={STRIP_BINARIES} | upx={ENABLE_UPX} | "
    f"qt_multimedia={INCLUDE_QT_MULTIMEDIA} | requests={INCLUDE_REQUESTS}"
)

hiddenimports = [
    "controller.ocr_import",
    "view.screen_region_selector",
    "view.screen_redion_selector",
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
