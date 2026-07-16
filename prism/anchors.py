"""Anchor points: invisible constraints that pin a point's position.

An *anchor point* is a pseudo-point — it is never drawn on the canvas. It only
governs where a real :class:`~prism.items.point_item.PointItem` sits and how it
responds to being dragged:

* :class:`LineAnchor` keeps a point on a line; dragging it *slides* it along.
* :class:`IntersectionAnchor` keeps a point at the crossing of two lines;
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


class IntersectionAnchor(Anchor):
    """Constrains a point to the crossing of two lines."""

    kind = "intersection"
    persistent = False

    def __init__(self, line_a, line_b):
        self.a = line_a
        self.b = line_b

    def position(self) -> QPointF | None:
        if self.a.scene() is None or self.b.scene() is None:
            return None
        kind, point = self.a.display_line().intersects(self.b.display_line())
        if kind == QLineF.IntersectionType.BoundedIntersection:
            return point
        return None

    def constrain_drag(self, scene_pos: QPointF) -> QPointF | None:
        return None  # dragging an intersection point detaches it

    def references_line(self, line) -> bool:
        return line is self.a or line is self.b
