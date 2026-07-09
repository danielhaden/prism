"""A drawable line (segment) on the canvas."""

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainterPath,
    QPainterPathStroker,
    QPen,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem

from prism.items.label import Labelable


class LineItem(Labelable, QGraphicsLineItem):
    """A straight line segment between two scene points.

    The whole segment can be selected and dragged. Hovering near either
    endpoint exposes a handle; dragging there moves just that endpoint. An
    endpoint can also be *bound* to a :class:`PointItem` (via snapping): while
    bound, the endpoint tracks that point when it moves, and dragging the line
    body carries the bound point along.

    For now this is a finite segment. Projective geometry ultimately deals in
    infinite lines; extending/clipping this to the view bounds is a natural
    next iteration.
    """

    #: Width (scene units) of the invisible band around the line that still
    #: counts as a "hit", so the thin line is easy to click and drag.
    HIT_WIDTH = 12.0

    #: On-screen pixel radius for grabbing an endpoint / drawing its handle.
    ENDPOINT_GRAB_PX = 10.0
    HANDLE_PX = 5.0

    def __init__(self, start: QPointF, end: QPointF):
        super().__init__(QLineF(start, end))

        pen = QPen(QColor("#333333"), 2)
        pen.setCosmetic(True)  # constant on-screen width regardless of zoom
        self.setPen(pen)

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        # Movement is handled manually (see _translate) so bound points and
        # free endpoints stay consistent; ItemIsMovable is intentionally off.
        self.setZValue(0)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.OpenHandCursor)  # signal the body is draggable

        # Endpoint -> bound PointItem (or None if the endpoint is free).
        self._bindings: dict[int, object] = {1: None, 2: None}

        self._hover_end: int | None = None
        self._drag_end: int | None = None
        self._body_drag = False
        self._last_scene = QPointF()
        self._label = None

    # -- Label -------------------------------------------------------------

    def _label_anchor(self) -> QPointF:
        line = self.line()
        return (line.p1() + line.p2()) / 2

    # -- Endpoint <-> point bindings --------------------------------------

    def bind_endpoint(self, end: int, point) -> None:
        """Bind endpoint 1 or 2 to a PointItem and snap it onto that point."""
        self._bindings[end] = point
        self.sync_from_point(point)

    def unbind_endpoint(self, end: int) -> None:
        self._bindings[end] = None

    def bound_point(self, end: int):
        return self._bindings[end]

    def sync_from_point(self, point) -> None:
        """Update any endpoint bound to ``point`` to that point's position."""
        line = self.line()
        changed = False
        for end in (1, 2):
            if self._bindings[end] is point:
                local = self.mapFromScene(point.center())
                if end == 1:
                    line = QLineF(local, line.p2())
                else:
                    line = QLineF(line.p1(), local)
                changed = True
        if changed:
            self.prepareGeometryChange()
            self.setLine(line)
            self._reposition_label()
            self.update()

    def scene_line(self) -> QLineF:
        """The segment in scene coordinates."""
        line = self.line()
        return QLineF(self.mapToScene(line.p1()), self.mapToScene(line.p2()))

    # -- Zoom-aware sizing -------------------------------------------------

    def _view_scale(self) -> float:
        scene = self.scene()
        views = scene.views() if scene else []
        if views:
            m11 = abs(views[0].transform().m11())
            if m11:
                return m11
        return 1.0

    def _px(self, pixels: float) -> float:
        """Convert an on-screen pixel length to local (scene) units."""
        return pixels / self._view_scale()

    def _endpoint_at(self, local_pos: QPointF) -> int | None:
        """Return 1 or 2 if ``local_pos`` is within grab range of an endpoint."""
        radius = self._px(self.ENDPOINT_GRAB_PX)
        line = self.line()
        for idx, p in ((1, line.p1()), (2, line.p2())):
            if QLineF(local_pos, p).length() <= radius:
                return idx
        return None

    # -- Hit testing / bounds ---------------------------------------------

    def shape(self) -> QPainterPath:
        """A fattened path around the segment for forgiving hit-testing."""
        path = QPainterPath()
        path.moveTo(self.line().p1())
        path.lineTo(self.line().p2())

        stroker = QPainterPathStroker()
        stroker.setWidth(self.HIT_WIDTH)
        return stroker.createStroke(path)

    def boundingRect(self) -> QRectF:
        # Grow the bounds so the hit band and endpoint handles aren't clipped.
        margin = max(self.HIT_WIDTH / 2, self._px(self.ENDPOINT_GRAB_PX))
        return super().boundingRect().adjusted(-margin, -margin, margin, margin)

    # -- Hover -------------------------------------------------------------

    def hoverMoveEvent(self, event):
        end = self._endpoint_at(event.pos())
        if end != self._hover_end:
            self._hover_end = end
            self.setCursor(Qt.PointingHandCursor if end else Qt.OpenHandCursor)
            self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        if self._hover_end is not None:
            self._hover_end = None
            self.update()
        self.setCursor(Qt.OpenHandCursor)
        super().hoverLeaveEvent(event)

    # -- Mouse: endpoint drag takes priority over whole-line move ---------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            end = self._endpoint_at(event.pos())
            if end is not None:
                self._drag_end = end
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return
        # Body: let the base handle selection, then we translate manually.
        self._body_drag = True
        self._last_scene = event.scenePos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_end is not None:
            self._drag_endpoint(event.scenePos())
            event.accept()
            return
        if self._body_drag and (event.buttons() & Qt.LeftButton):
            cur = event.scenePos()
            delta = cur - self._last_scene
            self._last_scene = cur
            self._translate(delta.x(), delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_end is not None:
            self._drag_endpoint(event.scenePos())
            end_local = self.mapFromScene(event.scenePos())
            self._drag_end = None
            scene = self.scene()
            if scene is not None:
                scene.hide_snap_indicator()
            self._hover_end = self._endpoint_at(end_local)
            self.setCursor(
                Qt.PointingHandCursor if self._hover_end else Qt.OpenHandCursor
            )
            self.update()
            event.accept()
            return
        if self._body_drag:
            self._body_drag = False
        super().mouseReleaseEvent(event)

    # -- Movement ----------------------------------------------------------

    def _drag_endpoint(self, scene_pos: QPointF) -> None:
        """Move the active endpoint, snapping/binding to a nearby point."""
        scene = self.scene()
        target = None
        if scene is not None and hasattr(scene, "snap_target"):
            target = scene.snap_target(scene_pos, exclude=self._other_bound(self._drag_end))

        if target is not None:
            self._bindings[self._drag_end] = target
            self._set_endpoint(self._drag_end, target.center())
            scene.show_snap_indicator(target.center())
        else:
            self._bindings[self._drag_end] = None
            self._set_endpoint(self._drag_end, scene_pos)
            if scene is not None:
                scene.hide_snap_indicator()

        if scene is not None:
            scene.on_line_changed(self)

    def _translate(self, dx: float, dy: float) -> None:
        line = self.line()
        self.prepareGeometryChange()
        self.setLine(
            QLineF(
                QPointF(line.x1() + dx, line.y1() + dy),
                QPointF(line.x2() + dx, line.y2() + dy),
            )
        )
        self._reposition_label()
        # Carry bound points along; their move re-syncs the endpoint exactly.
        for point in (self._bindings[1], self._bindings[2]):
            if point is not None:
                point.moveBy(dx, dy)
        scene = self.scene()
        if scene is not None:
            scene.on_line_changed(self)

    def _set_endpoint(self, end: int, scene_point: QPointF) -> None:
        local = self.mapFromScene(scene_point)
        line = self.line()
        self.prepareGeometryChange()
        if end == 1:
            self.setLine(QLineF(local, line.p2()))
        else:
            self.setLine(QLineF(line.p1(), local))
        self._reposition_label()
        self.update()

    def _other_bound(self, end: int):
        """The point bound to the *other* endpoint (to exclude from snapping)."""
        other = 2 if end == 1 else 1
        point = self._bindings[other]
        return (point,) if point is not None else ()

    # -- Painting ----------------------------------------------------------

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)

        if self.isSelected():
            pen = QPen(QColor("#ff7f0e"), 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(self.line())

        if self.isSelected() or self._hover_end is not None:
            self._paint_handles(painter)

    def _paint_handles(self, painter) -> None:
        radius = self._px(self.HANDLE_PX)
        line = self.line()
        painter.save()
        painter.setPen(QPen(QColor("#ff7f0e"), 0))
        for idx, p in ((1, line.p1()), (2, line.p2())):
            active = idx == self._hover_end or idx == self._drag_end
            painter.setBrush(QBrush(QColor("#ff7f0e") if active else QColor("#ffffff")))
            painter.drawEllipse(p, radius, radius)
        painter.restore()
