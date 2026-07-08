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


class LineItem(QGraphicsLineItem):
    """A straight line segment between two scene points.

    The whole segment can be selected and dragged. In addition, hovering near
    either endpoint exposes a handle: dragging there moves just that endpoint,
    leaving the other fixed.

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
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(0)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.OpenHandCursor)  # signal the body is draggable

        # Which endpoint (1 or 2) is currently hovered / being dragged.
        self._hover_end: int | None = None
        self._drag_end: int | None = None

    # -- Zoom-aware sizing -------------------------------------------------

    def _view_scale(self) -> float:
        """Approximate current view zoom (scene units per pixel = 1/scale)."""
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
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_end is not None:
            self._move_endpoint(self._drag_end, event.pos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_end is not None:
            self._drag_end = None
            self._hover_end = self._endpoint_at(event.pos())
            self.setCursor(
                Qt.PointingHandCursor if self._hover_end else Qt.OpenHandCursor
            )
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _move_endpoint(self, end: int, local_pos: QPointF) -> None:
        line = self.line()
        self.prepareGeometryChange()
        if end == 1:
            self.setLine(QLineF(local_pos, line.p2()))
        else:
            self.setLine(QLineF(line.p1(), local_pos))

    # -- Painting ----------------------------------------------------------

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)

        if self.isSelected():
            pen = QPen(QColor("#ff7f0e"), 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(self.line())

        # Show endpoint handles while selected or hovering an endpoint.
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
