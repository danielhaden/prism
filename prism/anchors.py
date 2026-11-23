"""Anchor points: invisible constraints that pin a point's position.

An *anchor point* is a pseudo-point — it is never drawn on the canvas. It only
governs where a real :class:`~prism.items.point_item.PointItem` sits and how it
responds to being dragged:

* :class:`LineAnchor` keeps a point on a line; dragging it *slides* it along.
* :class:`MeetAnchor` keeps a point at the crossing of two lines;
  dragging it *detaches* it into a free point.
* :class:`InfinityAnchor` keeps a point at the point at infinity of a
  direction, where every line parallel to it runs; it cannot be dragged.

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
                kind, point = live[first].meeting_line(live[second]).intersects(
                    live[second].meeting_line(live[first])
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


class InfinityAnchor(Anchor):
    """Constrains a point to the point at infinity of a direction.

    Every line in a given direction runs to the same ideal point: that is what
    it means for parallel lines to meet at infinity. So this anchor holds a
    *set* of lines, as :class:`MeetAnchor` does — a parallel line asking for
    its point at infinity **joins this anchor** rather than a second point
    appearing for the same direction. One point at infinity per direction, and
    all the parallels run to it.

    The point has no location; that is the whole of what makes it ideal. What
    :meth:`position` returns is where it is *drawn* — out at the edge of the
    reference frame, along one of its lines — which marks the direction
    without claiming the point sits there.
    """

    kind = "infinity"
    persistent = True

    def __init__(self, lines: list):
        """
        Args:
            lines: The parallel lines that run to this ideal point; one or more.
        """
        self.lines = list(lines)
        # Taken now, and kept: the point *is* this direction, so a line that
        # later turns away stops running to it rather than dragging the point
        # round with it. Reading it lazily instead would read it from the line
        # as it is by then, and nothing would ever look un-parallel.
        # See :meth:`prune`.
        self._direction: QPointF | None = None
        for line in self.lines:
            direction = line.ideal_direction()
            if direction is not None:
                self._direction = direction
                break

    def live_lines(self) -> list:
        """The lines still on a canvas."""
        return [line for line in self.lines if line.scene() is not None]

    def direction(self) -> QPointF | None:
        """The direction this is the ideal point of.

        Settled when the anchor is made and held from then on, so it belongs
        to the point rather than to whichever line happens to be first in the
        list. The fallback below is for an anchor built before its lines had a
        direction to give.

        Returns:
            A unit vector, or None when no line is left to read it from.
        """
        if self._direction is not None:
            return self._direction
        for line in self.live_lines():
            direction = line.ideal_direction()
            if direction is not None:
                self._direction = direction
                return self._direction
        return None

    def runs_this_way(self, line: object) -> bool:
        """Whether ``line`` runs to this ideal point.

        Args:
            line: The line to test.

        Returns:
            Whether it is parallel to this point's direction.
        """
        direction = self.direction()
        other = line.ideal_direction()
        if direction is None or other is None:
            return False
        cross = direction.x() * other.y() - direction.y() * other.x()
        return abs(cross) <= line.PARALLEL_EPS

    def prune(self) -> list:
        """Drop any line that has been turned off this point's direction.

        Rotate a line out of the pencil of parallels and it no longer runs to
        this point — it has a direction, and an ideal point, of its own now.
        Saying otherwise would have the point claim a line that meets its
        fellows at an ordinary, finite crossing.

        Lines that have left the canvas are left alone; those are dropped by
        the scene when it removes them.

        Returns:
            The lines dropped.
        """
        dropped = [
            line
            for line in self.live_lines()
            if not self.runs_this_way(line)
        ]
        for line in dropped:
            self.drop_line(line)
        return dropped

    def position(self) -> QPointF | None:
        # Where to *draw* it, not where it is: see the class docstring. The
        # first line that crosses the frame decides, so the ring stays put as
        # parallels join and only moves if that line itself goes away.
        for line in self.live_lines():
            where = line.frame_exit()
            if where is not None:
                return where
        return None

    def constrain_drag(self, scene_pos: QPointF) -> QPointF | None:
        # Held where it is. A point at infinity *is* its direction: there is
        # nowhere to drag it to, and releasing it would leave a free point
        # sitting on the frame edge, which would mean nothing at all.
        return self.position()

    def references_line(self, line) -> bool:
        return any(other is line for other in self.lines)

    def set_lines(self, lines: list) -> None:
        """Replace the set of lines running to this ideal point."""
        self.lines = list(lines)

    def add_line(self, line: object) -> bool:
        """Note that ``line`` runs to this ideal point too.

        Args:
            line: A line parallel to the ones already here.

        Returns:
            Whether it was new.
        """
        if self.references_line(line):
            return False
        self.lines.append(line)
        return True

    def drop_line(self, line: object) -> None:
        """Forget ``line``; it has gone from the canvas.

        Args:
            line: The line to drop.
        """
        self.lines = [other for other in self.lines if other is not line]
