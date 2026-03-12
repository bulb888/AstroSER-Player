"""Frame statistics display panel."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLabel,
)

from ..core.statistics import FrameStats
from .i18n import tr, I18n


class StatisticsPanel(QWidget):
    """Panel displaying frame statistics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        I18n.instance().language_changed.connect(self.retranslate)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._group = QGroupBox()
        self._form = QFormLayout(self._group)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._min_label = QLabel("-")
        self._max_label = QLabel("-")
        self._mean_label = QLabel("-")
        self._std_label = QLabel("-")
        self._sharp_label = QLabel("-")

        self._row_labels = []
        for val_label in (self._min_label, self._max_label, self._mean_label,
                          self._std_label, self._sharp_label):
            row_label = QLabel()
            self._row_labels.append(row_label)
            self._form.addRow(row_label, val_label)

        layout.addWidget(self._group)
        self.retranslate()

    def retranslate(self) -> None:
        self._group.setTitle(tr("group_statistics"))
        keys = ["stat_min", "stat_max", "stat_mean", "stat_std", "stat_sharpness"]
        for label, key in zip(self._row_labels, keys):
            label.setText(tr(key))

    def update_stats(self, stats: FrameStats) -> None:
        self._min_label.setText(f"{stats.min_val:.1f}")
        self._max_label.setText(f"{stats.max_val:.1f}")
        self._mean_label.setText(f"{stats.mean_val:.1f}")
        self._std_label.setText(f"{stats.std_val:.2f}")
        self._sharp_label.setText(f"{stats.sharpness:.1f}")

    def clear(self) -> None:
        for label in (self._min_label, self._max_label, self._mean_label,
                      self._std_label, self._sharp_label):
            label.setText("-")
