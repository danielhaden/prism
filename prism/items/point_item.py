"""A drawable point on the canvas."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QMenu

from prism.items.label import Labelable


class PointItem(Labelable, QGraphicsEllipseItem):
    """A point rendered as a small filled circle.

    The point is positioned by its center. It is drawn at a fixed on-screen
    radius so it stays a consistent size regardless of the view's zoom.

    ``is_derived`` marks points that are computed from other geometry (e.g.
    intersections). Derived points are not valid snap targets and are managed
    by the scene rather than the user.
    """

    RADIUS = 5.0
    is_derived = False

    def __init__(self, center: QPointF):
        super().__init__(-self.RADIUS, -self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS)
        self.setPos(center)

        self.setBrush(QBrush(QColor("#1f77b4")))
        self.setPen(QPen(QColor("#0d3d61"), 1.5))

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        # Keep the point a constant screen size independent of zoom.
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(10)  # points sit above lines
        self.setCursor(Qt.OpenHandCursor)  # signal it's draggable
        self._label = None

    def center(self) -> QPointF:
        """Return the point's center in scene coordinates."""
        return self.scenePos()

    def contextMenuEvent(self, event):
        scene = self.scene()
        menu = QMenu()
        pin_action = unpin_action = None
        if scene is not None and hasattr(scene, "pin_lines_through"):
            pinned = any(
                line.pivot() is self for line in scene._lines()
            )
            if pinned:
                unpin_action = menu.addAction("Unpin Lines From Point")
            pin_action = menu.addAction("Pin Lines Through Point")
            menu.addSeparator()
        label_actions = self.add_label_actions(menu)

        chosen = menu.exec(event.screenPos())
        if chosen is None:
            return
        if chosen is pin_action:
            scene.pin_lines_through(self)
        elif chosen is unpin_action:
            scene.unpin_lines_through(self)
        else:
            self.handle_label_action(chosen, label_actions)
        event.accept()

    def set_center(self, center: QPointF) -> None:
        """Move the point to a new center (scene coordinates)."""
        parent = self.parentItem()
        self.setPos(parent.mapFromScene(center) if parent is not None else center)

    def itemChange(self, change, value):
        # Snap the point onto nearby objects while it is being moved.
        if change == QGraphicsItem.ItemPositionChange and not self.is_derived:
            value = self._snap_position(value)
        # Notify the scene so bound line endpoints and intersections update.
        elif change == QGraphicsItem.ItemPositionHasChanged:
            scene = self.scene()
            if scene is not None and hasattr(scene, "on_point_moved"):
                scene.on_point_moved(self)
        return super().itemChange(change, value)

    def _snap_position(self, value: QPointF) -> QPointF:
        scene = self.scene()
        if scene is None or not hasattr(scene, "snap_position"):
            return value
        snapped = scene.snap_position(value, exclude=self)
        if snapped is not None:
            scene.show_snap_indicator(snapped)
            return snapped
        scene.hide_snap_indicator()
        return value

    def mouseReleaseEvent(self, event):
        scene = self.scene()
        if scene is not None:
            scene.hide_snap_indicator()
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        # Draw a selection halo instead of the default dashed rectangle.
        if self.isSelected():
            painter.save()
            painter.setPen(QPen(QColor("#ff7f0e"), 2))
            painter.setBrush(Qt.NoBrush)
            halo = self.RADIUS + 3
            painter.drawEllipse(QRectF(-halo, -halo, 2 * halo, 2 * halo))
            painter.restore()

        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawEllipse(self.rect())
