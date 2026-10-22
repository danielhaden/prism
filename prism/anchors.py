"""Anchor points: invisible constraints that pin a point's position.

An *anchor point* is a pseudo-point — it is never drawn on the canvas. It only
governs where a real :class:`~prism.items.point_item.PointItem` sits and how it
responds to being dragged:

* :class:`LineAnchor` keeps a point on a line; dragging it *slides* it along.
* :class:`MeetAnchor` keeps a point at the crossing of two lines;
  dragging it *detaches* it into a free point.

All points are the same kind of object; whether one is "an intersection point"
is just a matter of which anchor (if any) it currently carries.
"""

from PySide6.QtCore import QLineF, QPointF


class Anchor:
    """Base class for a point-position constraint."""

    #: Short tag identifying the anchor kind.
    kind = "anchor"
    #: Whether a point holding this anchor should be persisted (undo/templates).
    persistent = False

    def position(self) -> QPointF | None:
        """The pinned scene position, or None if currently undefined."""
        return None

    def constrain_drag(self, scene_pos: QPointF) -> QPointF | None:
        """Where a drag to ``scene_pos`` should land.

        Returns the constrained position, or ``None`` to detach the point
        (freeing it to move wherever the drag goes).
        """
        return None

    def references_line(self, line) -> bool:
        """Whether this anchor depends on ``line`` (for cleanup on delete)."""
        return False


class LineAnchor(Anchor):
    """Constrains a point to lie on a line, at a stored parameter along it."""

    kind = "line"
    persistent = True

    def __init__(self, line, t: float = 0.0):
        self.line = line
        self.t = t

    def position(self) -> QPointF | None:
        if self.line.scene() is None:
            return None
        return self.line.point_at_param(self.t)

    def constrain_drag(self, scene_pos: QPointF) -> QPointF | None:
        projected = self.line.project_scene(scene_pos)
        self.t = self.line.param_of(projected)
        return projected  # slide along the line; never detaches

    def references_line(self, line) -> bool:
        return line is self.line


class MeetAnchor(Anchor):
    """Constrains a point to where a set of lines meet.

    Two lines are enough to determine the point. Further lines through the
    same place **join this anchor** rather than spawning points of their own:
    three concurrent lines meet at one point, not at three points stacked on
    each other. That is what makes a pencil a pencil.

    The lines are the relation. A point does not know what sort of point it
    is — it knows what it is the meet of, and
    :meth:`~prism.items.line_item.LineItem.meets` reads the same relation from
    the other side.
    """

    kind = "meet"
    persistent = False

    def __init__(self, lines):
        """
        Args:
            lines: The lines that meet here; two or more.
        """
        self.lines = list(lines)

    def position(self) -> QPointF | None:
        live = [ln for ln in self.lines if ln.scene() is not None]
        for first in range(len(live)):
            for second in range(first + 1, len(live)):
                kind, point = live[first].display_line().intersects(
                    live[second].display_line()
                )
                if kind == QLineF.IntersectionType.BoundedIntersection:
                    return point
        return None

    def constrain_drag(self, scene_pos: QPointF) -> QPointF | None:
        return None  # the lines decide where this point is

    def references_line(self, line) -> bool:
        return any(other is line for other in self.lines)

    def set_lines(self, lines) -> None:
        """Replace the set of lines meeting here."""
        self.lines = list(lines)
