"""The canvas view: renders the scene with pan, zoom, and tool-aware panning."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsView

from prism.templates import TEMPLATE_MIME, deserialize, instantiate
from prism.tools import Tool


class CanvasView(QGraphicsView):
    """A QGraphicsView with wheel-zoom and tool-aware panning.

    The *reference frame* (the scene rect) defines how far out you can zoom:
    the view opens fitted to it and will not zoom out past it, so the working
    universe always fills the viewport.
    """

    MAX_SCALE = 20.0

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)

        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#fafafa"))
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self._fitted = False

    # -- Zoom limits -------------------------------------------------------

    def reference_frame(self) -> QRectF:
        """The rect that defines the fully-zoomed-out view."""
        scene = self.scene()
        if scene is None:
            return QRectF()
        if hasattr(scene, "reference_rect"):
            return scene.reference_rect()
        return scene.sceneRect()

    def min_scale(self) -> float:
        """The scale at which the reference frame exactly fills the viewport."""
        rect = self.reference_frame()
        viewport = self.viewport().rect()
        if rect.width() <= 0 or rect.height() <= 0 or viewport.isEmpty():
            return 0.01
        return min(viewport.width() / rect.width(), viewport.height() / rect.height())

    def fit_reference_frame(self) -> None:
        """Zoom fully out: fit the reference frame and center on it."""
        scale = self.min_scale()
        self.resetTransform()
        self.scale(scale, scale)
        self.centerOn(self.reference_frame().center())

    def _clamp_zoom(self) -> None:
        current = self.transform().m11()
        minimum = self.min_scale()
        if current < minimum:
            factor = minimum / current
            self.scale(factor, factor)

    # -- Staying within sight of the frame ---------------------------------

    def frame_in_view(self) -> bool:
        """Whether any part of the reference frame is on screen."""
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        return visible.intersects(self.reference_frame())

    def recenter_if_lost(self) -> bool:
        """Re-centre on the reference frame if it has scrolled out of sight.

        Returns:
            Whether the view had to be moved.
        """
        if self.frame_in_view():
            return False
        self.centerOn(self.reference_frame().center())
        return True

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fitted:
            self.fit_reference_frame()
            self._fitted = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._fitted:
            self.fit_reference_frame()
            self._fitted = True
        else:
            # A bigger viewport raises the floor; never sit below it.
            self._clamp_zoom()

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
        created = instantiate(self.scene(), template, scene_pos)
        scene = self.scene()
        if scene is not None and hasattr(scene, "commit_undo"):
            scene.commit_undo()
        return created

    # -- Zoom --------------------------------------------------------------

    def wheelEvent(self, event):
        current = self.transform().m11()

        if event.angleDelta().y() > 0:
            if current >= self.MAX_SCALE:
                return
            factor = min(1.15, self.MAX_SCALE / current)
            self.scale(factor, factor)
            return

        # Never zoom out past the reference frame — and once at that floor,
        # read another notch out as "take me back". The scene is far wider than
        # the frame and there's no grid to steer by, so a view panned into the
        # void is indistinguishable from an empty canvas.
        minimum = self.min_scale()
        if current > minimum * 1.0001:
            factor = max(1 / 1.15, minimum / current)
            self.scale(factor, factor)
        self.recenter_if_lost()

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
