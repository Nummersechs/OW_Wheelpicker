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

_AUDIO_EXTENSIONS = {".wav", ".ogg", ".mp3"}


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


datas = []
datas.extend(_audio_datas("Spin", "Spin"))
datas.extend(_audio_datas("Ding", "Ding"))

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
