"""A drawable line (segment) on the canvas."""

import shiboken6
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem, QMenu

from prism.items.definable import Definable
from prism.items.label import Labelable
from prism.items.point_item import PointItem


def _clip_line_to_rect(p0: QPointF, d: QPointF, rect):
    """Clip the infinite line ``p0 + t*d`` to ``rect`` (Liang-Barsky).

    Returns the two boundary points, or None if the line misses the rect.
    """
    t_min, t_max = -1e18, 1e18
    edges = (
        (-d.x(), p0.x() - rect.left()),
        (d.x(), rect.right() - p0.x()),
        (-d.y(), p0.y() - rect.top()),
        (d.y(), rect.bottom() - p0.y()),
    )
    for p, q in edges:
        if abs(p) < 1e-12:
            if q < 0:
                return None  # parallel and outside this slab
        else:
            t = q / p
            if p < 0:
                t_min = max(t_min, t)
            else:
                t_max = min(t_max, t)
    if t_min > t_max:
        return None
    return (
        QPointF(p0.x() + d.x() * t_min, p0.y() + d.y() * t_min),
        QPointF(p0.x() + d.x() * t_max, p0.y() + d.y() * t_max),
    )


class LineItem(Definable, Labelable, QGraphicsLineItem):
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

    #: Width of the invisible band around the line that still counts as a
    #: "hit", in **screen pixels**, so a thin line stays easy to click and drag.
    #: Scene units would shrink with the zoom — at the fully-zoomed-out default
    #: that left barely two pixels to aim at, and a line was nearly
    #: unselectable.
    HIT_PX = 12.0

    #: On-screen pixel radius for grabbing an endpoint / drawing its handle.
    ENDPOINT_GRAB_PX = 10.0
    HANDLE_PX = 5.0

    #: How far past each end of the drawn segment a crossing still counts as
    #: being on it, in scene units (see :meth:`meeting_line`). A crossing
    #: exactly *at* an end is the ordinary case — segment a line between two
    #: of its own crossings and the ends are those very points — and a plain
    #: bounded-intersection test loses it about half the time to floating-point
    #: rounding alone (measured: 1911 of 4000 random configurations). Far
    #: below a pixel at any zoom.
    MEET_EPS = 1e-6

    #: How nearly two lines must be parallel to share a point at infinity,
    #: as the cross product of their unit directions (so, the sine of the
    #: angle between them). Deliberately tight — about two ten-thousandths of
    #: a degree. Lines that merely *look* parallel do meet, somewhere off the
    #: canvas, and saying otherwise would hide a real crossing behind a
    #: convenience. Lines built to be parallel — two horizons, two uprights, a
    #: line translated from another — are parallel to the bit.
    PARALLEL_EPS = 1e-6

    #: How a line is drawn before anyone says otherwise.
    DEFAULT_COLOR = "#333333"
    DEFAULT_WIDTH = 2.0

    #: Whether this line's look was chosen directly rather than by a style.
    #: A class attribute, so it is there however early Qt calls back in.
    _styled_by_hand = False

    def __init__(self, start: QPointF, end: QPointF):
        super().__init__(QLineF(start, end))

        pen = QPen(QColor(self.DEFAULT_COLOR), self.DEFAULT_WIDTH)
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

        # A pivot point the line is pinned to: it stays a full line through
        # the point, and dragging the line rotates it about the point.
        self._pivot = None
        self._pivot_last: QPointF | None = None

        # Visible range: the line is infinite by default. Two ways to cut it
        # down, and only ever one of them at a time: an anchor point with an
        # extent each way, or a pair of points on the line that the drawn
        # segment runs between (and follows as they move).
        self._range_anchor = None
        self._range_neg = 0.0
        self._range_pos = 0.0
        self._range_ends = None

        # When locked, the line's direction is immutable: it can still be
        # moved, but no gesture rotates it (see set_orientation_locked).
        self._orientation_locked = False

        self._hover_end: int | None = None
        self._drag_end: int | None = None
        self._body_drag = False
        self._pivot_drag = False
        self._last_scene = QPointF()
        self._label = None

    # -- Label -------------------------------------------------------------

    def _label_anchor(self) -> QPointF:
        line = self.line()
        return (line.p1() + line.p2()) / 2

    # -- Context menu / line styling --------------------------------------

    def contextMenuEvent(self, event):
        scene = self.scene()
        menu = QMenu()
        # Offered for a click that actually landed on this line. No selection
        # needed: opening *this* line's menu already says which line is meant.
        # (The canvas menu's version does require selection — out there, on
        # blank canvas, which line you mean is a real question.)
        add_point_action = None
        # From scenePos, not pos(): correct however the event reached us.
        local_pos = self.mapFromScene(event.scenePos())
        if self.click_is_on_line(local_pos):
            add_point_action = menu.addAction("Add Point to Line")
            menu.addSeparator()

        # The ideal point this line runs to. Parallel lines share it, so the
        # wording says when it is already there to be shown rather than made.
        shared = (
            scene.point_at_infinity_of(self)
            if scene is not None and hasattr(scene, "point_at_infinity_of")
            else None
        )
        if shared is not None and shared.anchor().references_line(self):
            infinity_label = "Show Point at Infinity"
        elif shared is not None:
            others = ", ".join(
                sorted(
                    scene.line_id(line)
                    for line in shared.anchor().live_lines()
                )
            )
            infinity_label = f"Add Point at Infinity — shared with {others}"
        else:
            infinity_label = "Add Point at Infinity"
        infinity_action = menu.addAction(infinity_label)
        infinity_action.setEnabled(self.ideal_direction() is not None)
        menu.addSeparator()

        # Two lines selected: the point where they meet.
        meet_action = None
        selected_lines = (
            scene.selected_lines()
            if scene is not None and hasattr(scene, "selected_lines")
            else []
        )
        if len(selected_lines) == 2 and self in selected_lines:
            meet_action = menu.addAction("Add Point at Intersection")
            menu.addSeparator()
        elif scene is not None and len(selected_lines) > 2:
            unavailable = menu.addAction(
                f"Add Point at Intersection — {len(selected_lines)} lines "
                "selected, need 2"
            )
            unavailable.setEnabled(False)
            menu.addSeparator()
        line_props_action = menu.addAction("Line Properties…")
        proj_action = menu.addAction("Add Projectivity…")
        range_action = menu.addAction("Define Visible Range…")
        # Two selected points on this line: draw only the part between them.
        # Right-clicking the line says which line is meant, so no ambiguity
        # survives here even when several lines pass through both points.
        segment_action = None
        segment_points = (
            scene.selected_points()
            if scene is not None and hasattr(scene, "selected_points")
            else []
        )
        if len(segment_points) == 2 and all(
            self.passes_through(point) for point in segment_points
        ):
            segment_action = menu.addAction("Show Segment Between Points Only")
        else:
            segment_points = []
        show_full_action = (
            menu.addAction("Show Full Line") if self.has_visible_range() else None
        )

        # Anchor a point to this line when the selection is one line + point(s).
        snap_action = None
        sel_points, sel_line = (
            scene.selected_point_line_pair()
            if scene is not None and hasattr(scene, "selected_point_line_pair")
            else (None, None)
        )
        if sel_line is not None and sel_points:
            menu.addSeparator()
            snap_action = menu.addAction("Snap Point to Line")

        menu.addSeparator()
        label_actions = self.add_label_actions(menu)

        chosen = menu.exec(event.screenPos())
        if add_point_action is not None and chosen is add_point_action:
            if scene is not None:
                scene.point_on_line_command(self, event.scenePos())
        elif chosen is infinity_action:
            self._add_point_at_infinity()
        elif meet_action is not None and chosen is meet_action:
            self._add_meet_point(selected_lines)
        elif chosen is line_props_action:
            self.open_line_style_dialog()
        elif snap_action is not None and chosen is snap_action:
            scene.anchor_points_to_line(sel_points, sel_line)
        elif chosen is proj_action:
            self._add_projectivity_at(local_pos)
        elif chosen is range_action:
            self.open_visible_range_dialog()
        elif segment_action is not None and chosen is segment_action:
            self.show_segment_between(segment_points)
        elif show_full_action is not None and chosen is show_full_action:
            self._show_full_line()
        elif chosen is not None:
            self.handle_label_action(chosen, label_actions)
        event.accept()

    def _add_meet_point(self, lines: list) -> None:
        """Surface the point where two selected lines meet.

        Runs the console form, so clicking and typing stay the same thing and
        the command is recorded into the next script saved.

        Args:
            lines: The two selected lines.
        """
        scene = self.scene()
        if scene is None:
            return
        first, second = (scene.line_id(line) for line in lines)
        if not scene.run_as_command(f"(point {first} {second})"):
            scene.meet_of(*lines)

    def _add_point_at_infinity(self) -> None:
        """Surface the point at infinity this line runs to.

        Runs the console form, so clicking and typing stay the same thing and
        the command is recorded into the next script saved — the same bargain
        as :meth:`_add_meet_point`.
        """
        scene = self.scene()
        if scene is None:
            return
        if not scene.run_as_command(f"(point {scene.line_id(self)} infinity)"):
            scene.add_point_at_infinity(self)

    def _add_projectivity_at(self, local_pos: QPointF) -> None:
        """Add a pencil centered at the clicked point on this line."""
        from prism.projectivity_dialog import ProjectivityDialog

        scene = self.scene()
        if scene is None:
            return
        parent = scene.views()[0] if scene.views() else None
        angles = ProjectivityDialog.get_angles(parent)
        if not angles:
            return
        on_line = self._project_local(local_pos)  # snap the click onto the line
        center = scene.add_point(self.mapToScene(on_line))
        scene.add_projectivity(center, angles)

    def open_visible_range_dialog(self) -> None:
        from prism.visible_range_dialog import VisibleRangeDialog

        scene = self.scene()
        parent = scene.views()[0] if (scene and scene.views()) else None
        neg = self._range_neg if self.has_visible_range() else 120.0
        pos = self._range_pos if self.has_visible_range() else 120.0
        result = VisibleRangeDialog.get_range(neg, pos, parent)
        if result is None:
            return
        neg, pos = result
        if self._range_anchor is None and scene is not None:
            mid = (self.line().p1() + self.line().p2()) / 2  # a point on the line
            self._range_anchor = scene.add_point(self.mapToScene(mid))
        self.set_visible_range(self._range_anchor, neg, pos)
        if scene is not None:
            scene.on_line_changed(self)
            scene.commit_undo()

    def show_segment_between(self, points: list) -> None:
        """Draw only the part of this line between two points on it.

        Args:
            points: The two bounding points, in any order.
        """
        scene = self.scene()
        if scene is None:
            return
        first, second = (scene.point_id(point) for point in points)
        command = f"(segment {scene.line_id(self)} {first} {second})"
        if not scene.run_as_command(command):
            scene.segment_between(self, points[0], points[1])

    def _show_full_line(self) -> None:
        scene = self.scene()
        if scene is None:
            self.clear_visible_range()
            return
        if not scene.run_as_command(f"(segment {scene.line_id(self)} -full)"):
            scene.show_full_line(self)

    def set_style(
        self,
        color: QColor | None = None,
        width: float | None = None,
        style: Qt.PenStyle | None = None,
    ) -> None:
        """Change how this line is drawn, leaving out what isn't given.

        Args:
            color: A QColor, or None to keep the current one.
            width: Thickness in screen pixels (the pen is cosmetic), or None.
            style: A Qt pen style, or None.
        """
        scene = self.scene()
        as_default = scene is not None and scene.applying_default_style()
        if as_default and self._styled_by_hand:
            return  # formatted by hand; a style keeps its hands off it
        if not as_default:
            self._styled_by_hand = True
        pen = QPen(self.pen())
        if color is not None:
            pen.setColor(color)
        if width is not None:
            pen.setWidthF(width)
        if style is not None:
            pen.setStyle(style)
        pen.setCosmetic(True)  # keep thickness constant on screen
        self.setPen(pen)
        self.update()

    def reset_style(self) -> None:
        """Go back to how a line is drawn before anyone says otherwise.

        Also hands the line back to the canvas's style: it is no longer
        yours, so the next pass may dress it again.
        """
        self._styled_by_hand = False
        pen = QPen(QColor(self.DEFAULT_COLOR), self.DEFAULT_WIDTH)
        pen.setStyle(Qt.SolidLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.update()

    def is_styled_by_hand(self) -> bool:
        """Whether someone formatted this line directly.

        A line that was is left alone by the canvas's style — you picked it
        out on purpose, and a style re-asserting itself over the top would
        undo that every time anything was drawn.
        """
        return self._styled_by_hand

    def set_styled_by_hand(self, owned: bool) -> None:
        """Say whether this line's look is the user's own (for persistence)."""
        self._styled_by_hand = bool(owned)

    def open_line_style_dialog(self) -> None:
        from prism.line_dialog import LineStyleDialog

        pen = self.pen()
        scene = self.scene()
        parent = scene.views()[0] if (scene and scene.views()) else None
        color, width, style = LineStyleDialog.get_style(
            pen.color(), pen.widthF(), pen.style(), parent
        )
        if color is not None:
            new_pen = QPen(color, width)
            new_pen.setStyle(style)
            new_pen.setCosmetic(True)  # keep thickness constant on screen
            self.setPen(new_pen)
            self.update()
            if scene is not None and hasattr(scene, "commit_undo"):
                scene.commit_undo()

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
        """The *defining* segment (endpoints) in scene coordinates."""
        line = self.line()
        return QLineF(self.mapToScene(line.p1()), self.mapToScene(line.p2()))

    # -- Geometry queries (scene coords) ----------------------------------

    def scene_direction(self) -> QPointF | None:
        """Unit direction of the line in scene coords, or None if degenerate."""
        seg = self.scene_line()
        dx, dy = seg.x2() - seg.x1(), seg.y2() - seg.y1()
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1e-9:
            return None
        return QPointF(dx / length, dy / length)

    def param_of(self, scene_pt: QPointF) -> float:
        """Signed distance of ``scene_pt``'s projection from the line's origin."""
        d = self.scene_direction()
        if d is None:
            return 0.0
        p1 = self.scene_line().p1()
        return (scene_pt.x() - p1.x()) * d.x() + (scene_pt.y() - p1.y()) * d.y()

    def point_at_param(self, t: float) -> QPointF:
        """The point at parameter ``t`` along the (infinite) line."""
        p1 = self.scene_line().p1()
        d = self.scene_direction()
        if d is None:
            return QPointF(p1)
        return QPointF(p1.x() + d.x() * t, p1.y() + d.y() * t)

    def project_scene(self, scene_pt: QPointF) -> QPointF:
        """The closest point on the infinite line to ``scene_pt``."""
        return self.point_at_param(self.param_of(scene_pt))

    def span_in_rect(self, rect: QRectF) -> tuple | None:
        """Where the infinite line crosses ``rect``, ordered left to right.

        Vertical lines (whose ends share an x) are ordered top to bottom.

        Returns:
            An ``(a, b)`` pair of scene points, or None if the line misses
                the rect entirely.
        """
        direction = self.scene_direction()
        if direction is None:
            return None
        clipped = _clip_line_to_rect(self.scene_line().p1(), direction, rect)
        if clipped is None:
            return None
        a, b = clipped
        if (round(a.x(), 9), round(a.y(), 9)) > (round(b.x(), 9), round(b.y(), 9)):
            a, b = b, a
        return a, b

    # -- Points at infinity ------------------------------------------------

    def ideal_direction(self) -> QPointF | None:
        """The line's direction, signed so that parallels agree.

        A line runs both ways, but ``d`` and ``-d`` lead to the *same* point at
        infinity — the ideal point is one point, not two far ends. So the sign
        is settled here: rightward, or downward for an upright line. Two
        parallel lines then read the same vector however each of them happened
        to be drawn, which is what lets them share one ideal point.

        Returns:
            A unit vector, or None if the line is degenerate (zero length).
        """
        direction = self.scene_direction()
        if direction is None:
            return None
        flat = abs(direction.x()) <= 1e-12
        if direction.x() < 0 or (flat and direction.y() < 0):
            return QPointF(-direction.x(), -direction.y())
        return QPointF(direction.x(), direction.y())

    def is_parallel_to(self, other: "LineItem") -> bool:
        """Whether ``other`` runs in this line's direction.

        Parallel lines meet at infinity and nowhere else, so this is the test
        for whether the two share a point at infinity.

        Args:
            other: The line to compare with.

        Returns:
            Whether they are parallel to within :attr:`PARALLEL_EPS`.
        """
        mine = self.ideal_direction()
        theirs = other.ideal_direction()
        if mine is None or theirs is None:
            return False
        # Both are unit vectors, so the cross product is the sine of the angle
        # between them: zero exactly when they are parallel.
        cross = mine.x() * theirs.y() - mine.y() * theirs.x()
        return abs(cross) <= self.PARALLEL_EPS

    def frame_exit(self) -> QPointF | None:
        """Where the line leaves the reference frame, in its ideal direction.

        This is where a point at infinity on this line gets *drawn*. The point
        itself has no location, so the marker goes out at the edge of the
        frame, on the line, pointing the way it runs.

        Returns:
            A scene position, or None if the line misses the frame entirely
                (or there is no scene to ask about the frame).
        """
        scene = self.scene()
        if scene is None or not hasattr(scene, "reference_rect"):
            return None
        span = self.span_in_rect(scene.reference_rect())
        if span is None:
            return None
        # span_in_rect orders its pair left to right (top to bottom when
        # upright), and ideal_direction points that same way, so the far end
        # in the ideal direction is always the second of the two.
        return span[1]

    # -- Orientation lock --------------------------------------------------

    def set_orientation_locked(self, locked: bool) -> None:
        """Freeze (or release) the line's direction.

        A locked line can still be moved, but nothing rotates it: dragging an
        endpoint slides the whole line through the cursor instead of turning
        it, and pivot rotation is refused.
        """
        self._orientation_locked = bool(locked)

    def is_orientation_locked(self) -> bool:
        return self._orientation_locked

    def _translate_through(self, scene_pos: QPointF) -> None:
        """Move the line (keeping its direction) so it passes through a point."""
        projected = self.project_scene(scene_pos)
        self._translate(scene_pos.x() - projected.x(), scene_pos.y() - projected.y())

    # -- Infinite line / visible range ------------------------------------

    def set_visible_range(self, anchor, neg: float, pos: float) -> None:
        """Show only the segment ``neg`` back and ``pos`` forward of ``anchor``."""
        self._range_ends = None
        self._range_anchor = anchor
        self._range_neg = abs(neg)
        self._range_pos = abs(pos)
        self._range_changed()

    def set_segment_ends(self, first: PointItem, second: PointItem) -> None:
        """Show only the part of the line between two points on it.

        The two points are kept, not their positions, so the drawn segment
        follows them: slide one along the line, or move a line whose crossing
        is one of them, and the segment ends where the point now is. Both are
        projected onto the line, so a point that only sits near it still
        bounds the segment squarely.

        Args:
            first: One bounding point.
            second: The other.
        """
        self._range_anchor = None
        self._range_ends = (first, second)
        self._range_changed()

    def clear_visible_range(self) -> None:
        """Revert to a full (infinite) line, however it was cut down."""
        self._range_anchor = None
        self._range_ends = None
        self._range_changed()

    def _range_changed(self) -> None:
        self.prepareGeometryChange()
        self._reposition_label()
        self.update()

    def has_visible_range(self) -> bool:
        """Whether only part of this line is drawn, either way."""
        return self._range_anchor is not None or self._range_ends is not None

    def has_segment_ends(self) -> bool:
        """Whether the drawn part is bounded by two points on the line."""
        return self._range_ends is not None

    def range_anchor(self):
        return self._range_anchor

    def segment_ends(self) -> tuple | None:
        """The two points bounding the drawn segment, or None."""
        return self._range_ends

    def bounded_by(self, point) -> bool:
        """Whether ``point`` is one of the two ends of the drawn segment."""
        return any(end is point for end in (self._range_ends or ()))

    def _live_segment_ends(self) -> tuple | None:
        """The bounding points, while both can still place a segment.

        An end that has been deleted, or whose own definition has failed (a
        crossing whose lines no longer cross), leaves nothing to measure
        between. The line then draws in full rather than guessing: the segment
        comes back by itself the moment the point does.
        """
        if self._range_ends is None:
            return None
        for end in self._range_ends:
            if not shiboken6.isValid(end) or end.scene() is None:
                return None
            if end.position_undefined():
                return None
        return self._range_ends

    def _direction(self) -> QPointF | None:
        """Unit direction of the line (local coords), or None if degenerate."""
        line = self.line()
        dx, dy = line.x2() - line.x1(), line.y2() - line.y1()
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1e-9:
            return None
        return QPointF(dx / length, dy / length)

    def click_is_on_line(self, local_pos: QPointF) -> bool:
        """Whether a click landed on the line itself.

        Measured against the clickable band (:attr:`HIT_PX`), so "on the
        line" means what it looks like on screen rather than what the item's
        bounding box — fattened by the endpoint handles — would allow.

        Args:
            local_pos: The click, in this item's coordinates.

        Returns:
            Whether it is within the band.
        """
        offset = QLineF(local_pos, self._project_local(local_pos)).length()
        return offset <= self._px(self.HIT_PX) / 2

    def meets(self) -> list:
        """The points where this line meets others.

        The same relation :class:`~prism.anchors.MeetAnchor` holds, read from
        the line's side: these are points this line helps determine.

        Returns:
            The meet points on this line, in scene order of creation.
        """
        scene = self.scene()
        if scene is None:
            return []
        return [
            it
            for it in scene.items()
            if isinstance(it, PointItem)
            and it.is_meet()
            and it.anchor().references_line(self)
        ]

    def closest_scene_point(self, scene_pos: QPointF) -> QPointF:
        """The place on this line nearest ``scene_pos``, in scene coordinates.

        The line is infinite, so this is a perpendicular projection rather than
        a clamp to the drawn segment.

        Args:
            scene_pos: A position in scene coordinates, e.g. a click.

        Returns:
            The nearest position on the line.
        """
        return self.mapToScene(self._project_local(self.mapFromScene(scene_pos)))

    def _project_local(self, local_pt: QPointF) -> QPointF:
        line = self.line()
        p1 = line.p1()
        d = self._direction()
        if d is None:
            return p1
        t = (local_pt.x() - p1.x()) * d.x() + (local_pt.y() - p1.y()) * d.y()
        return QPointF(p1.x() + d.x() * t, p1.y() + d.y() * t)

    def _display_segment(self):
        """The segment actually drawn (local coords), or None if degenerate."""
        d = self._direction()
        if d is None:
            return None
        ends = self._live_segment_ends()
        if ends is not None:
            return tuple(
                self._project_local(self.mapFromScene(end.center())) for end in ends
            )
        if self._range_anchor is not None:
            c = self._project_local(self.mapFromScene(self._range_anchor.center()))
            return (
                QPointF(c.x() - d.x() * self._range_neg, c.y() - d.y() * self._range_neg),
                QPointF(c.x() + d.x() * self._range_pos, c.y() + d.y() * self._range_pos),
            )
        # Infinite: clip to the scene rect (the working universe).
        scene = self.scene()
        line = self.line()
        if scene is None:
            return (line.p1(), line.p2())
        rect = self.mapRectFromScene(scene.sceneRect())
        clipped = _clip_line_to_rect(line.p1(), d, rect)
        return clipped if clipped is not None else (line.p1(), line.p2())

    def display_line(self) -> QLineF:
        """The drawn segment in scene coordinates."""
        seg = self._display_segment()
        if seg is None:
            return self.scene_line()
        return QLineF(self.mapToScene(seg[0]), self.mapToScene(seg[1]))

    def meeting_line(self, other: "LineItem | None" = None) -> QLineF:
        """How far this line runs when asking where it crosses ``other``.

        The drawn segment, grown by :attr:`MEET_EPS` at each end: a crossing
        exists where the drawn parts meet, and the ends of a segment are
        themselves usually crossings, which a zero-tolerance test loses to
        rounding about half the time.

        With one exception, which is the whole reason this isn't just
        :meth:`display_line`: where ``other`` is a line that *makes* one of
        the points bounding the segment, the crossing is looked for along the
        **whole** line. A segment must not get to decide where its own ends
        are. Measure that crossing against the drawn part instead, and moving
        ``other`` outward puts the crossing past the end, which loses the
        crossing, which reopens the line, which brings the crossing back —
        round and round, a pass behind the drag.

        Args:
            other: The line being crossed, if the question is about a
                particular one.

        Returns:
            The segment to test, in scene coordinates.
        """
        line = (
            self.unbounded_line()
            if other is not None and self._bounded_by_crossing_with(other)
            else self.display_line()
        )
        d = self._direction()
        if d is None:
            return line
        # The direction is this item's; the segment is already in scene
        # coordinates, and the item is never rotated or scaled.
        eps = self.MEET_EPS
        return QLineF(
            QPointF(line.x1() - d.x() * eps, line.y1() - d.y() * eps),
            QPointF(line.x2() + d.x() * eps, line.y2() + d.y() * eps),
        )

    def unbounded_line(self) -> QLineF:
        """The whole line, clipped only to the scene, segment or no segment."""
        d = self._direction()
        scene = self.scene()
        line = self.line()
        if d is None or scene is None:
            return self.scene_line()
        rect = self.mapRectFromScene(scene.sceneRect())
        clipped = _clip_line_to_rect(line.p1(), d, rect)
        if clipped is None:
            return self.scene_line()
        return QLineF(self.mapToScene(clipped[0]), self.mapToScene(clipped[1]))

    def _bounded_by_crossing_with(self, other) -> bool:
        """Whether a point bounding the drawn segment is a crossing with ``other``."""
        for end in self._range_ends or ():
            if not shiboken6.isValid(end):
                continue
            anchor = end.anchor() if end.has_anchor() else None
            if anchor is None or anchor.kind != "meet":
                continue
            if anchor.references_line(self) and anchor.references_line(other):
                return True
        return False

    def passes_through(self, point: PointItem) -> bool:
        """Whether ``point`` lies on this line.

        A recorded relation settles it outright: a point anchored to the line,
        or a crossing this line helps make, is on it however the arithmetic
        comes out. Otherwise it is measured, against the same band a click
        gets (:attr:`HIT_PX`), so a point that looks on the line counts as on
        it.

        Args:
            point: The point to test.

        Returns:
            Whether it is on this line.
        """
        if point is None or point.position_undefined():
            return False
        if point.anchor_references_line(self):
            return True
        local = self.mapFromScene(point.center())
        return QLineF(local, self._project_local(local)).length() <= (
            self._px(self.HIT_PX) / 2
        )

    # -- Pivot (pinned through a point; rotates about it) -----------------

    def set_pivot(self, point) -> None:
        """Pin this line to pass through ``point`` (a pencil member)."""
        self._pivot = point
        self._pivot_last = point.center()

    def clear_pivot(self) -> None:
        self._pivot = None
        self._pivot_last = None

    def has_pivot(self) -> bool:
        return self._pivot is not None

    def pivot(self):
        return self._pivot

    def refresh_pivot_reference(self) -> None:
        """Re-baseline the pivot position without moving (after a rigid move)."""
        if self._pivot is not None:
            self._pivot_last = self._pivot.center()

    def sync_from_pivot(self) -> None:
        """The pivot moved: translate the line so it still passes through it."""
        if self._pivot is None:
            return
        center = self._pivot.center()
        if self._pivot_last is not None:
            delta = center - self._pivot_last
            if not delta.isNull():
                self._translate(delta.x(), delta.y())
        self._pivot_last = center

    def _rotate_about_pivot(self, cursor_scene: QPointF) -> None:
        """Rotate the line so it points from the pivot toward the cursor,
        keeping each endpoint's distance from the pivot (a full line through
        the point)."""
        if self._orientation_locked:
            return
        pivot = self._pivot.center()
        v = cursor_scene - pivot
        length = (v.x() ** 2 + v.y() ** 2) ** 0.5
        if length < 1e-6:
            return
        ux, uy = v.x() / length, v.y() / length

        line = self.line()
        new_pts = []
        for p in (line.p1(), line.p2()):
            dx, dy = p.x() - pivot.x(), p.y() - pivot.y()
            dist = (dx * dx + dy * dy) ** 0.5
            side = 1.0 if (dx * v.x() + dy * v.y()) >= 0 else -1.0
            new_pts.append(
                QPointF(pivot.x() + ux * dist * side, pivot.y() + uy * dist * side)
            )
        self.prepareGeometryChange()
        self.setLine(QLineF(new_pts[0], new_pts[1]))
        self._reposition_label()
        self.update()
        scene = self.scene()
        if scene is not None:
            scene.on_line_changed(self)

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
        """A fattened path around the drawn segment for forgiving hit-testing."""
        path = QPainterPath()
        seg = self._display_segment()
        if seg is None:
            return path
        path.moveTo(seg[0])
        path.lineTo(seg[1])
        stroker = QPainterPathStroker()
        stroker.setWidth(self._px(self.HIT_PX))
        return stroker.createStroke(path)

    def boundingRect(self) -> QRectF:
        line = self.line()
        pts = [line.p1(), line.p2()]  # defining endpoints (handles)
        seg = self._display_segment()
        if seg is not None:
            pts += [seg[0], seg[1]]
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        margin = (
            max(self._px(self.HIT_PX) / 2, self._px(self.ENDPOINT_GRAB_PX))
            + self._px(self.HANDLE_PX)
        )
        return QRectF(
            min(xs) - margin,
            min(ys) - margin,
            (max(xs) - min(xs)) + 2 * margin,
            (max(ys) - min(ys)) + 2 * margin,
        )

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
        # A pinned line rotates about its pivot no matter where it's grabbed.
        if event.button() == Qt.LeftButton and self.has_pivot():
            self._pivot_drag = True
            self.setCursor(Qt.ClosedHandCursor)
            super().mousePressEvent(event)  # allow selection
            event.accept()
            return
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
        if self._pivot_drag and (event.buttons() & Qt.LeftButton):
            self._rotate_about_pivot(event.scenePos())
            event.accept()
            return
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
        if self._pivot_drag:
            self._pivot_drag = False
            self.setCursor(Qt.OpenHandCursor)
        if self._body_drag:
            self._body_drag = False
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if scene is not None and hasattr(scene, "commit_undo"):
            scene.commit_undo()

    # -- Movement ----------------------------------------------------------

    def _drag_endpoint(self, scene_pos: QPointF) -> None:
        """Move the active endpoint, snapping/binding to a nearby point."""
        scene = self.scene()
        if self._orientation_locked:
            # Direction is frozen: slide the line through the cursor instead.
            self._translate_through(scene_pos)
            if scene is not None:
                scene.hide_snap_indicator()
            return
        target = None
        if scene is not None and hasattr(scene, "snap_target"):
            target = scene.snap_target(scene_pos, exclude=self._other_bound(self._drag_end))
            if target is not None and scene.would_cycle(self, target):
                target = None  # this line helps define that point

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
        seg = self._display_segment()
        if seg is not None:
            painter.setPen(self.pen())
            painter.drawLine(seg[0], seg[1])
            if self.isSelected():
                pen = QPen(QColor("#ff7f0e"), 2)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawLine(seg[0], seg[1])

        arrow = self._ideal_arrow()
        if arrow is not None:
            self._paint_ideal_arrow(painter, *arrow)

        if self.isSelected() or self._hover_end is not None:
            self._paint_handles(painter)

    def _ideal_arrow(self) -> tuple | None:
        """Where to draw this line's arrowhead, if it runs to an ideal point.

        **Every** line running to a point at infinity gets one, not just the
        one the point is drawn at: the arrow says where *this* line goes, and
        a figure of parallels should show that on each of them. The point they
        share is the one that carries the label.

        Returns:
            A ``(position, direction)`` pair in scene coordinates, or None if
                this line has no point at infinity, it is hidden, or the spot
                falls outside the part of the line actually drawn.
        """
        scene = self.scene()
        if scene is None or not hasattr(scene, "point_at_infinity_of"):
            return None
        point = scene.point_at_infinity_of(self)
        if point is None or not point.anchor().references_line(self):
            return None
        if not point.is_shown() or point.position_undefined():
            return None
        where = self.frame_exit()
        direction = self.ideal_direction()
        if where is None or direction is None:
            return None
        seg = self._display_segment()
        if seg is None:
            return None
        # A line cut down to a visible range may not reach the frame edge; an
        # arrowhead floating off the end of the drawn segment would be a
        # claim about a line that isn't there.
        local = self.mapFromScene(where)
        span = QLineF(seg[0], seg[1])
        along = QPointF(local) - seg[0]
        if span.length() < 1e-9:
            return None
        unit = QPointF(span.dx() / span.length(), span.dy() / span.length())
        t = along.x() * unit.x() + along.y() * unit.y()
        if not -1e-6 <= t <= span.length() + 1e-6:
            return None
        return self.mapFromScene(where), self.mapFromScene(
            self.mapToScene(QPointF(0, 0)) + direction
        )

    def _paint_ideal_arrow(
        self, painter, where: QPointF, direction: QPointF
    ) -> None:
        """Draw the arrowhead marking where this line runs off to infinity.

        Sized in screen pixels, like the endpoint handles, so it stays the
        same size whatever the zoom.

        Args:
            painter: The painter, in the item's local coordinates.
            where: The arrow's anchor point, in local coordinates.
            direction: A unit vector along the line, in local coordinates.
        """
        colour = self._ideal_arrow_colour()
        tip_reach = self._px(PointItem.INFINITY_TIP)
        back_reach = self._px(PointItem.INFINITY_BACK)
        half_width = self._px(PointItem.INFINITY_HALF_WIDTH)
        across = QPointF(-direction.y(), direction.x())
        tip = where + direction * tip_reach
        base = where - direction * back_reach
        wing = across * half_width
        painter.save()
        painter.setBrush(QBrush(colour))
        pen = QPen(colour, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawPolygon(QPolygonF([tip, base + wing, base - wing]))
        painter.restore()

    def _ideal_arrow_colour(self) -> QColor:
        """The arrowhead's colour: the point's, so a pencil of them matches."""
        scene = self.scene()
        point = (
            scene.point_at_infinity_of(self)
            if scene is not None and hasattr(scene, "point_at_infinity_of")
            else None
        )
        if point is not None:
            return QColor(point.brush().color())
        return QColor(self.pen().color())

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
