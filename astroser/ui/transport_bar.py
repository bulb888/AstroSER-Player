"""Transport control bar with playback controls and visual trim timeline."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QComboBox,
)

from ..core.playback_engine import PlaybackEngine
from .trim_timeline import TrimTimeline
from .i18n import tr, I18n


class TransportBar(QWidget):
    """Playback transport controls with visual trim timeline."""

    trim_save_requested = Signal(int, int)  # (start_frame, end_frame)

    def __init__(self, engine: PlaybackEngine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._updating_position = False
        self._frame_count: int = 0
        self._setup_ui()
        self._connect_signals()
        I18n.instance().language_changed.connect(self.retranslate)

    def _setup_ui(self) -> None:
        self.setStyleSheet("TransportBar { border-top: 1px solid #1e3050; }")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # --- Timeline row ---
        self._timeline = TrimTimeline()
        outer.addWidget(self._timeline)

        # --- Controls row ---
        row = QHBoxLayout()
        row.setSpacing(4)

        btn_style = (
            "QPushButton { min-width: 34px; min-height: 30px; font-size: 15px; "
            "border-radius: 5px; padding: 2px; }"
        )
        play_style = (
            "QPushButton { min-width: 44px; min-height: 30px; font-size: 17px; "
            "border-radius: 5px; padding: 2px; }"
        )

        self._btn_first = QPushButton("\u23ee")
        self._btn_first.setStyleSheet(btn_style)

        self._btn_prev = QPushButton("\u23f4")
        self._btn_prev.setStyleSheet(btn_style)

        self._btn_play = QPushButton("\u25b6")
        self._btn_play.setStyleSheet(play_style)

        self._btn_next = QPushButton("\u23f5")
        self._btn_next.setStyleSheet(btn_style)

        self._btn_last = QPushButton("\u23ed")
        self._btn_last.setStyleSheet(btn_style)

        for btn in (self._btn_first, self._btn_prev, self._btn_play,
                     self._btn_next, self._btn_last):
            row.addWidget(btn)

        row.addSpacing(8)

        # Frame label (HUD readout style)
        self._frame_label = QLabel()
        self._frame_label.setMinimumWidth(150)
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_label.setStyleSheet(
            "QLabel { color: #00d4ff; font-size: 12px; "
            "font-family: 'Consolas', monospace; "
            "background: #0a1520; border: 1px solid #1e3050; "
            "border-radius: 3px; padding: 3px 8px; }"
        )
        row.addWidget(self._frame_label)

        row.addSpacing(8)

        # Speed
        self._speed_label = QLabel()
        row.addWidget(self._speed_label)

        self._speed_combo = QComboBox()
        for speed in PlaybackEngine.SPEED_OPTIONS:
            self._speed_combo.addItem(f"{speed}x", speed)
        self._speed_combo.setCurrentText("1.0x")
        self._speed_combo.setMinimumWidth(70)
        row.addWidget(self._speed_combo)

        row.addStretch()

        # Trim controls (right side) — amber HUD accent
        trim_style = (
            "QPushButton { min-height: 28px; max-height: 28px; "
            "font-size: 13px; padding: 2px 10px; border-radius: 3px; }"
        )
        trim_active_style = (
            "QPushButton { min-height: 28px; max-height: 28px; "
            "font-size: 13px; padding: 2px 10px; border-radius: 3px; "
            "background: #2a1800; border: 1px solid #ff9500; color: #ff9500; }"
            "QPushButton:hover { background: #3a2400; color: #ffb040; }"
        )

        self._btn_trim_toggle = QPushButton("\u2702")
        self._btn_trim_toggle.setStyleSheet(trim_style)
        self._btn_trim_toggle.setCheckable(True)
        self._btn_trim_toggle_style_normal = trim_style
        self._btn_trim_toggle_style_active = trim_active_style
        row.addWidget(self._btn_trim_toggle)

        self._trim_info_label = QLabel()
        self._trim_info_label.setStyleSheet(
            "QLabel { color: #ff9500; font-size: 11px; "
            "font-family: 'Consolas', monospace; "
            "background: #1a1000; border: 1px solid #3a2500; "
            "border-radius: 3px; padding: 2px 6px; }"
        )
        self._trim_info_label.setVisible(False)
        row.addWidget(self._trim_info_label)

        self._btn_trim_reset = QPushButton("\u21ba")
        self._btn_trim_reset.setToolTip("")
        self._btn_trim_reset.setStyleSheet(
            "QPushButton { min-width: 28px; max-width: 28px; min-height: 28px; "
            "max-height: 28px; font-size: 14px; border-radius: 3px; }"
        )
        self._btn_trim_reset.setVisible(False)
        row.addWidget(self._btn_trim_reset)

        save_style = (
            "QPushButton { min-height: 28px; max-height: 28px; "
            "font-size: 12px; padding: 2px 14px; border-radius: 3px; "
            "background: #002838; border: 1px solid #00d4ff; color: #00d4ff; }"
            "QPushButton:hover { background: #003848; color: #80e8ff; }"
        )
        self._btn_trim_save = QPushButton("\u2702 Save")
        self._btn_trim_save.setStyleSheet(save_style)
        self._btn_trim_save.setVisible(False)
        row.addWidget(self._btn_trim_save)

        outer.addLayout(row)
        self.retranslate()

    def retranslate(self) -> None:
        self._btn_first.setToolTip(tr("tip_first"))
        self._btn_prev.setToolTip(tr("tip_prev"))
        self._btn_play.setToolTip(tr("tip_play"))
        self._btn_next.setToolTip(tr("tip_next"))
        self._btn_last.setToolTip(tr("tip_last"))
        self._btn_trim_toggle.setToolTip(tr("tip_trim_toggle"))
        self._btn_trim_save.setToolTip(tr("tip_trim_save"))
        self._btn_trim_reset.setToolTip(tr("tip_trim_reset"))
        self._btn_trim_save.setText("\u2702 " + tr("btn_trim_save"))
        self._speed_label.setText(tr("label_speed"))
        total = self._engine.frame_count
        current = self._engine.current_frame + 1 if total > 0 else 0
        self._frame_label.setText(tr("label_frame").format(current, total))
        self._update_trim_info()

    def _connect_signals(self) -> None:
        self._btn_first.clicked.connect(self._engine.go_to_first)
        self._btn_prev.clicked.connect(self._engine.step_backward)
        self._btn_play.clicked.connect(self._engine.toggle)
        self._btn_next.clicked.connect(self._engine.step_forward)
        self._btn_last.clicked.connect(self._engine.go_to_last)

        self._btn_trim_toggle.toggled.connect(self._on_trim_toggle)
        self._btn_trim_save.clicked.connect(self._on_trim_save)
        self._btn_trim_reset.clicked.connect(self._on_trim_reset)

        self._timeline.position_changed.connect(self._on_timeline_seek)
        self._timeline.trim_changed.connect(self._on_trim_changed)

        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)

        self._engine.frame_changed.connect(self._on_frame_changed)
        self._engine.playback_state_changed.connect(self._on_playback_state)

    # --- Trim ---

    def _on_trim_toggle(self, checked: bool) -> None:
        self._timeline.set_trim_active(checked)
        self._btn_trim_save.setVisible(checked)
        self._btn_trim_reset.setVisible(checked)
        self._trim_info_label.setVisible(checked)
        self._btn_trim_toggle.setStyleSheet(
            self._btn_trim_toggle_style_active if checked
            else self._btn_trim_toggle_style_normal
        )
        self._update_trim_info()

    def _on_trim_changed(self, trim_in: int, trim_out: int) -> None:
        self._update_trim_info()

    def _on_trim_reset(self) -> None:
        self._timeline.reset_trim()
        self._update_trim_info()

    def _on_trim_save(self) -> None:
        start = self._timeline.trim_in
        end = self._timeline.trim_out
        self.trim_save_requested.emit(start, end)

    def _update_trim_info(self) -> None:
        if not self._timeline.trim_active:
            return
        start = self._timeline.trim_in + 1
        end = self._timeline.trim_out + 1
        count = end - start + 1
        self._trim_info_label.setText(
            tr("label_trim_range").format(start, end, count)
        )

    # --- Timeline / Seek ---

    def _on_timeline_seek(self, frame: int) -> None:
        if not self._updating_position:
            self._engine.seek(frame)

    def _on_speed_changed(self, index: int) -> None:
        speed = self._speed_combo.currentData()
        if speed is not None:
            self._engine.set_speed(speed)

    def _on_frame_changed(self, frame: int) -> None:
        self._updating_position = True
        self._timeline.set_position(frame)
        self._updating_position = False
        self._frame_label.setText(tr("label_frame").format(frame + 1, self._engine.frame_count))

    def _on_playback_state(self, playing: bool) -> None:
        self._btn_play.setText("\u23f8" if playing else "\u25b6")

    def set_frame_count(self, count: int) -> None:
        self._frame_count = count
        self._timeline.set_frame_count(count)
        self._frame_label.setText(tr("label_frame").format(1, count))
        # Reset trim
        if self._btn_trim_toggle.isChecked():
            self._btn_trim_toggle.setChecked(False)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        for w in (self._btn_first, self._btn_prev, self._btn_play,
                  self._btn_next, self._btn_last, self._timeline,
                  self._speed_combo, self._btn_trim_toggle):
            w.setEnabled(enabled)
