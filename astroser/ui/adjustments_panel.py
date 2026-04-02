"""Image adjustments panel with sliders, deconvolution, and crop controls."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QCheckBox, QGroupBox, QPushButton, QSpinBox,
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
    """Panel with image adjustment, deconvolution, and crop controls."""

    adjustments_changed = Signal()
    crop_changed = Signal()  # Emitted when crop/center settings change

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        I18n.instance().language_changed.connect(self.retranslate)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # --- Image adjustments group ---
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

        self._sharpen = _LabeledSlider("", 0.0, 5.0, 0.0, 0.1)
        self._sharpen.value_changed.connect(lambda _: self.adjustments_changed.emit())
        group_layout.addWidget(self._sharpen)

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

        # --- Deconvolution group ---
        self._deconv_group = QGroupBox()
        deconv_layout = QVBoxLayout(self._deconv_group)
        deconv_layout.setSpacing(4)

        self._deconv_enable = QCheckBox()
        self._deconv_enable.setChecked(False)
        self._deconv_enable.setStyleSheet("QCheckBox { font-size: 11px; color: #999999; }")
        self._deconv_enable.toggled.connect(lambda _: self.adjustments_changed.emit())
        deconv_layout.addWidget(self._deconv_enable)

        self._psf_radius = _LabeledSlider("PSF", 0.5, 5.0, 1.5, 0.1)
        self._psf_radius.value_changed.connect(lambda _: self.adjustments_changed.emit())
        deconv_layout.addWidget(self._psf_radius)

        self._deconv_iters = _LabeledSlider("", 1.0, 50.0, 10.0, 1.0)
        self._deconv_iters.value_changed.connect(lambda _: self.adjustments_changed.emit())
        deconv_layout.addWidget(self._deconv_iters)

        layout.addWidget(self._deconv_group)

        # --- Crop group ---
        self._crop_group = QGroupBox()
        crop_layout = QVBoxLayout(self._crop_group)
        crop_layout.setSpacing(4)

        self._crop_enable = QCheckBox()
        self._crop_enable.setChecked(False)
        self._crop_enable.setStyleSheet("QCheckBox { font-size: 11px; color: #999999; }")
        self._crop_enable.toggled.connect(self._on_crop_toggled)
        crop_layout.addWidget(self._crop_enable)

        # Crop size
        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 0, 0, 0)
        self._crop_w_label = QLabel()
        self._crop_w_label.setStyleSheet(_SLIDER_LABEL_STYLE)
        size_row.addWidget(self._crop_w_label)
        self._crop_w = QSpinBox()
        self._crop_w.setRange(64, 9999)
        self._crop_w.setValue(640)
        self._crop_w.valueChanged.connect(lambda _: self.crop_changed.emit())
        size_row.addWidget(self._crop_w)
        size_row.addWidget(QLabel("×"))
        self._crop_h = QSpinBox()
        self._crop_h.setRange(64, 9999)
        self._crop_h.setValue(480)
        self._crop_h.valueChanged.connect(lambda _: self.crop_changed.emit())
        size_row.addWidget(self._crop_h)
        crop_layout.addLayout(size_row)

        # Center target
        self._center_target = QCheckBox()
        self._center_target.setChecked(False)
        self._center_target.setStyleSheet("QCheckBox { font-size: 11px; color: #999999; }")
        crop_layout.addWidget(self._center_target)

        # Detection threshold
        self._threshold = _LabeledSlider("", 50.0, 98.0, 85.0, 1.0)
        crop_layout.addWidget(self._threshold)

        layout.addWidget(self._crop_group)

        layout.addStretch()

        self.retranslate()

    def retranslate(self) -> None:
        self._group.setTitle(tr("group_adjustments"))
        self._brightness.set_label(tr("adj_brightness"))
        self._contrast.set_label(tr("adj_contrast"))
        self._sharpen.set_label(tr("adj_sharpen"))
        self._auto_stretch.setText(tr("adj_auto_stretch"))
        self._reset_btn.setText(tr("btn_reset"))

        self._deconv_group.setTitle(tr("mp4_deconv_enable"))
        self._deconv_enable.setText(tr("mp4_deconv_enable"))
        self._deconv_iters.set_label(tr("mp4_deconv_iters"))

        self._crop_group.setTitle(tr("mp4_crop_enable"))
        self._crop_enable.setText(tr("mp4_crop_enable"))
        self._crop_w_label.setText(tr("mp4_crop_size"))
        self._center_target.setText(tr("mp4_center_target"))
        self._threshold.set_label(tr("mp4_threshold"))

    def _reset(self) -> None:
        self._brightness.reset()
        self._contrast.reset()
        self._gamma.reset()
        self._sharpen.reset()
        self._auto_stretch.setChecked(False)
        self.adjustments_changed.emit()

    def _on_crop_toggled(self, checked: bool) -> None:
        self._crop_w.setEnabled(checked)
        self._crop_h.setEnabled(checked)
        self._center_target.setEnabled(checked)
        self._threshold.setEnabled(checked)
        self.crop_changed.emit()

    def set_frame_size(self, width: int, height: int) -> None:
        """Update crop spinbox ranges to match loaded frame size."""
        self._crop_w.setRange(64, width)
        self._crop_h.setRange(64, height)
        if self._crop_w.value() > width:
            self._crop_w.setValue(width)
        if self._crop_h.value() > height:
            self._crop_h.setValue(height)

    # --- Properties ---

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
    def sharpen(self) -> float:
        return self._sharpen.value()

    @property
    def auto_stretch_enabled(self) -> bool:
        return self._auto_stretch.isChecked()

    @property
    def deconv_enabled(self) -> bool:
        return self._deconv_enable.isChecked()

    @property
    def deconv_psf_radius(self) -> float:
        return self._psf_radius.value()

    @property
    def deconv_iterations(self) -> int:
        return int(self._deconv_iters.value())

    @property
    def crop_enabled(self) -> bool:
        return self._crop_enable.isChecked()

    @property
    def crop_size(self) -> tuple[int, int]:
        return self._crop_w.value(), self._crop_h.value()

    @property
    def center_target_enabled(self) -> bool:
        return self._center_target.isChecked()

    @property
    def center_threshold(self) -> float:
        return self._threshold.value()
