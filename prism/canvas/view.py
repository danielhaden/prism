"""The canvas view: renders the scene with pan, zoom, and tool-aware panning."""

import math

import shiboken6
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPolygonF
from PySide6.QtWidgets import QGraphicsView

from prism.items import PointItem
from prism.templates import TEMPLATE_MIME, deserialize, instantiate
from prism.tools import Tool


class CanvasView(QGraphicsView):
    """A QGraphicsView with wheel-zoom and tool-aware panning.

    The *reference frame* (the scene rect) defines how far out you can zoom:
    the view opens fitted to it and will not zoom out past it, so the working
    universe always fills the viewport.
    """

    MAX_SCALE = 20.0

    #: Chrome for a point that is defined but off-screen: an arrow at the edge
    #: pointing the way, with the point's name.
    OFFSCREEN_COLOR = "#5f5f5f"
    #: The selection orange the items themselves use, so a selected marker
    #: reads the same as a selected point.
    OFFSCREEN_SELECTED_COLOR = "#ff7f0e"
    OFFSCREEN_ARROW_PX = 9.0
    OFFSCREEN_MARGIN_PX = 3.0
    OFFSCREEN_ASIDE_PX = 9.0
    #: Slack around a marker's drawn shape, so it can be aimed at comfortably.
    OFFSCREEN_HIT_PAD_PX = 4.0

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)

        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#fafafa"))
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        # The off-screen markers live at the viewport edge, so a change
        # anywhere can alter them; repaint the lot rather than track it.
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self._fitted = False
        #: Where each off-screen marker was last drawn, as
        #: ``[(viewport rect, point), …]``. A marker is painted chrome rather
        #: than a scene item, so Qt's hit-testing knows nothing about it and
        #: the view has to answer clicks on one itself.
        self._offscreen_hits: list = []
        self._tool = Tool.SELECT
        self._marker_cursor = False
        self._marker_press = False

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

    # -- Points that are off-screen ---------------------------------------

    def drawForeground(self, painter, rect) -> None:
        super().drawForeground(painter, rect)
        self._draw_offscreen_points(painter)

    def _draw_offscreen_points(self, painter) -> None:
        """Mark each defined point that lies outside the view.

        A point you can't see is easy to forget, and a construction often
        reaches far off the canvas — a vanishing point especially. Each gets an
        arrow at the edge pointing its way, with its name, placed where the
        line it sits on leaves the view so you can follow that line to it.
        """
        self._offscreen_hits = []
        scene = self.scene()
        if scene is None or not hasattr(scene, "ordered_points"):
            return
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        away = [
            point
            for point in scene.ordered_points()
            if point.isVisible() and not visible.contains(point.center())
        ]
        if not away:
            return

        painter.save()
        painter.setWorldMatrixEnabled(False)  # from here on, viewport pixels
        metrics = QFontMetrics(painter.font())
        for point in away:
            colour = QColor(
                self.OFFSCREEN_SELECTED_COLOR
                if point.isSelected()
                else self.OFFSCREEN_COLOR
            )
            self._draw_offscreen_marker(painter, point, visible, colour, metrics)
        painter.restore()

    def _draw_offscreen_marker(self, painter, point, visible, colour, metrics):
        edge = self._edge_towards(point, visible)
        if edge is None:
            return
        at = QPointF(self.mapFromScene(edge))
        towards = QPointF(self.mapFromScene(point.center())) - at
        length = math.hypot(towards.x(), towards.y())
        if length < 1e-6:
            return
        direction = QPointF(towards.x() / length, towards.y() / length)
        perpendicular = QPointF(-direction.y(), direction.x())

        # Everything sits *inside* the viewport — an arrow tip past the edge
        # is simply clipped away — and a little to one side of the line, so
        # the marker doesn't sit on top of what it is annotating.
        aside = perpendicular * self.OFFSCREEN_ASIDE_PX
        tip = at - direction * self.OFFSCREEN_MARGIN_PX + aside
        base = tip - direction * self.OFFSCREEN_ARROW_PX
        painter.setPen(Qt.NoPen)
        painter.setBrush(colour)
        arrow = QPolygonF(
            [tip, base + perpendicular * 4.0, base - perpendicular * 4.0]
        )
        painter.drawPolygon(arrow)

        name = self.scene().element_name(point)
        width = metrics.horizontalAdvance(name)
        height = metrics.height()
        centre = base - direction * (max(width, height) / 2 + 4.0)
        box = QRectF(
            centre.x() - width / 2, centre.y() - height / 2, width, height
        )
        # Keep the name inside the viewport, however near the corner it is.
        bounds = QRectF(self.viewport().rect()).adjusted(2, 2, -2, -2)
        box.moveLeft(min(max(box.left(), bounds.left()), bounds.right() - width))
        box.moveTop(min(max(box.top(), bounds.top()), bounds.bottom() - height))
        painter.setPen(colour)
        painter.drawText(box, Qt.AlignCenter, name)

        # Remember where this landed, so a click on it can find the point.
        pad = self.OFFSCREEN_HIT_PAD_PX
        self._offscreen_hits.append(
            (box.united(arrow.boundingRect()).adjusted(-pad, -pad, pad, pad),
             point)
        )

    def _edge_towards(self, point, visible: QRectF):
        """Where to put the marker, in scene coordinates.

        Where the point's line leaves the view, if it has one — follow that
        line and you reach the point. Otherwise straight out from the middle.
        """
        for line in self._defining_lines(point)[:1]:
            crossings = _rect_crossings(line.display_line(), visible)
            if crossings:
                target = point.center()
                return min(
                    crossings, key=lambda hit: QLineF(hit, target).length()
                )
        return _leaves_rect(visible.center(), point.center(), visible)

    @staticmethod
    def _defining_lines(point) -> list:
        """The lines that place this point, most telling first."""
        if point.is_meet():
            return point.meeting_lines()
        anchor = point.anchor() if point.has_anchor() else None
        if anchor is not None and anchor.kind == "line":
            return [anchor.line]
        return []

    def point_at_marker(self, position: QPointF) -> PointItem | None:
        """The off-screen point whose edge marker lies under a viewport point.

        Args:
            position: Where the mouse is, in viewport coordinates.

        Returns:
            The point that marker names, or None if no marker is there.
        """
        for rect, point in reversed(self._offscreen_hits):
            # The list is only as fresh as the last repaint, so a point may
            # have gone since; reading a dead wrapper is a segfault.
            if rect.contains(position) and shiboken6.isValid(point):
                return point
        return None

    def _select_offscreen(self, event) -> bool:
        """Select the point an edge marker names, if a marker was clicked.

        Chrome at the edge is the only sign of a point that has scrolled off
        the canvas, so it is the natural thing to click at: without this the
        point can only be reached from the Elements panel.

        Args:
            event: The mouse press.

        Returns:
            Whether a marker took the click.
        """
        if self._tool != Tool.SELECT:
            return False  # in a drawing tool a click is for drawing
        point = self.point_at_marker(event.position())
        if point is None:
            return False
        if event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
            point.setSelected(not point.isSelected())
        else:
            scene = self.scene()
            if scene is not None:
                scene.clearSelection()
            point.setSelected(True)
        self.viewport().update()
        return True

    def _track_marker_cursor(self, event) -> None:
        """Point the cursor at a marker, so it reads as something to click."""
        over = self._tool == Tool.SELECT and (
            self.point_at_marker(event.position()) is not None
        )
        if over == self._marker_cursor:
            return
        self._marker_cursor = over
        if over:
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.viewport().unsetCursor()

    def apply_tool(self, tool: Tool) -> None:
        """Sync the view's drag mode with the active tool."""
        self._tool = tool
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
        if event.button() == Qt.LeftButton and self._select_offscreen(event):
            # Swallow the press so no rubber band starts on top of it, and
            # remember to swallow the release too — an unpaired release is
            # both a Qt warning and a half-finished gesture.
            self._marker_press = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_panning", False):
            self._pan_to(event)
            return
        self._track_marker_cursor(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and getattr(self, "_panning", False):
            self._end_pan()
            return
        if event.button() == Qt.LeftButton and self._marker_press:
            self._marker_press = False
            event.accept()
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


def _rect_crossings(segment: QLineF, rect: QRectF) -> list:
    """Where a segment crosses the sides of a rect."""
    sides = (
        QLineF(rect.topLeft(), rect.topRight()),
        QLineF(rect.topRight(), rect.bottomRight()),
        QLineF(rect.bottomRight(), rect.bottomLeft()),
        QLineF(rect.bottomLeft(), rect.topLeft()),
    )
    hits = []
    for side in sides:
        kind, where = segment.intersects(side)
        if kind == QLineF.IntersectionType.BoundedIntersection:
            hits.append(where)
    return hits


def _leaves_rect(inside: QPointF, outside: QPointF, rect: QRectF):
    """Where the segment from a point inside a rect to one outside leaves it."""
    crossings = _rect_crossings(QLineF(inside, outside), rect)
    if not crossings:
        return None
    return min(crossings, key=lambda hit: QLineF(hit, outside).length())
