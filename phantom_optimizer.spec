# -*- mode: python ; coding: utf-8 -*-
"""
Phantom Optimizer V2 — PyInstaller build spec.

Build (from project root, venv active):
    pyinstaller phantom_optimizer.spec --noconfirm

Output:
    dist/PhantomOptimizer.exe   (one-file, no console)
"""
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Bundle everything under assets/ into the same relative layout inside the exe.
# theme.py and main.py resolve asset paths at _MEIPASS/assets/...
datas = [
    ("assets", "assets"),
]

# PyOpenGL loads its platform backend lazily — keep every submodule.
hiddenimports = collect_submodules("OpenGL")

# pywin32 / wmi — confirmed runtime deps (hardware/disks.py, drivers.py,
# sensors.py, event_logs.py). win32timezone is imported lazily by wmi on
# first query; missing it = crash on Home / Hardware tabs.
hiddenimports += [
    "wmi",
    "win32com",
    "win32com.client",
    "pythoncom",
    "pywintypes",
    "win32evtlog",
    "win32timezone",
]

# Obvious runtime deps — safest to declare even though PyInstaller usually
# finds them.
hiddenimports += [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "psutil",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim the exe — these get pulled in by PyQt6 but are never used.
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuick3D",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.Qt3DCore",
        "PyQt6.QtMultimedia",
        "PyQt6.QtBluetooth",
        "PyQt6.QtNfc",
        "PyQt6.QtPositioning",
        "PyQt6.QtSerialPort",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        "PyQt6.QtCharts",
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PhantomOptimizer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX on PyQt6 triggers AV false positives
    runtime_tmpdir=None,
    console=False,           # GUI app — no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app_icon.ico",
)