"""ROI (Region of Interest) selector overlay on the image viewer."""

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPen, QColor, QBrush
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsView


class ROISelector(QGraphicsRectItem):
    """Draggable and resizable ROI rectangle overlay."""

    def __init__(self, x: float = 0, y: float = 0,
                 width: float = 100, height: float = 100):
        super().__init__(x, y, width, height)
        self._setup_appearance()
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._callback = None

    def _setup_appearance(self) -> None:
        pen = QPen(QColor(0, 255, 0, 200))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(0, 255, 0, 30)))

    def set_change_callback(self, callback) -> None:
        """Set a callback that fires when ROI position/size changes."""
        self._callback = callback

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionHasChanged:
            if self._callback:
                self._callback(self.get_roi())
        return super().itemChange(change, value)

    def get_roi(self) -> tuple[int, int, int, int]:
        """Get ROI as (x, y, width, height) in image coordinates."""
        rect = self.sceneBoundingRect()
        return (
            max(0, int(rect.x())),
            max(0, int(rect.y())),
            max(1, int(rect.width())),
            max(1, int(rect.height())),
        )
