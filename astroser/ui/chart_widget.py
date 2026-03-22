"""Reusable line chart widget with QPainter — dark theme."""

import numpy as np
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QPainterPath, QBrush, QLinearGradient
from PySide6.QtWidgets import QWidget, QSizePolicy


class ChartWidget(QWidget):
    """Generic line chart with optional anomaly markers.

    Features:
    - Single or dual Y-axis data series
    - Click to select frame → emits frame_clicked(int)
    - Hover tooltip with frame info
    - Anomaly highlighting (red vertical bars)
    - Dark theme styling
    """

    frame_clicked = Signal(int)  # emits frame index (0-based)

    # Colors
    C_BG = QColor(22, 22, 22)
    C_GRID = QColor(40, 40, 40)
    C_AXIS = QColor(70, 70, 70)
    C_TEXT = QColor(140, 140, 140)
    C_CURSOR = QColor(76, 159, 230, 120)
    C_ANOMALY = QColor(220, 60, 60, 50)

    # Default series colors
    PALETTE = [
        QColor(76, 159, 230),    # blue
        QColor(230, 160, 50),    # amber
        QColor(100, 200, 100),   # green
        QColor(200, 100, 200),   # purple
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._series: list[tuple[np.ndarray, QColor, str]] = []  # (data, color, label)
        self._anomaly_indices: np.ndarray | None = None
        self._x_label = ""
        self._y_label = ""
        self._hover_idx = -1
        self._margin = {"left": 52, "right": 12, "top": 16, "bottom": 24}
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_data(self, data: np.ndarray, color: QColor = None, label: str = "",
                 index: int = 0):
        """Set or replace a data series by index."""
        if color is None:
            color = self.PALETTE[index % len(self.PALETTE)]
        while len(self._series) <= index:
            self._series.append((np.array([]), self.PALETTE[len(self._series) % len(self.PALETTE)], ""))
        self._series[index] = (data, color, label)
        self.update()

    def set_anomalies(self, indices: np.ndarray):
        """Set indices of anomalous frames (highlighted in red)."""
        self._anomaly_indices = indices
        self.update()

    def set_labels(self, x_label: str = "", y_label: str = ""):
        self._x_label = x_label
        self._y_label = y_label
        self.update()

    def clear(self):
        self._series.clear()
        self._anomaly_indices = None
        self._hover_idx = -1
        self.update()

    def _plot_rect(self) -> QRectF:
        m = self._margin
        return QRectF(m["left"], m["top"],
                      self.width() - m["left"] - m["right"],
                      self.height() - m["top"] - m["bottom"])

    def _idx_from_x(self, x: float) -> int:
        """Convert widget x coordinate to data index."""
        r = self._plot_rect()
        if not self._series or r.width() <= 0:
            return -1
        n = len(self._series[0][0])
        if n <= 1:
            return 0
        frac = (x - r.left()) / r.width()
        return max(0, min(n - 1, int(frac * (n - 1) + 0.5)))

    def _x_from_idx(self, idx: int) -> float:
        r = self._plot_rect()
        if not self._series:
            return r.left()
        n = len(self._series[0][0])
        if n <= 1:
            return r.center().x()
        return r.left() + (idx / (n - 1)) * r.width()

    def mouseMoveEvent(self, e):
        idx = self._idx_from_x(e.position().x())
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            idx = self._idx_from_x(e.position().x())
            if idx >= 0:
                self.frame_clicked.emit(idx)

    def leaveEvent(self, e):
        self._hover_idx = -1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, self.C_BG)

        r = self._plot_rect()
        if r.width() < 10 or r.height() < 10 or not self._series:
            p.end()
            return

        # Grid lines
        p.setPen(QPen(self.C_GRID, 1))
        for i in range(1, 4):
            y = r.top() + r.height() * i / 4
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))

        # Compute global Y range across all series
        all_data = [s[0] for s in self._series if len(s[0]) > 0]
        if not all_data:
            p.end()
            return

        y_min = min(float(np.nanmin(d)) for d in all_data)
        y_max = max(float(np.nanmax(d)) for d in all_data)
        if y_min == y_max:
            y_min -= 1
            y_max += 1
        y_range = y_max - y_min
        y_pad = y_range * 0.05
        y_min -= y_pad
        y_max += y_pad
        y_range = y_max - y_min

        n = len(self._series[0][0])

        # Anomaly bars
        if self._anomaly_indices is not None and len(self._anomaly_indices) > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.C_ANOMALY)
            bw = max(1.0, r.width() / max(1, n - 1))
            for ai in self._anomaly_indices:
                ax = self._x_from_idx(int(ai))
                p.drawRect(QRectF(ax - bw / 2, r.top(), bw, r.height()))

        # Draw each series
        for data, color, label in self._series:
            if len(data) == 0:
                continue
            path = QPainterPath()
            for i in range(len(data)):
                x = r.left() + (i / max(1, n - 1)) * r.width() if n > 1 else r.center().x()
                val = float(data[i]) if not np.isnan(data[i]) else y_min
                y = r.bottom() - ((val - y_min) / y_range) * r.height()
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setPen(QPen(color, 1.2))
            p.drawPath(path)

        # Y axis labels
        font = QFont("Cascadia Mono", 7)
        p.setFont(font)
        p.setPen(self.C_TEXT)
        for i in range(5):
            val = y_min + y_range * (4 - i) / 4
            y = r.top() + r.height() * i / 4
            text = f"{val:.1f}" if abs(val) < 1000 else f"{val:.0f}"
            p.drawText(QRectF(0, y - 7, self._margin["left"] - 4, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)

        # Axis border
        p.setPen(QPen(self.C_AXIS, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)

        # Hover cursor
        if 0 <= self._hover_idx < n:
            hx = self._x_from_idx(self._hover_idx)
            p.setPen(QPen(self.C_CURSOR, 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(hx, r.top()), QPointF(hx, r.bottom()))

            # Tooltip
            tooltip_parts = [f"#{self._hover_idx + 1}"]
            for data, color, label in self._series:
                if self._hover_idx < len(data):
                    val = float(data[self._hover_idx])
                    prefix = f"{label}: " if label else ""
                    tooltip_parts.append(f"{prefix}{val:.2f}")
            tooltip = "  ".join(tooltip_parts)

            p.setFont(QFont("Cascadia Mono", 8))
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(tooltip) + 12
            th = fm.height() + 6
            tx = min(hx + 8, r.right() - tw)
            ty = r.top() + 4

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(30, 30, 30, 220))
            p.drawRoundedRect(QRectF(tx, ty, tw, th), 3, 3)
            p.setPen(QColor(220, 220, 220))
            p.drawText(QRectF(tx + 6, ty + 3, tw - 12, th - 6),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tooltip)

        p.end()
