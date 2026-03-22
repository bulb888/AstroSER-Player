"""Lucky imaging frame selection and export panel."""

import numpy as np
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QSlider, QPushButton, QFileDialog, QMessageBox, QProgressDialog,
    QApplication,
)

from ..core.ser_parser import SERFile
from ..core.statistics import compute_sharpness
from .chart_widget import ChartWidget
from .i18n import tr, I18n

_VAL_STYLE = (
    "QLabel { color: #e0e0e0; font-size: 12px; "
    "font-family: 'Cascadia Mono', 'Consolas', monospace; "
    "font-weight: 500; background: #252525; border: 1px solid #333333; "
    "border-radius: 3px; padding: 2px 6px; }"
)


class LuckyPanel(QWidget):
    """Panel for Lucky imaging: rank frames by sharpness, export top N%."""

    frames_selected = Signal(list)  # list of selected frame indices for timeline highlight

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ser_file: SERFile | None = None
        self._sharpness: np.ndarray | None = None
        self._sorted_indices: np.ndarray | None = None
        self._top_pct = 10
        self._setup_ui()
        I18n.instance().language_changed.connect(self.retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._group = QGroupBox()
        gl = QVBoxLayout(self._group)
        gl.setSpacing(4)

        # Top N% slider
        slider_row = QHBoxLayout()
        self._pct_label = QLabel()
        self._pct_label.setStyleSheet(_VAL_STYLE)
        slider_row.addWidget(self._pct_label, stretch=1)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(1)
        self._slider.setMaximum(100)
        self._slider.setValue(10)
        self._slider.valueChanged.connect(self._on_pct_changed)
        slider_row.addWidget(self._slider, stretch=2)
        gl.addLayout(slider_row)

        # Sharpness chart
        self._chart = ChartWidget()
        self._chart.setMinimumHeight(80)
        gl.addWidget(self._chart)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_analyze = QPushButton()
        self._btn_analyze.setStyleSheet("QPushButton { font-size: 11px; padding: 3px 10px; }")
        self._btn_analyze.clicked.connect(self._on_analyze)
        btn_row.addWidget(self._btn_analyze)

        btn_row.addStretch()

        self._btn_export = QPushButton()
        self._btn_export.setStyleSheet("QPushButton { font-size: 11px; padding: 3px 10px; }")
        self._btn_export.clicked.connect(self._on_export)
        self._btn_export.setEnabled(False)
        btn_row.addWidget(self._btn_export)

        gl.addLayout(btn_row)
        layout.addWidget(self._group)
        self.retranslate()
        self._update_pct_label()

    def retranslate(self):
        self._group.setTitle(tr("group_lucky"))
        self._btn_analyze.setText(tr("btn_reset").replace(tr("btn_reset"), "Analyze") if tr("btn_reset") == "Reset" else "分析锐度")
        self._btn_analyze.setText("Analyze" if I18n.instance().lang == "en" else "分析锐度")
        self._btn_export.setText(tr("btn_lucky_export"))
        self._update_pct_label()

    def set_ser_file(self, ser_file: SERFile):
        self._ser_file = ser_file
        self._sharpness = None
        self._sorted_indices = None
        self._btn_export.setEnabled(False)
        self._chart.clear()
        self._update_pct_label()

    def clear(self):
        self._ser_file = None
        self._sharpness = None
        self._sorted_indices = None
        self._btn_export.setEnabled(False)
        self._chart.clear()
        self._update_pct_label()

    def _update_pct_label(self):
        self._top_pct = self._slider.value()
        if self._sharpness is not None:
            count = max(1, int(len(self._sharpness) * self._top_pct / 100))
            self._pct_label.setText(tr("lucky_top_pct").format(self._top_pct, count))
        else:
            self._pct_label.setText(f"Top {self._top_pct}%")

    def _on_pct_changed(self, val):
        self._update_pct_label()
        self._emit_selected()

    def _on_analyze(self):
        """Compute sharpness for all frames."""
        if self._ser_file is None:
            return

        n = self._ser_file.frame_count
        progress = QProgressDialog("Computing sharpness...", "Cancel", 0, n, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        sharpness = np.zeros(n, dtype=np.float64)
        for i in range(n):
            if progress.wasCanceled():
                return
            frame = self._ser_file.get_frame(i)
            if frame.ndim == 3:
                # Convert to grayscale
                gray = np.mean(frame, axis=2)
            else:
                gray = frame.astype(np.float64)
            sharpness[i] = compute_sharpness(gray)
            if i % 10 == 0:
                progress.setValue(i)
                QApplication.processEvents()

        progress.setValue(n)

        self._sharpness = sharpness
        self._sorted_indices = np.argsort(sharpness)[::-1]  # highest first

        self._chart.set_data(sharpness, label="sharpness")
        self._btn_export.setEnabled(True)
        self._update_pct_label()
        self._emit_selected()

    def _emit_selected(self):
        if self._sorted_indices is None:
            return
        count = max(1, int(len(self._sorted_indices) * self._top_pct / 100))
        selected = self._sorted_indices[:count].tolist()
        self.frames_selected.emit(selected)

    def _on_export(self):
        """Export top N% frames as new SER file."""
        if self._ser_file is None or self._sorted_indices is None:
            return

        count = max(1, int(len(self._sorted_indices) * self._top_pct / 100))
        selected = sorted(self._sorted_indices[:count].tolist())

        src = self._ser_file.filepath
        suggested = src.parent / f"{src.stem}_lucky{self._top_pct}pct{src.suffix}"

        filepath, _ = QFileDialog.getSaveFileName(
            self, tr("dlg_lucky_export"), str(suggested), "SER Files (*.ser);;All Files (*)",
        )
        if not filepath:
            return

        try:
            self._export_frames(filepath, selected)
            QMessageBox.information(
                self, tr("dlg_lucky_export"),
                tr("dlg_lucky_success").format(len(selected), filepath),
            )
        except Exception as e:
            QMessageBox.critical(self, tr("dlg_error"), str(e))

    def _export_frames(self, output_path: str, frame_indices: list[int]):
        """Export selected frames to a new SER file."""
        import struct
        from ..core.ser_parser import TOTAL_HEADER_SIZE, FILE_ID_SIZE

        ser = self._ser_file
        new_count = len(frame_indices)

        with open(ser.filepath, "rb") as src:
            header_data = bytearray(src.read(TOTAL_HEADER_SIZE))

        # Patch frame count
        frame_count_offset = FILE_ID_SIZE + 6 * 4
        struct.pack_into("<i", header_data, frame_count_offset, new_count)

        with open(output_path, "wb") as out:
            out.write(header_data)

            frame_bytes = ser.frame_size_bytes
            with open(ser.filepath, "rb") as src:
                for idx in frame_indices:
                    src.seek(TOTAL_HEADER_SIZE + idx * frame_bytes)
                    out.write(src.read(frame_bytes))

            # Write timestamps if present
            if ser.has_timestamps:
                ts_array = np.array([ser._timestamps[i] for i in frame_indices], dtype=np.int64)
                out.write(ts_array.tobytes())
