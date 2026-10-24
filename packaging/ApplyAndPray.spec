# PyInstaller recipe for the Windows app. Build it with packaging\build.ps1 (it runs: pyinstaller packaging\ApplyAndPray.spec).
# Result: dist\ApplyAndPray\ApplyAndPray.exe plus its files (a folder app: starts faster and is more reliable than a single .exe).
# Your data is NOT inside the app: it goes to %LOCALAPPDATA%\ApplyAndPray (see modules/runtime.py), so updating the app keeps it.

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

hidden = (
    ["app", "runAiBot"]
    + [m for m in collect_submodules("modules", filter=lambda name: "__deprecated__" not in name)]
    + collect_submodules("config")
    + collect_submodules("undetected_chromedriver")
    + collect_submodules("keyring.backends")
    + ["win32ctypes.core", "pyautogui", "pyscreeze", "pymsgbox", "pytweening", "tkinter", "openai", "pypdf", "docx"]
)

import glob as _glob
datas = [
    (os.path.join(ROOT, "templates"), "templates"),
    (os.path.join(ROOT, "static"), "static"),
] + [(path, "config") for path in _glob.glob(os.path.join(ROOT, "config", "*.py"))]   # Only the defaults: never the .json files a user may have there
datas += collect_data_files("selenium") + collect_data_files("certifi")

# Python from Anaconda keeps the DLLs of ctypes, sqlite, tkinter... in Library\bin, where PyInstaller doesn't look
import sys, glob
binaries = []
conda_bin = os.path.join(getattr(sys, "base_prefix", sys.prefix), "Library", "bin")
if os.path.isdir(conda_bin):
    for pattern in ("ffi*.dll", "sqlite3.dll", "tcl86t.dll", "tk86t.dll", "libbz2.dll", "liblzma.dll", "zlib.dll", "libexpat.dll"):
        binaries += [(path, ".") for path in glob.glob(os.path.join(conda_bin, pattern))]

a = Analysis(
    [os.path.join(ROOT, "apply_and_pray.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["modules.__deprecated__", "matplotlib", "numpy.tests", "IPython", "jupyter", "notebook", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ApplyAndPray",
    console=True,            # A small window shows the dashboard's address; closing it stops the app
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ApplyAndPray")
