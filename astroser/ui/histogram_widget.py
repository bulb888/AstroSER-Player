"""Histogram display widget."""

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QSizePolicy

from .i18n import tr, I18n


class HistogramCanvas(QWidget):
    """Custom-painted histogram canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hist_data: np.ndarray | None = None
        self._hist_rgb: list[np.ndarray | None] = [None, None, None]
        self._is_color = False
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_histogram(self, hist, is_color=False, hist_rgb=None):
        self._hist_data = hist
        self._is_color = is_color
        self._hist_rgb = hist_rgb if hist_rgb and len(hist_rgb) == 3 else [None, None, None]
        self.update()

    def clear(self):
        self._hist_data = None
        self._hist_rgb = [None, None, None]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(20, 20, 20))
        if self._hist_data is None:
            painter.end()
            return
        margin = 4
        pw, ph = w - 2 * margin, h - 2 * margin
        if self._is_color and all(ch is not None for ch in self._hist_rgb):
            colors = [QColor(200, 60, 60, 120), QColor(60, 200, 60, 120), QColor(60, 60, 200, 120)]
            for ch_hist, color in zip(self._hist_rgb, colors):
                self._draw(painter, ch_hist, margin, margin, pw, ph, color)
        else:
            self._draw(painter, self._hist_data, margin, margin, pw, ph, QColor(180, 180, 180, 180))
        painter.end()

    def _draw(self, painter, hist, x0, y0, w, h, color):
        if hist is None or len(hist) == 0 or np.max(hist) <= 0:
            return
        hn = np.log1p(hist.astype(np.float64))
        mx = np.max(hn)
        if mx <= 0:
            return
        hn /= mx
        bins = len(hn)
        bw = w / bins
        path = QPainterPath()
        path.moveTo(x0, y0 + h)
        for i in range(bins):
            path.lineTo(x0 + i * bw, y0 + h - hn[i] * h)
        path.lineTo(x0 + w, y0 + h)
        path.closeSubpath()
        fc = QColor(color)
        fc.setAlpha(80)
        painter.fillPath(path, fc)
        pen = QPen(color)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)


class HistogramWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._group = QGroupBox()
        gl = QVBoxLayout(self._group)
        gl.setContentsMargins(4, 4, 4, 4)
        self._canvas = HistogramCanvas()
        gl.addWidget(self._canvas)
        layout.addWidget(self._group)
        I18n.instance().language_changed.connect(self.retranslate)
        self.retranslate()

    def retranslate(self):
        self._group.setTitle(tr("group_histogram"))

    def update_histogram(self, frame, subsample: bool = False):
        """Update histogram. Use subsample=True during playback for speed."""
        if subsample and frame.size > 500000:
            if frame.ndim == 3:
                frame = frame[::4, ::4, :]
            else:
                frame = frame[::4, ::4]

        if frame.ndim == 3:
            mv = float(np.max(frame)) if np.max(frame) > 0 else 255
            ha, _ = np.histogram(frame.ravel(), bins=256, range=(0, mv))
            hr = [np.histogram(frame[:, :, c].ravel(), bins=256, range=(0, mv))[0] for c in range(3)]
            self._canvas.set_histogram(ha, is_color=True, hist_rgb=hr)
        else:
            mv = float(np.max(frame)) if np.max(frame) > 0 else 255
            h, _ = np.histogram(frame.ravel(), bins=256, range=(0, mv))
            self._canvas.set_histogram(h)

    def clear(self):
        self._canvas.clear()
