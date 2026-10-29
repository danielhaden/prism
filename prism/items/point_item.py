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

    #: Clickable radius, in screen pixels. The drawn dot is radius 1, far too
    #: small to aim at; this is the target you actually get.
    HIT_PX = 6.0

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

    def is_ideal(self) -> bool:
        """Whether this is a **point at infinity** — a direction, not a place.

        Such a point is kept *visible* to Qt so it can be selected and acted
        on, but it draws nothing and has no shape, so it is never seen on the
        canvas and never caught by a click or a rubber band. The view shows
        it where its lines leave the viewport instead.
        """
        anchor = self.anchor()
        return anchor is not None and anchor.kind == "ideal"

    def boundingRect(self) -> QRectF:
        if self.is_ideal():
            return QRectF()
        r = max(self._radius + 4.0, self._glow_radius, self.HIT_PX) + 2.0
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self) -> QPainterPath:
        # The dot is drawn at radius 1 by default and the glow around it is
        # decorative, so the hit area is neither: it is a fixed target in
        # screen pixels, comparable to a line's band, since points sit above
        # lines and are the more specific thing to aim at. (These coordinates
        # are screen pixels: the item ignores view transformations.)
        if self.is_ideal():
            return QPainterPath()  # nothing to click at infinity
        path = QPainterPath()
        r = max(self._radius + 2.0, self.HIT_PX)
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

        # Line through exactly two selected points. When the selection isn't
        # two, say so in a disabled entry rather than silently omitting it —
        # a stray selected point (a crossing caught by a rubber band, say)
        # used to make the command vanish with no explanation.
        line_action = one_line_action = pencil_action = None
        two_points = (
            scene.selected_points()
            if scene is not None and hasattr(scene, "selected_points")
            else []
        )
        joining = len(two_points) == 2 and self in two_points
        if joining:
            # With two points picked, joining them is the thing you mean. The
            # single-point commands below would be three ways to draw a line
            # in one menu, so they stand down.
            line_action = menu.addAction("Add Line Through Points")
            menu.addSeparator()
        elif scene is not None:
            reason = self._join_unavailable_reason(two_points)
            if reason is not None:
                unavailable = menu.addAction(f"Add Line Through Points — {reason}")
                unavailable.setEnabled(False)
                menu.addSeparator()

        # Lines drawn *through* this point. The lines are new, so nothing can
        # depend on them yet and no cycle is possible — a crossing is as good a
        # centre for a pencil as any other point.
        if scene is not None and not joining:
            one_line_action = menu.addAction("Add Line Through Point")
            pencil_action = menu.addAction("Add Lines Through Point…")
            menu.addSeparator()

        # Anchor a point to a line when the selection is one line + point(s).
        snap_action = None
        sel_points, sel_line = (
            scene.selected_point_line_pair()
            if scene is not None and hasattr(scene, "selected_point_line_pair")
            else (None, None)
        )
        if sel_line is not None and sel_points:
            snap_action = menu.addAction("Snap Point to Line")
        lock_action = None
        if self._anchor is not None and self._anchor.kind == "line":
            lock_action = menu.addAction(
                "Unlock From Line" if self.is_locked_to_line() else "Lock to Line"
            )
        if snap_action or lock_action:
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

        # Removing this point. A meet can only be hidden — the lines still
        # cross there — so the entry says what it will actually do.
        selected = [p for p in two_points if p is not self]
        if self.is_meet():
            delete_action = menu.addAction("Hide Point")
        elif selected and self in two_points:
            delete_action = menu.addAction(f"Delete {len(two_points)} Points")
        else:
            delete_action = menu.addAction("Delete Point")
        menu.addSeparator()

        label_actions = self.add_label_actions(menu)

        chosen = menu.exec(event.screenPos())
        if chosen is None:
            return
        if chosen is display_action:
            self.open_display_dialog()
        elif line_action is not None and chosen is line_action:
            first, second = (scene.point_id(p) for p in two_points)
            if not scene.run_as_command(f"(add-line (list {first}) (list {second}))"):
                scene.add_line_between(two_points[0], two_points[1])
        elif one_line_action is not None and chosen is one_line_action:
            angle = self.NEW_LINE_ANGLE
            if not scene.run_as_command(
                f"(add-line {angle:g} (list {scene.point_id(self)}))"
            ):
                scene.add_line_through(self, angle)
        elif pencil_action is not None and chosen is pencil_action:
            self._add_lines_through()
        elif snap_action is not None and chosen is snap_action:
            scene.anchor_points_to_line(sel_points, sel_line)
        elif lock_action is not None and chosen is lock_action:
            if self.set_locked_to_line(not self.is_locked_to_line()):
                scene.commit_undo()
        elif chosen is delete_action:
            self._delete_requested(two_points)
        elif chosen is pin_action:
            scene.pin_lines_through(self)
        elif chosen is unpin_action:
            scene.unpin_lines_through(self)
        else:
            self.handle_label_action(chosen, label_actions)
        event.accept()

    def _delete_requested(self, selected) -> None:
        """Remove this point — or the whole selection, if it is one.

        A meet is hidden rather than removed: its lines still cross there, so
        the next recompute would bring it straight back.

        Args:
            selected: The points currently selected.
        """
        scene = self.scene()
        if scene is None:
            return
        targets = selected if (len(selected) > 1 and self in selected) else [self]
        # Highest id first: removing a point renumbers the ones after it, so
        # commands written for the lower ids would then name the wrong points.
        ordered = sorted(targets, key=scene.ordered_points().index, reverse=True)
        for point in ordered:
            if not scene.run_as_command(f"(rm {scene.point_id(point)})"):
                if point.is_meet():
                    point.set_shown(False)
                else:
                    scene._remove_geometry(point)
        scene.recompute_intersections()
        scene.settle_definitions()
        scene.commit_undo()

    def _join_unavailable_reason(self, selected) -> str | None:
        """Why two points can't be joined right now, phrased for the menu.

        Args:
            selected: The points currently selected.

        Returns:
            A short reason, or None when there's nothing worth saying.
        """
        count = len(selected)
        if count > 2:
            return f"{count} points selected, need 2"
        if count == 2:
            return "right-click one of the two"
        if count == 1 and self in selected:
            return "select one more point"
        return None

    def _add_lines_through(self) -> None:
        """Draw a pencil of lines through this point, at angles you choose."""
        from prism.projectivity_dialog import ProjectivityDialog

        scene = self.scene()
        if scene is None:
            return
        parent = scene.views()[0] if scene.views() else None
        angles = ProjectivityDialog.get_angles(parent)
        if not angles:
            return
        # One command per ray, so the pencil replays from a script.
        name = scene.point_id(self)
        for angle in angles:
            if not scene.run_as_command(f"(add-line {angle:g} (list {name}))"):
                scene.add_projectivity(self, [angle])

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
            if not (self._syncing and self.is_meet()):
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

    def is_meet(self) -> bool:
        """Whether this point is where a set of lines meet.

        Not a kind of point — a statement about what currently determines it.
        Ask :meth:`meeting_lines` for the lines themselves.
        """
        return self._anchor is not None and self._anchor.kind == "meet"

    def is_locked_to_line(self) -> bool:
        """Whether this point is held at a fixed place on its line."""
        anchor = self._anchor
        return (
            anchor is not None
            and anchor.kind == "line"
            and getattr(anchor, "locked", False)
        )

    def set_locked_to_line(self, locked: bool) -> bool:
        """Hold the point where it is on its line, or let it slide again.

        Args:
            locked: Whether it should be held.

        Returns:
            Whether anything changed.
        """
        anchor = self._anchor
        if anchor is None or anchor.kind != "line":
            return False
        if bool(locked) == getattr(anchor, "locked", False):
            return False
        anchor.locked = bool(locked)
        return True

    def meeting_lines(self) -> list:
        """The lines that meet at this point, or an empty list."""
        return list(self._anchor.lines) if self.is_meet() else []

    def set_anchor(self, anchor) -> None:
        """Pin this point with ``anchor`` and snap it to the anchor's position."""
        self._anchor = anchor
        self.sync_to_anchor()

    def clear_anchor(self) -> None:
        """Release the point; it moves freely again.

        The scene is told, because it keeps its own list of the points that
        mark where lines meet. Leaving a released point in that list gives it
        an entry with no anchor, which the next recompute walks straight into.
        """
        was_meet = self.is_meet()
        self._anchor = None
        scene = self.scene()
        if was_meet and scene is not None and hasattr(scene, "on_point_detached"):
            scene.on_point_detached(self)

    def set_anchor_line(self, line) -> None:
        """Convenience: constrain the point to slide along ``line``."""
        from prism.anchors import LineAnchor

        self.set_anchor(LineAnchor(line, line.param_of(self.center())))

    def is_determined(self) -> bool:
        """Whether this point's position is fully fixed by what defines it.

        A point at the meet of two lines has no freedom left: it is where those
        lines put it. A point anchored to one line still slides along it, and a
        free point goes anywhere. Prefer this over asking what *kind* of point
        it is — what matters is how much freedom it has.
        """
        anchor = self._anchor
        if anchor is None:
            return False
        if anchor.kind == "meet":
            return True
        # A point locked to its line has no freedom left either.
        return anchor.kind == "line" and getattr(anchor, "locked", False)

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
        if self.is_ideal():
            return  # there is no coordinate at infinity to draw at
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
