"""Image adjustments panel with sliders."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QCheckBox, QGroupBox, QPushButton,
)

from .i18n import tr, I18n

_SLIDER_LABEL_STYLE = (
    "QLabel { color: #b0b0b0; font-size: 12px; font-weight: 500; min-width: 54px; }"
)
_VALUE_LABEL_STYLE = (
    "QLabel { color: #d0d0d0; font-size: 12px; font-family: 'Cascadia Mono', 'Consolas', monospace; "
    "font-weight: 500; min-width: 38px; }"
)


class _LabeledSlider(QWidget):
    """Slider with label and value display."""
    value_changed = Signal(float)

    def __init__(self, label: str, min_val: float, max_val: float,
                 default: float, step: float = 0.01, parent=None):
        super().__init__(parent)
        self._min = min_val
        self._max = max_val
        self._step = step
        self._default = default

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        self._label = QLabel(label)
        self._label.setStyleSheet(_SLIDER_LABEL_STYLE)
        layout.addWidget(self._label)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(int((max_val - min_val) / step))
        self._slider.setValue(int((default - min_val) / step))
        self._slider.valueChanged.connect(self._on_changed)
        layout.addWidget(self._slider, stretch=1)

        self._value_label = QLabel(f"{default:.2f}")
        self._value_label.setStyleSheet(_VALUE_LABEL_STYLE)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._value_label)

    def set_label(self, text: str) -> None:
        self._label.setText(text)

    def _on_changed(self, tick: int) -> None:
        val = self._min + tick * self._step
        self._value_label.setText(f"{val:.2f}")
        self.value_changed.emit(val)

    def value(self) -> float:
        return self._min + self._slider.value() * self._step

    def reset(self) -> None:
        self._slider.setValue(int((self._default - self._min) / self._step))


class AdjustmentsPanel(QWidget):
    """Panel with image adjustment controls."""

    adjustments_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        I18n.instance().language_changed.connect(self.retranslate)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._group = QGroupBox()
        group_layout = QVBoxLayout(self._group)
        group_layout.setSpacing(4)

        self._brightness = _LabeledSlider("", -1.0, 1.0, 0.0, 0.01)
        self._brightness.value_changed.connect(lambda _: self.adjustments_changed.emit())
        group_layout.addWidget(self._brightness)

        self._contrast = _LabeledSlider("", 0.1, 3.0, 1.0, 0.01)
        self._contrast.value_changed.connect(lambda _: self.adjustments_changed.emit())
        group_layout.addWidget(self._contrast)

        self._gamma = _LabeledSlider("Gamma", 0.1, 3.0, 1.0, 0.01)
        self._gamma.value_changed.connect(lambda _: self.adjustments_changed.emit())
        group_layout.addWidget(self._gamma)

        stretch_row = QHBoxLayout()
        stretch_row.setContentsMargins(0, 2, 0, 2)
        self._auto_stretch = QCheckBox()
        self._auto_stretch.setChecked(False)
        self._auto_stretch.setStyleSheet("QCheckBox { font-size: 11px; color: #999999; }")
        self._auto_stretch.toggled.connect(lambda _: self.adjustments_changed.emit())
        stretch_row.addWidget(self._auto_stretch)
        stretch_row.addStretch()
        group_layout.addLayout(stretch_row)

        self._reset_btn = QPushButton()
        self._reset_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 3px 10px; }"
        )
        self._reset_btn.clicked.connect(self._reset)
        group_layout.addWidget(self._reset_btn)

        layout.addWidget(self._group)
        layout.addStretch()

        self.retranslate()

    def retranslate(self) -> None:
        self._group.setTitle(tr("group_adjustments"))
        self._brightness.set_label(tr("adj_brightness"))
        self._contrast.set_label(tr("adj_contrast"))
        self._auto_stretch.setText(tr("adj_auto_stretch"))
        self._reset_btn.setText(tr("btn_reset"))

    def _reset(self) -> None:
        self._brightness.reset()
        self._contrast.reset()
        self._gamma.reset()
        self._auto_stretch.setChecked(False)
        self.adjustments_changed.emit()

    @property
    def brightness(self) -> float:
        return self._brightness.value()

    @property
    def contrast(self) -> float:
        return self._contrast.value()

    @property
    def gamma(self) -> float:
        return self._gamma.value()

    @property
    def auto_stretch_enabled(self) -> bool:
        return self._auto_stretch.isChecked()
