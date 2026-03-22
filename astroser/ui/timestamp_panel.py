"""Timestamp quality analysis panel."""

import numpy as np
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLabel, QPushButton, QFileDialog,
)

from ..core.timestamp_analysis import (
    analyze_timestamps, get_deltas_ms, export_csv, TimestampReport,
)
from .chart_widget import ChartWidget
from .i18n import tr, I18n

_ROW_STYLE = "QLabel { color: #8a8a8a; font-size: 12px; font-weight: 500; padding: 2px 0; }"
_VAL_STYLE = (
    "QLabel { color: #e0e0e0; font-size: 12px; "
    "font-family: 'Cascadia Mono', 'Consolas', monospace; "
    "font-weight: 500; background: #252525; border: 1px solid #333333; "
    "border-radius: 3px; padding: 2px 6px; }"
)
_ANOMALY_STYLE = (
    "QLabel { color: #ff6666; font-size: 12px; "
    "font-family: 'Cascadia Mono', 'Consolas', monospace; "
    "font-weight: 500; background: #2a1515; border: 1px solid #553333; "
    "border-radius: 3px; padding: 2px 6px; }"
)


class TimestampPanel(QWidget):
    """Panel showing timestamp quality analysis and delta chart."""

    frame_selected = Signal(int)  # 0-based frame index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timestamps = None
        self._report: TimestampReport | None = None
        self._setup_ui()
        I18n.instance().language_changed.connect(self.retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Stats group
        self._group = QGroupBox()
        form = QFormLayout(self._group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(4)
        form.setHorizontalSpacing(8)

        self._lbl_fps = self._make_val("-")
        self._lbl_avg = self._make_val("-")
        self._lbl_minmax = self._make_val("-")
        self._lbl_std = self._make_val("-")
        self._lbl_zero = self._make_val("-")
        self._lbl_anomaly = self._make_val("-")
        self._lbl_duration = self._make_val("-")

        self._row_labels = []
        fields = [
            ("ts_fps", self._lbl_fps),
            ("ts_avg_delta", self._lbl_avg),
            ("ts_minmax", self._lbl_minmax),
            ("ts_std", self._lbl_std),
            ("ts_zero", self._lbl_zero),
            ("ts_anomaly", self._lbl_anomaly),
            ("ts_duration", self._lbl_duration),
        ]
        self._field_keys = [k for k, _ in fields]
        for key, val_label in fields:
            rl = QLabel()
            rl.setStyleSheet(_ROW_STYLE)
            self._row_labels.append(rl)
            form.addRow(rl, val_label)

        layout.addWidget(self._group)

        # Delta chart
        self._chart = ChartWidget()
        self._chart.setMinimumHeight(100)
        self._chart.frame_clicked.connect(self._on_chart_click)
        layout.addWidget(self._chart)

        # Export button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_export = QPushButton()
        self._btn_export.setStyleSheet("QPushButton { font-size: 11px; padding: 3px 10px; }")
        self._btn_export.clicked.connect(self._on_export)
        self._btn_export.setEnabled(False)
        btn_row.addWidget(self._btn_export)
        layout.addLayout(btn_row)

        self.retranslate()

    @staticmethod
    def _make_val(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(_VAL_STYLE)
        return lbl

    def retranslate(self):
        self._group.setTitle(tr("group_timestamp"))
        keys = ["ts_fps", "ts_avg_delta", "ts_minmax", "ts_std",
                "ts_zero", "ts_anomaly", "ts_duration"]
        for lbl, key in zip(self._row_labels, keys):
            lbl.setText(tr(key))
        self._btn_export.setText(tr("btn_export_csv"))

    def set_timestamps(self, timestamps: np.ndarray):
        """Load timestamps and compute analysis."""
        self._timestamps = timestamps
        self._report = analyze_timestamps(timestamps)
        r = self._report

        self._lbl_fps.setText(f"{r.avg_fps:.2f}")
        self._lbl_avg.setText(f"{r.avg_delta_ms:.2f} ms")
        self._lbl_minmax.setText(f"{r.min_delta_ms:.2f} / {r.max_delta_ms:.2f} ms")
        self._lbl_std.setText(f"{r.std_delta_ms:.3f} ms")

        self._lbl_zero.setText(f"{r.zero_delta_count} ({r.zero_delta_pct:.1f}%)")
        if r.zero_delta_count > 0:
            self._lbl_zero.setStyleSheet(_ANOMALY_STYLE)
        else:
            self._lbl_zero.setStyleSheet(_VAL_STYLE)

        self._lbl_anomaly.setText(f"{r.anomaly_count} ({r.anomaly_pct:.1f}%)")
        if r.anomaly_count > 0:
            self._lbl_anomaly.setStyleSheet(_ANOMALY_STYLE)
        else:
            self._lbl_anomaly.setStyleSheet(_VAL_STYLE)

        self._lbl_duration.setText(f"{r.duration_sec:.2f} s")

        # Update chart
        deltas = get_deltas_ms(timestamps)
        self._chart.set_data(deltas, label="delta(ms)")

        # Mark anomalies
        if r.avg_delta_ms > 0:
            mask = (deltas == 0) | (deltas > 2 * r.avg_delta_ms)
            anomaly_idx = np.where(mask)[0]
            self._chart.set_anomalies(anomaly_idx)

        self._btn_export.setEnabled(True)

    def clear(self):
        self._timestamps = None
        self._report = None
        for lbl in (self._lbl_fps, self._lbl_avg, self._lbl_minmax,
                    self._lbl_std, self._lbl_zero, self._lbl_anomaly,
                    self._lbl_duration):
            lbl.setText("-")
            lbl.setStyleSheet(_VAL_STYLE)
        self._chart.clear()
        self._btn_export.setEnabled(False)

    def _on_chart_click(self, idx: int):
        # Chart index is delta index (between frames), map to frame
        self.frame_selected.emit(idx + 1)

    def _on_export(self):
        if self._timestamps is None:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, tr("dlg_export_csv"), "", "CSV (*.csv);;All Files (*)",
        )
        if filepath:
            export_csv(Path(filepath), self._timestamps)
