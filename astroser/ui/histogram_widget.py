"""Histogram display widget — clean dark style."""

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QLinearGradient, QBrush
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QSizePolicy

from .i18n import tr, I18n


class HistogramCanvas(QWidget):
    BG = QColor(22, 22, 22)
    GRID = QColor(36, 36, 36)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hist_data = None
        self._hist_rgb = [None, None, None]
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
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        m = 4
        pw, ph = w - 2 * m, h - 2 * m

        p.fillRect(0, 0, w, h, self.BG)

        # Grid
        p.setPen(QPen(self.GRID, 1))
        for i in range(1, 4):
            y = m + int(ph * i / 4)
            p.drawLine(m, y, m + pw, y)

        if self._hist_data is not None:
            if self._is_color and all(ch is not None for ch in self._hist_rgb):
                specs = [
                    (self._hist_rgb[0], QColor(200, 70, 70), QColor(200, 70, 70, 30)),
                    (self._hist_rgb[1], QColor(70, 190, 70), QColor(70, 190, 70, 30)),
                    (self._hist_rgb[2], QColor(80, 110, 220), QColor(80, 110, 220, 30)),
                ]
                for hist, lc, fc in specs:
                    self._draw(p, hist, m, m, pw, ph, lc, fc)
            else:
                self._draw(p, self._hist_data, m, m, pw, ph,
                           QColor(170, 190, 210), QColor(76, 159, 230, 40))

        p.setPen(QPen(QColor(44, 44, 44), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, w, h, 3, 3)
        p.end()

    def _draw(self, p, hist, x0, y0, w, h, line_c, fill_c):
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

        grad = QLinearGradient(0, y0, 0, y0 + h)
        grad.setColorAt(0.0, fill_c)
        bot = QColor(fill_c); bot.setAlpha(4)
        grad.setColorAt(1.0, bot)
        p.fillPath(path, QBrush(grad))

        p.setPen(QPen(line_c, 1.0))
        top = QPainterPath()
        top.moveTo(x0, y0 + h)
        for i in range(bins):
            top.lineTo(x0 + i * bw, y0 + h - hn[i] * h)
        p.drawPath(top)


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

    def update_histogram(self, frame, subsample=False):
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
