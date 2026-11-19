"""
app/gpu_test_ui.py
Two separate windows for the GPU Pulse test:
  - GpuTestConfirmDialog    (modal)   pre-test confirmation
  - GpuTestPreviewWindow    (separate) live Mandelbrot / progress
"""
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QSizePolicy,
)
from PyQt6.QtGui import QPixmap, QImage, QFont, QIcon
from PyQt6.QtCore import Qt

from core.configs import (
    GPU_TEST_TEMP_WARN_C,
    GPU_TEST_TEMP_ABORT_C,
    GPU_TEST_DURATION_S,
    GPU_TEST_GPU_USE_WARN_PCT,
)


# ============================================================
# Confirmation dialog
# ============================================================

class GpuTestConfirmDialog(QDialog):
    """Modal pre-test confirmation. Cannot be bypassed."""

    def __init__(self, info: dict, palette: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GPU Pulse — Confirm Test")
        self.setModal(True)

        # App icon (optional — silently skipped if missing)
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets", "app_icon.ico",
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))      
        # self.setModal(True)
        self.setMinimumWidth(560)
        self.user_proceeded = False
        self._palette = palette
        self._info = info or {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        ar, ag, ab = palette["accent"]
        tr, tg, tb = palette["text"]
        br, bg, bb = palette["bg"]
        is_light = br > 150

        def _text_color():
            return "#000000" if is_light else f"rgb({tr},{tg},{tb})"

        def _accent():
            return f"rgb({ar},{ag},{ab})"

        # ---- Title ----
        title = QLabel("GPU Pulse — Benchmark Confirmation")
        title.setStyleSheet(
            f"color: {_accent()}; font-size: 15px; font-weight: bold;"
        )
        layout.addWidget(title)

        # ---- GPU info block ----
        info_frame = QFrame()
        info_frame.setStyleSheet(
            f"QFrame {{ background-color: rgba({ar},{ag},{ab},30); "
            f"border: 1px solid rgba({ar},{ag},{ab},120); border-radius: 8px; }}"
        )
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(3)

        gpu_name = self._info.get("name", "Unknown GPU")
        driver = self._info.get("driver", "-")
        vram = self._info.get("vram_gb", 0)
        temp = self._info.get("temp_c", "--")
        kind = self._info.get("primary_kind", "unknown")
        all_gpus = self._info.get("all_gpus", []) or []

        # Build the temp line honestly — "--" means sensor unavailable
        if isinstance(temp, (int, float)):
            temp_line = (
                f"Current Temp: {temp} °C  "
                f"(limit: {GPU_TEST_TEMP_WARN_C} °C start / "
                f"{GPU_TEST_TEMP_ABORT_C} °C abort)"
            )
        else:
            temp_line = "Current Temp: unavailable (sensor not detected)"

        for line in (
            f"Primary GPU: {gpu_name}  [{kind}]",
            f"Driver: {driver}",
            f"VRAM: {vram} GB",
            temp_line,
        ):
            lbl = QLabel(line)
            lbl.setStyleSheet(f"color: {_text_color()}; font-size: 12px;")
            info_layout.addWidget(lbl)

        # Multi-GPU disclosure
        others = [g for g in all_gpus if g.get("name") != gpu_name]
        if others:
            sep = QLabel("─" * 42)
            sep.setStyleSheet(f"color: {_text_color()}; font-size: 11px;")
            info_layout.addWidget(sep)
            hdr = QLabel(f"Also detected ({len(others)} more):")
            hdr.setStyleSheet(
                f"color: {_text_color()}; font-size: 11px; font-weight: 600;"
            )
            info_layout.addWidget(hdr)
            for g in others:
                gkind = g.get("kind", "unknown")
                gvram = g.get("vram_gb", 0)
                lbl = QLabel(f"   • {g.get('name', '?')}  [{gkind}, {gvram} GB]")
                lbl.setStyleSheet(f"color: {_text_color()}; font-size: 11px;")
                info_layout.addWidget(lbl)
            tip = QLabel(
                "OpenGL may use the integrated GPU by default. To force the "
                "discrete GPU, set Phantom Optimizer to 'High performance' in "
                "Windows Settings → Display → Graphics."
            )
            tip.setWordWrap(True)
            tip.setStyleSheet(
                f"color: {_text_color()}; font-size: 10px; font-style: italic;"
            )
            info_layout.addWidget(tip)

        layout.addWidget(info_frame)

        # ---- Duration ----
        dur = QLabel(
            f"Duration: ~{GPU_TEST_DURATION_S} seconds "
            f"(fill rate + ALU throughput)"
        )
        dur.setStyleSheet(f"color: {_text_color()}; font-size: 12px; font-weight: 600;")
        layout.addWidget(dur)

        # ---- Cannot-cancel warning ----
        warn_frame = QFrame()
        warn_frame.setStyleSheet(
            "QFrame { background-color: rgba(200, 80, 60, 45); "
            "border: 1px solid rgba(200, 80, 60, 160); border-radius: 8px; }"
        )
        warn_layout = QVBoxLayout(warn_frame)
        warn_layout.setContentsMargins(12, 10, 12, 10)
        warn_layout.setSpacing(4)

        for line in (
            "⚠  IMPORTANT",
            "• MAKE SURE THAT BATTERY IS PLUGGED IN (HIGH PERFORMANCE MODE).",
            "• This test CANNOT be cancelled once started.",
            "• GPU will be under sustained load for ~8 seconds.",
            "• Close other GPU-heavy apps before proceeding.",
            "• Do not force-quit the application during the test.",
        ):
            lbl = QLabel(line)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"color: {_text_color()}; font-size: 11px;"
                + (" font-weight: bold;" if line.startswith("⚠") else "")
            )
            warn_layout.addWidget(lbl)
        layout.addWidget(warn_frame)

        # ---- GPU users detection ----
        users_data = self._info.get("gpu_users", {}) or {}
        confirmed = users_data.get("confirmed", []) or []
        possible = users_data.get("possible", []) or []
        util = users_data.get("util_pct", None)

        users_frame = QFrame()
        users_frame.setStyleSheet(
            f"QFrame {{ background-color: rgba({ar},{ag},{ab},20); "
            f"border: 1px solid rgba({ar},{ag},{ab},80); border-radius: 8px; }}"
        )
        users_layout = QVBoxLayout(users_frame)
        users_layout.setContentsMargins(12, 10, 12, 10)
        users_layout.setSpacing(3)

        # Utilization headline
        if isinstance(util, (int, float)):
            util_hdr = QLabel(f"NVIDIA GPU utilization: {util:.0f}%")
            util_hdr.setStyleSheet(
                f"color: {_text_color()}; font-size: 12px; font-weight: 600;"
            )
            users_layout.addWidget(util_hdr)

        # Confirmed users (nvidia-smi compute apps)
        if confirmed:
            chdr = QLabel("Confirmed GPU users (nvidia-smi):")
            chdr.setStyleSheet(
                f"color: {_text_color()}; font-size: 12px; font-weight: 600;"
            )
            users_layout.addWidget(chdr)
            for u in confirmed[:6]:
                lbl = QLabel(f"   • {u}")
                lbl.setStyleSheet(f"color: {_text_color()}; font-size: 11px;")
                users_layout.addWidget(lbl)

        # Possible users (heuristic)
        if possible:
            phdr = QLabel("Common GPU-using apps running (may be idle):")
            phdr.setStyleSheet(
                f"color: {_text_color()}; font-size: 12px; font-weight: 600;"
            )
            users_layout.addWidget(phdr)
            for u in possible[:6]:
                lbl = QLabel(f"   • {u}")
                lbl.setStyleSheet(f"color: {_text_color()}; font-size: 11px;")
                users_layout.addWidget(lbl)
            if len(possible) > 6:
                lbl = QLabel(f"   … and {len(possible) - 6} more")
                lbl.setStyleSheet(f"color: {_text_color()}; font-size: 11px;")
                users_layout.addWidget(lbl)

        # Empty state
        if not confirmed and not possible and (
            util is None or util < GPU_TEST_GPU_USE_WARN_PCT
        ):
            hdr = QLabel("No GPU activity detected.")
            hdr.setStyleSheet(
                f"color: {_text_color()}; font-size: 12px; font-weight: 600;"
            )
            users_layout.addWidget(hdr)

        # Recommendation
        if confirmed or possible:
            tip = QLabel(
                "Close these before proceeding for accurate results."
            )
            tip.setStyleSheet(
                f"color: {_text_color()}; font-size: 11px; font-style: italic;"
            )
            users_layout.addWidget(tip)

        layout.addWidget(users_frame)

        layout.addStretch(1)

        # ---- Buttons ----
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        btn_decline = QPushButton("Decline")
        btn_decline.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_decline.setStyleSheet(self._btn_style(secondary=True))
        btn_decline.clicked.connect(self._on_decline)
        btn_row.addWidget(btn_decline)

        btn_proceed = QPushButton("Proceed")
        btn_proceed.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_proceed.setStyleSheet(self._btn_style(secondary=False))
        btn_proceed.clicked.connect(self._on_proceed)
        btn_row.addWidget(btn_proceed)

        layout.addLayout(btn_row)

    def _btn_style(self, secondary: bool) -> str:
        ar, ag, ab = self._palette["accent"]
        tr, tg, tb = self._palette["text"]
        if secondary:
            bg = "rgba(80,80,80,180)"
            fg = f"rgb({tr},{tg},{tb})"
            bd = "rgba(120,120,120,180)"
        else:
            bg = f"rgba({ar},{ag},{ab},220)"
            fg = "#000000"
            bd = f"rgb({ar},{ag},{ab})"
        return f"""
        QPushButton {{
            background-color: {bg};
            color: {fg};
            border: 1px solid {bd};
            border-radius: 8px;
            padding: 8px 22px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            border: 1px solid rgb({tr},{tg},{tb});
        }}
        """

    def _on_proceed(self):
        self.user_proceeded = True
        self.accept()

    def _on_decline(self):
        self.user_proceeded = False
        self.reject()


# ============================================================
# Live preview window
# ============================================================

class GpuTestPreviewWindow(QDialog):
    """
    Separate window showing live Mandelbrot / progress during the test.
    Non-modal. Closing this window does NOT stop the test.
    """

    def __init__(self, palette: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GPU Pulse — Running")
        self.setModal(False)

        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets", "app_icon.ico",
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))     
        # self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(720, 560)
        self._palette = palette

        ar, ag, ab = palette["accent"]
        tr, tg, tb = palette["text"]
        br, bg, bb = palette["bg"]
        is_light = br > 150

        def _text_color():
            return "#000000" if is_light else f"rgb({tr},{tg},{tb})"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title
        title = QLabel("GPU Pulse — Live Preview")
        title.setStyleSheet(
            f"color: rgb({ar},{ag},{ab}); font-size: 14px; font-weight: bold;"
        )
        layout.addWidget(title)

        # Preview image
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumSize(480, 270)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._image_label.setStyleSheet(
            f"background-color: rgba(0,0,0,120); "
            f"border: 1px solid rgba({ar},{ag},{ab},120); border-radius: 6px; "
            f"color: {_text_color()};"
        )
        self._image_label.setText("Waiting for first frame…")
        layout.addWidget(self._image_label, 1)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFixedHeight(18)
        self._progress.setStyleSheet(f"""
        QProgressBar {{
            background-color: rgba(0,0,0,100);
            border: 1px solid rgba({ar},{ag},{ab},120);
            border-radius: 4px;
            color: {_text_color()};
            font-size: 11px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: rgb({ar},{ag},{ab});
            border-radius: 3px;
        }}
        """)
        layout.addWidget(self._progress)

        # Status text
        self._status = QLabel("Starting…")
        self._status.setStyleSheet(
            f"color: {_text_color()}; font-size: 11px;"
        )
        layout.addWidget(self._status)

        # Cannot-cancel notice
        notice = QLabel(
            "This test cannot be cancelled. Closing this window will NOT stop the test."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            f"color: rgba({ar},{ag},{ab},220); font-size: 10px; font-style: italic;"
        )
        layout.addWidget(notice)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._close_btn = QPushButton("Hide (test continues)")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet(f"""
        QPushButton {{
            background-color: rgba(80,80,80,180);
            color: {_text_color()};
            border: 1px solid rgba(120,120,120,180);
            border-radius: 6px;
            padding: 6px 16px;
            font-size: 12px;
        }}
        QPushButton:hover {{
            background-color: rgba(120,120,120,200);
        }}
        """)
        self._close_btn.clicked.connect(self.close)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

    def update_preview(self, qimage: QImage):
        try:
            pix = QPixmap.fromImage(qimage)
            self._image_label.setPixmap(pix)
        except Exception:
            pass

    def update_progress(self, pct: int, msg: str):
        try:
            self._progress.setValue(int(pct))
            self._status.setText(str(msg))
        except Exception:
            pass

    def mark_complete(self):
        try:
            self._progress.setValue(100)
            self._status.setText("Complete — results shown in Holo panel.")
            self._close_btn.setText("Close")
        except Exception:
            pass