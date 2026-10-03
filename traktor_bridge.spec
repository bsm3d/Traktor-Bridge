# Benoit Saint-Moulin
# Traktor Bridge : PyInstaller spec, portable onedir build (run through build.py)

import os

ROOT = os.path.abspath(SPECPATH)
# build.py compiles the core into build/stage first, the spec then reads the staged copy
BASE = os.environ.get("TB_STAGE", ROOT)
PKG = os.path.join(BASE, "traktor_bridge")
ICON = os.path.join(PKG, "ui", "res", "icon.ico")

datas = [
    (os.path.join(PKG, "ui", "res"), os.path.join("traktor_bridge", "ui", "res")),
]

# the author's rekordbox player files: personal build only, TB_PUBLIC=1 leaves them out
RBREF = os.path.join(PKG, "export", "cdj", "rbref")
if os.path.isdir(RBREF) and not os.environ.get("TB_PUBLIC"):
    datas.append((RBREF, os.path.join("traktor_bridge", "export", "cdj", "rbref")))

# librosa (and numba / llvmlite behind it) is only a fallback for m4a / aac,
# soundfile reads everything else. Out of the portable build, it weighs more than the app.
excludes = [
    "librosa", "numba", "llvmlite", "audioread", "resampy", "sklearn", "joblib",
    "matplotlib", "pandas", "IPython", "tkinter", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtBluetooth",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
]

# PyInstaller cannot read imports inside a compiled .pyd: list the package modules and
# the libraries the core uses by hand
core_imports = [
    "numpy", "scipy.signal", "soundfile", "PIL.Image", "sqlite3", "xml.etree.ElementTree",
    "hashlib", "struct", "base64", "concurrent.futures", "dataclasses", "datetime",
]
modules = []
for dirpath, _, names in os.walk(PKG):
    rel = os.path.relpath(dirpath, BASE).replace(os.sep, ".")
    for n in names:
        stem = n.split(".")[0]
        if n.endswith((".py", ".pyd")) and stem != "__init__":
            modules.append(f"{rel}.{stem}")

# the C++ core, built next to native.py by compile_core.py
native_libs = [(os.path.join(dirpath, n), os.path.relpath(dirpath, BASE))
               for dirpath, _, names in os.walk(PKG) for n in names if n.startswith(("tbcore.", "libtbcore."))]

a = Analysis(
    [os.path.join(BASE, "main.py")],
    pathex=[BASE],
    datas=datas,
    binaries=native_libs,
    hiddenimports=["PySide6.QtMultimedia", *core_imports, *modules],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TraktorBridge",
    console=False,
    icon=[ICON],
    upx=False,
    contents_directory="runtime",
)

coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="TraktorBridge")
