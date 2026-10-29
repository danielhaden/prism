"""Anchor points: invisible constraints that pin a point's position.

An *anchor point* is a pseudo-point — it is never drawn on the canvas. It only
governs where a real :class:`~prism.items.point_item.PointItem` sits and how it
responds to being dragged:

* :class:`LineAnchor` keeps a point on a line; dragging it *slides* it along.
* :class:`MeetAnchor` keeps a point at the crossing of two lines;
  dragging it *detaches* it into a free point.
* :class:`IdealAnchor` marks a point as a **point at infinity** — a
  direction rather than a place. It has no position at all.

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

    def __init__(self, line: object, t: float = 0.0, locked: bool = False):
        """
        Args:
            line: The line the point lies on.
            t: Where along it, as the line's own parameter.
            locked: Whether the point is fixed at ``t`` rather than free to
                slide.
        """
        self.line = line
        self.t = t
        self.locked = locked

    def position(self) -> QPointF | None:
        if self.line.scene() is None:
            return None
        return self.line.point_at_param(self.t)

    def constrain_drag(self, scene_pos: QPointF) -> QPointF | None:
        if self.locked:
            # Held where it is. Returning None would mean "the anchor let go",
            # which is the opposite of what locking asks for.
            return self.position()
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

    def __init__(self, lines: list):
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
        # Held where the lines put it. Returning None would mean "the anchor
        # let go", turning a crossing into a free point under the cursor —
        # geometry you did not ask for, from a slip of the mouse.
        return self.position()

    def references_line(self, line) -> bool:
        return any(other is line for other in self.lines)

    def set_lines(self, lines: list) -> None:
        """Replace the set of lines meeting here."""
        self.lines = list(lines)


class IdealAnchor(Anchor):
    """Marks a point as the **point at infinity** of a direction.

    A line's two ends run out to the same ideal point, and parallel lines
    share it — which is exactly what "parallels meet at infinity" means. So
    the anchor holds a *set* of lines, as :class:`MeetAnchor` does, and a
    second line parallel to the first joins the same anchor rather than
    making a point of its own.

    It has **no position**, ever. ``position()`` returns None, so the scene
    marks the point undefined and never draws it at a coordinate — which is
    the truth: there is no coordinate. The view shows it where its lines
    leave the viewport instead.
    """

    kind = "ideal"
    persistent = True

    def __init__(self, lines: list):
        """
        Args:
            lines: The lines sharing this direction; at least one.
        """
        self.lines = list(lines)

    def position(self) -> QPointF | None:
        # At infinity: there is no finite place to be, and saying so is what
        # keeps the point undefined and undrawn.
        return None

    def constrain_drag(self, scene_pos: QPointF) -> QPointF | None:
        # Unreachable: an undefined point is hidden, and Qt leaves hidden
        # items out of hit-testing, so it can never be picked up.
        return None

    def live_lines(self) -> list:
        """The lines still on the canvas."""
        return [line for line in self.lines if line.scene() is not None]

    def direction(self) -> QLineF | None:
        """The shared direction as a segment, or None if every line is gone."""
        for line in self.live_lines():
            segment = line.scene_line()
            if segment.length() > 1e-9:
                return segment
        return None

    def angle(self) -> float | None:
        """The direction in degrees clockwise from horizontal.

        Prism's own angle convention, so the answer feeds straight back into
        ``(add-line <angle> …)``.

        Returns:
            The angle, or None if no line is left to read it from.
        """
        segment = self.direction()
        if segment is None:
            return None
        import math

        delta = segment.p2() - segment.p1()
        return math.degrees(math.atan2(delta.y(), delta.x()))

    def references_line(self, line) -> bool:
        return any(other is line for other in self.lines)

    def add_line(self, line) -> None:
        """Note another line running to this same point at infinity."""
        if not self.references_line(line):
            self.lines.append(line)

    def drop_line(self, line) -> None:
        """Forget a line that has gone."""
        self.lines = [other for other in self.lines if other is not line]
