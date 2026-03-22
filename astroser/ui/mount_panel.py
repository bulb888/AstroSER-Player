"""Mount response and delay analysis panel."""

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLabel,
)

from ..core.delay_analysis import DelayStats, MountResponse
from .chart_widget import ChartWidget
from .i18n import tr, I18n

_ROW_STYLE = "QLabel { color: #8a8a8a; font-size: 12px; font-weight: 500; padding: 2px 0; }"
_VAL_STYLE = (
    "QLabel { color: #e0e0e0; font-size: 12px; "
    "font-family: 'Cascadia Mono', 'Consolas', monospace; "
    "font-weight: 500; background: #252525; border: 1px solid #333333; "
    "border-radius: 3px; padding: 2px 6px; }"
)


class MountPanel(QWidget):
    """Panel showing mount response curves and delay analysis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        I18n.instance().language_changed.connect(self.retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Delay stats group
        self._delay_group = QGroupBox()
        form = QFormLayout(self._delay_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(4)
        form.setHorizontalSpacing(8)

        self._lbl_avg = self._make_val("-")
        self._lbl_max = self._make_val("-")
        self._lbl_p95 = self._make_val("-")
        self._lbl_median = self._make_val("-")
        self._lbl_backlash = self._make_val("-")
        self._lbl_mount = self._make_val("-")

        self._row_labels = []
        for key, val in [
            ("delay_avg", self._lbl_avg),
            ("delay_max", self._lbl_max),
            ("delay_p95", self._lbl_p95),
            ("delay_median", self._lbl_median),
            ("mount_backlash", self._lbl_backlash),
            ("mount_info", self._lbl_mount),
        ]:
            rl = QLabel()
            rl.setStyleSheet(_ROW_STYLE)
            self._row_labels.append((key, rl))
            form.addRow(rl, val)

        layout.addWidget(self._delay_group)

        # Response curve: command vs response (primary axis)
        self._cmd_group = QGroupBox("RA/Az: Command vs Response")
        cmd_layout = QVBoxLayout(self._cmd_group)
        cmd_layout.setContentsMargins(4, 4, 4, 4)
        self._cmd_chart = ChartWidget()
        self._cmd_chart.setMinimumHeight(80)
        cmd_layout.addWidget(self._cmd_chart)
        layout.addWidget(self._cmd_group)

        # Secondary axis
        self._cmd2_group = QGroupBox("Dec/Alt: Command vs Response")
        cmd2_layout = QVBoxLayout(self._cmd2_group)
        cmd2_layout.setContentsMargins(4, 4, 4, 4)
        self._cmd2_chart = ChartWidget()
        self._cmd2_chart.setMinimumHeight(80)
        cmd2_layout.addWidget(self._cmd2_chart)
        layout.addWidget(self._cmd2_group)

        self.retranslate()

    @staticmethod
    def _make_val(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(_VAL_STYLE)
        return lbl

    def retranslate(self):
        self._delay_group.setTitle(tr("group_delay") if tr("group_delay") != "group_delay" else "Control Delay")
        labels = {
            "delay_avg": "Avg Delay:",
            "delay_max": "Max Delay:",
            "delay_p95": "P95 Delay:",
            "delay_median": "Median:",
            "mount_backlash": "Backlash:",
            "mount_info": "Mount:",
        }
        for key, rl in self._row_labels:
            rl.setText(labels.get(key, key))

    def set_delay(self, stats: DelayStats):
        self._lbl_avg.setText(f"{stats.avg_delay_ms:.1f} ms")
        self._lbl_max.setText(f"{stats.max_delay_ms:.1f} ms")
        self._lbl_p95.setText(f"{stats.p95_delay_ms:.1f} ms")
        self._lbl_median.setText(f"{stats.median_delay_ms:.1f} ms (n={stats.sample_count})")

    def set_response(self, resp: MountResponse):
        if resp.mount_info:
            self._lbl_mount.setText(resp.mount_info[:60])
        else:
            self._lbl_mount.setText("-")

        self._lbl_backlash.setText(
            f"RA: {resp.backlash_primary:.1f} px  Dec: {resp.backlash_secondary:.1f} px"
        )

        # Primary axis chart: command + response
        self._cmd_chart.set_data(resp.cmd_primary, QColor(230, 160, 50), "cmd", index=0)
        self._cmd_chart.set_data(resp.resp_dx, QColor(76, 159, 230), "resp", index=1)

        # Secondary axis chart
        self._cmd2_chart.set_data(resp.cmd_secondary, QColor(230, 160, 50), "cmd", index=0)
        self._cmd2_chart.set_data(resp.resp_dy, QColor(76, 159, 230), "resp", index=1)

    def clear(self):
        for lbl in (self._lbl_avg, self._lbl_max, self._lbl_p95,
                    self._lbl_median, self._lbl_backlash, self._lbl_mount):
            lbl.setText("-")
        self._cmd_chart.clear()
        self._cmd2_chart.clear()
