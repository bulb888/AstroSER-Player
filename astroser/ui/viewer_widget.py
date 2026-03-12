"""Image viewer widget with zoom and pan support."""

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QImage, QPixmap, QWheelEvent, QMouseEvent, QPainter, QFont, QColor
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem

from .i18n import tr, I18n


class ImageViewer(QGraphicsView):
    """QGraphicsView-based image viewer with zoom and pan."""

    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self.setScene(self._scene)

        self._zoom_factor = 1.0
        self._min_zoom = 0.05
        self._max_zoom = 20.0
        self._has_image = False

        # View settings
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setBackgroundBrush(QColor(30, 30, 30))

        # Enable drag-and-drop
        self.setAcceptDrops(True)

        I18n.instance().language_changed.connect(lambda _: self.viewport().update())

    def set_image(self, image: QImage) -> None:
        """Display a QImage in the viewer."""
        self._pixmap_item.setPixmap(QPixmap.fromImage(image))
        if not self._has_image:
            self._scene.setSceneRect(QRectF(self._pixmap_item.pixmap().rect()))
            self._has_image = True
            return
        # Only update the visible region, not the entire scene
        self._pixmap_item.update()

    def fit_in_view(self) -> None:
        """Fit the image to the view."""
        if not self._has_image or self._pixmap_item.pixmap().isNull():
            return
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_factor = self.transform().m11()
        self.zoom_changed.emit(self._zoom_factor)

    def set_zoom(self, factor: float) -> None:
        """Set absolute zoom factor."""
        if not self._has_image:
            return
        factor = max(self._min_zoom, min(self._max_zoom, factor))
        # Get current center to restore after zoom
        center = self.mapToScene(self.viewport().rect().center())
        self.resetTransform()
        self.scale(factor, factor)
        self.centerOn(center)
        self._zoom_factor = factor
        self.zoom_changed.emit(self._zoom_factor)

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom_factor * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom_factor / 1.25)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom with mouse wheel."""
        delta = event.angleDelta().y()
        if delta > 0:
            scale = 1.15
        elif delta < 0:
            scale = 1.0 / 1.15
        else:
            return

        new_zoom = self._zoom_factor * scale
        if self._min_zoom <= new_zoom <= self._max_zoom:
            self.scale(scale, scale)
            self._zoom_factor = new_zoom
            self.zoom_changed.emit(self._zoom_factor)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double-click to fit in view."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.fit_in_view()
        else:
            super().mouseDoubleClickEvent(event)

    def reset_view(self) -> None:
        """Reset for a new file."""
        self._has_image = False

    def paintEvent(self, event) -> None:
        """Paint the view, showing welcome hint when no image is loaded."""
        super().paintEvent(event)
        if not self._has_image:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Draw hint text
            font = QFont()
            font.setPointSize(16)
            painter.setFont(font)
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(
                self.viewport().rect(),
                Qt.AlignmentFlag.AlignCenter,
                tr("welcome_hint"),
            )
            painter.end()

    def dragEnterEvent(self, event) -> None:
        """Accept SER file drag."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.ser'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        """Accept drag move for SER files."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.ser'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:
        """Forward drop to main window."""
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith('.ser'):
                event.acceptProposedAction()
                # Find the MainWindow and call open_file
                window = self.window()
                if hasattr(window, 'open_file'):
                    window.open_file(filepath)
                return

    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor
