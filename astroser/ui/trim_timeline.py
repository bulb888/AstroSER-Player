"""Clean trim timeline with playhead and draggable in/out handles."""

from datetime import datetime
from typing import Optional, Callable

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QMouseEvent, QPainterPath
from PySide6.QtWidgets import QWidget, QToolTip

_HANDLE_HIT = 14


class TrimTimeline(QWidget):
    position_changed = Signal(int)
    trim_changed = Signal(int, int)

    C_BG      = QColor(28, 28, 28)
    C_BORDER  = QColor(50, 50, 50)
    C_KEPT    = QColor(50, 55, 60)
    C_DIM     = QColor(18, 18, 18, 200)
    C_HEAD    = QColor(76, 159, 230)
    C_HEAD_GL = QColor(76, 159, 230, 45)
    C_TRIM    = QColor(230, 160, 50)
    C_TRIM_DM = QColor(230, 160, 50, 100)
    C_LABEL   = QColor(230, 175, 70)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame_count = 0
        self._position = 0
        self._trim_in = 0
        self._trim_out = 0
        self._trim_active = False
        self._dragging = None
        self._utc_callback: Optional[Callable[[int], Optional[datetime]]] = None
        self.setMinimumHeight(32)
        self.setMaximumHeight(32)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_utc_callback(self, callback: Optional[Callable[[int], Optional[datetime]]]):
        """Set callback to get UTC time for a frame index: fn(frame_idx) -> datetime or None."""
        self._utc_callback = callback

    def set_frame_count(self, count):
        self._frame_count = max(0, count)
        self._position = 0
        self._trim_in = 0
        self._trim_out = max(0, count - 1)
        self._trim_active = False
        self.update()

    def set_position(self, frame):
        self._position = max(0, min(frame, self._frame_count - 1))
        self.update()

    def set_trim_active(self, active):
        self._trim_active = active
        if active and self._frame_count > 0:
            if self._trim_in < 0: self._trim_in = 0
            if self._trim_out < 0: self._trim_out = self._frame_count - 1
        self.update()

    @property
    def trim_active(self): return self._trim_active
    @property
    def trim_in(self): return self._trim_in if self._trim_active else 0
    @property
    def trim_out(self): return self._trim_out if self._trim_active else self._frame_count - 1

    def reset_trim(self):
        self._trim_in = 0
        self._trim_out = max(0, self._frame_count - 1)
        self.trim_changed.emit(self._trim_in, self._trim_out)
        self.update()

    def _bar(self):
        return QRectF(8, 6, self.width() - 16, self.height() - 12)

    def _f2x(self, f):
        b = self._bar()
        return b.left() + (f / max(1, self._frame_count - 1)) * b.width() if self._frame_count > 1 else b.left()

    def _x2f(self, x):
        b = self._bar()
        if self._frame_count <= 1 or b.width() <= 0: return 0
        return round(max(0.0, min(1.0, (x - b.left()) / b.width())) * (self._frame_count - 1))

    def _hit(self, pos):
        if self._frame_count <= 0: return None
        x = pos.x()
        if self._trim_active:
            if abs(x - self._f2x(self._trim_in)) <= _HANDLE_HIT: return 'in'
            if abs(x - self._f2x(self._trim_out)) <= _HANDLE_HIT: return 'out'
        return 'head'

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._frame_count > 0:
            self._dragging = self._hit(e.position())
            self._do_drag(e.position())

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._do_drag(e.position())
        else:
            h = self._hit(e.position())
            self.setCursor(Qt.CursorShape.SizeHorCursor if h in ('in','out') else Qt.CursorShape.PointingHandCursor)
            # UTC tooltip
            if self._utc_callback and self._frame_count > 0:
                f = self._x2f(e.position().x())
                utc = self._utc_callback(f)
                if utc:
                    tip = f"#{f+1}  {utc.strftime('%H:%M:%S.%f')[:-3]} UTC"
                    QToolTip.showText(e.globalPosition().toPoint(), tip, self)
                else:
                    QToolTip.hideText()

    def mouseReleaseEvent(self, e):
        self._dragging = None

    def _do_drag(self, pos):
        f = self._x2f(pos.x())
        if self._dragging == 'in':
            self._trim_in = max(0, min(f, self._trim_out - 1))
            self._position = self._trim_in
            self.position_changed.emit(self._trim_in)
            self.trim_changed.emit(self._trim_in, self._trim_out)
        elif self._dragging == 'out':
            self._trim_out = min(self._frame_count - 1, max(f, self._trim_in + 1))
            self._position = self._trim_out
            self.position_changed.emit(self._trim_out)
            self.trim_changed.emit(self._trim_in, self._trim_out)
        elif self._dragging == 'head':
            self._position = f
            self.position_changed.emit(f)
        self.update()

    def paintEvent(self, event):
        if self._frame_count <= 0: return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar = self._bar()

        # Bar
        p.setPen(QPen(self.C_BORDER, 1))
        p.setBrush(self.C_BG)
        p.drawRoundedRect(bar, 3, 3)

        # Trim
        if self._trim_active:
            ix, ox = self._f2x(self._trim_in), self._f2x(self._trim_out)
            # Kept
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.C_KEPT)
            p.drawRect(QRectF(ix, bar.top()+1, ox-ix, bar.height()-2))
            # Dim
            p.setBrush(self.C_DIM)
            if ix > bar.left()+1:
                p.drawRect(QRectF(bar.left()+1, bar.top()+1, ix-bar.left()-1, bar.height()-2))
            if ox < bar.right()-1:
                p.drawRect(QRectF(ox, bar.top()+1, bar.right()-ox-1, bar.height()-2))
            # Trim lines
            p.setPen(QPen(self.C_TRIM, 1.5))
            p.drawLine(QPointF(ix, bar.top()), QPointF(ix, bar.bottom()))
            p.drawLine(QPointF(ox, bar.top()), QPointF(ox, bar.bottom()))
            # Handles
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.C_TRIM)
            for hx, left in [(ix, True), (ox, False)]:
                w = 4
                if left:
                    p.drawRoundedRect(QRectF(hx, bar.top()-1, w, 6), 1, 1)
                    p.drawRoundedRect(QRectF(hx, bar.bottom()-5, w, 6), 1, 1)
                else:
                    p.drawRoundedRect(QRectF(hx-w, bar.top()-1, w, 6), 1, 1)
                    p.drawRoundedRect(QRectF(hx-w, bar.bottom()-5, w, 6), 1, 1)
            # Labels
            font = QFont("Consolas", 7)
            p.setFont(font)
            p.setPen(self.C_LABEL)
            p.drawText(QRectF(ix-24, bar.bottom()+1, 48, 10), Qt.AlignmentFlag.AlignCenter, str(self._trim_in+1))
            p.drawText(QRectF(ox-24, bar.bottom()+1, 48, 10), Qt.AlignmentFlag.AlignCenter, str(self._trim_out+1))

        # Playhead glow
        hx = self._f2x(self._position)
        glow_pen = QPen(self.C_HEAD_GL, 6)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(glow_pen)
        p.drawLine(QPointF(hx, bar.top()+2), QPointF(hx, bar.bottom()-2))
        # Playhead line
        p.setPen(QPen(self.C_HEAD, 1.5))
        p.drawLine(QPointF(hx, bar.top()), QPointF(hx, bar.bottom()))
        # Playhead marker
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.C_HEAD)
        tri = QPainterPath()
        tri.moveTo(hx-4, bar.top()-1)
        tri.lineTo(hx+4, bar.top()-1)
        tri.lineTo(hx, bar.top()+4)
        tri.closeSubpath()
        p.drawPath(tri)

        p.end()
