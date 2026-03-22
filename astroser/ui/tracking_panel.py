"""Tracking log overlay panel — shows err_dx/dy and vp/vi curves."""

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QLabel, QHBoxLayout,
)

from ..core.tracking_log import TrackingLog, TrackingEntry
from .chart_widget import ChartWidget
from .i18n import tr, I18n

_INFO_STYLE = (
    "QLabel { color: #e0e0e0; font-size: 11px; "
    "font-family: 'Cascadia Mono', 'Consolas', monospace; "
    "background: #252525; border: 1px solid #333333; "
    "border-radius: 3px; padding: 3px 6px; }"
)


class TrackingPanel(QWidget):
    """Panel showing tracking error and control curves."""

    frame_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log: TrackingLog | None = None
        self._matched: list[TrackingEntry | None] = []
        self._setup_ui()
        I18n.instance().language_changed.connect(self.retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Session info
        self._session_label = QLabel("-")
        self._session_label.setStyleSheet(_INFO_STYLE)
        self._session_label.setWordWrap(True)
        layout.addWidget(self._session_label)

        # Error chart (dx/dy)
        self._err_group = QGroupBox("Error dx/dy (px)")
        err_layout = QVBoxLayout(self._err_group)
        err_layout.setContentsMargins(4, 4, 4, 4)
        self._err_chart = ChartWidget()
        self._err_chart.setMinimumHeight(90)
        self._err_chart.frame_clicked.connect(lambda i: self.frame_selected.emit(i))
        err_layout.addWidget(self._err_chart)
        layout.addWidget(self._err_group)

        # Control chart (vp/vi)
        self._ctrl_group = QGroupBox("Control vp/vi")
        ctrl_layout = QVBoxLayout(self._ctrl_group)
        ctrl_layout.setContentsMargins(4, 4, 4, 4)
        self._ctrl_chart = ChartWidget()
        self._ctrl_chart.setMinimumHeight(90)
        self._ctrl_chart.frame_clicked.connect(lambda i: self.frame_selected.emit(i))
        ctrl_layout.addWidget(self._ctrl_chart)
        layout.addWidget(self._ctrl_group)

        # Current frame OSD info
        self._osd_label = QLabel("-")
        self._osd_label.setStyleSheet(_INFO_STYLE)
        layout.addWidget(self._osd_label)

        self.retranslate()

    def retranslate(self):
        self._err_group.setTitle(tr("group_tracking_error") if tr("group_tracking_error") != "group_tracking_error" else "Error dx/dy (px)")
        self._ctrl_group.setTitle(tr("group_tracking_ctrl") if tr("group_tracking_ctrl") != "group_tracking_ctrl" else "Control vp/vi")

    def set_data(self, log: TrackingLog, matched: list[TrackingEntry | None]):
        """Set tracking data matched to frames."""
        self._log = log
        self._matched = matched

        if log.session_header:
            self._session_label.setText(log.session_header.split(" ", 1)[-1][:80] if " " in log.session_header else log.session_header[:80])
        else:
            self._session_label.setText("-")

        n = len(matched)
        err_dx = np.full(n, np.nan)
        err_dy = np.full(n, np.nan)
        vp_x = np.full(n, np.nan)
        vp_y = np.full(n, np.nan)
        vi_x = np.full(n, np.nan)
        vi_y = np.full(n, np.nan)

        for i, entry in enumerate(matched):
            if entry is not None:
                err_dx[i] = entry.err_dx
                err_dy[i] = entry.err_dy
                vp_x[i] = entry.vp_x
                vp_y[i] = entry.vp_y
                vi_x[i] = entry.vi_x
                vi_y[i] = entry.vi_y

        self._err_chart.set_data(err_dx, QColor(76, 159, 230), "dx", index=0)
        self._err_chart.set_data(err_dy, QColor(230, 160, 50), "dy", index=1)

        self._ctrl_chart.set_data(vp_x, QColor(100, 200, 100), "vp_x", index=0)
        self._ctrl_chart.set_data(vp_y, QColor(200, 100, 200), "vp_y", index=1)
        self._ctrl_chart.set_data(vi_x, QColor(76, 159, 230, 150), "vi_x", index=2)
        self._ctrl_chart.set_data(vi_y, QColor(230, 160, 50, 150), "vi_y", index=3)

    def update_frame(self, frame_idx: int):
        """Update OSD for current frame."""
        if 0 <= frame_idx < len(self._matched) and self._matched[frame_idx] is not None:
            e = self._matched[frame_idx]
            det = "Y" if e.detected else "N"
            self._osd_label.setText(
                f"det={det}  dx={e.err_dx:+.1f}  dy={e.err_dy:+.1f}  "
                f"vp={e.vp_x:+.4f}/{e.vp_y:+.4f}  lost={e.lost_count}"
            )
        else:
            self._osd_label.setText("-")

    def get_osd_text(self, frame_idx: int) -> str:
        """Get OSD overlay text for painting on the viewer."""
        if 0 <= frame_idx < len(self._matched) and self._matched[frame_idx] is not None:
            e = self._matched[frame_idx]
            det = "Y" if e.detected else "N"
            return (
                f"det={det}  err=({e.err_dx:+.1f}, {e.err_dy:+.1f})  "
                f"vp=({e.vp_x:+.4f}, {e.vp_y:+.4f})  "
                f"vi=({e.vi_x:+.4f}, {e.vi_y:+.4f})"
            )
        return ""

    def clear(self):
        self._log = None
        self._matched = []
        self._session_label.setText("-")
        self._osd_label.setText("-")
        self._err_chart.clear()
        self._ctrl_chart.clear()
