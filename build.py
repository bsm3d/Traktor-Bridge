# Benoit Saint-Moulin
# Traktor Bridge : portable build (PyInstaller onedir) and its zip

"""python build.py [--no-zip]

dist/TraktorBridge/ is copied as is (USB key, another PC, no admin rights).
Settings and log land next to TraktorBridge.exe. No .py file ships, the code only
lives compiled in the PYZ, the core (tags, sources, export/cdj) is native code (Nuitka) and
the __init__ files that carry logic go through PyArmor."""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "TraktorBridge"

sys.path.insert(0, str(ROOT))
from traktor_bridge import VERSION

# Qt pieces the app never touches, the hooks drag them in anyway
PRUNE = ["translations", "qml", "Qt6WebEngine*", "Qt6Quick*", "Qt6Qml*", "Qt6Pdf*", "Qt6Designer*",
         "opengl32sw.dll", "Qt6VirtualKeyboard*", "Qt6Charts*", "Qt63D*"]
SOURCE_SUFFIXES = {".py", ".pyw", ".pyi", ".pyx", ".pxd", ".c", ".cpp", ".h", ".hpp"}


def clear(folder: Path):
    """Rename first: Windows refuses while a TraktorBridge.exe from there is running,
    a plain rmtree would delete half the folder under the running app."""
    if not folder.exists():
        return
    old = folder.with_name(folder.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    try:
        folder.rename(old)
    except OSError:
        sys.exit(f"{folder} is in use, close Traktor Bridge first (nothing was deleted)")
    shutil.rmtree(old, ignore_errors=True)


def run_pyinstaller():
    clear(DIST)
    clear(ROOT / "build")
    # the core (tags, sources, export/cdj) is compiled to native modules first
    subprocess.run([sys.executable, str(ROOT / "compile_core.py")], cwd=ROOT, check=True)
    env = {**os.environ, "TB_STAGE": str(ROOT / "build" / "stage")}
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    str(ROOT / "traktor_bridge.spec")], cwd=ROOT, check=True, env=env)


def prune():
    rt = DIST / "runtime"
    gone = 0
    for pat in PRUNE:
        for p in rt.rglob(pat):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            gone += 1
    # sources shipped as data by some hooks, the compiled modules are in the PYZ already
    for p in rt.rglob("*"):
        if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES:
            p.unlink()
            gone += 1
    return gone


def check_seal():
    """What PyInstaller copied is what the seal says, byte for byte."""
    from traktor_bridge import integrity
    seal = ast.parse((ROOT / "build" / "stage" / "traktor_bridge" / "_seal.py").read_text(encoding="utf-8"))
    hashes = ast.literal_eval(seal.body[0].value)
    found = integrity.problems(DIST / "runtime" / "traktor_bridge", hashes)
    if found:
        sys.exit("the built folder does not match its seal:\n  " + "\n  ".join(found))
    print(f"seal checked: {len(hashes)} native modules match")


def size(p: Path) -> float:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6


def make_zip() -> Path:
    z = ROOT / "dist" / f"Portable_TraktorBridge-{VERSION}-win64.zip"
    z.unlink(missing_ok=True)
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in sorted(DIST.rglob("*")):
            if f.is_file():
                zf.write(f, Path("TraktorBridge") / f.relative_to(DIST))
    return z


def main() -> int:
    run_pyinstaller()
    n = prune()
    check_seal()
    # the license travels with every copy, PolyForm asks for it
    shutil.copyfile(ROOT / "LICENSE", DIST / "LICENSE.txt")
    left = [p for p in DIST.rglob("*") if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES]
    if left:
        sys.exit("Source files remain in the release:\n  " + "\n  ".join(map(str, left)))
    print(f"\npruned {n} files, no source files left, {size(DIST):.0f} MB in {DIST}")
    if "--no-zip" not in sys.argv:
        z = make_zip()
        print(f"zip: {z} ({z.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
