"""
main.py
Phantom Optimizer V2 entry point.
Launches the PyQt6 PhantomScene shell with admin elevation.
"""
import sys
import os
import subprocess

# ---------------------------------------------------------------------------
# Hide child-process console windows in the frozen exe.
#
# Windows creates a new visible console for every subprocess call when the
# parent (this exe, built with console=False) has no console to inherit.
# Result: bcdedit / powercfg / wmic / shutdown / resmon / nvidia-smi each
# flash a cmd window for a split second. Patch subprocess.Popen once here
# and every backend utility goes silent in one shot.
#
# Only patches when sys.frozen — source mode is unchanged, developer still
# sees subprocess output in their terminal as before.
# ---------------------------------------------------------------------------
if sys.platform == "win32" and getattr(sys, "frozen", False):
    _CREATE_NO_WINDOW     = 0x08000000
    _STARTF_USESHOWWINDOW = 0x00000001
    _SW_HIDE              = 0

    _orig_popen = subprocess.Popen

    class _HiddenPopen(_orig_popen):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("creationflags", _CREATE_NO_WINDOW)
            if "startupinfo" not in kwargs:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= _STARTF_USESHOWWINDOW
                si.wShowWindow = _SW_HIDE
                kwargs["startupinfo"] = si
            super().__init__(*args, **kwargs)

    subprocess.Popen = _HiddenPopen

    # os.system bypasses subprocess.Popen — patch it separately.
    def _hidden_system(cmd):
        try:
            return _HiddenPopen(cmd, shell=True).wait()
        except Exception:
            return -1

    os.system = _hidden_system

# --- Make the project root importable ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QFontDatabase

from system.admin import ensure_admin
from app.ui.scene import PhantomScene


def main():
    import multiprocessing
    multiprocessing.freeze_support()
    ensure_admin()

    app = QApplication(sys.argv)

    if getattr(sys, "frozen", False):
        font_dir = os.path.join(sys._MEIPASS, "assets", "fonts")
    else:
        font_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets", "fonts"
        )

    orbitron_path = os.path.join(font_dir, "Orbitron-Bold.ttf")
    if os.path.exists(orbitron_path):
        fid = QFontDatabase.addApplicationFont(orbitron_path)
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams:
            app.setFont(QFont(fams[0]))

    for weight in (300, 400, 500, 600, 700):
        p = os.path.join(font_dir, f"rajdhani-{weight}.ttf")
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)

    window = PhantomScene()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()