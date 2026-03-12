"""Playback engine with QTimer-based frame advancement."""

import time
from PySide6.QtCore import QObject, QTimer, Signal


class PlaybackEngine(QObject):
    """Manages playback state and frame advancement."""

    frame_changed = Signal(int)
    playback_state_changed = Signal(bool)

    SPEED_OPTIONS = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame_count = 0
        self._current_frame = 0
        self._is_playing = False
        self._base_fps = 25.0
        self._speed = 1.0
        self._loop = True

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._update_interval()

        # Frame timing for skip logic
        self._last_frame_time = 0.0
        self._target_interval = 0.04  # seconds

    def set_frame_count(self, count: int) -> None:
        """Set the total number of frames."""
        self._frame_count = count
        self._current_frame = 0

    @property
    def current_frame(self) -> int:
        return self._current_frame

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def base_fps(self) -> float:
        return self._base_fps

    def play(self) -> None:
        if self._frame_count <= 0:
            return
        self._is_playing = True
        self._last_frame_time = time.perf_counter()
        self._timer.start()
        self.playback_state_changed.emit(True)

    def pause(self) -> None:
        self._is_playing = False
        self._timer.stop()
        self.playback_state_changed.emit(False)

    def toggle(self) -> None:
        if self._is_playing:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self.pause()
        self.seek(0)

    def step_forward(self) -> None:
        self.pause()
        if self._current_frame < self._frame_count - 1:
            self._current_frame += 1
        elif self._loop:
            self._current_frame = 0
        self.frame_changed.emit(self._current_frame)

    def step_backward(self) -> None:
        self.pause()
        if self._current_frame > 0:
            self._current_frame -= 1
        elif self._loop:
            self._current_frame = self._frame_count - 1
        self.frame_changed.emit(self._current_frame)

    def go_to_first(self) -> None:
        self.pause()
        self.seek(0)

    def go_to_last(self) -> None:
        self.pause()
        self.seek(self._frame_count - 1)

    def seek(self, frame: int) -> None:
        frame = max(0, min(frame, self._frame_count - 1))
        self._current_frame = frame
        self.frame_changed.emit(self._current_frame)

    def set_speed(self, speed: float) -> None:
        self._speed = speed
        self._update_interval()
        if self._is_playing:
            self._timer.start()

    def set_fps(self, fps: float) -> None:
        self._base_fps = max(1.0, fps)
        self._update_interval()
        if self._is_playing:
            self._timer.start()

    def set_loop(self, loop: bool) -> None:
        self._loop = loop

    def _update_interval(self) -> None:
        self._target_interval = 1.0 / (self._base_fps * self._speed)
        interval = max(1, int(self._target_interval * 1000))
        self._timer.setInterval(interval)

    def _advance(self) -> None:
        now = time.perf_counter()
        elapsed = now - self._last_frame_time

        # Calculate how many frames to skip based on elapsed time
        frames_due = max(1, int(elapsed / self._target_interval))

        # At high speeds, skip frames to keep up (cap skip to avoid large jumps)
        skip = min(frames_due, 8)

        new_frame = self._current_frame + skip
        if new_frame >= self._frame_count:
            if self._loop:
                new_frame = new_frame % self._frame_count
            else:
                self._current_frame = self._frame_count - 1
                self.frame_changed.emit(self._current_frame)
                self.pause()
                return

        self._current_frame = new_frame
        self._last_frame_time = now
        self.frame_changed.emit(self._current_frame)
