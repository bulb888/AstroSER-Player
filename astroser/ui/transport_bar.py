"""Transport control bar with playback controls and seek slider."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QSlider, QLabel, QComboBox,
)

from ..core.playback_engine import PlaybackEngine
from .i18n import tr, I18n


class TransportBar(QWidget):
    """Playback transport controls."""

    def __init__(self, engine: PlaybackEngine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._updating_slider = False
        self._pending_seek = -1
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(16)  # ~60fps throttle
        self._seek_timer.timeout.connect(self._flush_seek)
        self._setup_ui()
        self._connect_signals()
        I18n.instance().language_changed.connect(self.retranslate)

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        btn_style = "QPushButton { min-width: 32px; min-height: 28px; font-size: 14px; }"

        self._btn_first = QPushButton("\u23ee")
        self._btn_first.setStyleSheet(btn_style)

        self._btn_prev = QPushButton("\u23f4")
        self._btn_prev.setStyleSheet(btn_style)

        self._btn_play = QPushButton("\u25b6")
        self._btn_play.setStyleSheet(btn_style + "QPushButton { min-width: 40px; }")

        self._btn_next = QPushButton("\u23f5")
        self._btn_next.setStyleSheet(btn_style)

        self._btn_last = QPushButton("\u23ed")
        self._btn_last.setStyleSheet(btn_style)

        for btn in (self._btn_first, self._btn_prev, self._btn_play,
                     self._btn_next, self._btn_last):
            layout.addWidget(btn)

        layout.addSpacing(8)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        layout.addWidget(self._slider, stretch=1)

        layout.addSpacing(8)

        self._frame_label = QLabel()
        self._frame_label.setMinimumWidth(130)
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._frame_label)

        layout.addSpacing(8)

        self._speed_label = QLabel()
        layout.addWidget(self._speed_label)

        self._speed_combo = QComboBox()
        for speed in PlaybackEngine.SPEED_OPTIONS:
            self._speed_combo.addItem(f"{speed}x", speed)
        self._speed_combo.setCurrentText("1.0x")
        self._speed_combo.setMinimumWidth(70)
        layout.addWidget(self._speed_combo)

        self.retranslate()

    def retranslate(self) -> None:
        self._btn_first.setToolTip(tr("tip_first"))
        self._btn_prev.setToolTip(tr("tip_prev"))
        self._btn_play.setToolTip(tr("tip_play"))
        self._btn_next.setToolTip(tr("tip_next"))
        self._btn_last.setToolTip(tr("tip_last"))
        self._speed_label.setText(tr("label_speed"))
        total = self._engine.frame_count
        current = self._engine.current_frame + 1 if total > 0 else 0
        self._frame_label.setText(tr("label_frame").format(current, total))

    def _connect_signals(self) -> None:
        self._btn_first.clicked.connect(self._engine.go_to_first)
        self._btn_prev.clicked.connect(self._engine.step_backward)
        self._btn_play.clicked.connect(self._engine.toggle)
        self._btn_next.clicked.connect(self._engine.step_forward)
        self._btn_last.clicked.connect(self._engine.go_to_last)

        self._slider.valueChanged.connect(self._on_slider_changed)
        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)

        self._engine.frame_changed.connect(self._on_frame_changed)
        self._engine.playback_state_changed.connect(self._on_playback_state)

    def _on_slider_changed(self, value: int) -> None:
        if not self._updating_slider:
            self._pending_seek = value
            if not self._seek_timer.isActive():
                self._seek_timer.start()

    def _flush_seek(self) -> None:
        if self._pending_seek >= 0:
            self._engine.seek(self._pending_seek)
            self._pending_seek = -1

    def _on_speed_changed(self, index: int) -> None:
        speed = self._speed_combo.currentData()
        if speed is not None:
            self._engine.set_speed(speed)

    def _on_frame_changed(self, frame: int) -> None:
        self._updating_slider = True
        self._slider.setValue(frame)
        self._updating_slider = False
        self._frame_label.setText(tr("label_frame").format(frame + 1, self._engine.frame_count))

    def _on_playback_state(self, playing: bool) -> None:
        self._btn_play.setText("\u23f8" if playing else "\u25b6")

    def set_frame_count(self, count: int) -> None:
        self._slider.setMaximum(max(0, count - 1))
        self._frame_label.setText(tr("label_frame").format(1, count))

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        for w in (self._btn_first, self._btn_prev, self._btn_play,
                  self._btn_next, self._btn_last, self._slider, self._speed_combo):
            w.setEnabled(enabled)
