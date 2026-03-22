"""Main application window."""

from pathlib import Path
from typing import Optional

import numpy as np

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QVBoxLayout, QWidget,
    QSplitter, QStatusBar, QLabel, QScrollArea, QProgressDialog,
    QDialog, QFormLayout, QSpinBox, QSlider, QDialogButtonBox,
    QCheckBox, QHBoxLayout, QTabWidget,
)

import time

from ..core.ser_parser import SERFile, ColorID

# Map Bayer ColorID to (red_col, red_row), (blue_col, blue_row) offsets in 2x2 block
_BAYER_OFFSETS = {
    ColorID.BAYER_RGGB: ((0.0, 0.0), (1.0, 1.0)),
    ColorID.BAYER_GRBG: ((1.0, 0.0), (0.0, 1.0)),
    ColorID.BAYER_GBRG: ((0.0, 1.0), (1.0, 0.0)),
    ColorID.BAYER_BGGR: ((1.0, 1.0), (0.0, 0.0)),
}
from ..core.frame_pipeline import FramePipeline
from ..core.playback_engine import PlaybackEngine
from ..core.statistics import compute_stats
from .viewer_widget import ImageViewer
from .transport_bar import TransportBar

# Try OpenGL viewer, fall back to software
try:
    from .gl_viewer_widget import GLImageViewer
    _HAS_GL = True
except ImportError:
    _HAS_GL = False
from .file_info_panel import FileInfoPanel
from .adjustments_panel import AdjustmentsPanel
from .histogram_widget import HistogramWidget
from .statistics_panel import StatisticsPanel
from .roi_selector import ROISelector
from .timestamp_panel import TimestampPanel
from .tracking_panel import TrackingPanel
from .lucky_panel import LuckyPanel
from .mount_panel import MountPanel
from .i18n import tr, I18n, LANGUAGES


class MainWindow(QMainWindow):
    """AstroSER Player main window."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(900, 650)
        self.resize(1200, 800)

        self._ser_file: Optional[SERFile] = None
        self._pipeline: Optional[FramePipeline] = None
        self._roi: Optional[tuple[int, int, int, int]] = None
        self._roi_item: Optional[ROISelector] = None
        self._stats_update_counter = 0
        self._use_gl = _HAS_GL

        self._engine = PlaybackEngine(self)
        self._setup_ui()
        self._setup_menus()
        self._setup_shortcuts()
        self._setup_statusbar()

        self._engine.frame_changed.connect(self._on_frame_changed)
        self._adjustments.adjustments_changed.connect(self._on_adjustments_changed)
        self._transport.trim_save_requested.connect(self._on_trim_save)

        I18n.instance().language_changed.connect(self.retranslate)
        self.retranslate()

        # Restore window geometry
        settings = QSettings("AstroSER", "Player")
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = settings.value("windowState")
        if state:
            self.restoreState(state)

        # Restore splitter proportions (ensure right panel is visible)
        splitter_state = settings.value("splitterState")
        if splitter_state:
            self._splitter.restoreState(splitter_state)
        else:
            # Default: ~75% viewer, ~25% info panel
            w = self.width()
            self._splitter.setSizes([w * 3 // 4, w // 4])

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        if self._use_gl:
            self._viewer = GLImageViewer()
        else:
            self._viewer = ImageViewer()
        self._splitter.addWidget(self._viewer)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        # ── Core panels (always visible) ──
        self._file_info = FileInfoPanel()
        right_layout.addWidget(self._file_info)

        self._adjustments = AdjustmentsPanel()
        right_layout.addWidget(self._adjustments)

        self._histogram = HistogramWidget()
        right_layout.addWidget(self._histogram)

        self._statistics = StatisticsPanel()
        right_layout.addWidget(self._statistics)

        # ── Analysis tabs (shown when activated) ──
        self._analysis_tabs = QTabWidget()
        self._analysis_tabs.setDocumentMode(True)
        self._analysis_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._analysis_tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background: transparent; }"
            "QTabBar::tab { font-size: 11px; padding: 4px 10px; }"
        )
        self._analysis_tabs.setVisible(False)

        self._timestamp_panel = TimestampPanel()
        self._timestamp_panel.frame_selected.connect(self._engine.seek)

        self._tracking_panel = TrackingPanel()
        self._tracking_panel.frame_selected.connect(self._engine.seek)

        self._mount_panel = MountPanel()

        self._lucky_panel = LuckyPanel()

        right_layout.addWidget(self._analysis_tabs)
        right_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(right_panel)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(240)
        scroll.setMaximumWidth(360)
        self._splitter.addWidget(scroll)

        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self._splitter, stretch=1)

        self._transport = TransportBar(self._engine)
        self._transport.setEnabled(False)
        main_layout.addWidget(self._transport)

    def _setup_menus(self) -> None:
        menubar = self.menuBar()

        # File menu
        self._file_menu = menubar.addMenu("")
        self._open_action = QAction("", self)
        self._open_action.setShortcut(QKeySequence.StandardKey.Open)
        self._open_action.triggered.connect(self._open_file_dialog)
        self._file_menu.addAction(self._open_action)
        self._file_menu.addSeparator()
        self._export_mp4_action = QAction("", self)
        self._export_mp4_action.setShortcut(QKeySequence("Ctrl+E"))
        self._export_mp4_action.triggered.connect(self._export_mp4)
        self._export_mp4_action.setEnabled(False)
        self._file_menu.addAction(self._export_mp4_action)
        self._file_menu.addSeparator()
        self._exit_action = QAction("", self)
        self._exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._exit_action.triggered.connect(self.close)
        self._file_menu.addAction(self._exit_action)

        # View menu
        self._view_menu = menubar.addMenu("")
        self._fit_action = QAction("", self)
        self._fit_action.setShortcut(QKeySequence("Ctrl+0"))
        self._fit_action.triggered.connect(self._viewer.fit_in_view)
        self._view_menu.addAction(self._fit_action)

        self._zoom_in_action = QAction("", self)
        self._zoom_in_action.setShortcut(QKeySequence("Ctrl+="))
        self._zoom_in_action.triggered.connect(self._viewer.zoom_in)
        self._view_menu.addAction(self._zoom_in_action)

        self._zoom_out_action = QAction("", self)
        self._zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        self._zoom_out_action.triggered.connect(self._viewer.zoom_out)
        self._view_menu.addAction(self._zoom_out_action)

        self._view_menu.addSeparator()

        self._zoom_100_action = QAction("", self)
        self._zoom_100_action.setShortcut(QKeySequence("Ctrl+1"))
        self._zoom_100_action.triggered.connect(lambda: self._viewer.set_zoom(1.0))
        self._view_menu.addAction(self._zoom_100_action)

        self._zoom_200_action = QAction("", self)
        self._zoom_200_action.setShortcut(QKeySequence("Ctrl+2"))
        self._zoom_200_action.triggered.connect(lambda: self._viewer.set_zoom(2.0))
        self._view_menu.addAction(self._zoom_200_action)

        # Tools menu
        self._tools_menu = menubar.addMenu("")
        self._roi_action = QAction("", self)
        self._roi_action.setShortcut(QKeySequence("Ctrl+R"))
        self._roi_action.setCheckable(True)
        self._roi_action.toggled.connect(self._toggle_roi)
        self._tools_menu.addAction(self._roi_action)

        self._solar_action = QAction("", self)
        self._solar_action.setShortcut(QKeySequence("Ctrl+S"))
        self._solar_action.setCheckable(True)
        self._solar_action.toggled.connect(self._toggle_solar)
        self._tools_menu.addAction(self._solar_action)

        # Analysis menu
        self._analysis_menu = menubar.addMenu("")
        self._timestamp_action = QAction("", self)
        self._timestamp_action.setCheckable(True)
        self._timestamp_action.toggled.connect(self._toggle_timestamp_panel)
        self._analysis_menu.addAction(self._timestamp_action)

        self._load_tracking_action = QAction("", self)
        self._load_tracking_action.triggered.connect(self._load_tracking_log)
        self._analysis_menu.addAction(self._load_tracking_action)

        self._analysis_menu.addSeparator()

        self._lucky_action = QAction("", self)
        self._lucky_action.setCheckable(True)
        self._lucky_action.toggled.connect(self._toggle_lucky_panel)
        self._analysis_menu.addAction(self._lucky_action)

        # Language menu
        self._lang_menu = menubar.addMenu("")
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        current_lang = I18n.instance().lang
        for code, name in LANGUAGES.items():
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(code == current_lang)
            action.setData(code)
            action.triggered.connect(lambda checked, c=code: self._change_language(c))
            lang_group.addAction(action)
            self._lang_menu.addAction(action)

        # Help menu
        self._help_menu = menubar.addMenu("")
        self._about_action = QAction("", self)
        self._about_action.triggered.connect(self._show_about)
        self._help_menu.addAction(self._about_action)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._engine.toggle)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._engine.step_forward)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self._engine.step_backward)
        QShortcut(QKeySequence(Qt.Key.Key_Home), self, self._engine.go_to_first)
        QShortcut(QKeySequence(Qt.Key.Key_End), self, self._engine.go_to_last)
        QShortcut(QKeySequence(Qt.Key.Key_Plus), self, self._viewer.zoom_in)
        QShortcut(QKeySequence(Qt.Key.Key_Minus), self, self._viewer.zoom_out)
        QShortcut(QKeySequence(Qt.Key.Key_Equal), self, self._viewer.zoom_in)

    def _setup_statusbar(self) -> None:
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)

        self._status_file = QLabel()
        self._status_info = QLabel("")
        self._status_zoom = QLabel("")
        statusbar.addWidget(self._status_file, stretch=1)
        statusbar.addPermanentWidget(self._status_zoom)
        statusbar.addPermanentWidget(self._status_info)

        self._viewer.zoom_changed.connect(
            lambda z: self._status_zoom.setText(tr("status_zoom").format(z * 100) + "  ")
        )

    def retranslate(self) -> None:
        """Update all menu and status text for current language."""
        self.setWindowTitle(tr("app_title"))
        if self._ser_file:
            self.setWindowTitle(f"{tr('app_title')} - {self._ser_file.filepath.name}")

        self._file_menu.setTitle(tr("menu_file"))
        self._open_action.setText(tr("menu_open"))
        self._export_mp4_action.setText(tr("menu_export_mp4"))
        self._exit_action.setText(tr("menu_exit"))

        self._view_menu.setTitle(tr("menu_view"))
        self._fit_action.setText(tr("menu_fit"))
        self._zoom_in_action.setText(tr("menu_zoom_in"))
        self._zoom_out_action.setText(tr("menu_zoom_out"))
        self._zoom_100_action.setText(tr("menu_zoom_100"))
        self._zoom_200_action.setText(tr("menu_zoom_200"))

        self._tools_menu.setTitle(tr("menu_tools"))
        self._roi_action.setText(tr("menu_roi"))
        self._solar_action.setText(tr("menu_solar"))

        self._analysis_menu.setTitle(tr("menu_analysis"))
        self._timestamp_action.setText(tr("menu_timestamp_panel"))
        self._load_tracking_action.setText(tr("menu_load_tracking"))
        self._lucky_action.setText(tr("menu_lucky_export"))

        # Update analysis tab titles
        _tab_map = {
            self._timestamp_panel: tr("tab_timestamp"),
            self._tracking_panel: tr("tab_tracking"),
            self._mount_panel: tr("tab_mount"),
            self._lucky_panel: tr("tab_lucky"),
        }
        for i in range(self._analysis_tabs.count()):
            w = self._analysis_tabs.widget(i)
            if w in _tab_map:
                self._analysis_tabs.setTabText(i, _tab_map[w])

        self._lang_menu.setTitle(tr("menu_language"))
        self._help_menu.setTitle(tr("menu_help"))
        self._about_action.setText(tr("menu_about"))

        if not self._ser_file:
            self._status_file.setText(tr("no_file"))

    def _change_language(self, lang_code: str) -> None:
        I18n.instance().set_language(lang_code)

    def _open_file_dialog(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self, tr("dlg_open_title"), "", tr("dlg_filter"),
        )
        if filepath:
            self.open_file(filepath)

    def open_file(self, filepath: str) -> None:
        self._close_file()
        try:
            ser = SERFile(filepath)
            ser.open()
        except Exception as e:
            QMessageBox.critical(self, tr("dlg_error"), tr("dlg_open_error").format(e))
            return

        self._ser_file = ser
        self._pipeline = FramePipeline(ser)

        # Sync current adjustment state to new pipeline
        self._pipeline.brightness = self._adjustments.brightness
        self._pipeline.contrast = self._adjustments.contrast
        self._pipeline.gamma = self._adjustments.gamma
        self._pipeline.auto_stretch = self._adjustments.auto_stretch_enabled
        self._pipeline.solar_colorize = self._solar_action.isChecked()

        self._engine.set_frame_count(ser.frame_count)
        self._transport.set_frame_count(ser.frame_count)
        self._transport.setEnabled(True)
        self._export_mp4_action.setEnabled(True)

        self._file_info.update_info(ser)

        self._status_file.setText(Path(filepath).name)
        self._status_info.setText(
            f"{ser.width}\u00d7{ser.height} | "
            f"{ser.color_id.display_name} | "
            f"{ser.pixel_depth}bit | "
            f"{tr('status_frames').format(ser.frame_count)}"
        )

        # Set UTC callback for timeline tooltip
        if ser.has_timestamps:
            self._transport._timeline.set_utc_callback(
                lambda idx: ser.get_timestamp(idx)
            )
        else:
            self._transport._timeline.set_utc_callback(None)

        self._viewer.reset_view()
        self._engine.seek(0)
        self._viewer.fit_in_view()

        self.setWindowTitle(f"{tr('app_title')} - {Path(filepath).name}")

    def _close_file(self) -> None:
        self._engine.stop()
        self._remove_roi()
        if self._ser_file:
            self._ser_file.close()
            self._ser_file = None
        self._pipeline = None
        self._transport.setEnabled(False)
        self._export_mp4_action.setEnabled(False)
        self._file_info.clear()
        self._histogram.clear()
        self._statistics.clear()
        self._analysis_tabs.clear()
        self._analysis_tabs.setVisible(False)
        self._timestamp_panel.clear()
        self._tracking_panel.clear()
        self._lucky_panel.clear()
        self._mount_panel.clear()
        if self._timestamp_action.isChecked():
            self._timestamp_action.setChecked(False)
        if self._lucky_action.isChecked():
            self._lucky_action.setChecked(False)

    def _on_frame_changed(self, index: int) -> None:
        if self._pipeline is None:
            return
        try:
            t0 = time.perf_counter()

            if self._use_gl:
                self._on_frame_changed_gl(index, t0)
            else:
                self._on_frame_changed_sw(index, t0)

            # Update tracking OSD if visible
            if self._analysis_tabs.indexOf(self._tracking_panel) >= 0:
                self._tracking_panel.update_frame(index)

        except Exception as e:
            print(f"Frame {index} render error: {e}")

    def _on_frame_changed_gl(self, index: int, t0: float) -> None:
        """GL path: upload raw frame to GPU, shader does adjustments + debayer."""
        color_id = self._ser_file.color_id
        pixel_max = float((1 << self._ser_file.pixel_depth) - 1)

        # For Bayer data, upload raw single-channel; GPU shader does debayer
        if color_id.is_bayer and color_id in _BAYER_OFFSETS:
            frame = self._pipeline.get_raw_frame(index)
            is_mono = False
            is_bayer = True
            red_off, blue_off = _BAYER_OFFSETS[color_id]
        else:
            frame = self._pipeline.get_display_frame(index)
            is_mono = not color_id.is_color and not color_id.is_bayer
            is_bayer = False
            red_off, blue_off = (0.0, 0.0), (1.0, 1.0)

        # GL normalizes textures by type max (255 for uint8, 65535 for uint16)
        type_max = 65535.0 if frame.dtype == np.uint16 else 255.0
        gl_rescale = type_max / pixel_max

        # Compute auto-stretch percentiles if needed
        auto_lo, auto_hi = 0.0, 1.0
        if self._pipeline.auto_stretch:
            sample = frame
            if frame.size > 500000:
                if frame.ndim == 2:
                    sample = frame[::4, ::4]
                else:
                    sample = frame[::4, ::4, :]
            sample_f = sample.astype(np.float32) / pixel_max
            auto_lo = float(np.percentile(sample_f, self._pipeline.stretch_low))
            auto_hi = float(np.percentile(sample_f, self._pipeline.stretch_high))

        # Update GL viewer uniforms and upload texture
        viewer = self._viewer
        viewer.brightness = self._pipeline.brightness
        viewer.contrast = self._pipeline.contrast
        viewer.gamma = self._pipeline.gamma
        viewer.auto_stretch = self._pipeline.auto_stretch
        viewer.solar_colorize = self._pipeline.solar_colorize
        viewer.is_bayer = is_bayer
        viewer.bayer_red_offset = red_off
        viewer.bayer_blue_offset = blue_off
        viewer.set_frame(frame, is_mono, gl_rescale, auto_lo, auto_hi)

        self._update_stats(index, t0)

    def _on_frame_changed_sw(self, index: int, t0: float) -> None:
        """Software path: CPU-based pipeline with QImage."""
        qimage = self._pipeline.process_frame(index)
        self._viewer.set_image(qimage)
        self._update_stats(index, t0)

    def _update_stats(self, index: int, t0: float) -> None:
        """Update histogram and statistics with adaptive frequency."""
        playing = self._engine.is_playing
        self._stats_update_counter += 1

        if playing:
            frame_ms = (time.perf_counter() - t0) * 1000
            budget_ok = frame_ms < 20

            if budget_ok and self._stats_update_counter % 8 == 0:
                self._pipeline.prefetch(index, direction=1, count=6)
            if budget_ok and self._stats_update_counter % 5 == 0:
                raw = self._pipeline.get_raw_frame(index)
                self._histogram.update_histogram(raw, subsample=True)
                stats = compute_stats(raw, self._roi, fast=True)
                self._statistics.update_stats(stats)
        else:
            raw = self._pipeline.get_raw_frame(index)
            self._histogram.update_histogram(raw)
            stats = compute_stats(raw, self._roi)
            self._statistics.update_stats(stats)

    def _on_adjustments_changed(self) -> None:
        if self._pipeline is None:
            return
        self._pipeline.brightness = self._adjustments.brightness
        self._pipeline.contrast = self._adjustments.contrast
        self._pipeline.gamma = self._adjustments.gamma
        self._pipeline.auto_stretch = self._adjustments.auto_stretch_enabled
        if not self._use_gl:
            self._pipeline.invalidate_cache()
        self._on_frame_changed(self._engine.current_frame)

    def _toggle_solar(self, enabled: bool) -> None:
        if self._pipeline is None:
            return
        self._pipeline.solar_colorize = enabled
        if not self._use_gl:
            self._pipeline.invalidate_cache()
        self._on_frame_changed(self._engine.current_frame)

    def _toggle_roi(self, enabled: bool) -> None:
        if enabled:
            self._add_roi()
        else:
            self._remove_roi()

    def _add_roi(self) -> None:
        if self._ser_file is None:
            return
        w = min(200, self._ser_file.width // 2)
        h = min(200, self._ser_file.height // 2)
        x = (self._ser_file.width - w) // 2
        y = (self._ser_file.height - h) // 2
        if self._use_gl:
            self._viewer.set_roi(x, y, w, h)
            self._viewer.roi_changed.connect(self._on_roi_changed)
            self._roi = self._viewer.get_roi()
        else:
            self._roi_item = ROISelector(x, y, w, h)
            self._roi_item.set_change_callback(self._on_roi_changed)
            self._viewer._scene.addItem(self._roi_item)
            self._roi = self._roi_item.get_roi()

    def _remove_roi(self) -> None:
        if self._use_gl:
            self._viewer.clear_roi()
            try:
                self._viewer.roi_changed.disconnect(self._on_roi_changed)
            except RuntimeError:
                pass
        elif self._roi_item:
            self._viewer._scene.removeItem(self._roi_item)
            self._roi_item = None
        self._roi = None
        if self._roi_action.isChecked():
            self._roi_action.setChecked(False)

    def _on_roi_changed(self, roi: tuple[int, int, int, int]) -> None:
        self._roi = roi
        if self._pipeline is not None:
            raw = self._pipeline.get_raw_frame(self._engine.current_frame)
            stats = compute_stats(raw, self._roi)
            self._statistics.update_stats(stats)

    def _on_trim_save(self, start: int, end: int) -> None:
        """Save trimmed SER file."""
        if self._ser_file is None:
            return

        # Suggest a filename based on the original
        src = self._ser_file.filepath
        suggested = src.parent / f"{src.stem}_trim_{start + 1}-{end + 1}{src.suffix}"

        filepath, _ = QFileDialog.getSaveFileName(
            self, tr("dlg_trim_save_title"), str(suggested), tr("dlg_filter"),
        )
        if not filepath:
            return

        try:
            count = self._ser_file.save_trimmed(filepath, start, end)
            QMessageBox.information(
                self, tr("dlg_trim_save_title"),
                tr("dlg_trim_success").format(count, filepath),
            )
        except Exception as e:
            QMessageBox.critical(self, tr("dlg_error"), tr("dlg_trim_error").format(e))

    # --- Analysis features ---

    def _add_analysis_tab(self, widget: QWidget, title: str) -> None:
        """Add a tab to analysis tabs if not already present."""
        for i in range(self._analysis_tabs.count()):
            if self._analysis_tabs.widget(i) is widget:
                self._analysis_tabs.setCurrentIndex(i)
                return
        self._analysis_tabs.addTab(widget, title)
        self._analysis_tabs.setCurrentWidget(widget)
        self._analysis_tabs.setVisible(True)

    def _remove_analysis_tab(self, widget: QWidget) -> None:
        """Remove a tab from analysis tabs."""
        idx = self._analysis_tabs.indexOf(widget)
        if idx >= 0:
            self._analysis_tabs.removeTab(idx)
        if self._analysis_tabs.count() == 0:
            self._analysis_tabs.setVisible(False)

    def _toggle_timestamp_panel(self, checked: bool) -> None:
        if checked and self._ser_file and self._ser_file.has_timestamps:
            self._timestamp_panel.set_timestamps(self._ser_file._timestamps)
            self._add_analysis_tab(self._timestamp_panel, tr("tab_timestamp"))
        elif checked and self._ser_file and not self._ser_file.has_timestamps:
            QMessageBox.information(self, tr("group_timestamp"), tr("ts_no_timestamps"))
            self._timestamp_action.setChecked(False)
        elif not checked:
            self._remove_analysis_tab(self._timestamp_panel)

    def _load_tracking_log(self) -> None:
        if self._ser_file is None:
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self, tr("menu_load_tracking"), "", "Log Files (*.log);;All Files (*)",
        )
        if not filepath:
            return
        self._load_tracking_log_file(filepath)

    def _toggle_lucky_panel(self, checked: bool) -> None:
        if checked and self._ser_file:
            self._lucky_panel.set_ser_file(self._ser_file)
            self._add_analysis_tab(self._lucky_panel, tr("tab_lucky"))
        elif not checked:
            self._remove_analysis_tab(self._lucky_panel)

    def _export_mp4(self) -> None:
        """Export current SER file to MP4."""
        if self._ser_file is None or self._pipeline is None:
            return

        has_roi = self._roi is not None
        has_tracking = bool(self._analysis_tabs.indexOf(self._tracking_panel) >= 0
                            and hasattr(self._tracking_panel, '_matched')
                            and self._tracking_panel._matched)

        # Build options dialog
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("dlg_export_mp4_title"))
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()

        # FPS
        fps_spin = QSpinBox()
        fps_spin.setRange(1, 120)
        default_fps = 25
        if self._ser_file.has_timestamps and len(self._ser_file._timestamps) > 1:
            deltas = np.diff(self._ser_file._timestamps.astype(np.int64)) / 10_000.0
            avg_ms = float(np.mean(deltas))
            if avg_ms > 0:
                default_fps = min(120, max(1, round(1000.0 / avg_ms)))
        fps_spin.setValue(default_fps)
        form.addRow(tr("mp4_fps_label"), fps_spin)

        # Quality (CRF)
        quality_layout = QHBoxLayout()
        quality_slider = QSlider(Qt.Orientation.Horizontal)
        quality_slider.setRange(15, 35)
        quality_slider.setValue(23)
        quality_label = QLabel("23")
        quality_slider.valueChanged.connect(lambda v: quality_label.setText(str(v)))
        quality_layout.addWidget(quality_slider)
        quality_layout.addWidget(quality_label)
        form.addRow(tr("mp4_quality_label"), quality_layout)

        # Trim range checkbox
        trim_check = QCheckBox(tr("mp4_use_trim"))
        trim_active = self._transport._timeline.trim_active
        trim_check.setChecked(trim_active)
        trim_check.setEnabled(trim_active)
        form.addRow("", trim_check)

        # Crop to ROI checkbox (always available — without ROI uses custom size centered)
        crop_check = QCheckBox(tr("mp4_crop_roi"))
        crop_check.setChecked(False)
        form.addRow("", crop_check)

        # Auto-center checkbox
        center_check = QCheckBox(tr("mp4_crop_center"))
        center_check.setChecked(False)
        center_check.setEnabled(bool(has_roi and has_tracking))
        form.addRow("", center_check)

        # Crop size (for when no ROI but user wants manual crop size with auto-center)
        crop_w_spin = QSpinBox()
        crop_w_spin.setRange(64, self._ser_file.width)
        crop_h_spin = QSpinBox()
        crop_h_spin.setRange(64, self._ser_file.height)
        if has_roi:
            crop_w_spin.setValue(self._roi[2])
            crop_h_spin.setValue(self._roi[3])
        else:
            crop_w_spin.setValue(min(640, self._ser_file.width))
            crop_h_spin.setValue(min(480, self._ser_file.height))
        size_layout = QHBoxLayout()
        size_layout.addWidget(crop_w_spin)
        size_layout.addWidget(QLabel("×"))
        size_layout.addWidget(crop_h_spin)
        form.addRow(tr("mp4_crop_size"), size_layout)

        # Show/hide crop size based on crop checkbox
        def _update_crop_ui():
            use_crop = crop_check.isChecked()
            center_check.setEnabled(bool(use_crop and has_tracking))
            crop_w_spin.setEnabled(use_crop)
            crop_h_spin.setEnabled(use_crop)
            if not use_crop:
                center_check.setChecked(False)

        crop_check.toggled.connect(_update_crop_ui)
        _update_crop_ui()

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        fps = fps_spin.value()
        quality = quality_slider.value()

        # Frame range
        if trim_check.isChecked():
            start = self._transport._timeline.trim_in
            end = self._transport._timeline.trim_out
        else:
            start = 0
            end = self._ser_file.frame_count - 1

        # Crop ROI
        crop_roi = None
        if crop_check.isChecked():
            cw, ch = crop_w_spin.value(), crop_h_spin.value()
            if has_roi:
                cx, cy = self._roi[0], self._roi[1]
            else:
                cx = (self._ser_file.width - cw) // 2
                cy = (self._ser_file.height - ch) // 2
            crop_roi = (cx, cy, cw, ch)

        # Tracking offsets for auto-centering
        tracking_offsets = None
        if center_check.isChecked() and has_tracking:
            matched = self._tracking_panel._matched
            tracking_offsets = []
            for entry in matched:
                if entry is not None:
                    tracking_offsets.append((entry.err_dx, entry.err_dy))
                else:
                    tracking_offsets.append(None)

        # Output path
        src = self._ser_file.filepath
        suggested = src.parent / f"{src.stem}.mp4"
        filepath, _ = QFileDialog.getSaveFileName(
            self, tr("dlg_export_mp4_title"), str(suggested), tr("dlg_mp4_filter"),
        )
        if not filepath:
            return

        total = end - start + 1

        # Progress dialog
        progress = QProgressDialog(tr("mp4_exporting"), tr("menu_exit"), 0, total, self)
        progress.setWindowTitle(tr("dlg_export_mp4_title"))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        cancelled = [False]

        def on_progress(current, total_frames):
            progress.setValue(current)
            if progress.wasCanceled():
                cancelled[0] = True
                return False
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            return True

        try:
            from ..core.mp4_export import export_mp4
            count = export_mp4(
                self._ser_file, self._pipeline,
                filepath, start, end, fps, quality,
                crop_roi=crop_roi,
                tracking_offsets=tracking_offsets,
                progress_cb=on_progress,
            )
            progress.close()

            if not cancelled[0]:
                QMessageBox.information(
                    self, tr("dlg_export_mp4_title"),
                    tr("mp4_success").format(count, filepath),
                )
        except Exception as e:
            progress.close()
            QMessageBox.critical(
                self, tr("dlg_export_mp4_title"),
                tr("mp4_error").format(str(e)),
            )

    def _show_about(self) -> None:
        QMessageBox.about(self, tr("about_title"), tr("about_text"))

    def closeEvent(self, event) -> None:
        self._close_file()
        settings = QSettings("AstroSER", "Player")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("splitterState", self._splitter.saveState())
        super().closeEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                lf = url.toLocalFile().lower()
                if lf.endswith('.ser') or lf.endswith('.log'):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith('.ser'):
                self.open_file(filepath)
                break
            elif filepath.lower().endswith('.log') and self._ser_file:
                self._load_tracking_log_file(filepath)
                break

    def _load_tracking_log_file(self, filepath: str) -> None:
        """Load a tracking log file by path."""
        from ..core.tracking_log import parse_tracking_log, match_log_to_frames
        from ..core.timestamp_analysis import get_utc_times
        from ..core.delay_analysis import compute_delay, compute_mount_response

        ref_date = self._ser_file.datetime_utc or self._ser_file.datetime_local
        log = parse_tracking_log(Path(filepath), ref_date)

        if not log.entries:
            return

        if self._ser_file.has_timestamps:
            frame_utcs = get_utc_times(self._ser_file._timestamps)
        else:
            frame_utcs = [None] * self._ser_file.frame_count

        matched = match_log_to_frames(log, frame_utcs)
        self._tracking_panel.set_data(log, matched)
        self._add_analysis_tab(self._tracking_panel, tr("tab_tracking"))
        self._tracking_panel.update_frame(self._engine.current_frame)

        # Compute delay and mount response
        avg_interval_ms = 33.0
        if self._ser_file.has_timestamps and len(self._ser_file._timestamps) > 1:
            deltas = np.diff(self._ser_file._timestamps.astype(np.int64)) / 10_000.0
            avg_interval_ms = float(np.mean(deltas))

        delay_stats = compute_delay(log.entries, avg_interval_ms)
        mount_resp = compute_mount_response(log)

        if delay_stats or mount_resp:
            if delay_stats:
                self._mount_panel.set_delay(delay_stats)
            if mount_resp:
                self._mount_panel.set_response(mount_resp)
            self._add_analysis_tab(self._mount_panel, tr("tab_mount"))
