"""
app/ui/widgets.py
All custom QWidget / QDialog / QFrame classes used by PhantomScene.

Extracted verbatim from app/test_ui_layout.py — every class body is
unchanged. Only the imports were rewired to pull shared constants
from app.ui.theme.
"""
import math
import os

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QFrame, QLabel, QGraphicsOpacityEffect,
    QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea, QAbstractItemView, QDialog, QProgressBar,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QLinearGradient, QPainterPath, QPixmap,
    QFont, QRegion,
)
from PyQt6.QtCore import (
    Qt, QTimer, QEasingCurve, QPropertyAnimation, QPoint, QRectF,
)

from app.ui.theme import ASSET_PATH, compute_frame_rect


# -------------------- Harvester (base only, anchor bottom-right)
class HarvesterWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.theme_mode = "default"
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

        self.layer_files = [
            "aura_full.png", "idle_breathe.png", "armor_edges.png",
            "base.png", "sword_glow.png", "armor_glow.png",
            "veins_glow.png", "eye_glow.png"
        ]

        self.layers = {}
        self.effects = {}
        self.active_layer = None
        self.phase = 0.0

        for name in self.layer_files:
            lbl = QLabel(self)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setScaledContents(True)
            path = os.path.join(ASSET_PATH, name)
            if os.path.exists(path):
                lbl.setPixmap(QPixmap(path))

            eff = QGraphicsOpacityEffect(lbl)
            lbl.setGraphicsEffect(eff)

            if name in ("base.png", "sword_glow.png"):
                eff.setOpacity(1.0)
            else:
                eff.setOpacity(0.0)

            self.layers[name] = lbl
            self.effects[name] = eff

        back_layers = ["aura_full.png", "idle_breathe.png", "armor_edges.png"]
        front_layers = ["armor_glow.png", "veins_glow.png", "eye_glow.png"]

        for n in back_layers:
            if n in self.layers:
                self.layers[n].lower()

        if "base.png" in self.layers:
            self.layers["base.png"].raise_()
        if "sword_glow.png" in self.layers:
            self.layers["sword_glow.png"].raise_()

        for n in front_layers:
            if n in self.layers:
                self.layers[n].raise_()

        self.timer = QTimer()
        self.timer.timeout.connect(self._pulse_update)
        self.timer.start(30)

    def resizeEvent(self, e):
        for lbl in self.layers.values():
            lbl.resize(self.size())

    def _pulse_update(self):
        if self.theme_mode != "default":
            for name, eff in self.effects.items():
                eff.setOpacity(1.0 if name == "base.png" else 0.0)
            return

        self.phase = (self.phase + 0.08) % math.tau

        if "idle_breathe.png" in self.effects:
            val = (math.sin(self.phase * 0.8) + 1) / 2
            self.effects["idle_breathe.png"].setOpacity(0.25 + 0.25 * val)

        if "sword_glow.png" in self.effects:
            sword_phase = (math.sin(self.phase * 1.5) + 1) / 2
            sword_opacity = 0.7 + 0.3 * sword_phase
            self.effects["sword_glow.png"].setOpacity(sword_opacity)

        if self.active_layer:
            raw = (math.sin(self.phase) + 1) / 2
            pulse = 0.35 + 0.65 * (raw ** 0.25)
            if self.active_layer in self.effects:
                self.effects[self.active_layer].setOpacity(pulse)
        else:
            if "aura_full.png" in self.effects:
                faint = 0.12 + 0.08 * (math.sin(self.phase * 0.5) + 1)
                self.effects["aura_full.png"].setOpacity(faint)

        self.update()

    def activate_layer(self, name):
        self.active_layer = name
        is_default = self.theme_mode == "default"
        for layer, eff in self.effects.items():
            if layer == "base.png":
                eff.setOpacity(1.0)
                continue
            if layer == "sword_glow.png":
                eff.setOpacity(1.0 if is_default else 0.0)
                continue
            if layer == "idle_breathe.png":
                # In default mode the pulse timer animates this layer;
                # in dark/light it must stay invisible.
                if not is_default:
                    eff.setOpacity(0.0)
                continue
            if is_default and layer == name:
                eff.setOpacity(0.6)
            else:
                eff.setOpacity(0.0)
        self.update()


# -------------------- Background + Monitor Frame + Wire
class SceneBackground(QWidget):
    def __init__(self, theme_mode_getter):
        super().__init__()
        self.bg_img = QPixmap(os.path.join(ASSET_PATH, "background.png"))
        self.frame_img = QPixmap(os.path.join(ASSET_PATH, "frame_and_wire.png"))
        self.theme_mode_getter = theme_mode_getter
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if not self.bg_img.isNull():
            painter.drawPixmap(
                0, 0,
                self.bg_img.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
        else:
            mode = self.theme_mode_getter()
            grad = QLinearGradient(0, 0, self.width(), self.height())
            if mode == "dark":
                grad.setColorAt(0, QColor("#07070a")); grad.setColorAt(1, QColor("#11121a"))
            elif mode == "light":
                grad.setColorAt(0, QColor("#e7ecf2")); grad.setColorAt(1, QColor("#c6d6e5"))
            else:
                grad.setColorAt(0, QColor("#0b0c10")); grad.setColorAt(1, QColor("#1a1b25"))
            painter.fillRect(self.rect(), grad)

        if not self.frame_img.isNull():
            painter.setOpacity(1.0)
            painter.drawPixmap(
                0, 0,
                self.frame_img.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
        else:
            frame = compute_frame_rect(self.width(), self.height())
            corner = 22
            painter.setBrush(QColor(0, 255, 255, 34))
            painter.setPen(QPen(QColor(0, 255, 255, 175), 3))
            painter.drawRoundedRect(frame, corner, corner)

        painter.end()


# -------------------- Pulsing-panel base (Utility/Notes) with content slot
class PulsingPanel(QFrame):
    def __init__(self, title: str, theme_color_getter):
        super().__init__()
        self.title = title
        self.theme_color_getter = theme_color_getter
        self.pulsing = False
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.setVisible(False)

        self.corner_radius = 16
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # -------- content slot (additive; overlays above painted visuals) --------
        self.content = QWidget(self)
        self.content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)
        self.content.setVisible(False)

    def show_content(self):
        self.content.setVisible(True)
        self.content.raise_()

    def clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.content.setVisible(False)

    def start_pulse(self):
        self.pulsing = True
        self._ensure_timer()

    def stop_pulse(self):
        self.pulsing = False

    def _ensure_timer(self):
        if not self.timer.isActive():
            self.timer.start(30)

    def _tick(self):
        if self.pulsing:
            self.phase = (self.phase + 0.05) % math.tau
        self.update()
        if not self.pulsing and self.phase == 0:
            self.timer.stop()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Content sits below the 40px title bar with margins.
        rect = self.rect().adjusted(14, 58, -14, -14)
        self.content.setGeometry(rect)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        radius = self.corner_radius

        palette = self.theme_color_getter()
        accent_r, accent_g, accent_b = palette["accent"]
        text_r, text_g, text_b = palette["text"]
        bg_r, bg_g, bg_b = palette["bg"]

        bg_alpha = 180 if bg_r < 60 else 240
        painter.setBrush(QColor(bg_r, bg_g, bg_b, bg_alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, radius, radius)

        base = QColor(accent_r, accent_g, accent_b)
        pulse = 0.65 + 0.35 * ((math.sin(self.phase) + 1) / 2 if self.pulsing else 0)
        r = min(255, int(base.red()   * (0.75 + 0.25 * pulse)))
        g = min(255, int(base.green() * (0.75 + 0.25 * pulse)))
        b = min(255, int(base.blue()  * (0.75 + 0.25 * pulse)))
        border_color = QColor(r, g, b)

        painter.setPen(QPen(border_color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)

        bar_height = 40
        bar = rect.adjusted(10, 10, -10, -(rect.height() - (10 + bar_height)))
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(bar, radius - 6, radius - 6)

        painter.setPen(QColor(text_r, text_g, text_b))
        f = QFont()
        f.setPointSize(10)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(bar, Qt.AlignmentFlag.AlignCenter, self.title)

        painter.end()


# -------------------- Holo panel (center): border pulse + inner shape square/circle
class HoloPanel(PulsingPanel):
    def __init__(self, theme_color_getter):
        super().__init__("HOLOGRAPHIC SCREEN", theme_color_getter)
        self.shape_mode = "square"
        self.about_mode = True
        self.corner_radius = 16
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._lines = []
        self._widget_mode = False

    def set_shape(self, shape: str):
        self.shape_mode = shape
        self.update()

    def set_about(self, on: bool):
        self.about_mode = on
        self.update()

    def set_lines(self, lines):
        # Returning to painted mode — drop any content widget.
        if self._widget_mode:
            self.clear_content()
            self._widget_mode = False
        self._lines = [str(l) for l in (lines or [])]
        self.update()

    def clear_lines(self):
        # Clear both painted lines and any content widget.
        if self._widget_mode:
            self.clear_content()
            self._widget_mode = False
        self._lines = []
        self.update()

    def set_content_widget(self, widget):
        """Switch Holo into widget mode. Painted text is skipped."""
        self.clear_content()
        self.content_layout.addWidget(widget)
        self.content.setVisible(True)
        self.content.raise_()
        self._widget_mode = True
        self.update()

    def apply_theme(self, palette):
        self._palette_override = palette
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Align content geometry with the painted inner rect (20, 50, -20, -20).
        inner = self.rect().adjusted(20, 50, -20, -20)
        self.content.setGeometry(inner)

        R = float(self.corner_radius)
        rectf = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rectf, R, R)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def paintEvent(self, e):
        super().paintEvent(e)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        palette = getattr(self, "_palette_override", self.theme_color_getter())
        accent_r, accent_g, accent_b = palette["accent"]
        text_r, text_g, text_b = palette["text"]

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(accent_r, accent_g, accent_b), 2))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1),
                                self.corner_radius, self.corner_radius)

        rect = self.rect().adjusted(20, 50, -20, -20)
        painter.setBrush(QColor(accent_r, accent_g, accent_b, 18))
        painter.setPen(Qt.PenStyle.NoPen)

        if self.shape_mode == "circle":
            d = min(rect.width(), rect.height())
            cx = rect.center().x() - d // 2
            cy = rect.center().y() - d // 2
            painter.drawEllipse(QRectF(cx, cy, d, d))
        else:
            painter.drawRoundedRect(rect, 16, 16)

        if self._widget_mode:
            painter.end()
            return

        painter.setPen(QColor(text_r, text_g, text_b))
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        painter.setFont(f)

        if self.about_mode:
            text = "Phantom Optimizer — About / Build Info\n(info)"
        elif self._lines:
            text = "\n".join(self._lines)
        else:
            text = "Analyzing…"

        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


# -------------------- Tabs overlay (drawer) — visuals preserved
class TabsOverlay(QFrame):
    NORMAL_W = 172
    NORMAL_H = 48
    ACTIVE_H = 54
    GAP_Y    = 12

    TAB_NAMES = ["Home", "Scan", "Optimizer", "Performance",
                 "Hardware", "Tools", "System"]

    def __init__(self, parent, theme_color_getter, on_tab_clicked):
        super().__init__(parent)
        self.theme_color_getter = theme_color_getter
        self.on_tab_clicked = on_tab_clicked
        self.setStyleSheet("background: rgba(0,0,0,140);")
        self.setVisible(False)
        self.buttons = []
        self.anim = None
        self.active_name = "Home"
        self._build()

    def _build(self):
        y = 20
        for name in self.TAB_NAMES:
            b = QPushButton(name, self)
            b.setGeometry(8, y, self.NORMAL_W, self.NORMAL_H)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, n=name: self._select(n))
            b.mouseDoubleClickEvent = lambda e, n=name: self._reset_to_default(n)
            self.buttons.append(b)
            y += self.NORMAL_H + self.GAP_Y
        self.refresh_colors()

    def _select(self, name: str):
        if name == self.active_name:
            if hasattr(self.parent(), "_reset_scene"):
                self.parent()._reset_scene()
            self.active_name = "Home"
        else:
            self.active_name = name
            self.on_tab_clicked(name)
        self._update_active_visuals()

    def _update_active_visuals(self):
        palette = self.theme_color_getter()
        accent_r, accent_g, accent_b = palette["accent"]
        text_r, text_g, text_b = palette["text"]

        theme_mode = getattr(self, "_theme_mode", "default")

        if theme_mode == "light":
            base_bg = "rgba(0,0,0,0)"
            hover_bg = "rgba(0,0,0,30)"
            active_bg = "rgb(0,0,0)"
            border_col = "rgb(80,80,80)"
            text_col = "rgb(0,0,0)"
            active_text = "rgb(255,255,255)"
        elif theme_mode == "dark":
            base_bg = f"rgba(255,255,255,20)"
            hover_bg = f"rgba({accent_r},{accent_g},{accent_b},220)"
            active_bg = f"rgb({accent_r},{accent_g},{accent_b})"
            border_col = f"rgb(200,220,240)"
            text_col = f"rgb(230,240,250)"
            active_text = f"rgb(15,15,15)"
        else:
            base_bg = f"rgba(0,0,0,120)"
            hover_bg = f"rgba({accent_r},{accent_g},{accent_b},220)"
            active_bg = f"rgb({accent_r},{accent_g},{accent_b})"
            border_col = f"rgb({accent_r},{accent_g},{accent_b})"
            text_col = f"rgb({text_r},{text_g},{text_b})"
            active_text = f"black"

        base = f"""
        QPushButton {{
            background-color: {base_bg};
            color: {text_col};
            border: 2px solid {border_col};
            border-radius: 12px;
            font-size: 13px;
            padding: 6px 10px;
        }}
        QPushButton:hover {{
            background-color: {hover_bg};
            color: rgb({text_r},{text_g},{text_b});
        }}
        """
        active = f"""
        QPushButton {{
            background-color: {active_bg};
            color: {active_text};
            border: 2px solid {border_col};
            border-radius: 14px;
            font-weight: 600;
            font-size: 13px;
            padding-top: 10px;
            padding-bottom: 10px;
        }}
        """

        for b in self.buttons:
            if b.text() == self.active_name:
                b.setStyleSheet(active)
                b.setFixedHeight(self.ACTIVE_H)
            else:
                b.setStyleSheet(base)
                b.setFixedHeight(self.NORMAL_H)

    def refresh_colors(self):
        self._update_active_visuals()

    def slide(self, show: bool):
        if self.anim and self.anim.state() == QPropertyAnimation.State.Running:
            return
        self.setVisible(True)
        end_x = 0 if show else -self.width()
        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(350)
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(QPoint(end_x, self.y()))
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(lambda: (not show) and self.setVisible(False))
        self.anim.start()

    def _reset_to_default(self, name):
        if hasattr(self.parent(), "_reset_scene"):
            self.parent()._reset_scene()

    def set_theme_mode(self, mode: str):
        self._theme_mode = mode
        if mode == "light":
            self.setStyleSheet("background: rgba(220, 220, 220, 210);")
        elif mode == "dark":
            self.setStyleSheet("background: rgba(15, 22, 35, 210);")
        else:
            self.setStyleSheet("background: rgba(0, 0, 0, 140);")
        self._update_active_visuals()


# -------------------- Startup details popup
class StartupDetailsDialog(QDialog):
    """Read-only popup showing all startup entries with full detail."""
    def __init__(self, rows, palette, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Startup Entries — Full Details")
        self.resize(1000, 600)

        r, g, b = palette["accent"]
        bg_r, bg_g, bg_b = palette["bg"]
        tr, tg, tb = palette["text"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Name", "Location", "Status", "Command"])
        table.setRowCount(len(rows))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        bg_r, bg_g, bg_b = palette["bg"]
        if bg_r > 150:
            tbl_bg = "rgb(232, 234, 238)"
            tbl_text = "rgb(0, 0, 0)"
            tbl_grid = "rgba(120, 125, 132, 80)"
            hdr_bg = "rgb(160, 165, 172)"
            hdr_text = "rgb(0, 0, 0)"
        else:
            tbl_bg = "rgba(0,0,0,90)"
            tbl_text = "rgb(225, 230, 238)"
            tbl_grid = f"rgba({r},{g},{b},60)"
            hdr_bg = f"rgba({r},{g},{b},80)"
            hdr_text = "black"

        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {tbl_bg};
                color: {tbl_text};
                border: 1px solid rgba({r},{g},{b},140);
                gridline-color: {tbl_grid};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background-color: {hdr_bg};
                color: {hdr_text};
                padding: 4px;
                border: none;
                font-size: 12px;
            }}
        """)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        for i, row in enumerate(rows):
            for j in range(min(4, len(row))):
                table.setItem(i, j, QTableWidgetItem(str(row[j])))

        layout.addWidget(table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0,0,0,140);
                color: rgb({tr},{tg},{tb});
                border: 1px solid rgb({r},{g},{b});
                border-radius: 8px;
                padding: 6px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: rgb({r},{g},{b});
                color: black;
            }}
        """)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


# -------------------- Software scan full-details popup
class SoftwareDetailsDialog(QDialog):
    """Read-only popup showing all installed applications."""
    def __init__(self, apps, palette, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Software Scan — Full Details")
        self.resize(1000, 600)

        r, g, b = palette["accent"]
        bg_r, bg_g, bg_b = palette["bg"]
        tr, tg, tb = palette["text"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        info = QLabel(f"{len(apps)} applications")
        info.setStyleSheet(
            f"color: rgb({tr},{tg},{tb}); font-size: 12px; padding-bottom: 4px;"
        )
        layout.addWidget(info)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Name", "Version", "Publisher", "Install Path"])
        table.setRowCount(len(apps))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        bg_r, bg_g, bg_b = palette["bg"]
        if bg_r > 150:
            tbl_bg = "rgb(232, 234, 238)"
            tbl_text = "rgb(0, 0, 0)"
            tbl_grid = "rgba(120, 125, 132, 80)"
            hdr_bg = "rgb(160, 165, 172)"
            hdr_text = "rgb(0, 0, 0)"
        else:
            tbl_bg = "rgba(0,0,0,90)"
            tbl_text = "rgb(225, 230, 238)"
            tbl_grid = f"rgba({r},{g},{b},60)"
            hdr_bg = f"rgba({r},{g},{b},80)"
            hdr_text = "black"

        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {tbl_bg};
                color: {tbl_text};
                border: 1px solid rgba({r},{g},{b},140);
                gridline-color: {tbl_grid};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background-color: {hdr_bg};
                color: {hdr_text};
                padding: 4px;
                border: none;
                font-size: 12px;
            }}
        """)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        for i, row in enumerate(apps):
            try:
                if len(row) >= 4:
                    name, version, publisher, install_path = row[0], row[1], row[2], row[3]
                else:
                    name, version, publisher = row
                    install_path = "-"
            except Exception:
                name, version, publisher, install_path = str(row), "-", "-", "-"
            table.setItem(i, 0, QTableWidgetItem(str(name)))
            table.setItem(i, 1, QTableWidgetItem(str(version)))
            table.setItem(i, 2, QTableWidgetItem(str(publisher)))
            table.setItem(i, 3, QTableWidgetItem(str(install_path)))

        layout.addWidget(table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0,0,0,140);
                color: rgb({tr},{tg},{tb});
                border: 1px solid rgb({r},{g},{b});
                border-radius: 8px;
                padding: 6px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: rgb({r},{g},{b});
                color: black;
            }}
        """)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


# -------------------- Scan progress ring widget
class ScanProgressRing(QWidget):
    """Large circular progress ring displayed inside Holo during a scan."""
    def __init__(self, palette_getter):
        super().__init__()
        self._pct = 0
        self._message = "Preparing..."
        self._palette_getter = palette_getter

    def reset(self):
        self._pct = 0
        self._message = "Preparing..."
        self.update()

    def set_progress(self, pct, message):
        try:
            self._pct = max(0, min(100, int(pct)))
        except Exception:
            self._pct = 0
        self._message = str(message or "")
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        palette = self._palette_getter()
        r, g, b = palette["accent"]
        tr, tg, tb = palette["text"]

        w = self.width()
        h = self.height()
        size = max(120, min(w, h) - 120)
        cx = w // 2
        cy = h // 2 - 20
        rect = QRectF(cx - size / 2, cy - size / 2, size, size)

        # Background ring
        pen_bg = QPen(QColor(80, 80, 80, 160), 10)
        pen_bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        # Foreground arc
        if self._pct > 0:
            pen_fg = QPen(QColor(r, g, b), 10)
            pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_fg)
            span = -int(360 * 16 * self._pct / 100)
            painter.drawArc(rect, 90 * 16, span)

        # Percentage
        painter.setPen(QColor(tr, tg, tb))
        f = QFont()
        f.setPointSize(20)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self._pct}%")

        # Message below
        if self._message:
            f.setPointSize(10)
            f.setBold(False)
            painter.setFont(f)
            msg_rect = QRectF(10, cy + size / 2 + 24, w - 20, 60)
            painter.drawText(
                msg_rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap,
                self._message,
            )


# -------------------- Scan mini ring (result header)
class MiniCompleteRing(QWidget):
    def __init__(self, palette_getter):
        super().__init__()
        self._palette_getter = palette_getter

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        palette = self._palette_getter()
        r, g, b = palette["accent"]
        tr, tg, tb = palette["text"]

        size = max(20, min(self.width(), self.height()) - 8)
        cx = self.width() // 2
        cy = self.height() // 2
        rect = QRectF(cx - size / 2, cy - size / 2, size, size)

        pen = QPen(QColor(r, g, b), 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        painter.setPen(QColor(tr, tg, tb))
        f = QFont()
        f.setPointSize(7)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "100%")


# -------------------- Scan result view
class ScanResultView(QWidget):
    """Result view shown after a scan completes: mini ring + results below."""
    def __init__(self, scan_type, result, palette_getter):
        super().__init__()
        self._scan_type = scan_type
        self._result = result or {}
        self._palette_getter = palette_getter
        self._build()

    def _build(self):
        palette = self._palette_getter()
        tr, tg, tb = palette["text"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)

        mini = MiniCompleteRing(self._palette_getter)
        mini.setFixedSize(56, 56)
        header.addWidget(mini)

        title = QLabel(self._title())
        title.setStyleSheet(
            f"color: rgb({tr},{tg},{tb}); font-size: 14px; font-weight: bold;"
        )
        title.setWordWrap(True)
        header.addWidget(title, 1)

        layout.addLayout(header)

        if self._scan_type == "software":
            layout.addWidget(self._build_software_table(), 1)
        else:
            layout.addWidget(self._build_text_results(), 1)

    def _title(self):
        if self._scan_type == "full":
            health = self._result.get("health", "UNKNOWN")
            return f"Full Scan Complete — {health}"
        if self._scan_type == "phantom":
            health = self._result.get("health", "UNKNOWN")
            return f"Phantom Scan Complete — {health}"
        if self._scan_type == "software":
            count = self._result.get("count", 0)
            return f"Software Scan — {count} applications"
        if self._scan_type == "hardware":
            return "Hardware Scan Complete"
        return "Scan Complete"

    def _build_text_results(self):
        palette = self._palette_getter()
        tr, tg, tb = palette["text"]

        lines = []
        if self._scan_type in ("full", "phantom"):
            cats = self._result.get("categories", {})
            for name, info in cats.items():
                status = info.get("status", "?")
                marker = {"OK": "✓", "WARN": "⚠", "FAIL": "✗", "N/A": "—"}.get(status, "?")
                lines.append(f"{marker}  {name}")
                text = info.get("text", "")
                if text:
                    lines.append(f"      {text}")
                lines.append("")
        elif self._scan_type == "hardware":
            hw = self._result

            # --- CPU ---
            cpu = hw.get("cpu") or {}
            if cpu.get("name"):
                lines.append("── CPU ──")
                lines.append(f"  {cpu['name']}")
                details = []
                if cpu.get("cores"):   details.append(f"{cpu['cores']} cores")
                if cpu.get("threads"): details.append(f"{cpu['threads']} threads")
                if cpu.get("base_mhz"): details.append(f"{cpu['base_mhz']} MHz")
                if details:
                    lines.append("  " + " | ".join(details))
                lines.append("")

            # --- Motherboard / BIOS ---
            mb = hw.get("motherboard") or {}
            if mb.get("manufacturer") or mb.get("product") or mb.get("bios_version"):
                lines.append("── Motherboard / BIOS ──")
                if mb.get("manufacturer") or mb.get("product"):
                    lines.append(f"  Board: {mb.get('manufacturer','-')} {mb.get('product','')}".rstrip())
                if mb.get("bios_vendor") or mb.get("bios_version"):
                    lines.append(f"  BIOS:  {mb.get('bios_vendor','-')} {mb.get('bios_version','')} ({mb.get('bios_date','-')})".rstrip())
                lines.append("")

            # --- GPUs ---
            gpus = hw.get("gpus") or []
            if gpus:
                lines.append(f"── GPU ({len(gpus)}) ──")
                for g in gpus:
                    if isinstance(g, dict):
                        extras = []
                        if g.get("vram_gb"):     extras.append(f"{g['vram_gb']} GB VRAM")
                        if g.get("driver"):      extras.append(f"driver {g['driver']}")
                        if g.get("resolution"):  extras.append(g["resolution"])
                        line = f"  {g.get('name','Unknown')}"
                        if extras:
                            line += "  [" + ", ".join(extras) + "]"
                        lines.append(line)
                    else:
                        lines.append(f"  {g}")
                lines.append("")

            # --- RAM ---
            ram_gb = hw.get("ram_gb", 0)
            sticks = hw.get("ram_sticks") or []
            if ram_gb or sticks:
                lines.append("── RAM ──")
                if ram_gb:
                    lines.append(f"  Total: {ram_gb} GB")
                for s in sticks:
                    lines.append(f"  Slot {s.get('slot','-')}: "
                                 f"{s.get('size_gb','?')} GB "
                                 f"{s.get('manufacturer','-')} "
                                 f"{s.get('part','-')}".rstrip() + "  "
                                 f"@ {s.get('speed_mhz','?')} MHz")
                lines.append("")

            # --- Physical disks ---
            disks = hw.get("disks") or []
            if disks:
                lines.append(f"── Physical Disks ({len(disks)}) ──")
                for d in disks:
                    if isinstance(d, dict):
                        lines.append(f"  {d.get('model','?')}  "
                                     f"[{d.get('media','-')}, {d.get('size_gb','?')} GB, "
                                     f"{d.get('health','-')}/{d.get('status','-')}]")
                    else:
                        lines.append(f"  {d}")
                lines.append("")

            # --- Volumes ---
            vols = hw.get("volumes") or []
            if vols:
                lines.append(f"── Volumes ({len(vols)}) ──")
                for v in vols:
                    lines.append(f"  {v.get('mount','?')}  "
                                 f"{v.get('fs','-')}  "
                                 f"{v.get('used_gb',0)}/{v.get('total_gb',0)} GB used  "
                                 f"({v.get('percent',0)}%)")
                lines.append("")

            # --- Network ---
            net = hw.get("network") or []
            if net:
                lines.append(f"── Network Adapters ({len(net)}) ──")
                for n in net:
                    spd = n.get("speed_mbps")
                    spd_str = f"{spd} Mbps" if spd else "-"
                    lines.append(f"  {n.get('name','?')}  "
                                 f"MAC {n.get('mac','-')}  {spd_str}")
                lines.append("")

            # --- Audio ---
            audio = hw.get("audio") or []
            if audio:
                lines.append(f"── Audio ({len(audio)}) ──")
                for a in audio:
                    lines.append(f"  {a.get('name','?')}  [{a.get('status','-')}]")
                lines.append("")

            # --- Monitors ---
            mons = hw.get("monitors") or []
            if mons:
                lines.append(f"── Monitors ({len(mons)}) ──")
                for m in mons:
                    lines.append(f"  {m.get('name','?')}  ({m.get('vendor','-')}, {m.get('year','-')})")
                lines.append("")

            # --- USB devices ---
            usb = hw.get("usb") or []
            if usb:
                lines.append(f"── USB Devices ({len(usb)}) ──")
                for u in usb:
                    lines.append(f"  {u.get('name','?')}  [{u.get('status','-')}]")
                lines.append("")

            # --- Sensors ---
            sensors = hw.get("sensors") or {}
            if sensors.get("cpu_temp") is not None or sensors.get("gpu_temp") is not None:
                lines.append("── Sensors ──")
                if sensors.get("cpu_temp") is not None:
                    lines.append(f"  CPU: {sensors['cpu_temp']} °C")
                if sensors.get("gpu_temp") is not None:
                    lines.append(f"  GPU: {sensors['gpu_temp']} °C")
                lines.append("")

            if not lines:
                lines.append("No hardware detected.")

        from PyQt6.QtWidgets import QTextBrowser

        text = "\n".join(lines) if lines else "No results."
        browser = QTextBrowser()
        browser.setPlainText(text)
        browser.setStyleSheet(
            f"QTextBrowser {{ color: rgb({tr},{tg},{tb}); font-size: 12px; "
            f"background: transparent; border: none; }}"
        )
        return browser

    def _build_software_table(self):
        palette = self._palette_getter()
        r, g, b = palette["accent"]
        tr, tg, tb = palette["text"]

        apps = self._result.get("apps", [])

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Name", "Version", "Publisher"])
        table.setRowCount(len(apps))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        bg_r, bg_g, bg_b = palette["bg"]
        if bg_r > 150:
            tbl_bg = "rgb(232, 234, 238)"
            tbl_text = "rgb(0, 0, 0)"
            tbl_grid = "rgba(120, 125, 132, 80)"
            hdr_bg = "rgb(160, 165, 172)"
            hdr_text = "rgb(0, 0, 0)"
        else:
            tbl_bg = "rgba(0,0,0,90)"
            tbl_text = "rgb(225, 230, 238)"
            tbl_grid = f"rgba({r},{g},{b},60)"
            hdr_bg = f"rgba({r},{g},{b},80)"
            hdr_text = "black"

        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {tbl_bg};
                color: {tbl_text};
                border: 1px solid rgba({r},{g},{b},140);
                gridline-color: {tbl_grid};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background-color: {hdr_bg};
                color: {hdr_text};
                padding: 4px;
                border: none;
                font-size: 12px;
            }}
        """)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        for i, row in enumerate(apps):
            try:
                name, version, publisher = row[0], row[1], row[2]
            except Exception:
                name, version, publisher = str(row), "-", "-"
            table.setItem(i, 0, QTableWidgetItem(str(name)))
            table.setItem(i, 1, QTableWidgetItem(str(version)))
            table.setItem(i, 2, QTableWidgetItem(str(publisher)))

        return table


# -------------------- Live monitor widget (attached bottom of Holo)
class LiveMonitorWidget(QWidget):
    """2-column live monitor: Disk/Memory (left) | GPU/CPU with temps (right)."""
    def __init__(self, palette_getter):
        super().__init__()
        self._palette_getter = palette_getter
        self.setFixedHeight(100)
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        # Left block: Disk / Memory
        left = QVBoxLayout()
        left.setSpacing(8)
        self._disk_row = self._make_row("Disk", label_width=46)
        self._mem_row = self._make_row("Memory", label_width=46)
        left.addLayout(self._disk_row["layout"])
        left.addLayout(self._mem_row["layout"])
        layout.addLayout(left, 1)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet("color: rgba(150,150,150,80);")
        layout.addWidget(div)

        # Right block: GPU / CPU with temp
        right = QVBoxLayout()
        right.setSpacing(8)
        self._gpu_row = self._make_row("GPU", with_temp=True, label_width=32)
        self._cpu_row = self._make_row("CPU", with_temp=True, label_width=32)
        right.addLayout(self._gpu_row["layout"])
        right.addLayout(self._cpu_row["layout"])
        layout.addLayout(right, 1)

    def _make_row(self, label, with_temp=False, label_width=42):
        palette = self._palette_getter()
        tr, tg, tb = palette["text"]

        row = QHBoxLayout()
        row.setSpacing(3)

        lbl = QLabel(label)
        lbl.setFixedWidth(label_width)
        lbl.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 10px;")
        row.addWidget(lbl)

        bar = QProgressBar()
        bar.setMaximum(100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(10)
        bar.setMinimumWidth(15)
        bar.setStyleSheet(self._bar_style())
        row.addWidget(bar, 1)

        pct_lbl = QLabel("--")
        pct_lbl.setFixedWidth(26)
        pct_lbl.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 10px;")
        pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(pct_lbl)

        temp_lbl = None
        if with_temp:
            temp_lbl = QLabel("--°C")
            temp_lbl.setFixedWidth(40)
            temp_lbl.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 10px;")
            temp_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(temp_lbl)

        return {"layout": row, "bar": bar, "pct": pct_lbl, "temp": temp_lbl}

    def _bar_style(self):
        palette = self._palette_getter()
        r, g, b = palette["accent"]
        return f"""
        QProgressBar {{
            background-color: rgba(0,0,0,120);
            border: 1px solid rgba({r},{g},{b},140);
            border-radius: 5px;
        }}
        QProgressBar::chunk {{
            background-color: rgb({r},{g},{b});
            border-radius: 4px;
        }}
        """

    def set_stats(self, stats):
        self._update_bar(self._disk_row, stats.get("disk"))
        self._update_bar(self._mem_row, stats.get("mem"))
        self._update_bar(self._gpu_row, stats.get("gpu"))
        self._update_temp(self._gpu_row, stats.get("gpu_temp"))
        self._update_bar(self._cpu_row, stats.get("cpu"))
        self._update_temp(self._cpu_row, stats.get("cpu_temp"))

    def _update_bar(self, row, val):
        if val is None:
            row["bar"].setValue(0)
            row["pct"].setText("--")
        else:
            try:
                v = max(0, min(100, int(val)))
                row["bar"].setValue(v)
                row["pct"].setText(f"{v}%")
            except Exception:
                row["bar"].setValue(0)
                row["pct"].setText("--")

    def _update_temp(self, row, val):
        if row["temp"] is None:
            return
        if isinstance(val, (int, float)):
            row["temp"].setText(f"{val}°C")
        else:
            row["temp"].setText("--°C")

    def refresh_style(self):
        palette = self._palette_getter()
        tr, tg, tb = palette["text"]

        # Enforce pure black text in light mode
        if palette["bg"][0] > 150:
            tr, tg, tb = 0, 0, 0

        text_style = f"color: rgb({tr},{tg},{tb}); font-size: 10px;"
        bar_style = self._bar_style()

        for lbl in self.findChildren(QLabel):
            lbl.setStyleSheet(text_style)
        for bar in self.findChildren(QProgressBar):
            bar.setStyleSheet(bar_style)


# -------------------- Performance container (results + live monitor)
class PerformanceContentView(QWidget):
    """Results area (scrollable, top) + live monitor (fixed, bottom)."""
    def __init__(self, palette_getter):
        super().__init__()
        self._palette_getter = palette_getter
        self._build()

    def _build(self):
        palette = self._palette_getter()
        tr, tg, tb = palette["text"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Results (scrollable, top)
        self._results_scroll = QScrollArea()
        self._results_scroll.setWidgetResizable(True)
        self._results_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._results_scroll.setStyleSheet("background: transparent;")
        self._results_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._results_label = QLabel("Run a test to see results here.")
        self._results_label.setWordWrap(True)
        self._results_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self._results_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._results_label.setStyleSheet(
            f"color: rgb({tr},{tg},{tb}); font-size: 12px; background: transparent;"
        )
        self._results_scroll.setWidget(self._results_label)
        layout.addWidget(self._results_scroll, 1)

        # Live monitor (fixed, bottom)
        self._live_monitor = LiveMonitorWidget(self._palette_getter)
        layout.addWidget(self._live_monitor, 0)

    def append_result(self, title, text):
        current = self._results_label.text()
        if not current.strip() or current.startswith("Run a test"):
            combined = f"=== {title} ===\n{text}"
        else:
            combined = f"{current}\n\n=== {title} ===\n{text}"
        self._results_label.setText(combined)

    def clear_results(self):
        self._results_label.setText("Run a test to see results here.")

    def set_live_stats(self, stats):
        self._live_monitor.set_stats(stats)

    def refresh_style(self):
        palette = self._palette_getter()
        tr, tg, tb = palette["text"]
        self._results_label.setStyleSheet(
            f"color: rgb({tr},{tg},{tb}); font-size: 12px; background: transparent;"
        )
        self._live_monitor.refresh_style()