"""
app/ui/scene.py
PhantomScene — main window. Wires widgets, controllers, and theme.

Extracted from app/test_ui_layout.py. All logic unchanged. Theme helpers
that used to live as PhantomScene methods are now thin delegations to
app.ui.theme, so every internal call site is unchanged.
"""
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel,
    QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog,
)
from PyQt6.QtGui import QPixmap, QColor, QIcon
from PyQt6.QtCore import Qt, QTimer

import os, sys, csv, re

# Make <project> importable — one level deeper than the old
# app/test_ui_layout.py, hence the extra dirname().
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from app.controllers.optimizer_controller import OptimizerController
from app.controllers.home_controller import HomeController
from app.controllers.hardware_controller import HardwareController, CATEGORIES
from app.controllers.tools_controller import ToolsController
from app.controllers.system_controller import SystemController
from app.controllers.scan_controller import ScanController
from app.controllers.performance_controller import PerformanceController
from app.gpu_test_ui import GpuTestConfirmDialog, GpuTestPreviewWindow

from app.ui.theme import (
    ASSET_PATH,
    APP_ICON_PATH,
    HOLO_NOTES_FONT_QSS,
    compute_frame_rect,
    get_palette,
    get_adjusted_palette,
    button_qss,
    list_qss,
    menu_qss,
)
from app.ui.widgets import (
    HarvesterWidget,
    SceneBackground,
    PulsingPanel,
    HoloPanel,
    TabsOverlay,
    StartupDetailsDialog,
    SoftwareDetailsDialog,
    ScanProgressRing,
    MiniCompleteRing,
    ScanResultView,
    LiveMonitorWidget,
    PerformanceContentView,
)


# -------------------- Main scene
class PhantomScene(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phantom Optimizer — V2.0")
        self.resize(1280, 720)
        self.theme_mode = "default"
        self._current_tab = "Home"   # MUST be initialized before _apply_theme()

        # App window icon (optional — silently skipped if missing)
        if os.path.exists(APP_ICON_PATH):
            self.setWindowIcon(QIcon(APP_ICON_PATH))

        self.bg = SceneBackground(lambda: self.theme_mode)
        self.bg.setParent(self); self.bg.lower()

        self.utility = PulsingPanel("UTILITY", self._theme_color_rgb)
        self.utility.setParent(self); self.utility.raise_()

        self.holo = HoloPanel(self._theme_color_rgb)
        self.holo.setParent(self); self.holo.raise_()

        self._opt_last_snapshot = {}
        self._opt_last_candidates = []

        self.notes = PulsingPanel("NOTES / CONTEXT", self._theme_color_rgb)
        self.notes.setParent(self); self.notes.raise_()

        self.notes.content.setObjectName("phantomNotesContent")
        self.holo.content.setObjectName("phantomHoloContent")

        self.harvester = HarvesterWidget()
        self.harvester.setParent(self); self.harvester.raise_()
        self.harvester.activate_layer(None)

        self.btn_theme = QPushButton("👁", self)
        self.btn_theme.setFixedSize(42, 42)
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)

        # Theme button tooltip instead of a permanent label
        self.btn_theme.setToolTip(
            "Switch theme:  Default → Dark → Light\n\n"
            "Default mode animates the Harvester character.\n"
            "Dark / Light modes stop the animation for lower CPU usage."
        )

        self._style_top_buttons()

        self.tabs = TabsOverlay(self, self._theme_color_rgb, self._open_tab)
        self.tabs.raise_()
        self.tabs_visible = False

        self.btn_theme.clicked.connect(self._toggle_theme)

        # --- Optimizer controller ---
        self.optimizer_ctrl = OptimizerController(self)
        self._wire_optimizer_controller()

        # --- Home controller ---
        self.home_ctrl = HomeController(self)
        self.home_ctrl.info_ready.connect(self._on_home_info)
        self.home_ctrl.error_occurred.connect(self._on_simple_error)

        # --- Hardware controller ---
        self.hardware_ctrl = HardwareController(self)
        self.hardware_ctrl.category_ready.connect(self._on_hw_category)
        self.hardware_ctrl.error_occurred.connect(self._on_simple_error)

        # --- Tools controller ---
        self.tools_ctrl = ToolsController(self)
        self.tools_ctrl.content_ready.connect(self._on_tools_content)
        self.tools_ctrl.action_done.connect(self._on_tools_action_done)
        self.tools_ctrl.operation_started.connect(self._on_tools_op_started)
        self.tools_ctrl.operation_finished.connect(self._on_tools_op_finished)
        self.tools_ctrl.kill_finished.connect(self._on_tools_kill_finished)
        self.tools_ctrl.event_logs_ready_for_export.connect(self._on_event_logs_export_ready)
        self.tools_ctrl.error_occurred.connect(self._on_simple_error)

        # --- System controller ---
        self.system_ctrl = SystemController(self)
        self.system_ctrl.content_ready.connect(self._on_system_content)
        self.system_ctrl.action_done.connect(self._on_system_action_done)
        self.system_ctrl.operation_started.connect(self._on_system_op_started)
        self.system_ctrl.operation_finished.connect(self._on_system_op_finished)
        self.system_ctrl.error_occurred.connect(self._on_simple_error)

        # --- Scan controller ---
        self.scan_ctrl = ScanController(self)
        self.scan_ctrl.progress_changed.connect(self._on_scan_progress)
        self.scan_ctrl.scan_finished.connect(self._on_scan_finished)
        self.scan_ctrl.scan_cancelled.connect(self._on_scan_cancelled)
        self.scan_ctrl.operation_started.connect(self._on_scan_op_started)
        self.scan_ctrl.operation_finished.connect(self._on_scan_op_finished)
        self.scan_ctrl.error_occurred.connect(self._on_simple_error)

        # --- Performance controller ---
        self.perf_ctrl = PerformanceController(self)
        self.perf_ctrl.live_stats_ready.connect(self._on_perf_live_stats)
        self.perf_ctrl.test_finished.connect(self._on_perf_test_finished)
        self.perf_ctrl.operation_started.connect(self._on_perf_op_started)
        self.perf_ctrl.operation_finished.connect(self._on_perf_op_finished)
        self.perf_ctrl.error_occurred.connect(self._on_simple_error)
        self.perf_ctrl.gpu_preview_ready.connect(self._on_gpu_preview)
        self.perf_ctrl.gpu_progress_changed.connect(self._on_gpu_progress)
        self.perf_ctrl.gpu_info_ready.connect(self._on_gpu_info_ready)

        # --- Tools / System state ---
        self._tools_buttons = []
        self._tools_action_buttons = []
        self._tools_action_layout = None
        self._tools_current = ""
        self._tools_table = None
        self._tools_selected_row = None
        self._tools_notes_label = None
        self._tools_startup_rows = []

        self._system_buttons = []
        self._system_action_buttons = []
        self._system_action_layout = None
        self._system_current = ""
        self._system_table = None
        self._system_selected_row = None
        self._system_notes_label = None

        self._scan_buttons = []
        self._scan_progress_widget = None
        self._scan_result_view = None
        self._scan_cancel_timer = None
        self._scan_last_type = None
        self._scan_last_software_result = None

        self._perf_buttons = []
        self._perf_view = None
        self._perf_live_timer = None
        self._perf_test_running = False
        self._gpu_preview_window = None
        self._gpu_watchdog_timer = None
        self._gpu_test_abandoned = False
        self._gpu_lock_active = False
        self._gpu_lock_saved = {}

        # --- Home / Hardware UI refs ---
        self._home_buttons = []
        self._hw_buttons = []
        self._hw_selected = "CPU"
        self._current_tab = "Home"

        # --- Optimizer UI references (reset on each tab open) ---
        self._opt_buttons = []
        self._opt_list = None
        self._opt_status_label = None
        self._opt_summary_label = None
        self._opt_notes_label = None

        self.holo.set_about(True)
        self.holo.setVisible(True)

        self.repaint_timer = QTimer(self)
        self.repaint_timer.timeout.connect(self.bg.update)
        self.repaint_timer.start(1200)

        # Apply initial theme now that every widget ref exists
        self._apply_theme()

        # Show the Home tab on launch (deferred until event loop runs)
        QTimer.singleShot(0, lambda: self._open_tab("Home"))

    # ---- theme helpers (delegating — real logic lives in app.ui.theme)
    def _theme_color_rgb(self):
        return get_palette(self.theme_mode)

    def _adjusted_palette(self):
        return get_adjusted_palette(self.theme_mode)

    def _style_top_buttons(self):
        palette = self._adjusted_palette()
        r, g, b = palette["accent"]
        tr, tg, tb = palette["text"]
        br, bg, bb = palette["bg"]
        self.btn_theme.setStyleSheet(f"""
        QPushButton {{
            background-color: rgba({br},{bg},{bb},120);
            color: rgb({tr},{tg},{tb});
            border: 1px solid rgb({r},{g},{b});
            border-radius: 8px;
            font-size: 18px;
        }}
        QPushButton:hover {{
            background-color: rgb({r},{g},{b});
            color: rgb({br},{bg},{bb});
        }}
        """)

    # ---- interactions
    def _toggle_tabs(self):
        self.tabs_visible = not self.tabs_visible
        self.tabs.slide(self.tabs_visible)

    def _toggle_theme(self):
        modes = ["default", "dark", "light"]
        self.theme_mode = modes[(modes.index(self.theme_mode) + 1) % 3]
        self._apply_theme()

    def _apply_theme(self):
        for w in (self.utility, self.holo, self.notes, self.harvester):
            if hasattr(w, "timer") and w.timer.isActive():
                w.timer.stop()

        if self.theme_mode == "default":
            bg_name = "background.png"
            frame_name = "frame_and_wire.png"
            base_name = "base.png"
        else:
            bg_name = f"background_{self.theme_mode}.png"
            frame_name = f"frame_{self.theme_mode}.png"
            base_name = f"base_{self.theme_mode}.png"

        self.harvester.theme_mode = self.theme_mode

        # Optimize harvester: only animate in default mode to save CPU
        if self.theme_mode == "default":
            self.harvester.timer.start(30)
            # Restore per-tab glow for current tab
            tab = self._current_tab.lower()
            if tab == "scan":
                self.harvester.activate_layer("eye_glow.png")
            elif tab == "optimizer":
                self.harvester.activate_layer("veins_glow.png")
            elif tab == "performance":
                self.harvester.activate_layer("armor_glow.png")
            elif tab == "hardware":
                self.harvester.activate_layer("armor_edges.png")
            elif tab in ("tools", "system"):
                self.harvester.activate_layer("aura_full.png")
            else:
                self.harvester.activate_layer(None)
        else:
            self.harvester.timer.stop()
            # Clear glow layer — with the timer stopped, any glow would
            # freeze at partial opacity as a visible artifact.
            self.harvester.activate_layer(None)

        self.bg.bg_img = QPixmap(os.path.join(ASSET_PATH, bg_name))
        self.bg.frame_img = QPixmap(os.path.join(ASSET_PATH, frame_name))

        base_layer = self.harvester.layers.get("base.png")
        if base_layer:
            new_path = os.path.join(ASSET_PATH, base_name)
            if os.path.exists(new_path):
                base_layer.setPixmap(QPixmap(new_path))
            self.harvester.effects["base.png"].setOpacity(1.0)

        for name, eff in self.harvester.effects.items():
            if name != "base.png":
                eff.setOpacity(0.0)

        if hasattr(self.tabs, "set_theme_mode"):
            self.tabs.set_theme_mode(self.theme_mode)
        self.tabs.refresh_colors()

        palette = self._theme_color_rgb()
        for panel in (self.utility, self.holo, self.notes):
            if hasattr(panel, "apply_theme"):
                panel.apply_theme(palette)
            panel.update()

        self.bg.update()
        self._style_top_buttons()

        # Style Context Menus (Right-Click) to be solid instead of transparent
        app = QApplication.instance()
        if app:
            app.setStyleSheet(HOLO_NOTES_FONT_QSS + menu_qss(self.theme_mode))

        if self.theme_mode == "default":
            for w in (self.utility, self.holo, self.notes):
                if hasattr(w, "timer"):
                    w.timer.start(30)

        if self._opt_buttons:
            self._refresh_optimizer_styles()
        if self._home_buttons:
            self._refresh_home_styles()
        if self._hw_buttons:
            self._refresh_hardware_styles()
        if self._tools_buttons:
            self._refresh_tools_styles()
        if self._system_buttons:
            self._refresh_system_styles()
        if self._scan_buttons:
            self._refresh_scan_styles()
        if self._perf_buttons:
            self._refresh_performance_styles()
        # Update theme icon to show current mode
        icon_map = {"default": "👁", "dark": "🌙", "light": "☀️"}
        self.btn_theme.setText(icon_map.get(self.theme_mode, "👁"))
        self._refresh_panel_text_colors()

        # QListWidget items use item.setForeground() — not stylesheet —
        # so _refresh_panel_text_colors() doesn't touch them. Re-render
        # the optimizer list with the new palette colors.
        if self._current_tab == "Optimizer" and self._opt_list is not None:
            try:
                all_procs = self._opt_last_snapshot.get("all_processes", [])
                if all_procs:
                    self._render_process_list(all_procs)
            except (RuntimeError, AttributeError):
                pass

    def _refresh_panel_text_colors(self):
        """Updates dynamically created text/tables so they don't get stuck on old theme colors."""
        palette = self._theme_color_rgb()
        tr, tg, tb = palette["text"]
        r, g, b = palette["accent"]
        bg_r, bg_g, bg_b = palette["bg"]

        if self.theme_mode == "light":
            txt_color = "rgb(0, 0, 0)"
        else:
            txt_color = f"rgb({tr},{tg},{tb})"

        from PyQt6.QtWidgets import QTextBrowser
        color_re = re.compile(r'(?<![-\w])color:\s*[^;]+;?')

        for panel in (self.utility, self.holo, self.notes):
            if not hasattr(panel, "content"):
                continue

            # ---- QLabels (flat stylesheets) ----
            for lbl in panel.content.findChildren(QLabel):
                if isinstance(lbl.parent(), QWidget) and "LiveMonitor" in str(lbl.parent().__class__):
                    continue
                style = color_re.sub('', lbl.styleSheet())
                lbl.setStyleSheet(f"{style} color: {txt_color};")

            # ---- QTextBrowser (selector-scoped stylesheet: QTextBrowser { color: ... }) ----
            for browser in panel.content.findChildren(QTextBrowser):
                style = browser.styleSheet()
                new_style, n = color_re.subn(f'color: {txt_color};', style)
                if n == 0:
                    # No color in the stylesheet at all — append a top-level default.
                    new_style = f"{style} color: {txt_color};"
                browser.setStyleSheet(new_style)

            # ---- QTableWidgets (unchanged) ----
            for table in panel.content.findChildren(QTableWidget):
                if bg_r > 150:
                    tbl_bg = "rgb(232, 234, 238)"; tbl_text = "rgb(0, 0, 0)"
                    tbl_grid = "rgba(120, 125, 132, 80)"
                    hdr_bg = "rgb(160, 165, 172)"; hdr_text = "rgb(0, 0, 0)"
                else:
                    tbl_bg = "rgba(0,0,0,90)"; tbl_text = "rgb(225, 230, 238)"
                    tbl_grid = f"rgba({r},{g},{b},60)"
                    hdr_bg = f"rgba({r},{g},{b},80)"; hdr_text = "black"
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

            # ---- Custom-paint children (Scan ring, mini ring) ----
            # Their paintEvent reads the live palette, but the parent's update()
            # doesn't reliably cascade for translucent parents.
            for child in panel.content.findChildren(QWidget):
                if type(child) in (ScanProgressRing, MiniCompleteRing):
                    child.update()

    def _open_tab(self, name: str):
        # ---- Cancel any in-flight work from the previous tab ----
        prev_tab = self._current_tab
        if prev_tab == "Scan":
            try:
                self.scan_ctrl.cancel_scan()
            except Exception:
                pass
            if self._scan_cancel_timer is not None:
                try: self._scan_cancel_timer.stop()
                except Exception: pass
                self._scan_cancel_timer = None
        if prev_tab == "Performance":
            if self._perf_live_timer is not None:
                try: self._perf_live_timer.stop()
                except Exception: pass
                self._perf_live_timer = None
            self._perf_test_running = False
        # -----------------------------------------------------------
        # Reset per-tab refs BEFORE clearing panels so queued signals
        # do not touch deleted widgets.
        self._current_tab = name
        self._opt_buttons = []
        self._opt_list = None
        self._opt_status_label = None
        self._opt_summary_label = None
        self._opt_notes_label = None
        self._home_buttons = []
        self._hw_buttons = []
        self._tools_buttons = []
        self._tools_action_buttons = []
        self._tools_action_layout = None
        self._tools_current = ""
        self._tools_table = None
        self._tools_selected_row = None
        self._tools_notes_label = None
        self._scan_buttons = []
        self._scan_progress_widget = None
        self._scan_result_view = None
        self._scan_cancel_timer = None
        self._perf_buttons = []
        self._perf_view = None
        self._perf_test_running = False
        if self._perf_live_timer is not None:
            try:
                self._perf_live_timer.stop()
            except Exception:
                pass
            self._perf_live_timer = None
        self._system_buttons = []
        self._system_action_buttons = []
        self._system_action_layout = None
        self._system_current = ""
        self._system_table = None
        self._system_selected_row = None
        self._system_notes_label = None

        self.utility.setVisible(True); self.notes.setVisible(True)
        self.utility.start_pulse();    self.notes.start_pulse()

        self.holo.set_about(False)
        if name.lower() == "optimizer":
            self.holo.set_shape("circle")
        else:
            self.holo.set_shape("square")
        self.holo.start_pulse()

        self.utility.clear_content()
        self.notes.clear_content()
        self.holo.clear_lines()

        tab = name.lower()

        # Harvester glow per tab — ONLY in default theme.
        # In dark/light mode the pulse timer is stopped, so setting a glow
        # layer would leave it frozen at partial opacity forever (visible
        # as a stray glow layer over the base image).
        if self.theme_mode == "default":
            if tab == "scan":
                self.harvester.activate_layer("eye_glow.png")
            elif tab == "optimizer":
                self.harvester.activate_layer("veins_glow.png")
            elif tab == "performance":
                self.harvester.activate_layer("armor_glow.png")
            elif tab == "hardware":
                self.harvester.activate_layer("armor_edges.png")
            elif tab in ("tools", "system"):
                self.harvester.activate_layer("aura_full.png")
            else:
                self.harvester.activate_layer(None)
        else:
            self.harvester.activate_layer(None)

        # Tab content
        if tab == "optimizer":
            self._setup_optimizer_tab()
        elif tab == "home":
            self._setup_home_tab()
        elif tab == "hardware":
            self._setup_hardware_tab()
        elif tab == "tools":
            self._setup_tools_tab()
        elif tab == "system":
            self._setup_system_tab()
        elif tab == "scan":
            self._setup_scan_tab()
        elif tab == "performance":
            self._setup_performance_tab()
        else:
            self._setup_placeholder_tab(name)

    # ---- placeholder
    def _setup_placeholder_tab(self, name: str):
        palette = self._theme_color_rgb()
        tr, tg, tb = palette["text"]

        lbl = QLabel(f"{name.upper()} — Utility\n(coming soon)")
        lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        lbl.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 12px;")
        lbl.setWordWrap(True)
        self.utility.content_layout.addWidget(lbl)
        self.utility.show_content()

        notes_lbl = QLabel(f"{name} — notes will appear here.")
        notes_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        notes_lbl.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 12px;")
        notes_lbl.setWordWrap(True)
        self.notes.content_layout.addWidget(notes_lbl)
        self.notes.show_content()

    # ============================================================
    # SHARED
    # ============================================================

    def _on_simple_error(self, title, message):
        QMessageBox.warning(self, title, message)

    # ============================================================
    # HOME TAB
    # ============================================================

    def _setup_home_tab(self):
        palette = self._theme_color_rgb()
        tr, tg, tb = palette["text"]

        self._home_buttons = []

        btn_about = QPushButton("About")
        btn_contact = QPushButton("Contact")
        for btn in (btn_about, btn_contact):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(button_qss(palette, self.theme_mode))
            self.utility.content_layout.addWidget(btn)
            self._home_buttons.append(btn)

        btn_about.clicked.connect(self._home_about)
        btn_contact.clicked.connect(self._home_contact)

        self.utility.content_layout.addStretch(1)
        self.utility.show_content()

        notes = QLabel(
            "HOME\n\n"
            "Phantom Optimizer is an offline-first\n"
            "system utility.\n\n"
            "It reads your system state, identifies\n"
            "heavy processes, and offers controlled\n"
            "actions.\n\n"
            "No data leaves your machine."
        )
        notes.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        notes.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 12px;")
        notes.setWordWrap(True)
        self.notes.content_layout.addWidget(notes)
        self.notes.show_content()

        self.holo.set_lines(["HOME", "", "Loading system info…"])
        self.home_ctrl.load()

    def _home_about(self):
        QMessageBox.information(
            self, "About Phantom Optimizer",
            "Phantom Optimizer V2\n"
            "Offline-first system utility.\n\n"
            "Author: Sobhan Salmani Soula AKA Glory The Architect"
        )

    def _home_contact(self):
        QMessageBox.information(
            self, "Contact",
            "GitHub: https://github.com/glorythearchitect."
            "Direct Contact: @NiceCitizen on Telegram"
        )

    def _on_home_info(self, info):
        if self._current_tab != "Home":
            return

        gpu_names = info.get("gpu_names", []) or []
        primary = info.get("gpu_primary", "")
        primary_vram = info.get("gpu_primary_vram_gb", 0.0)
        gpu_details = info.get("gpu_details", []) or []

        if not gpu_names:
            gpu_lines = ["GPU:     Unavailable"]
        else:
            # Use rich data if available (newer backend)
            if primary and primary != "Unavailable":
                vram_part = f"  ({primary_vram} GB)" if primary_vram else ""
                gpu_lines = [f"GPU:     {primary}{vram_part}"]
                for g in gpu_details:
                    name = g.get("name", "?")
                    if name != primary:
                        kind = g.get("kind", "")
                        kind_part = f"  [{kind}]" if kind else ""
                        gpu_lines.append(f"         {name}{kind_part}")
            else:
                # Fallback for older backend
                gpu_lines = [f"GPU:     {gpu_names[0]}"]
                for g in gpu_names[1:]:
                    gpu_lines.append(f"         {g}")

        ram = info.get("ram_total_gb", 0)
        disk_total = info.get("disk_total_gb", 0)
        disk_free = info.get("disk_free_gb", 0)

        lines = [
            f"USER:    {info.get('username', 'Unavailable')}",
            f"DEVICE:  {info.get('device_name', 'Unavailable')}",
            "",
            f"CPU:     {info.get('cpu_name', 'Unavailable')}",
            *gpu_lines,
            f"WINDOWS: {info.get('windows', 'Unavailable')}",
            "",
            f"RAM:     {ram} GB",
            f"DISK:    {disk_total} GB total  |  {disk_free} GB free",
        ]
        self._holo_show_text("HOME", "\n".join(lines))

    def _refresh_home_styles(self):
        palette = self._theme_color_rgb()
        for btn in list(self._home_buttons):
            try:
                btn.setStyleSheet(button_qss(palette, self.theme_mode))
            except RuntimeError:
                pass

    # ============================================================
    # HARDWARE TAB
    # ============================================================

    def _setup_hardware_tab(self):
        palette = self._theme_color_rgb()
        tr, tg, tb = palette["text"]

        self._hw_buttons = []

        for cat in CATEGORIES:
            b = QPushButton(cat)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True)
            b.setStyleSheet(button_qss(palette, self.theme_mode))
            b.clicked.connect(lambda _, c=cat: self._hw_load(c))
            self.utility.content_layout.addWidget(b)
            self._hw_buttons.append((cat, b))

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setStyleSheet(button_qss(palette, self.theme_mode))
        btn_refresh.clicked.connect(lambda: self._hw_load(self._hw_selected))
        self.utility.content_layout.addWidget(btn_refresh)
        self._hw_buttons.append(("Refresh", btn_refresh))

        self.utility.content_layout.addStretch(1)
        self.utility.show_content()

        notes = QLabel(
            "HARDWARE INFO\n\n"
            "Read-only overview of detected\n"
            "hardware and system components.\n\n"
            "No modification is performed from\n"
            "this panel."
        )
        notes.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        notes.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 12px;")
        notes.setWordWrap(True)
        self.notes.content_layout.addWidget(notes)
        self.notes.show_content()

        self.holo.set_lines([self._hw_selected, "", "Loading…"])
        self._hw_load(self._hw_selected)

    def _hw_load(self, category):
        self._hw_selected = category
        for cat, btn in self._hw_buttons:
            if cat == "Refresh":
                continue
            try:
                btn.setChecked(cat == category)
            except RuntimeError:
                pass
        self.holo.set_lines([category, "", "Loading…"])
        self.hardware_ctrl.load_category(category)

    def _on_hw_category(self, category, data):
        if self._current_tab != "Hardware":
            return

        kind = data.get("kind", "text")
        payload = data.get("payload", "")

        if kind == "table":
            self._holo_show_table(category, payload or [])
        else:
            self._holo_show_text(category, payload or "")

    def _holo_show_text(self, title, text):
        """Word-wrapped, scrollable text inside Holo."""
        palette = self._theme_color_rgb()
        tr, tg, tb = palette["text"]

        def _esc(s):
            return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        escaped = _esc(text).replace("\n", "<br>")
        html = f"<b>{_esc(title)}</b><br><br>{escaped}"

        from PyQt6.QtWidgets import QTextBrowser

        browser = QTextBrowser()
        browser.setHtml(html)
        browser.setOpenExternalLinks(False)
        browser.setStyleSheet(
            f"QTextBrowser {{ color: rgb({tr},{tg},{tb}); font-size: 14px; "
            f"background: transparent; border: none; }}"
        )

        self.holo.set_content_widget(browser)

    def _holo_show_table(self, title, rows):
        """Event logs table inside Holo. Retained for later Tools/System use."""
        palette = self._theme_color_rgb()
        r, g, b = palette["accent"]
        tr, tg, tb = palette["text"]

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Time", "Source", "Message"])
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
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        for i, row in enumerate(rows):
            try:
                t, src, msg = row
            except Exception:
                t, src, msg = "", "", str(row)
            table.setItem(i, 0, QTableWidgetItem(str(t)))
            table.setItem(i, 1, QTableWidgetItem(str(src)))
            table.setItem(i, 2, QTableWidgetItem(str(msg)))

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title_lbl = QLabel(f"<b>{title}</b>  ({len(rows)} events)")
        title_lbl.setStyleSheet(
            f"color: rgb({tr},{tg},{tb}); font-size: 12px; background: transparent;"
        )
        layout.addWidget(title_lbl)
        layout.addWidget(table, 1)

        self.holo.set_content_widget(container)

    def _refresh_hardware_styles(self):
        palette = self._theme_color_rgb()
        for cat, btn in list(self._hw_buttons):
            try:
                btn.setStyleSheet(button_qss(palette, self.theme_mode))
            except RuntimeError:
                pass

    # ============================================================
    # GENERIC DATA TABLE (used by Tools / System)
    # ============================================================

    def _holo_show_data_table(self, title, columns, rows,
                              on_select=None, checkable=None):
        palette = self._theme_color_rgb()
        r, g, b = palette["accent"]
        tr, tg, tb = palette["text"]

        has_check = checkable is not None and len(checkable) == len(rows)
        col_offset = 1 if has_check else 0

        table = QTableWidget()
        table.setColumnCount(len(columns) + col_offset)
        if has_check:
            table.setHorizontalHeaderLabels(["✓"] + list(columns))
        else:
            table.setHorizontalHeaderLabels(list(columns))
        table.setRowCount(len(rows))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
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
        if has_check:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            for i in range(1, len(columns) + 1):
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            if len(columns) > 0:
                header.setSectionResizeMode(len(columns), QHeaderView.ResizeMode.Stretch)
        else:
            for i in range(len(columns)):
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            if len(columns) > 0:
                header.setSectionResizeMode(len(columns) - 1, QHeaderView.ResizeMode.Stretch)

        for i, row in enumerate(rows):
            if has_check:
                chk = QTableWidgetItem()
                if checkable[i]:
                    chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                    chk.setCheckState(Qt.CheckState.Unchecked)
                else:
                    chk.setFlags(Qt.ItemFlag.NoItemFlags)
                table.setItem(i, 0, chk)

            for j, val in enumerate(row):
                if j < len(columns):
                    table.setItem(i, j + col_offset,
                                  QTableWidgetItem(str(val) if val is not None else "-"))

        if on_select is not None:
            table.itemSelectionChanged.connect(lambda t=table: on_select(t.currentRow()))

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title_lbl = QLabel(f"<b>{title}</b>  ({len(rows)} rows)")
        title_lbl.setStyleSheet(
            f"color: rgb({tr},{tg},{tb}); font-size: 12px; background: transparent;"
        )
        layout.addWidget(title_lbl)
        layout.addWidget(table, 1)

        self.holo.set_content_widget(container)
        return table

    def _holo_show_startup_table(self, columns, rows):
        """
        Startup Manager table with checkbox column.
        columns: list of display column headers (Command excluded)
        rows:    list of full rows (Name, Location, Status, Command)
        """
        palette = self._theme_color_rgb()
        r, g, b = palette["accent"]
        tr, tg, tb = palette["text"]

        table = QTableWidget()
        table.setColumnCount(len(columns) + 1)
        table.setHorizontalHeaderLabels(["✓"] + list(columns))
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
        for i in range(1, len(columns) + 1):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

        for i, row in enumerate(rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            table.setItem(i, 0, chk)

            for j in range(len(columns)):
                if j < len(row):
                    table.setItem(i, j + 1, QTableWidgetItem(str(row[j])))

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title_lbl = QLabel(f"<b>Startup Manager</b>  ({len(rows)} entries)")
        title_lbl.setStyleSheet(
            f"color: rgb({tr},{tg},{tb}); font-size: 12px; background: transparent;"
        )
        layout.addWidget(title_lbl)
        layout.addWidget(table, 1)

        self.holo.set_content_widget(container)
        return table

    # ============================================================
    # TOOLS TAB
    # ============================================================

    def _setup_tools_tab(self):
        palette = self._theme_color_rgb()
        tr, tg, tb = palette["text"]

        self._tools_buttons = []
        self._tools_current = ""

        for tool in ["Startup Manager", "Cleaner", "Event Logs", "Network Usage"]:
            btn = QPushButton(tool)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(button_qss(palette, self.theme_mode))
            btn.clicked.connect(lambda _, t=tool: self._tools_load(t))
            self.utility.content_layout.addWidget(btn)
            self._tools_buttons.append((tool, btn))

        # Action area (rebuilt per tool)
        action_widget = QWidget()
        self._tools_action_layout = QVBoxLayout(action_widget)
        self._tools_action_layout.setContentsMargins(0, 6, 0, 0)
        self._tools_action_layout.setSpacing(4)
        self.utility.content_layout.addWidget(action_widget)

        self.utility.content_layout.addStretch(1)
        self.utility.show_content()

        self.notes.clear_content()
        self._tools_notes_label = QLabel("TOOLS\n\nSelect a tool from the left.")
        self._tools_notes_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._tools_notes_label.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 12px;")
        self._tools_notes_label.setWordWrap(True)
        self.notes.content_layout.addWidget(self._tools_notes_label)
        self.notes.show_content()

        self._tools_load("Startup Manager")

    def _tools_clear_actions(self):
        if self._tools_action_layout is None:
            return
        while self._tools_action_layout.count():
            item = self._tools_action_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._tools_action_buttons = []

    def _tools_add_action(self, label, handler):
        palette = self._theme_color_rgb()
        btn = QPushButton(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(button_qss(palette, self.theme_mode))
        btn.clicked.connect(handler)
        self._tools_action_layout.addWidget(btn)
        self._tools_action_buttons.append(btn)

    def _tools_set_notes(self, title, body):
        if self._tools_notes_label is None:
            return
        palette = self._theme_color_rgb()
        tr, tg, tb = palette["text"]
        try:
            self._tools_notes_label.setText(f"{title}\n\n{body}")
        except RuntimeError:
            self._tools_notes_label = None

    def _tools_load(self, tool):
        self._tools_current = tool
        for name, btn in self._tools_buttons:
            try:
                btn.setChecked(name == tool)
            except RuntimeError:
                pass

        self._tools_clear_actions()
        self._tools_selected_row = None

        if tool == "Startup Manager":
            self._tools_add_action("Enable Selected", self._on_startup_enable)
            self._tools_add_action("Disable Selected", self._on_startup_disable)
            self._tools_add_action("View Full Details", self._on_startup_view_full)
            self._tools_add_action("Refresh", self._on_startup_refresh)
            self._tools_set_notes("STARTUP MANAGER",
                "Check entries, then Enable / Disable.\n\n"
                "Enable / Disable are reversible.\n"
                "Use View Full Details to read the\n"
                "full command for any entry.")
            self.holo.set_lines(["Startup Manager", "", "Loading…"])
            self.tools_ctrl.load_startup()

        elif tool == "Cleaner":
            self._tools_add_action("Scan", self._on_cleaner_scan)
            self._tools_add_action("Clean Now", self._on_cleaner_execute)
            self._tools_set_notes("CLEANER",
                "Scans safe temporary and cache\n"
                "locations.\n\n"
                "Clean Now deletes the selected\n"
                "cached data — this cannot be\n"
                "undone.")
            self.holo.set_lines(["Cleaner", "", "Scanning…"])
            self.tools_ctrl.load_cleaner()

        elif tool == "Event Logs":
            self._tools_add_action("Refresh", self._on_event_logs_refresh)
            self._tools_add_action("Export TXT (100)", self._on_event_logs_export_txt)
            self._tools_add_action("Export CSV (100)", self._on_event_logs_export_csv)
            self._tools_set_notes("EVENT LOGS",
                "Last 50 system warnings and\n"
                "errors shown.\n\n"
                "Export pulls the last 100 from\n"
                "the Windows Event Viewer\n"
                "as TXT or CSV.")
            self.holo.set_lines(["Event Logs", "", "Loading…"])
            self.tools_ctrl.load_event_logs()

        elif tool == "Network Usage":
            self._tools_add_action("Kill Selected", self._on_network_kill_selected)
            self._tools_add_action("Refresh", self._on_network_refresh)
            self._tools_add_action("Open Resource Monitor", self._on_network_open_resmon)
            self._tools_set_notes("NETWORK USAGE",
                "Connection information only.\n"
                "Per-process bandwidth measurement\n"
                "is not available in this version.\n\n"
                "Open Windows Resource Monitor\n"
                "for bandwidth details.")
            self.holo.set_lines(["Network Usage", "", "Loading…"])
            self.tools_ctrl.load_network()

    # ---- Startup Manager handlers
    def _on_startup_refresh(self):
        self.tools_ctrl.load_startup()

    def _get_checked_startup_items(self):
        items = []
        if self._tools_table is None:
            return items
        for row in range(self._tools_table.rowCount()):
            chk = self._tools_table.item(row, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                name_item = self._tools_table.item(row, 1)
                loc_item = self._tools_table.item(row, 2)
                if name_item and loc_item:
                    items.append((name_item.text(), loc_item.text()))
        return items

    def _on_startup_enable(self):
        items = self._get_checked_startup_items()
        if not items:
            QMessageBox.information(self, "Startup Manager",
                                    "Check at least one entry first.")
            return
        self.tools_ctrl.toggle_startup_batch(items, enable=True)

    def _on_startup_disable(self):
        items = self._get_checked_startup_items()
        if not items:
            QMessageBox.information(self, "Startup Manager",
                                    "Check at least one entry first.")
            return
        self.tools_ctrl.toggle_startup_batch(items, enable=False)

    def _on_startup_view_full(self):
        if not self._tools_startup_rows:
            QMessageBox.information(self, "Startup Manager",
                                    "No data to view. Click Refresh first.")
            return
        dlg = StartupDetailsDialog(
            self._tools_startup_rows,
            self._theme_color_rgb(),
            self,
        )
        dlg.exec()

    # ---- Cleaner handlers
    def _on_cleaner_scan(self):
        self.tools_ctrl.load_cleaner()

    def _on_cleaner_execute(self):
        reply = QMessageBox.question(
            self, "Confirm Cleanup",
            "Delete cached files and temporary data?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.tools_ctrl.execute_cleaner()

    # ---- Event Logs / Network handlers
    def _on_event_logs_refresh(self):
        self.tools_ctrl.load_event_logs()

    def _on_event_logs_export_txt(self):
        self.tools_ctrl.export_event_logs("txt")

    def _on_event_logs_export_csv(self):
        self.tools_ctrl.export_event_logs("csv")

    def _on_event_logs_export_ready(self, logs, fmt):
        from datetime import datetime
        default_name = (
            f"phantom_event_logs_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"
        )
        filters = {
            "txt": "Text Files (*.txt)",
            "csv": "CSV Files (*.csv)",
        }
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export Event Logs ({fmt.upper()})",
            default_name, filters.get(fmt, "All Files (*.*)"),
        )
        if not path:
            return
        try:
            if fmt == "txt":
                with open(path, "w", encoding="utf-8") as f:
                    f.write("Phantom Optimizer — Event Logs Export\n")
                    f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Entries:   {len(logs)}\n")
                    f.write("=" * 80 + "\n\n")
                    for t, src, msg in logs:
                        f.write(f"Time:    {t}\n")
                        f.write(f"Source:  {src}\n")
                        f.write(f"Message: {msg}\n")
                        f.write("-" * 80 + "\n")
            elif fmt == "csv":
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Time", "Source", "Message"])
                    for row in logs:
                        writer.writerow(row)
            QMessageBox.information(
                self, "Export Complete",
                f"Exported {len(logs)} events to:\n{path}"
            )
        except Exception as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _on_network_refresh(self):
        self.tools_ctrl.load_network()

    def _on_network_open_resmon(self):
        import subprocess
        try:
            subprocess.Popen(["resmon.exe"])
        except Exception as e:
            QMessageBox.warning(self, "Resource Monitor",
                                f"Could not launch Resource Monitor:\n{e}")

    def _on_network_kill_selected(self):
        if self._tools_table is None:
            return
        pairs = []
        for row in range(self._tools_table.rowCount()):
            chk = self._tools_table.item(row, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                name_item = self._tools_table.item(row, 1)
                pid_item = self._tools_table.item(row, 2)
                if name_item and pid_item:
                    try:
                        pid = int(pid_item.text())
                    except (ValueError, TypeError):
                        continue
                    pairs.append((pid, name_item.text()))
        if not pairs:
            QMessageBox.information(self, "Network Usage",
                                    "Check at least one process first.")
            return
        preview = "\n".join(f"{n} (PID {p})" for p, n in pairs)
        reply = QMessageBox.question(
            self, "Confirm Kill",
            f"Terminate the following processes?\n\n{preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.tools_ctrl.kill_network_process(pairs)

    # ---- Tools controller signal handlers
    def _on_tools_content(self, tool_name, data):
        if self._current_tab != "Tools":
            return
        kind = data.get("kind", "text")

        if tool_name == "Startup Manager":
            rows = data.get("rows", []) or []
            self._tools_startup_rows = rows
            self._tools_table = self._holo_show_startup_table(
                ["Name", "Location", "Status"],
                rows,
            )
            return

        if kind == "checkable_table":
            rows = data.get("rows", []) or []
            if not rows:
                self._tools_table = None
                self._holo_show_text(
                    "Network Usage",
                    "No network connections detected."
                )
                return
            self._tools_table = self._holo_show_data_table(
                tool_name,
                data.get("columns", []),
                rows,
                checkable=data.get("checkable", []) or None,
            )
        elif kind == "table":
            self._tools_table = self._holo_show_data_table(
                tool_name,
                data.get("columns", []),
                data.get("rows", []),
            )
        else:
            self._tools_table = None
            self._holo_show_text(tool_name, data.get("payload", ""))

    def _on_tools_action_done(self, action, success, message):
        if not success:
            QMessageBox.warning(self, action, message)
            return  # Don't reload on failure — let user see the error
        # Reload current tool so the user sees updated state
        QTimer.singleShot(0, self._reload_current_tool)

    def _on_tools_kill_finished(self, results):
        if not results:
            return
        completed = sum(1 for r in results if r["status"] in ("terminated", "killed"))
        blocked   = sum(1 for r in results if r["status"] in ("protected", "self_protected"))
        denied    = sum(1 for r in results if r["status"] == "access_denied")
        failed    = sum(1 for r in results if r["status"] in ("failed", "not_found"))

        lines = [f"Selected:  {len(results)}", f"Completed: {completed}"]
        if blocked:
            lines.append(f"Blocked:   {blocked}")
        if denied:
            lines.append(f"Denied:    {denied}")
        if failed:
            lines.append(f"Failed:    {failed}")
            lines.append("")
            for r in results:
                if r["status"] in ("failed", "not_found") and r.get("detail"):
                    lines.append(f"  • {r['name']} ({r['pid']}): {r['detail']}")
        QMessageBox.information(self, "Kill Result", "\n".join(lines))
        QTimer.singleShot(0, self._reload_current_tool)

    def _reload_current_tool(self):
        if self._current_tab != "Tools":
            return
        t = self._tools_current
        if t == "Startup Manager":
            self.tools_ctrl.load_startup()
        elif t == "Cleaner":
            self.tools_ctrl.load_cleaner()
        elif t == "Event Logs":
            self.tools_ctrl.load_event_logs()
        elif t == "Network Usage":
            self.tools_ctrl.load_network()

    def _on_tools_op_started(self, op_name):
        for _, btn in self._tools_buttons:
            try:
                btn.setEnabled(False)
            except RuntimeError:
                pass
        for btn in self._tools_action_buttons:
            try:
                btn.setEnabled(False)
            except RuntimeError:
                pass

    def _on_tools_op_finished(self, op_name):
        for _, btn in self._tools_buttons:
            try:
                btn.setEnabled(True)
            except RuntimeError:
                pass
        for btn in self._tools_action_buttons:
            try:
                btn.setEnabled(True)
            except RuntimeError:
                pass

    def _refresh_tools_styles(self):
        palette = self._theme_color_rgb()
        for _, btn in list(self._tools_buttons):
            try:
                btn.setStyleSheet(button_qss(palette, self.theme_mode))
            except RuntimeError:
                pass
        for btn in list(self._tools_action_buttons):
            try:
                btn.setStyleSheet(button_qss(palette, self.theme_mode))
            except RuntimeError:
                pass

    # ============================================================
    # SYSTEM TAB
    # ============================================================

    def _setup_system_tab(self):
        palette = self._theme_color_rgb()
        tr, tg, tb = palette["text"]

        self._system_buttons = []
        self._system_current = ""

        for name in ["Power", "Privacy", "Windows Update", "Admin", "Safe Mode", "Shutdown"]:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(button_qss(palette, self.theme_mode))
            btn.clicked.connect(lambda _, n=name: self._system_load(n))
            self.utility.content_layout.addWidget(btn)
            self._system_buttons.append((name, btn))

        action_widget = QWidget()
        self._system_action_layout = QVBoxLayout(action_widget)
        self._system_action_layout.setContentsMargins(0, 6, 0, 0)
        self._system_action_layout.setSpacing(4)
        self.utility.content_layout.addWidget(action_widget)

        self.utility.content_layout.addStretch(1)
        self.utility.show_content()

        self.notes.clear_content()
        self._system_notes_label = QLabel("SYSTEM\n\nSelect a system function from the left.")
        self._system_notes_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._system_notes_label.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 12px;")
        self._system_notes_label.setWordWrap(True)
        self.notes.content_layout.addWidget(self._system_notes_label)
        self.notes.show_content()

        self._system_load("Power")

    def _system_clear_actions(self):
        if self._system_action_layout is None:
            return
        while self._system_action_layout.count():
            item = self._system_action_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._system_action_buttons = []

    def _system_add_action(self, label, handler):
        palette = self._theme_color_rgb()
        btn = QPushButton(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(button_qss(palette, self.theme_mode))
        btn.clicked.connect(handler)
        self._system_action_layout.addWidget(btn)
        self._system_action_buttons.append(btn)

    def _system_set_notes(self, title, body):
        if self._system_notes_label is None:
            return
        try:
            self._system_notes_label.setText(f"{title}\n\n{body}")
        except RuntimeError:
            self._system_notes_label = None

    def _system_load(self, name):
        self._system_current = name
        for n, btn in self._system_buttons:
            try:
                btn.setChecked(n == name)
            except RuntimeError:
                pass

        self._system_clear_actions()
        self._system_selected_row = None
        self._system_table = None

        if name == "Power":
            self._system_add_action("Activate Selected", self._on_power_activate)
            self._system_add_action("Auto Switch (AC/Battery)", self._on_power_auto)
            self._system_add_action("Refresh", self._on_power_refresh)
            self._system_set_notes("POWER",
                "Select a plan and activate it.\n\n"
                "Auto Switch picks Balanced on\n"
                "AC and Power Saver on Battery.")
            self.holo.set_lines(["Power", "", "Loading…"])
            self.system_ctrl.load_power()

        elif name == "Privacy":
            self._system_add_action("Enable All", self._on_privacy_enable)
            self._system_add_action("Disable All", self._on_privacy_disable)
            self._system_add_action("Refresh", self._on_privacy_refresh)
            self._system_set_notes("PRIVACY",
                "Toggles Windows telemetry, ads,\n"
                "and tracking settings.\n\n"
                "All changes are reversible.")
            self.holo.set_lines(["Privacy", "", "Loading…"])
            self.system_ctrl.load_privacy()

        elif name == "Windows Update":
            self._system_add_action("Pause (7 days)", self._on_update_pause)
            self._system_add_action("Refresh", self._on_update_refresh)
            self._system_set_notes("WINDOWS UPDATE",
                "Pause defers updates for 7 days.\n"
                "Updates resume automatically after\n"
                "that period, or sooner via Windows\n"
                "Settings.")
            self.holo.set_lines(["Windows Update", "", "Loading…"])
            self.system_ctrl.load_update()

        elif name == "Admin":
            self._system_add_action("Refresh", self._on_admin_refresh)
            self._system_set_notes("ADMIN",
                "Phantom Optimizer requests\n"
                "elevation at startup.\n\n"
                "This panel is read-only.")
            self.holo.set_lines(["Admin", "", "Loading…"])
            self.system_ctrl.load_admin()

        elif name == "Safe Mode":
            self._system_add_action("Enter Safe Mode", self._on_safe_mode_enter)
            self._system_add_action("Exit Safe Mode", self._on_safe_mode_exit)
            self._system_set_notes("SAFE MODE",
                "Enter: reboots into Safe Mode.\n"
                "Exit: reboots to normal mode.\n\n"
                "To leave Safe Mode, relaunch\n"
                "Phantom Optimizer there and\n"
                "click Exit Safe Mode.\n\n"
                "Manual fallback (admin CMD):\n"
                "bcdedit /deletevalue {current}\n"
                "safeboot\n"
                "shutdown /r /t 0")

        elif name == "Shutdown":
            self._system_add_action("Shutdown Now", self._on_shutdown_now)
            self._system_add_action("Restart Now", self._on_restart_now)
            self._system_add_action("Cancel Pending", self._on_shutdown_cancel)
            self._system_set_notes("SHUTDOWN",
                "Windows closes open apps and\n"
                "shuts down after 5 seconds.\n\n"
                "Unsaved work may be lost.")
            self.holo.set_lines(["Shutdown", "", "Loading…"])
            self.system_ctrl.load_shutdown()

    # ---- Power handlers
    def _on_power_refresh(self):
        self.system_ctrl.load_power()

    def _on_power_activate(self):
        if self._system_table is None or self._system_selected_row is None:
            QMessageBox.information(self, "Power", "Select a plan first.")
            return
        # _system_selected_row stores (name, guid)
        guid = self._system_selected_row[1]
        self.system_ctrl.set_power_plan(guid)

    def _on_power_auto(self):
        self.system_ctrl.auto_switch_power()

    def _on_power_row_selected(self, row):
        if self._system_table is None or row < 0:
            self._system_selected_row = None
            return
        name_item = self._system_table.item(row, 0)
        guid_item = self._system_table.item(row, 1)
        if name_item and guid_item:
            self._system_selected_row = (name_item.text(), guid_item.text())
        else:
            self._system_selected_row = None

    # ---- Privacy handlers
    def _on_privacy_refresh(self):
        self.system_ctrl.load_privacy()

    def _on_privacy_enable(self):
        self.system_ctrl.set_privacy_all(True)

    def _on_privacy_disable(self):
        self.system_ctrl.set_privacy_all(False)

    # ---- Update handlers
    def _on_update_refresh(self):
        self.system_ctrl.load_update()

    def _on_update_pause(self):
        self.system_ctrl.pause_updates(7)

    # ---- Admin handlers
    def _on_admin_refresh(self):
        self.system_ctrl.load_admin()

    # ---- Safe Mode handlers
    def _on_safe_mode_enter(self):
        reply = QMessageBox.warning(
            self, "Enter Safe Mode",
            "The system will restart into Safe Mode in 5 seconds.\n\n"
            "To exit Safe Mode:\n"
            "  1. Relaunch Phantom Optimizer from Safe Mode\n"
            "  2. Click System → Safe Mode → Exit Safe Mode\n\n"
            "If Phantom Optimizer cannot launch, use admin CMD:\n"
            "  bcdedit /deletevalue {current} safeboot\n"
            "  shutdown /r /t 0\n\n"
            "Save your work before continuing.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.system_ctrl.enter_safe_mode()

    def _on_safe_mode_exit(self):
        reply = QMessageBox.question(
            self, "Exit Safe Mode",
            "The Safe Mode boot flag will be cleared and the system\n"
            "will restart into normal mode in 5 seconds.\n\n"
            "Save your work before continuing.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.system_ctrl.exit_safe_mode()

    # ---- Shutdown handlers
    def _on_shutdown_now(self):
        reply = QMessageBox.question(
            self, "Shutdown",
            "Shut down the system in 5 seconds?\n\nUnsaved work may be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.system_ctrl.execute_shutdown(restart=False)

    def _on_restart_now(self):
        reply = QMessageBox.question(
            self, "Restart",
            "Restart the system in 5 seconds?\n\nUnsaved work may be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.system_ctrl.execute_shutdown(restart=True)

    def _on_shutdown_cancel(self):
        from shutdown.safe_shutdown import cancel_shutdown
        try:
            r = cancel_shutdown()
            if r.get("success"):
                QMessageBox.information(self, "Shutdown", r.get("detail", "Cancelled."))
            else:
                QMessageBox.warning(self, "Shutdown", r.get("detail", "Cancel failed."))
        except Exception as e:
            QMessageBox.warning(self, "Shutdown", str(e))

    # ---- System controller signal handlers
    def _on_system_content(self, name, data):
        if self._current_tab != "System":
            return
        kind = data.get("kind", "text")
        if kind == "table":
            rows = data.get("rows", []) or []
            if name == "Power" and not rows:
                self._system_table = None
                self._holo_show_text(
                    "Power",
                    "No power plans detected.\n\n"
                    "Run 'powercfg /L' in a terminal to verify "
                    "Windows is responding to power queries."
                )
                return
            self._system_table = self._holo_show_data_table(
                name,
                data.get("columns", []),
                rows,
                on_select=self._on_power_row_selected if name == "Power" else None,
            )
        else:
            self._system_table = None
            self._holo_show_text(name, data.get("payload", ""))

    def _on_system_action_done(self, action, success, message):
        if not success:
            QMessageBox.warning(self, action, message)
            return
        QTimer.singleShot(0, self._reload_current_system)

    def _reload_current_system(self):
        if self._current_tab != "System":
            return
        n = self._system_current
        if n == "Power":
            self.system_ctrl.load_power()
        elif n == "Privacy":
            self.system_ctrl.load_privacy()
        elif n == "Windows Update":
            self.system_ctrl.load_update()
        elif n == "Admin":
            self.system_ctrl.load_admin()
        elif n == "Safe Mode":
            self.system_ctrl.load_safe_mode()
        elif n == "Shutdown":
            self.system_ctrl.load_shutdown()

    def _on_system_op_started(self, op_name):
        for _, btn in self._system_buttons:
            try:
                btn.setEnabled(False)
            except RuntimeError:
                pass
        for btn in self._system_action_buttons:
            try:
                btn.setEnabled(False)
            except RuntimeError:
                pass

    def _on_system_op_finished(self, op_name):
        for _, btn in self._system_buttons:
            try:
                btn.setEnabled(True)
            except RuntimeError:
                pass
        for btn in self._system_action_buttons:
            try:
                btn.setEnabled(True)
            except RuntimeError:
                pass

    def _refresh_system_styles(self):
        palette = self._theme_color_rgb()
        for _, btn in list(self._system_buttons):
            try:
                btn.setStyleSheet(button_qss(palette, self.theme_mode))
            except RuntimeError:
                pass
        for btn in list(self._system_action_buttons):
            try:
                btn.setStyleSheet(button_qss(palette, self.theme_mode))
            except RuntimeError:
                pass

    # ============================================================
    # SCAN TAB
    # ============================================================

    def _setup_scan_tab(self):
        palette = self._theme_color_rgb()
        tr, tg, tb = palette["text"]

        self._scan_buttons = []
        self._scan_last_type = None
        self._scan_last_software_result = None

        btn_full      = QPushButton("Full Scan")
        btn_phantom   = QPushButton("Phantom Scan")
        btn_software  = QPushButton("Software Scan")
        btn_hardware  = QPushButton("Hardware Scan")
        btn_cancel    = QPushButton("Cancel")
        btn_refresh   = QPushButton("Refresh")
        btn_view_full = QPushButton("View Full Details")

        for btn in (btn_full, btn_phantom, btn_software,
                    btn_hardware, btn_cancel, btn_refresh, btn_view_full):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(button_qss(palette, self.theme_mode))
            self.utility.content_layout.addWidget(btn)
            self._scan_buttons.append(btn)

        # Cancel starts disabled, enabled by 5-second timer
        btn_cancel.setEnabled(False)
        # View Full Details disabled until a software scan completes
        btn_view_full.setEnabled(False)

        btn_full.clicked.connect(lambda: self._start_scan("full"))
        btn_phantom.clicked.connect(lambda: self._start_scan("phantom"))
        btn_software.clicked.connect(lambda: self._start_scan("software"))
        btn_hardware.clicked.connect(lambda: self._start_scan("hardware"))
        btn_cancel.clicked.connect(self._scan_cancel_clicked)
        btn_refresh.clicked.connect(
            lambda: self._start_scan(self._scan_last_type or "full")
        )
        btn_view_full.clicked.connect(self._scan_view_software_full)

        self.utility.content_layout.addStretch(1)
        self.utility.show_content()

        self.notes.clear_content()
        notes_lbl = QLabel(
            "SCAN\n\n"
            "Full — deep system scan.\n"
            "Phantom — quick CPU/RAM/Disk.\n"
            "Software — installed applications.\n"
            "Hardware — connected hardware.\n\n"
            "Cancel unlocks after 5 seconds."
        )
        notes_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        notes_lbl.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 12px;")
        notes_lbl.setWordWrap(True)
        self.notes.content_layout.addWidget(notes_lbl)
        self.notes.show_content()

        self._scan_progress_widget = ScanProgressRing(self._theme_color_rgb)
        self._scan_progress_widget.set_progress(0, "Select a scan to begin.")
        self.holo.set_content_widget(self._scan_progress_widget)

    def _start_scan(self, scan_type):
        self._scan_last_type = scan_type

        # Disable all scan buttons immediately
        for btn in list(self._scan_buttons):
            try:
                btn.setEnabled(False)
            except RuntimeError:
                pass

        # Recreate the ring if it was replaced by a result view
        if self._scan_progress_widget is None:
            self._scan_progress_widget = ScanProgressRing(self._theme_color_rgb)
            self.holo.set_content_widget(self._scan_progress_widget)

        # Reset ring
        try:
            self._scan_progress_widget.reset()
        except RuntimeError:
            self._scan_progress_widget = None

        # Start 5-second cancel timer
        if self._scan_cancel_timer is not None:
            try:
                self._scan_cancel_timer.stop()
            except Exception:
                pass
        self._scan_cancel_timer = QTimer(self)
        self._scan_cancel_timer.setSingleShot(True)
        self._scan_cancel_timer.timeout.connect(self._enable_scan_cancel)
        self._scan_cancel_timer.start(5000)

        self.scan_ctrl.start_scan(scan_type)

    def _enable_scan_cancel(self):
        if len(self._scan_buttons) > 4:
            try:
                self._scan_buttons[4].setEnabled(True)
            except RuntimeError:
                pass

    def _scan_cancel_clicked(self):
        self.scan_ctrl.cancel_scan()

    def _scan_view_software_full(self):
        result = self._scan_last_software_result
        if not result or not result.get("apps"):
            QMessageBox.information(
                self, "Software Scan",
                "No software scan result available.\n\n"
                "Run a Software Scan first."
            )
            return
        try:
            dlg = SoftwareDetailsDialog(
                result.get("apps", []),
                self._theme_color_rgb(),
                self,
            )
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(
                self, "Software Scan",
                f"Could not open details view:\n{e}"
            )

    def _refresh_scan_styles(self):
        palette = self._theme_color_rgb()
        for btn in list(self._scan_buttons):
            try:
                btn.setStyleSheet(button_qss(palette, self.theme_mode))
            except RuntimeError:
                pass

    def _on_scan_progress(self, pct, message):
        if self._current_tab != "Scan":
            return
        if self._scan_progress_widget is not None:
            try:
                self._scan_progress_widget.set_progress(pct, message)
            except RuntimeError:
                self._scan_progress_widget = None

    def _on_scan_finished(self, scan_type, result):
        # Stop cancel timer
        if self._scan_cancel_timer is not None:
            try:
                self._scan_cancel_timer.stop()
            except Exception:
                pass
            self._scan_cancel_timer = None

        # Null stale progress widget before swapping
        self._scan_progress_widget = None

        if self._current_tab != "Scan":
            return  # User navigated away; discard

        if not isinstance(result, dict):
            self._holo_show_text("Scan", "Scan returned no data.")
            return

        # Cache software scan result for View Full Details
        if scan_type == "software":
            self._scan_last_software_result = result
            if len(self._scan_buttons) >= 7:
                try:
                    self._scan_buttons[6].setEnabled(True)
                except RuntimeError:
                    pass

        try:
            result_view = ScanResultView(scan_type, result, self._theme_color_rgb)
            self._scan_result_view = result_view
            self.holo.set_content_widget(result_view)
        except Exception as e:
            self._holo_show_text("Scan", f"Could not build result view: {e}")

    def _on_scan_cancelled(self, scan_type):
        if self._scan_cancel_timer is not None:
            try:
                self._scan_cancel_timer.stop()
            except Exception:
                pass
            self._scan_cancel_timer = None

        if self._current_tab != "Scan":
            self._scan_progress_widget = None
            return

        if self._scan_progress_widget is not None:
            try:
                self._scan_progress_widget.set_progress(0, "Scan cancelled.")
            except RuntimeError:
                self._scan_progress_widget = None

    def _on_scan_op_started(self, op_name):
        for btn in list(self._scan_buttons):
            try:
                btn.setEnabled(False)
            except RuntimeError:
                pass

    def _on_scan_op_finished(self, op_name):
        # Buttons stay disabled until the user starts a new scan
        # (except Cancel, which resets to disabled after finishing)
        if len(self._scan_buttons) >= 6:
            try:
                self._scan_buttons[4].setEnabled(False)  # Cancel
            except RuntimeError:
                pass
            # Re-enable scan type buttons + refresh
            for i in (0, 1, 2, 3, 5):
                try:
                    self._scan_buttons[i].setEnabled(True)
                except RuntimeError:
                    pass
        # View Full Details: enabled only when a software result exists
        if len(self._scan_buttons) >= 7:
            try:
                self._scan_buttons[6].setEnabled(
                    self._scan_last_software_result is not None
                )
            except RuntimeError:
                pass

    # ============================================================
    # OPTIMIZER TAB
    # ============================================================
    # ============================================================
    # PERFORMANCE TAB
    # ============================================================

    def _setup_performance_tab(self):
        palette = self._theme_color_rgb()
        tr, tg, tb = palette["text"]

        self._perf_buttons = []

        btn_cpu     = QPushButton("CPU Test")
        btn_gpu     = QPushButton("GPU Test")
        btn_disk    = QPushButton("Disk Test")
        btn_mem     = QPushButton("Memory Test")
        btn_refresh = QPushButton("Refresh")

        for btn in (btn_cpu, btn_gpu, btn_disk, btn_mem, btn_refresh):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(button_qss(palette, self.theme_mode))
            self.utility.content_layout.addWidget(btn)
            self._perf_buttons.append(btn)

        # Named refs — robust against button reordering
        self._btn_gpu = btn_gpu

        btn_gpu.clicked.connect(lambda: self._start_perf_test("gpu"))

        btn_cpu.clicked.connect(lambda: self._start_perf_test("cpu"))
        btn_disk.clicked.connect(lambda: self._start_perf_test("disk"))
        btn_mem.clicked.connect(lambda: self._start_perf_test("memory"))
        btn_refresh.clicked.connect(self._perf_refresh)

        self.utility.content_layout.addStretch(1)
        self.utility.show_content()

        self.notes.clear_content()
        notes_lbl = QLabel(
            "PERFORMANCE\n\n"
            "Each test runs once and\n"
            "reports its raw result.\n\n"
            "Live monitor at the bottom\n"
            "of the Holo panel updates\n"
            "every second.\n\n"
            "Live monitor is paused while\n"
            "a test is running."
        )
        notes_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        notes_lbl.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 12px;")
        notes_lbl.setWordWrap(True)
        self.notes.content_layout.addWidget(notes_lbl)
        self.notes.show_content()

        self._perf_view = PerformanceContentView(self._theme_color_rgb)
        self.holo.set_content_widget(self._perf_view)

        # Live monitor timer (1s)
        self._perf_live_timer = QTimer(self)
        self._perf_live_timer.timeout.connect(self._perf_tick)
        self._perf_live_timer.start(1000)

        # First tick immediately so the UI isn't empty
        QTimer.singleShot(0, self._perf_tick)

    def _perf_tick(self):
        if self._current_tab != "Performance":
            return
        if self._perf_test_running:
            return
        self.perf_ctrl.request_live_stats()

    def _start_perf_test(self, test_type):
        if self._perf_test_running:
            return
        if test_type == "gpu":
            self._start_gpu_test()
            return
        if test_type in ("cpu", "disk", "memory"):
            if not self._confirm_perf_test(test_type):
                return
        self._perf_test_running = True

        # Pause live monitor for the duration of the test
        if self._perf_live_timer is not None:
            try:
                self._perf_live_timer.stop()
            except Exception:
                pass

        if test_type == "cpu":
            self.perf_ctrl.run_cpu_benchmark()
        elif test_type == "disk":
            self.perf_ctrl.run_disk_test()
        elif test_type == "memory":
            self.perf_ctrl.run_memory_test()

    def _confirm_perf_test(self, test_type) -> bool:
        """Lightweight confirmation before CPU / Disk / Memory tests."""
        messages = {
            "cpu": (
                "CPU Benchmark",
                "This will run the CPU at 100% for ~4.5 seconds.\n\n"
                "• Warmup (0.5s, discarded)\n"
                "• Single-thread phase (2s)\n"
                "• Multi-thread phase (2s, all cores)\n\n"
                "Thermal safety gates are active (85°C start / 90°C abort).\n"
                "Your system may briefly become unresponsive.\n\n"
                "Proceed?"
            ),
            "disk": (
                "Disk Benchmark",
                "This will write and read a 256 MB temporary file.\n\n"
                "• Sequential write + read (fsync'd for accuracy)\n"
                "• Small-file IOPS (50 × 4 KB files)\n\n"
                "Requires ~500 MB free space in your temp directory.\n\n"
                "Proceed?"
            ),
            "memory": (
                "Memory Benchmark",
                "This will allocate 256 MB of RAM for pattern validation.\n\n"
                "• 5 patterns: 0x00, 0xFF, 0xAA, 0x55, ramp\n"
                "• Catches stuck bits and addressing errors\n\n"
                "Close other applications to ensure 256 MB is available.\n\n"
                "Proceed?"
            ),
        }
        title, body = messages[test_type]
        reply = QMessageBox.question(
            self, title, body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _start_gpu_test(self):
        """Async entry — fetch GPU info in worker, then show dialog.
        No UI freeze while GPU info is being read."""
        if self._perf_test_running:
            return
        self._perf_test_running = True

        # Pause live monitor while we fetch info
        if self._perf_live_timer is not None:
            try: self._perf_live_timer.stop()
            except Exception: pass

        # Visual feedback on the GPU button itself
        try:
            self._btn_gpu.setText("Reading GPU…")
            self._btn_gpu.setEnabled(False)
        except (IndexError, RuntimeError):
            pass

        self.perf_ctrl.prepare_gpu_test()

    def _on_gpu_info_ready(self, info):
        """Fires when prepare_gpu_test() completes."""
        # Restore the GPU button
        try:
            self._btn_gpu.setText("GPU Test")
            self._btn_gpu.setEnabled(True)
        except (IndexError, RuntimeError):
            pass

        # User switched away — bail silently
        if self._current_tab != "Performance":
            self._perf_test_running = False
            return

        # Error / empty info
        if not info:
            self._perf_test_running = False
            if self._perf_live_timer is not None:
                try: self._perf_live_timer.start(1000)
                except RuntimeError: pass
            QMessageBox.warning(self, "GPU Test", "Could not read GPU info.")
            return

        # PyOpenGL missing
        if not info.get("gl_available"):
            self._perf_test_running = False
            if self._perf_live_timer is not None:
                try: self._perf_live_timer.start(1000)
                except RuntimeError: pass
            QMessageBox.warning(
                self, "GPU Test Unavailable",
                f"{info.get('gl_reason', 'OpenGL not available')}\n\n"
                "Install PyOpenGL to enable the GPU test:\n\n"
                "    pip install PyOpenGL"
            )
            return

        # Confirm dialog
        dlg = GpuTestConfirmDialog(info, self._theme_color_rgb(), self)
        dlg.exec()
        if not dlg.user_proceeded:
            self._perf_test_running = False
            if self._perf_live_timer is not None and self._current_tab == "Performance":
                try: self._perf_live_timer.start(1000)
                except RuntimeError: pass
            QTimer.singleShot(0, self._perf_tick)
            return

        # ---- User proceeded — continue with original test flow ----
        from core.configs import GPU_TEST_DURATION_S
        self._gpu_test_abandoned = False
        # _perf_test_running stays True

        # Preview BEFORE lock (so it isn't disabled by the lock)
        try:
            self._gpu_preview_window = GpuTestPreviewWindow(
                self._theme_color_rgb()
            )
            self._gpu_preview_window.show()
        except Exception:
            self._gpu_preview_window = None

        # Lock UI (skips preview buttons)
        self._lock_ui_for_gpu_test()

        # Start test — runs on GUI thread with cooperative yields.
        # No QTimer watchdog needed: the benchmark self-terminates via
        # inline hard-timeout checks between frames.
        self.perf_ctrl.run_gpu_test()

    def _on_gpu_preview(self, qimage):
        if self._gpu_preview_window is not None:
            try:
                self._gpu_preview_window.update_preview(qimage)
            except RuntimeError:
                self._gpu_preview_window = None

    def _on_gpu_progress(self, pct, msg):
        if self._gpu_preview_window is not None:
            try:
                self._gpu_preview_window.update_progress(pct, msg)
            except RuntimeError:
                self._gpu_preview_window = None

    def _lock_ui_for_gpu_test(self):
        """Disable all interactive buttons during the GPU test.
        Skips buttons inside the preview window so the user can still
        hide/close it (which does NOT cancel the test)."""
        if self._gpu_lock_active:
            return
        self._gpu_lock_active = True
        self._gpu_lock_saved = {}

        preview = self._gpu_preview_window
        for btn in self.findChildren(QPushButton):
            # Skip buttons inside the preview window
            try:
                if preview is not None and btn.window() is preview:
                    continue
            except RuntimeError:
                pass
            try:
                self._gpu_lock_saved[btn] = btn.isEnabled()
                btn.setEnabled(False)
            except RuntimeError:
                pass

        try:
            self.tabs.setEnabled(False)
        except RuntimeError:
            pass

        # Stop 30ms pulse timers — they trigger ~800 repaints during the
        # 8s test and steal GPU time on iGPUs.
        for panel in (self.utility, self.holo, self.notes):
            try:
                if hasattr(panel, 'timer') and panel.timer.isActive():
                    panel.timer.stop()
            except RuntimeError:
                pass
        try:
            if hasattr(self.harvester, 'timer') and self.harvester.timer.isActive():
                self.harvester.timer.stop()
        except RuntimeError:
            pass

    def _unlock_ui_after_gpu_test(self):
        """Restore the exact enabled state each button had before the lock."""
        if not self._gpu_lock_active:
            return
        self._gpu_lock_active = False

        for btn, was_enabled in self._gpu_lock_saved.items():
            try:
                btn.setEnabled(was_enabled)
            except RuntimeError:
                pass
        self._gpu_lock_saved = {}

        try:
            self.tabs.setEnabled(True)
        except RuntimeError:
            pass

        # Restart pulse timers
        for panel in (self.utility, self.holo, self.notes):
            try:
                if hasattr(panel, 'timer') and not panel.timer.isActive() and panel.pulsing:
                    panel.timer.start(30)
            except RuntimeError:
                pass
        try:
            if (hasattr(self.harvester, 'timer')
                    and not self.harvester.timer.isActive()
                    and self.theme_mode == "default"):
                self.harvester.timer.start(30)
        except RuntimeError:
            pass


    def _format_perf_result(self, test_name, result):
        if test_name == "CPU Test":
            if not result.get("supported", True):
                return f"Unsupported: {result.get('reason', 'unknown')}"
            if result.get("aborted"):
                reason = result["aborted"]
                temp = result.get("temp_after_c") or result.get("temp_before_c", "?")
                return (
                    f"Aborted: {reason}\n"
                    f"Temp: {temp} °C\n\n"
                    + "\n".join(result.get("notes", []))
                )
            lines = [
                f"Single-thread:  {result.get('score', 0):,} ops/sec",
                f"  ({result.get('iterations', 0):,} iterations, "
                f"{result.get('duration', 0)}s)",
            ]
            if result.get("multi_available"):
                lines.append(
                    f"Multi-thread:   {result.get('multi_score', 0):,} ops/sec"
                )
                lines.append(
                    f"  ({result.get('multi_scaling_x', 0)}× over "
                    f"{result.get('multi_workers', '?')} workers, "
                    f"{result.get('multi_duration', 0)}s)"
                )
            else:
                lines.append("Multi-thread:   unavailable (single-core system)")
            lines.append("")
            lines.append(
                f"Jitter (chunk): {result.get('single_chunk_jitter_pct', 0)}%  |  "
                f"Stability: {result.get('stability', '?')}"
            )
            lines.append(
                f"Temp: {result.get('temp_before_c', '?')}°C → "
                f"{result.get('temp_after_c', '?')}°C"
            )
            notes = result.get("notes", [])
            if notes:
                lines.append("")
                lines.extend(notes)
            return "\n".join(lines)

        elif test_name == "Disk Test":
            if result.get("error"):
                return f"Failed: {result['error']}"
            lines = [
                f"Sequential write:  {result.get('write_speed', 0):,} MB/s",
                f"Sequential read:   {result.get('read_speed', 0):,} MB/s",
                f"Write IOPS:        {result.get('write_iops', 0):,}"
                f"  ({result.get('small_file_count', 0)} × "
                f"{result.get('small_file_size_kb', 4)} KB)",
                f"Read IOPS:         {result.get('read_iops', 0):,}",
                "",
                f"Duration: {result.get('duration', 0)}s",
            ]
            return "\n".join(lines)

        elif test_name == "Memory Test":
            if result.get("error"):
                return f"FAILED: {result['error']}"
            patterns = result.get("patterns_tested", [])
            pat_str = ", ".join(patterns) if patterns else "-"
            if result.get("passed"):
                return (
                    f"PASSED\n"
                    f"Checked:  {result.get('checked_mb', 0)} MB\n"
                    f"Patterns: {pat_str}\n"
                    f"Duration: {result.get('duration', 0)}s"
                )
            return (
                f"FAILED\n"
                f"Errors:   {result.get('errors', 0)}\n"
                f"Checked:  {result.get('checked_mb', 0)} MB\n"
                f"Patterns: {pat_str}\n"
                f"Duration: {result.get('duration', 0)}s"
            )

        elif test_name == "GPU Test":
            if not result.get("supported", False):
                return (
                    f"Unsupported: {result.get('reason', 'unknown')}\n"
                    f"GPU: {result.get('gpu_name', '?')}\n"
                    + "\n".join(result.get("notes", []))
                )
            if result.get("aborted"):
                gpu = result.get("gpu_name", "?")
                if result["aborted"] == "pre_hot":
                    temp_line = f"Temp (before): {result.get('temp_before_c', '?')} °C"
                else:
                    temp_line = f"Temp (after): {result.get('temp_after_c', '?')} °C"
                return (
                    f"Aborted: {result['aborted']}\n"
                    f"GPU: {gpu}\n"
                    f"{temp_line}\n\n"
                    + "\n".join(result.get("notes", []))
                )
            notes = result.get("notes", []) or []
            body = (
                f"GPU: {result.get('gpu_name', '?')} "
                f"(driver {result.get('driver_version', '?')}, "
                f"{result.get('vram_gb', 0)} GB)\n"
            )
            gl_renderer = result.get("gl_renderer", "")
            if gl_renderer and gl_renderer != "unknown":
                body += f"OpenGL Renderer: {gl_renderer}\n"
            all_gpus = result.get("all_gpus", []) or []
            if len(all_gpus) > 1:
                primary_name = result.get("gpu_name", "")
                others = [g for g in all_gpus if g.get("name") != primary_name]
                if others:
                    body += "Other GPUs: " + ", ".join(
                        g.get("name", "?") for g in others
                    ) + "\n"
            body += (
                f"OpenGL: {result.get('gl_version', '?')}\n"
                f"Duration: {result.get('duration_s', 0)}s\n\n"
                f"Fill Rate:  {result.get('fill_rate_mpix_s', 0):,} Mpix/s\n"
                f"ALU Peak:   {result.get('alu_mops_s', 0):,} Mops/s "
                f"(at {result.get('alu_iterations', 128)} iters, "
                f"theoretical ceiling)\n\n"
                f"Frames: {result.get('fill_frames', 0)} fill / "
                f"{result.get('alu_frames', 0)} alu\n"
                f"Jitter (MAD): {result.get('frame_jitter_pct', 0)}%  |  "
                f"Thermal: {result.get('thermal_headroom_pct', 0)}%\n"
                f"Stability: {result.get('stability', '?')}\n\n"
                f"Temp: {result.get('temp_before_c', '?')}°C → "
                f"{result.get('temp_after_c', '?')}°C"
            )
            if notes:
                body += "\n\n" + "\n".join(notes)
            return body

        return str(result)

    def _on_perf_test_finished(self, test_name, result):
        self._perf_test_running = False

        # Discard late result if the watchdog already abandoned this test
        if test_name == "GPU Test" and self._gpu_test_abandoned:
            self._gpu_test_abandoned = False
            return

        if self._perf_view is not None:
            try:
                text = self._format_perf_result(test_name, result)
                self._perf_view.append_result(test_name, text)
            except RuntimeError:
                pass

        # Close GPU preview window (test is done)
        if test_name == "GPU Test" and self._gpu_preview_window is not None:
            try:
                self._gpu_preview_window.mark_complete()
                self._gpu_preview_window.close()
            except RuntimeError:
                pass
            self._gpu_preview_window = None

        # Resume live monitor
        if self._perf_live_timer is not None and self._current_tab == "Performance":
            try:
                self._perf_live_timer.start(1000)
            except RuntimeError:
                pass

        QTimer.singleShot(0, self._perf_tick)

    def _on_perf_live_stats(self, stats):
        if self._current_tab != "Performance":
            return
        if self._perf_view is not None:
            try:
                self._perf_view.set_live_stats(stats)
            except RuntimeError:
                pass

    def _perf_refresh(self):
        self._perf_tick()

    def _on_perf_op_started(self, op_name):
        for btn in list(self._perf_buttons):
            try:
                btn.setEnabled(False)
            except RuntimeError:
                pass

    def _on_perf_op_finished(self, op_name):
        # Reset test-running lock on BOTH success and error paths.
        if op_name in ("CPU Test", "Disk Test", "Memory Test"):
            self._perf_test_running = False
            if self._perf_live_timer is not None and self._current_tab == "Performance":
                try:
                    self._perf_live_timer.start(1000)
                except RuntimeError:
                    pass

        if op_name == "GPU Test":
            self._perf_test_running = False

            # Stop watchdog
            if self._gpu_watchdog_timer is not None:
                try:
                    self._gpu_watchdog_timer.stop()
                except RuntimeError:
                    pass
                self._gpu_watchdog_timer = None

            # Close preview if still open (error path; success closes it in test_finished)
            if self._gpu_preview_window is not None:
                try:
                    self._gpu_preview_window.close()
                except RuntimeError:
                    pass
                self._gpu_preview_window = None

            # Unlock UI (idempotent — restores exact pre-test enabled state)
            self._unlock_ui_after_gpu_test()

            # Resume live monitor
            if self._perf_live_timer is not None and self._current_tab == "Performance":
                try:
                    self._perf_live_timer.start(1000)
                except RuntimeError:
                    pass
            return  # Skip generic re-enable — handled by _unlock_ui_after_gpu_test

        for btn in list(self._perf_buttons):
            try:
                btn.setEnabled(True)
            except RuntimeError:
                pass
        # NOTE: GPU Test button is now fully functional — no re-disable here.

    def _refresh_performance_styles(self):
        palette = self._theme_color_rgb()
        for btn in list(self._perf_buttons):
            try:
                btn.setStyleSheet(button_qss(palette, self.theme_mode))
            except RuntimeError:
                pass
        if self._perf_view is not None:
            try:
                self._perf_view.refresh_style()
            except (RuntimeError, AttributeError):
                pass


    def _setup_optimizer_tab(self):
        palette = self._theme_color_rgb()
        tr, tg, tb = palette["text"]

        # ---- Utility: buttons + summary label (list moved to Holo) ----
        btn_analyze = QPushButton("Analyze")
        btn_refresh = QPushButton("Refresh")
        btn_kill    = QPushButton("Kill Selected")
        btn_auto    = QPushButton("Auto Optimize")
        btn_white   = QPushButton("Edit Whitelist")

        self._opt_buttons = [btn_analyze, btn_refresh, btn_kill, btn_auto, btn_white]
        for btn in self._opt_buttons:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(button_qss(palette, self.theme_mode))
            self.utility.content_layout.addWidget(btn)

        self._opt_summary_label = QLabel("Candidates: —")
        self._opt_summary_label.setStyleSheet(
            f"color: rgb({tr},{tg},{tb}); font-size: 12px;"
        )
        self._opt_summary_label.setWordWrap(True)
        self.utility.content_layout.addWidget(self._opt_summary_label)

        self._opt_status_label = QLabel("Press Analyze to begin.")
        self._opt_status_label.setStyleSheet(
            f"color: rgb({tr},{tg},{tb}); font-size: 11px;"
        )
        self._opt_status_label.setWordWrap(True)
        self.utility.content_layout.addWidget(self._opt_status_label)

        self.utility.content_layout.addStretch(1)
        self.utility.show_content()

        # ---- Notes ----
        self._opt_notes_label = QLabel(
            "OPTIMIZER\n\n"
            "Review candidate processes before\n"
            "executing an optimization action.\n\n"
            "Protected processes are excluded\n"
            "automatically.\n\n"
            "Check items in the Holo panel to\n"
            "select them for termination."
        )
        self._opt_notes_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._opt_notes_label.setStyleSheet(f"color: rgb({tr},{tg},{tb}); font-size: 12px;")
        self._opt_notes_label.setWordWrap(True)
        self.notes.content_layout.addWidget(self._opt_notes_label)
        self.notes.show_content()

        # ---- Holo: candidate list widget ----
        self._opt_list = QListWidget()
        self._opt_list.setStyleSheet(list_qss(palette, self.theme_mode))
        self._opt_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        placeholder = QListWidgetItem("Analyzing…")
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        self._opt_list.addItem(placeholder)

        self.holo.set_content_widget(self._opt_list)

        # ---- Wire buttons ----
        btn_analyze.clicked.connect(lambda: self.optimizer_ctrl.analyze())
        btn_refresh.clicked.connect(lambda: self.optimizer_ctrl.refresh())
        btn_kill.clicked.connect(self._opt_on_kill_selected)
        btn_auto.clicked.connect(self._opt_on_auto_optimize)
        btn_white.clicked.connect(self.optimizer_ctrl.open_whitelist_file)

        # Kick off the first analysis
        self.optimizer_ctrl.analyze()

    def _refresh_optimizer_styles(self):
        if not self._opt_buttons:
            return
        palette = self._theme_color_rgb()
        for btn in self._opt_buttons:
            try:
                btn.setStyleSheet(button_qss(palette, self.theme_mode))
            except RuntimeError:
                pass
        if self._opt_list is not None:
            try:
                self._opt_list.setStyleSheet(list_qss(palette, self.theme_mode))
            except RuntimeError:
                pass

    # ---- controller wiring
    def _wire_optimizer_controller(self):
        self.optimizer_ctrl.snapshot_ready.connect(self._on_opt_snapshot)
        self.optimizer_ctrl.candidates_ready.connect(self._on_opt_candidates)
        self.optimizer_ctrl.kill_finished.connect(self._on_opt_kill_finished)
        self.optimizer_ctrl.memory_result_ready.connect(self._on_opt_memory_result)
        self.optimizer_ctrl.operation_started.connect(self._on_opt_op_started)
        self.optimizer_ctrl.operation_finished.connect(self._on_opt_op_finished)
        self.optimizer_ctrl.error_occurred.connect(self._on_opt_error)

    # ---- handlers
    def _on_opt_snapshot(self, data):
        self._opt_last_snapshot = data
        self._update_optimizer_summary()

        # Populate Holo process list from the tagged full list
        all_procs = data.get("all_processes", [])
        self._render_process_list(all_procs)

        if self._opt_status_label is None:
            return
        try:
            mem = data.get("memory", {})
            usage = mem.get("Usage (%)", 0)
            apps = len(data.get("apps", []))
            bgs = len(data.get("background", []))
            self._opt_status_label.setText(
                f"Apps: {apps}  |  Background: {bgs}  |  RAM: {usage}%"
            )
        except RuntimeError:
            self._opt_status_label = None

    def _render_process_list(self, entries):
        if self._opt_list is None:
            return
        try:
            self._opt_list.clear()
        except RuntimeError:
            self._opt_list = None
            return

        if not entries:
            item = QListWidgetItem("No processes.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._opt_list.addItem(item)
            return

        # Colors per tag — force pure black in light mode
        if self.theme_mode == "light":
            tag_color = {
                "CRITICAL":  QColor(0, 0, 0),
                "SYSTEM":    QColor(0, 0, 0),
                "WHITELIST": QColor(0, 0, 0),
                "USER":      QColor(0, 0, 0),
            }
            default_color = QColor(0, 0, 0)
        else:
            tag_color = {
                "CRITICAL":  QColor(150, 150, 150),
                "SYSTEM":    QColor(180, 200, 220),
                "WHITELIST": QColor(120, 210, 200),
                "USER":      QColor(230, 240, 250),
            }
            default_color = QColor(230, 240, 250)

        for e in entries:
            pid = e["pid"]
            name = e["name"]
            cpu = e["cpu"]
            mem = e["mem_mb"]
            tag = e.get("tag", "USER")
            heavy = e.get("heavy", False)

            marker = "🔥 " if (heavy and tag == "USER") else ""
            line = f"[{tag}]  {name}  (PID {pid})  CPU {cpu}%  MEM {mem}MB"
            item = QListWidgetItem(marker + line)
            item.setForeground(tag_color.get(tag, default_color))

            # Only USER entries are checkable
            if tag == "USER":
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setData(Qt.ItemDataRole.UserRole, [pid, name])
            else:
                item.setFlags(Qt.ItemFlag.NoItemFlags)

            self._opt_list.addItem(item)

    def _update_optimizer_summary(self):
        mem = self._opt_last_snapshot.get("memory", {})
        apps = self._opt_last_snapshot.get("apps", [])
        bgs = self._opt_last_snapshot.get("background", [])
        all_procs = self._opt_last_snapshot.get("all_processes", [])

        user_count = sum(1 for e in all_procs if e.get("tag") == "USER")
        heavy_user = sum(
            1 for e in all_procs
            if e.get("tag") == "USER" and e.get("heavy")
        )

        if self._opt_summary_label is not None:
            try:
                self._opt_summary_label.setText(
                    f"Processes: {len(all_procs)}  |  User: {user_count}  |  Heavy: {heavy_user}\n"
                    f"RAM: {mem.get('Usage (%)', 0)}%  |  "
                    f"Apps: {len(apps)}  BG: {len(bgs)}"
                )
            except RuntimeError:
                self._opt_summary_label = None

    def _on_opt_candidates(self, candidates):
        # Full process list is now rendered by _on_opt_snapshot via all_processes.
        # This signal is only used to update summary counters.
        self._update_optimizer_summary()

    def _on_opt_kill_finished(self, results):
        if self._opt_notes_label is None or not results:
            return
        try:
            completed = sum(1 for r in results if r["status"] in ("terminated", "killed"))
            blocked   = sum(1 for r in results if r["status"] in ("protected", "self_protected"))
            denied    = sum(1 for r in results if r["status"] == "access_denied")
            failed    = sum(1 for r in results if r["status"] in ("failed", "not_found"))

            lines = ["EXECUTION RESULT", ""]
            lines.append(f"Selected:  {len(results)}")
            lines.append(f"Completed: {completed}")
            if blocked: lines.append(f"Blocked:   {blocked}  (protected)")
            if denied:  lines.append(f"Denied:    {denied}  (access)")
            if failed:  lines.append(f"Failed:    {failed}")
            lines.append("")
            for r in results:
                lines.append(f"  • {r['name']} ({r['pid']}) — {r['status']}")
                if r.get("detail"):
                    lines.append(f"      {r['detail']}")
            self._opt_notes_label.setText("\n".join(lines))
        except RuntimeError:
            self._opt_notes_label = None

        self.optimizer_ctrl.refresh()

    def _on_opt_memory_result(self, result):
        if self._opt_notes_label is None:
            return
        try:
            self._opt_notes_label.setText(
                f"MEMORY OPTIMIZATION\n\n"
                f"Freed: ~{result.get('freed_mb', 0)} MB\n"
                f"Available: {result.get('status', {}).get('Available (GB)', 0)} GB\n"
                f"Total: {result.get('status', {}).get('Total (GB)', 0)} GB"
            )
        except RuntimeError:
            self._opt_notes_label = None

    def _on_opt_op_started(self, op_name):
        for btn in list(self._opt_buttons):
            try:
                btn.setEnabled(False)
            except RuntimeError:
                pass
        if self._opt_status_label is not None:
            try:
                self._opt_status_label.setText(f"Running: {op_name}…")
            except RuntimeError:
                self._opt_status_label = None

    def _on_opt_op_finished(self, op_name):
        for btn in list(self._opt_buttons):
            try:
                btn.setEnabled(True)
            except RuntimeError:
                pass

    def _on_opt_error(self, title, message):
        QMessageBox.warning(self, title, message)

    # ---- button handlers
    def _opt_on_kill_selected(self):
        if self._opt_list is None:
            return
        pairs = []
        for i in range(self._opt_list.count()):
            item = self._opt_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data:
                    pairs.append(tuple(data))

        if not pairs:
            QMessageBox.information(self, "Kill Selected", "No processes selected.")
            return

        preview = "\n".join(f"{n} (PID {p})" for p, n in pairs)
        reply = QMessageBox.question(
            self, "Confirm Kill",
            f"Terminate the following processes?\n\n{preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.optimizer_ctrl.kill_selected(pairs)

    def _opt_on_auto_optimize(self):
        preview = [c for c in self.optimizer_ctrl.preview_candidates()
                   if not c.get("protected", False)]
        if not preview:
            QMessageBox.information(self, "Auto Optimize", "No heavy processes detected.")
            return

        lines = "\n".join(
            f"{c['name']} (CPU {c['cpu']}%, MEM {c['mem_mb']}MB)"
            for c in preview
        )
        reply = QMessageBox.question(
            self, "Confirm Auto Optimize",
            f"The following may be terminated:\n\n{lines}\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.optimizer_ctrl.auto_optimize()

    # ---- anchoring everything to frame
    def resizeEvent(self, e):
        self.bg.resize(self.size())

        frame = compute_frame_rect(self.width(), self.height())
        pad = 14
        inner = frame.adjusted(pad, pad, -pad, -pad)

        util_w  = int(inner.width() * 0.22)
        holo_w  = int(inner.width() * 0.56)
        notes_w = inner.width() - util_w - holo_w

        self.utility.setGeometry(inner.left(), inner.top(), util_w, inner.height())
        self.holo.setGeometry(inner.left() + util_w, inner.top(), holo_w, inner.height())
        self.notes.setGeometry(self.holo.geometry().right() + 1, inner.top(), notes_w, inner.height())

        right_gap = max(320, int(self.width() * 0.28))
        offset_x = int(right_gap * 0.12)
        offset_y = int(self.height() * 0.08)
        self.harvester.setGeometry(self.width() - right_gap + offset_x, offset_y,
                                   right_gap, self.height())

        tabs_w = 180
        tabs_h = int(self.height() * 0.86)
        tabs_y = (self.height() - tabs_h) // 2
        self.tabs.setGeometry(0, tabs_y, tabs_w, tabs_h)
        self.tabs.setVisible(True)

        self.btn_theme.move(self.width() - 62, 18)

    def _reset_scene(self):
        # Cancel any in-flight work before tearing down
        if self._current_tab == "Scan":
            try:
                self.scan_ctrl.cancel_scan()
            except Exception:
                pass
        if self._current_tab == "Performance":
            if self._perf_live_timer is not None:
                try: self._perf_live_timer.stop()
                except Exception: pass
                self._perf_live_timer = None
            self._perf_test_running = False

        # Defensive: clean up any lingering GPU test state
        if self._gpu_watchdog_timer is not None:
            try:
                self._gpu_watchdog_timer.stop()
            except Exception:
                pass
            self._gpu_watchdog_timer = None
        self._gpu_test_abandoned = False
        if self._gpu_preview_window is not None:
            try:
                self._gpu_preview_window.close()
            except Exception:
                pass
            self._gpu_preview_window = None
        self._unlock_ui_after_gpu_test()  # idempotent

        self.utility.setVisible(False)
        self.notes.setVisible(False)
        self.utility.clear_content()
        self.notes.clear_content()
        self.holo.clear_lines()
        self.holo.set_about(True)
        self.holo.set_shape("square")
        self.holo.stop_pulse()
        self.utility.stop_pulse()
        self.notes.stop_pulse()
        self.tabs.active_name = "Home"
        self.tabs._update_active_visuals()
        self._opt_buttons = []
        self._opt_list = None
        self._opt_status_label = None
        self._opt_summary_label = None
        self._opt_notes_label = None
        self._home_buttons = []
        self._hw_buttons = []
        self._tools_buttons = []
        self._tools_action_buttons = []
        self._tools_action_layout = None
        self._tools_table = None
        self._tools_selected_row = None
        self._tools_notes_label = None
        self._tools_current = ""
        self._scan_buttons = []
        self._scan_progress_widget = None
        self._scan_result_view = None
        self._scan_cancel_timer = None
        self._scan_last_type = None
        self._scan_last_software_result = None
        self._perf_buttons = []
        self._perf_view = None
        self._perf_test_running = False
        if self._perf_live_timer is not None:
            try:
                self._perf_live_timer.stop()
            except Exception:
                pass
            self._perf_live_timer = None
        self._system_buttons = []
        self._system_action_buttons = []
        self._system_action_layout = None
        self._system_table = None
        self._system_selected_row = None
        self._system_notes_label = None
        self._tools_startup_rows = []
        self._system_current = ""
        self._current_tab = "Home"


# ---- run
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PhantomScene()
    w.show()
    sys.exit(app.exec())