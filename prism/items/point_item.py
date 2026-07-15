"""A drawable point on the canvas."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QMenu

from prism.items.label import Labelable


class PointItem(Labelable, QGraphicsEllipseItem):
    """A point rendered as a small filled circle.

    The point is positioned by its center. It is drawn at a fixed on-screen
    radius so it stays a consistent size regardless of the view's zoom.

    Display properties (all in on-screen pixels / colors):

    * ``radius`` - the dot's radius.
    * ``color`` - the dot's fill.
    * ``glow_radius`` / ``glow_color`` - a filled disc drawn *behind* the dot
      but *over* the lines, giving the point a clear surround. Typically the
      background color, so converging lines are cut away near the point. A
      ``glow_radius`` of 0 disables it.

    ``is_derived`` marks points that are computed from other geometry (e.g.
    intersections). Derived points are not valid snap targets and are managed
    by the scene rather than the user.
    """

    RADIUS = 5.0
    DEFAULT_COLOR = "#1f77b4"
    DEFAULT_GLOW_COLOR = "#fafafa"  # matches the canvas background
    is_derived = False

    def __init__(self, center: QPointF):
        # Initialise display state before super()/setFlag/setPos, any of which
        # can trigger boundingRect() (which reads these attributes).
        self._radius = float(self.RADIUS)
        self._glow_radius = 0.0
        self._glow_color = QColor(self.DEFAULT_GLOW_COLOR)

        super().__init__(-self.RADIUS, -self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS)
        self.setPos(center)

        self.setBrush(QBrush(QColor(self.DEFAULT_COLOR)))
        self.setPen(QPen(QColor(self.DEFAULT_COLOR).darker(180), 1.5))

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        # Keep the point a constant screen size independent of zoom.
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(10)  # points sit above lines
        self.setCursor(Qt.OpenHandCursor)  # signal it's draggable
        self._label = None

    # -- Display properties ------------------------------------------------

    def display_style(self) -> dict:
        """The point's current display properties."""
        return {
            "radius": self._radius,
            "color": QColor(self.brush().color()),
            "glow_radius": self._glow_radius,
            "glow_color": QColor(self._glow_color),
        }

    def set_display(
        self, radius=None, color=None, glow_radius=None, glow_color=None
    ) -> None:
        """Update any of the point's display properties."""
        self.prepareGeometryChange()
        if radius is not None:
            self._radius = float(radius)
            self.setRect(-self._radius, -self._radius, 2 * self._radius, 2 * self._radius)
        if color is not None:
            color = QColor(color)
            self.setBrush(QBrush(color))
            self.setPen(QPen(color.darker(180), 1.5))
        if glow_radius is not None:
            self._glow_radius = float(glow_radius)
        if glow_color is not None:
            self._glow_color = QColor(glow_color)
        self.update()

    # -- Geometry ----------------------------------------------------------

    def boundingRect(self) -> QRectF:
        r = max(self._radius + 4.0, self._glow_radius) + 2.0
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self) -> QPainterPath:
        # Hit area is the dot itself; the glow is purely decorative.
        path = QPainterPath()
        r = self._radius + 2.0
        path.addEllipse(QPointF(0, 0), r, r)
        return path

    def center(self) -> QPointF:
        """Return the point's center in scene coordinates."""
        return self.scenePos()

    def contextMenuEvent(self, event):
        scene = self.scene()
        menu = QMenu()
        display_action = menu.addAction("Modify Display Properties…")
        menu.addSeparator()
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
        if chosen is display_action:
            self.open_display_dialog()
        elif chosen is pin_action:
            scene.pin_lines_through(self)
        elif chosen is unpin_action:
            scene.unpin_lines_through(self)
        else:
            self.handle_label_action(chosen, label_actions)
        event.accept()

    def open_display_dialog(self) -> None:
        """Edit this point's display properties (optionally applying to all)."""
        from prism.point_dialog import PointStyleDialog

        scene = self.scene()
        parent = scene.views()[0] if (scene and scene.views()) else None
        current = self.display_style()
        style, apply_all = PointStyleDialog.get_style(
            current["radius"],
            current["color"],
            current["glow_radius"],
            current["glow_color"],
            parent,
        )
        if style is None:
            return
        if apply_all and scene is not None and hasattr(
            scene, "apply_point_style_to_all"
        ):
            scene.apply_point_style_to_all(style)
        else:
            self.set_display(**style)

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
        origin = QPointF(0, 0)
        painter.save()

        # Glow: a filled disc behind the dot but over the lines, so geometry
        # is cut away around the point.
        if self._glow_radius > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(self._glow_color))
            painter.drawEllipse(origin, self._glow_radius, self._glow_radius)

        # A selection halo instead of the default dashed rectangle.
        if self.isSelected():
            painter.setPen(QPen(QColor("#ff7f0e"), 2))
            painter.setBrush(Qt.NoBrush)
            halo = self._radius + 3
            painter.drawEllipse(origin, halo, halo)

        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawEllipse(origin, self._radius, self._radius)
        painter.restore()
