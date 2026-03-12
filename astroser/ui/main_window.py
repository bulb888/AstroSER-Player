"""Main application window."""

from pathlib import Path
from typing import Optional

import numpy as np

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QVBoxLayout, QWidget,
    QSplitter, QStatusBar, QLabel, QScrollArea,
)

import time

from ..core.ser_parser import SERFile, ColorID
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

        self._file_info = FileInfoPanel()
        right_layout.addWidget(self._file_info)

        self._adjustments = AdjustmentsPanel()
        right_layout.addWidget(self._adjustments)

        self._histogram = HistogramWidget()
        right_layout.addWidget(self._histogram)

        self._statistics = StatisticsPanel()
        right_layout.addWidget(self._statistics)

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

        self._file_info.update_info(ser)

        self._status_file.setText(Path(filepath).name)
        self._status_info.setText(
            f"{ser.width}\u00d7{ser.height} | "
            f"{ser.color_id.display_name} | "
            f"{ser.pixel_depth}bit | "
            f"{tr('status_frames').format(ser.frame_count)}"
        )

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
        self._file_info.clear()
        self._histogram.clear()
        self._statistics.clear()

    def _on_frame_changed(self, index: int) -> None:
        if self._pipeline is None:
            return
        try:
            t0 = time.perf_counter()

            if self._use_gl:
                self._on_frame_changed_gl(index, t0)
            else:
                self._on_frame_changed_sw(index, t0)

        except Exception as e:
            print(f"Frame {index} render error: {e}")

    def _on_frame_changed_gl(self, index: int, t0: float) -> None:
        """GL path: upload raw frame to GPU, shader does adjustments."""
        frame = self._pipeline.get_display_frame(index)
        color_id = self._ser_file.color_id
        is_mono = not color_id.is_color and not color_id.is_bayer
        pixel_max = float((1 << self._ser_file.pixel_depth) - 1)

        # GL normalizes textures by type max (255 for uint8, 65535 for uint16)
        # We need a rescale factor so shader maps [0, pixel_max] -> [0, 1]
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
            if budget_ok and self._stats_update_counter % 30 == 0:
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
        if self._use_gl:
            # ROI not yet supported in GL mode
            return
        w = min(200, self._ser_file.width // 2)
        h = min(200, self._ser_file.height // 2)
        x = (self._ser_file.width - w) // 2
        y = (self._ser_file.height - h) // 2
        self._roi_item = ROISelector(x, y, w, h)
        self._roi_item.set_change_callback(self._on_roi_changed)
        self._viewer._scene.addItem(self._roi_item)
        self._roi = self._roi_item.get_roi()

    def _remove_roi(self) -> None:
        if self._roi_item and not self._use_gl:
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

    def _show_about(self) -> None:
        QMessageBox.about(self, tr("about_title"), tr("about_text"))

    def closeEvent(self, event) -> None:
        self._close_file()
        settings = QSettings("AstroSER", "Player")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        super().closeEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.ser'):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith('.ser'):
                self.open_file(filepath)
                break
