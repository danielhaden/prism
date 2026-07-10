"""The canvas view: renders the scene with pan, zoom, and a grid."""

from PySide6.QtCore import QLineF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsView

from prism.templates import TEMPLATE_MIME, deserialize, instantiate
from prism.tools import Tool


class CanvasView(QGraphicsView):
    """A QGraphicsView with wheel-zoom, a light grid, and tool-aware panning."""

    MIN_SCALE = 0.1
    MAX_SCALE = 20.0
    GRID_SIZE = 50

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)

        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#fafafa"))
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

    def apply_tool(self, tool: Tool) -> None:
        """Sync the view's drag mode with the active tool."""
        if tool == Tool.SELECT:
            self.setDragMode(QGraphicsView.RubberBandDrag)
        else:
            # Disable rubber-band so drawing clicks aren't swallowed.
            self.setDragMode(QGraphicsView.NoDrag)

    # -- Drag & drop (templates from the Library) -------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TEMPLATE_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(TEMPLATE_MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat(TEMPLATE_MIME):
            template = deserialize(mime.data(TEMPLATE_MIME))
            scene_pos = self.mapToScene(event.position().toPoint())
            self.insert_template(template, scene_pos)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def insert_template(self, template, scene_pos):
        """Instantiate a template at a scene position (returns new items)."""
        return instantiate(self.scene(), template, scene_pos)

    # -- Zoom --------------------------------------------------------------

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        current = self.transform().m11()
        target = current * factor
        if target < self.MIN_SCALE or target > self.MAX_SCALE:
            return
        self.scale(factor, factor)

    # -- Pan (middle mouse drag) ------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._start_pan(event)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_panning", False):
            self._pan_to(event)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and getattr(self, "_panning", False):
            self._end_pan()
            return
        super().mouseReleaseEvent(event)

    def _start_pan(self, event):
        self._panning = True
        self._pan_anchor = event.position().toPoint()
        self.setCursor(Qt.ClosedHandCursor)

    def _pan_to(self, event):
        pos = event.position().toPoint()
        delta = pos - self._pan_anchor
        self._pan_anchor = pos
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - delta.x()
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - delta.y()
        )

    def _end_pan(self):
        self._panning = False
        self.unsetCursor()

    # -- Grid --------------------------------------------------------------

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)

        left = int(rect.left()) - (int(rect.left()) % self.GRID_SIZE)
        top = int(rect.top()) - (int(rect.top()) % self.GRID_SIZE)

        lines = []
        x = left
        while x < rect.right():
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
            x += self.GRID_SIZE
        y = top
        while y < rect.bottom():
            lines.append(QLineF(rect.left(), y, rect.right(), y))
            y += self.GRID_SIZE

        pen = QPen(QColor("#e6e6e6"), 0)
        painter.setPen(pen)
        painter.drawLines(lines)

        # Emphasise the origin axes.
        axis_pen = QPen(QColor("#cfcfcf"), 0)
        painter.setPen(axis_pen)
        painter.drawLine(QLineF(0, rect.top(), 0, rect.bottom()))
        painter.drawLine(QLineF(rect.left(), 0, rect.right(), 0))
