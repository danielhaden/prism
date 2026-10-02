"""A drawable point on the canvas."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QMenu

from prism.items.definable import Definable
from prism.items.label import Labelable


class PointItem(Definable, Labelable, QGraphicsEllipseItem):
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

    A point may carry an :class:`~prism.anchors.Anchor` that pins its position
    (e.g. to a line, or to the intersection of two lines). All points are the
    same kind of object regardless; the anchor is an invisible constraint, not
    a different type of point.
    """

    RADIUS = 1.0
    DEFAULT_COLOR = "#000000"
    DEFAULT_GLOW_RADIUS = 7.0
    DEFAULT_GLOW_COLOR = "#fafafa"  # matches the canvas background

    #: Angle for "Add Line Through Point", in degrees clockwise from
    #: horizontal. A diagonal, so the new line reads as distinct from a horizon
    #: or an upright however the point was placed; it is pinned to the point,
    #: so dragging it rotates it to wherever you want.
    NEW_LINE_ANGLE = 45.0

    def __init__(self, center: QPointF):
        # Initialise state before super()/setFlag/setPos, any of which can
        # trigger boundingRect()/itemChange() (which read these attributes).
        self._radius = float(self.RADIUS)
        self._glow_radius = float(self.DEFAULT_GLOW_RADIUS)
        self._glow_color = QColor(self.DEFAULT_GLOW_COLOR)
        # An optional invisible constraint pinning this point's position.
        self._anchor = None
        self._syncing = False

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

        # Line through exactly two selected points.
        line_action = None
        two_points = (
            scene.selected_points()
            if scene is not None and hasattr(scene, "selected_points")
            else []
        )
        if len(two_points) == 2 and self in two_points:
            line_action = menu.addAction("Add Line Through Points")
            menu.addSeparator()

        # Lines drawn *through* this point. The lines are new, so nothing can
        # depend on them yet and no cycle is possible — a crossing is as good a
        # centre for a pencil as any other point.
        one_line_action = pencil_action = None
        if scene is not None:
            one_line_action = menu.addAction("Add Line Through Point")
            pencil_action = menu.addAction("Add Lines Through Point…")
            menu.addSeparator()

        # Anchor a point to a line when the selection is one line + point(s).
        snap_action = unsnap_action = None
        sel_points, sel_line = (
            scene.selected_point_line_pair()
            if scene is not None and hasattr(scene, "selected_point_line_pair")
            else (None, None)
        )
        if sel_line is not None and sel_points:
            snap_action = menu.addAction("Snap Point to Line")
        if self.has_anchor():
            unsnap_action = menu.addAction("Remove Anchor")
        if snap_action is not None or unsnap_action is not None:
            menu.addSeparator()

        # Pinning uses this point as a pivot. A computed point can drive lines
        # now; pin_lines_through() skips any line this point is itself computed
        # from, which would be circular.
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
        elif line_action is not None and chosen is line_action:
            scene.add_line_between(two_points[0], two_points[1])
        elif one_line_action is not None and chosen is one_line_action:
            scene.add_line_through(self, self.NEW_LINE_ANGLE)
        elif pencil_action is not None and chosen is pencil_action:
            self._add_lines_through()
        elif snap_action is not None and chosen is snap_action:
            scene.anchor_points_to_line(sel_points, sel_line)
        elif unsnap_action is not None and chosen is unsnap_action:
            self.clear_anchor()
        elif chosen is pin_action:
            scene.pin_lines_through(self)
        elif chosen is unpin_action:
            scene.unpin_lines_through(self)
        else:
            self.handle_label_action(chosen, label_actions)
        event.accept()

    def _add_lines_through(self) -> None:
        """Draw a pencil of lines through this point, at angles you choose."""
        from prism.projectivity_dialog import ProjectivityDialog

        scene = self.scene()
        if scene is None:
            return
        parent = scene.views()[0] if scene.views() else None
        angles = ProjectivityDialog.get_angles(parent)
        if angles:
            scene.add_projectivity(self, angles)

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
            scene.apply_point_style_to_all(style)  # commits its own undo step
        else:
            self.set_display(**style)
            if scene is not None and hasattr(scene, "commit_undo"):
                scene.commit_undo()

    def set_center(self, center: QPointF) -> None:
        """Move the point to a new center (scene coordinates)."""
        parent = self.parentItem()
        self.setPos(parent.mapFromScene(center) if parent is not None else center)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            if self._syncing:
                pass  # the scene is repositioning us from our anchor
            elif self._anchor is not None:
                value = self._drag_anchored(value)
            else:
                value = self._snap_position(value)  # free: snap while dragging
        elif change == QGraphicsItem.ItemPositionHasChanged:
            # Notify so bound endpoints / anchored points / intersections
            # update. An intersection point moved *by the scene* has nothing
            # depending on it, so skip that to avoid needless churn.
            if not (self._syncing and self.is_intersection()):
                scene = self.scene()
                if scene is not None and hasattr(scene, "on_point_moved"):
                    scene.on_point_moved(self)
        return super().itemChange(change, value)

    # -- Anchor ------------------------------------------------------------

    def anchor(self):
        """The invisible constraint pinning this point, or None."""
        return self._anchor

    def has_anchor(self) -> bool:
        return self._anchor is not None

    def is_intersection(self) -> bool:
        """Whether this point is currently pinned to a line intersection."""
        return self._anchor is not None and self._anchor.kind == "intersection"

    def set_anchor(self, anchor) -> None:
        """Pin this point with ``anchor`` and snap it to the anchor's position."""
        self._anchor = anchor
        self.sync_to_anchor()

    def clear_anchor(self) -> None:
        """Release the point; it moves freely again."""
        self._anchor = None

    def set_anchor_line(self, line) -> None:
        """Convenience: constrain the point to slide along ``line``."""
        from prism.anchors import LineAnchor

        self.set_anchor(LineAnchor(line, line.param_of(self.center())))

    def anchor_references_line(self, line) -> bool:
        return self._anchor is not None and self._anchor.references_line(line)

    def sync_to_anchor(self) -> None:
        """Put the point back at its anchor's computed position."""
        if self._anchor is None:
            return
        target = self._anchor.position()
        if target is None or target == self.center():
            return
        self._syncing = True
        try:
            self.set_center(target)
        finally:
            self._syncing = False

    def _drag_anchored(self, value: QPointF) -> QPointF:
        """Apply the anchor's drag rule; detach (and snap) if it releases."""
        parent = self.parentItem()
        scene_pt = parent.mapToScene(value) if parent is not None else value
        constrained = self._anchor.constrain_drag(scene_pt)
        if constrained is None:
            # The anchor released: this point is now free.
            self._anchor = None
            scene = self.scene()
            if scene is not None and hasattr(scene, "on_point_detached"):
                scene.on_point_detached(self)
            return self._snap_position(value)
        return parent.mapFromScene(constrained) if parent is not None else constrained

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
        if scene is not None and hasattr(scene, "commit_undo"):
            scene.commit_undo()

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
