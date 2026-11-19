"""
app/ui/theme.py
Central definition of Phantom Optimizer's visual constants.

Extracted from the original app/test_ui_layout.py — every value,
string, and formula is identical. Only the wrapping changed
(methods on PhantomScene -> module-level functions).

Contents:
  - ASSET_PATH / APP_ICON_PATH  (filesystem paths)
  - HOLO_NOTES_FONT_QSS         (Rajdhani rule for Notes + Holo content)
  - compute_frame_rect()        (frame geometry helper)
  - get_palette()               (theme_mode -> accent / text / bg tuples)
  - get_adjusted_palette()      (theme_mode -> shifted accent for top bar)
  - button_qss()                (per-tab + utility button stylesheet)
  - list_qss()                  (optimizer QListWidget stylesheet)
  - menu_qss()                  (right-click context menu stylesheet)
"""
import os
import sys
from PyQt6.QtCore import QRect


# ============================================================
# Asset paths
# ============================================================
# theme.py lives at <project>/app/ui/theme.py — but inside a PyInstaller
# bundle the tree is flattened under sys._MEIPASS. Detect and resolve both.
if getattr(sys, "frozen", False):
    _PROJ_DIR = sys._MEIPASS
else:
    _THIS_FILE = os.path.abspath(__file__)
    _THIS_DIR  = os.path.dirname(_THIS_FILE)      # <project>/app/ui
    _APP_DIR   = os.path.dirname(_THIS_DIR)       # <project>/app
    _PROJ_DIR  = os.path.dirname(_APP_DIR)        # <project>

_APP_DIR = os.path.join(_PROJ_DIR, "app")

# Matches original app/test_ui_layout.py ASSET_PATH
ASSET_PATH = os.path.join(_PROJ_DIR, "assets", "harvester")

# Matches original PhantomScene icon_path computation
APP_ICON_PATH = os.path.join(_PROJ_DIR, "assets", "app_icon.ico")


# ============================================================
# Font rule — Rajdhani for Notes + Holo content only
# ============================================================
HOLO_NOTES_FONT_QSS = """
    QWidget#phantomNotesContent  QLabel,
    QWidget#phantomNotesContent  QTextBrowser,
    QWidget#phantomHoloContent   QLabel,
    QWidget#phantomHoloContent   QTextBrowser,
    QWidget#phantomHoloContent   QListWidget,
    QWidget#phantomHoloContent   QTableWidget {
        font-family: 'Rajdhani';
        font-weight: 700;
    }
"""


# ============================================================
# Frame geometry — reserves left gap for tabs drawer,
# right gutter for the Harvester character
# ============================================================
def compute_frame_rect(w: int, h: int):
    left_gap   = 180 + 24
    right_gap  = max(320, int(w * 0.28))
    usable_w   = max(600, w - left_gap - right_gap)

    base_w   = int(usable_w * 0.78)
    base_x   = left_gap + (usable_w - base_w) // 2
    new_w    = min(int(usable_w * 0.84), usable_w - (base_x - left_gap))

    frame_w  = int(usable_w * 1.09)
    frame_h  = int(h * 0.7)
    frame_x  = left_gap + int(usable_w * 0.025)
    frame_y  = int(h * 0.14)
    return QRect(frame_x, frame_y, frame_w, frame_h)


# ============================================================
# Palettes
# ============================================================
def get_palette(theme_mode: str) -> dict:
    """Was PhantomScene._theme_color_rgb(self)."""
    if theme_mode == "dark":
        # Dark petrol blue background, oil blue accent, off-white text
        return {"accent": (70, 140, 190),
                "text":   (225, 232, 240),
                "bg":     (18, 26, 42)}
    elif theme_mode == "light":
        # Pure grayscale: light gray surfaces, black text, dark gray accents
        return {"accent": (50, 50, 50),
                "text":   (0, 0, 0),
                "bg":     (220, 220, 220)}
    else:
        return {"accent": (0, 255, 255),
                "text":   (200, 255, 255),
                "bg":     (15, 16, 22)}


def get_adjusted_palette(theme_mode: str) -> dict:
    """Was PhantomScene._adjusted_palette(self)."""
    palette = get_palette(theme_mode)
    accent = palette["accent"]
    if theme_mode == "dark":
        accent = tuple(min(255, c + 20) for c in accent)
    elif theme_mode == "light":
        accent = tuple(max(0, c - 15) for c in accent)
    return {"accent": accent,
            "text":   palette["text"],
            "bg":     palette["bg"]}


# ============================================================
# Reusable stylesheet builders
# ============================================================
def button_qss(palette: dict, theme_mode: str) -> str:
    """Was PhantomScene._btn_style(self, palette)."""
    r, g, b = palette["accent"]
    tr, tg, tb = palette["text"]

    if theme_mode == "light":
        btn_bg          = "rgba(200, 205, 212, 220)"
        hover_bg        = "rgb(55, 60, 68)"
        hover_text      = "rgb(255, 255, 255)"
        checked_bg      = "rgb(55, 60, 68)"
        checked_text    = "rgb(255, 255, 255)"
        disabled_bg     = "rgba(190, 195, 202, 150)"
        disabled_text   = "rgba(120, 125, 132, 200)"
        disabled_border = "rgba(140, 145, 152, 180)"
    elif theme_mode == "dark":
        btn_bg          = "rgba(28,38,55,200)"
        hover_bg        = f"rgb({r},{g},{b})"
        hover_text      = "rgb(15,15,20)"
        checked_bg      = f"rgb({r},{g},{b})"
        checked_text    = "rgb(15,15,20)"
        disabled_bg     = "rgba(40,48,62,150)"
        disabled_text   = "rgba(120,128,142,180)"
        disabled_border = "rgba(60,72,90,150)"
    else:  # default cyber
        btn_bg          = "rgba(0,0,0,140)"
        hover_bg        = f"rgb({r},{g},{b})"
        hover_text      = "rgb(0,0,0)"
        checked_bg      = f"rgba({r},{g},{b},90)"
        checked_text    = f"rgb({tr},{tg},{tb})"
        disabled_bg     = "rgba(40,40,40,120)"
        disabled_text   = "rgba(150,150,150,140)"
        disabled_border = "rgba(100,100,100,120)"

    return f"""
    QPushButton {{
        background-color: {btn_bg};
        color: rgb({tr},{tg},{tb});
        border: 1px solid rgb({r},{g},{b});
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {hover_bg};
        color: {hover_text};
    }}
    QPushButton:checked {{
        background-color: {checked_bg};
        color: {checked_text};
        font-weight: 600;
    }}
    QPushButton:disabled {{
        background-color: {disabled_bg};
        color: {disabled_text};
        border: 1px solid {disabled_border};
    }}
    """


def list_qss(palette: dict, theme_mode: str) -> str:
    """Was PhantomScene._list_style(self, palette)."""
    r, g, b = palette["accent"]
    tr, tg, tb = palette["text"]

    if theme_mode == "light":
        list_bg = "rgba(200, 205, 212, 220)"
    elif theme_mode == "dark":
        list_bg = "rgba(20,30,45,200)"
    else:
        list_bg = "rgba(0,0,0,90)"

    return f"""
    QListWidget {{
        background-color: {list_bg};
        color: rgb({tr},{tg},{tb});
        border: 1px solid rgba({r},{g},{b},140);
        border-radius: 8px;
        font-size: 12px;
        padding: 6px;
    }}
    QListWidget::item {{
        padding: 5px;
        border-radius: 4px;
    }}
    QListWidget::item:selected {{
        background-color: rgba({r},{g},{b},80);
    }}
    """


def menu_qss(theme_mode: str) -> str:
    """Was the inline menu_style block inside _apply_theme."""
    if theme_mode == "light":
        menu_bg = "#f0f0f0"; menu_text = "#000000"
        menu_border = "#a0a0a0"; menu_sel = "#c0c0c0"
    elif theme_mode == "dark":
        menu_bg = "#121a2a"; menu_text = "#e1e8f0"
        menu_border = "#4664be"; menu_sel = "#2a3a5a"
    else:
        menu_bg = "#0f1016"; menu_text = "#c8ffff"
        menu_border = "#00ffff"; menu_sel = "#004c4c"

    return f"""
    QMenu {{
        background-color: {menu_bg};
        color: {menu_text};
        border: 1px solid {menu_border};
        padding: 4px;
        font-family: 'Segoe UI', 'Inter', sans-serif;
        font-size: 11px;
    }}
    QMenu::item {{
        padding: 6px 20px 6px 20px;
    }}
    QMenu::item:selected {{
        background-color: {menu_sel};
    }}
    QMenu::separator {{
        height: 1px;
        background: {menu_border};
        margin: 4px 10px;
    }}
    """