"""The drawing scene: turns mouse interaction into geometry items.

Beyond raw drawing, the scene coordinates dependent geometry:
  * line endpoints snap onto (and bind to) existing points, and
  * a derived point is maintained wherever two lines cross.
When a point or line moves, the scene propagates the change so bound
endpoints follow and intersections recompute.
"""

import math
from typing import Callable

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPen, QTransform
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsScene,
    QMenu,
)

from prism.anchors import MeetAnchor
from prism.dependencies import (
    Changed,
    DependencyGraph,
    Geometry,
    dependencies_of,
)
from prism.items import GroupItem, LineItem, PointItem
from prism.items.label import LabelItem
from prism.tools import Tool


def _closest_on_segment(p: QPointF, seg: QLineF) -> QPointF:
    """The point on segment ``seg`` nearest to ``p``."""
    a, b = seg.p1(), seg.p2()
    abx, aby = b.x() - a.x(), b.y() - a.y()
    denom = abx * abx + aby * aby
    if denom == 0:
        return QPointF(a)
    t = ((p.x() - a.x()) * abx + (p.y() - a.y()) * aby) / denom
    t = max(0.0, min(1.0, t))
    return QPointF(a.x() + t * abx, a.y() + t * aby)


def _number(value: float) -> str:
    """A float as a command would be typed: short, but still exact enough."""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _letters(index: int) -> str:
    """Spreadsheet-style lowercase name for a 0-based index: a, b, .. z, aa .."""
    name = ""
    n = index
    while True:
        name = chr(ord("a") + n % 26) + name
        n = n // 26 - 1
        if n < 0:
            break
    return name


class CanvasScene(QGraphicsScene):
    """A QGraphicsScene that draws points and lines based on the active tool."""

    #: Emitted with a short hint for the status bar.
    statusMessage = Signal(str)
    #: Emitted when the undo/redo stacks change (args: can_undo, can_redo).
    historyChanged = Signal(bool, bool)

    #: On-screen pixel radius within which an endpoint snaps to a point.
    SNAP_PX = 12.0

    #: How near a *selected* line a right-click on blank canvas may land and
    #: still offer to put a point on it, in screen pixels. Deliberately far
    #: more generous than the line's own clickable band: you have already said
    #: which line you mean by selecting it, so aim is not the point.
    NEAR_LINE_PX = 40.0

    #: Side length of the reference frame: the working area the canvas shows
    #: when fully zoomed out. Deliberately much smaller than the scene rect,
    #: which only needs to be big enough that infinite lines always run past
    #: the viewport (so their clipped ends are never visible).
    REFERENCE_SIZE = 1200.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-2000, -2000, 4000, 4000)

        self._tool = Tool.SELECT
        self._line_start: QPointF | None = None
        self._line_start_point: PointItem | None = None
        self._preview_line: LineItem | None = None

        # Intersection points (plain points with an MeetAnchor), keyed
        # by the (ordered id) line pair.
        # Points where lines meet. One per place, however many lines concur
        # there; the lines are held by each point's MeetAnchor.
        self._meets: list[PointItem] = []
        self._snap_indicator: QGraphicsEllipseItem | None = None
        self._updating = False
        self._syncing_anchors = False
        self._seq_counter = 0

        # Undo/redo: snapshots of the whole scene, newest last.
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._restoring = False
        # Display properties applied to points created from now on (None = use
        # each item's own defaults). Set via apply_point_style_to_all().
        self._point_style: dict | None = None
        # Set by MainWindow: lets canvas actions run as console commands.
        self._run_command = None

    # -- Undo / redo -------------------------------------------------------

    #: Most snapshots kept; older history is discarded.
    UNDO_LIMIT = 100

    def init_history(self) -> None:
        """Record the starting state; call once the scene is set up."""
        from prism.scene_state import capture

        self._undo_stack = [capture(self)]
        self._redo_stack.clear()
        self._emit_history()

    def commit_undo(self) -> None:
        """Record the current state as a new undo step (call after an action)."""
        if self._restoring:
            return
        from prism.scene_state import capture

        state = capture(self)
        if self._undo_stack and state == self._undo_stack[-1]:
            return  # nothing actually changed
        self._undo_stack.append(state)
        if len(self._undo_stack) > self.UNDO_LIMIT:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._emit_history()

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 1

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> bool:
        """Step back to the previous state. Returns whether anything happened."""
        if not self.can_undo():
            return False
        self._redo_stack.append(self._undo_stack.pop())
        self._apply_state(self._undo_stack[-1])
        return True

    def redo(self) -> bool:
        """Step forward again. Returns whether anything happened."""
        if not self.can_redo():
            return False
        state = self._redo_stack.pop()
        self._undo_stack.append(state)
        self._apply_state(state)
        return True

    def _apply_state(self, state: dict) -> None:
        from prism.scene_state import restore

        self._restoring = True
        try:
            restore(self, state)
        finally:
            self._restoring = False
        self._emit_history()

    def _emit_history(self) -> None:
        self.historyChanged.emit(self.can_undo(), self.can_redo())

    # -- Tool management ---------------------------------------------------

    def set_tool(self, tool: Tool) -> None:
        """Switch the active tool, cancelling any in-progress drawing."""
        self._cancel_line()
        self.hide_snap_indicator()
        self._tool = tool
        self.clearSelection()
        self._emit_hint()

    def tool(self) -> Tool:
        return self._tool

    def _emit_hint(self) -> None:
        hints = {
            Tool.SELECT: "Select: click to select, drag to move.",
            Tool.POINT: "Point: click on the canvas to place a point.",
            Tool.LINE: "Line: click a start point, then an end point.",
        }
        self.statusMessage.emit(hints[self._tool])

    # -- Snapping ----------------------------------------------------------

    def reference_rect(self) -> QRectF:
        """The working area shown when the canvas is fully zoomed out."""
        half = self.REFERENCE_SIZE / 2
        return QRectF(-half, -half, self.REFERENCE_SIZE, self.REFERENCE_SIZE)

    def nearest_selected_line(self, scene_pos: QPointF) -> LineItem | None:
        """The selected line nearest ``scene_pos``, if one is within reach.

        "Within reach" is :attr:`NEAR_LINE_PX` on screen, so it means the same
        distance however far you are zoomed out.

        Args:
            scene_pos: A position in scene coordinates, e.g. a click.

        Returns:
            The nearest selected line, or None if none is close enough.
        """
        views = self.views()
        scale = abs(views[0].transform().m11()) if views else 1.0
        limit = self.NEAR_LINE_PX / (scale or 1.0)
        best = None
        for line in self._lines():
            if not line.isSelected():
                continue
            offset = QLineF(scene_pos, line.closest_scene_point(scene_pos)).length()
            if offset <= limit:
                limit = offset
                best = line
        return best

    def snap_radius(self) -> float:
        """Snap threshold in scene units (constant on screen across zoom)."""
        views = self.views()
        scale = abs(views[0].transform().m11()) if views else 1.0
        return self.SNAP_PX / (scale or 1.0)

    def snap_target(self, scene_pos: QPointF, exclude=()) -> PointItem | None:
        """The nearest point a line endpoint may bind to, or None.

        Crossings count: updates now run in dependency order, so a line bound
        to a computed point follows it. Points with no current position are
        skipped — there is nothing there to snap to.
        """
        radius = self.snap_radius()
        best = None
        best_d = radius
        for item in self.items():
            if (
                isinstance(item, PointItem)
                and not item.position_undefined()
                and item not in exclude
            ):
                d = QLineF(scene_pos, item.center()).length()
                if d <= best_d:
                    best_d = d
                    best = item
        return best

    def snap_position(self, scene_pos: QPointF, exclude=None) -> QPointF | None:
        """Snap position for a point: onto a nearby point, else onto a line.

        Other user points take priority over lines. ``exclude`` is the point
        being placed/moved, so it never snaps to itself or to a line it is
        bound to. Returns the snapped position, or None if nothing is near.
        """
        radius = self.snap_radius()

        # 1) Nearest other point wins (any point - they're all the same).
        best = None
        best_d = radius
        for item in self.items():
            if isinstance(item, PointItem) and item is not exclude:
                d = QLineF(scene_pos, item.center()).length()
                if d <= best_d:
                    best_d = d
                    best = item.center()
        if best is not None:
            return best

        # 2) Otherwise, the nearest point on a line (skipping lines the moved
        #    point is bound to, which would just snap it to itself). Project
        #    onto the *visible* extent, so a point snaps anywhere along an
        #    infinite line - not just near its two defining endpoints.
        best = None
        best_d = radius
        for line in self._lines():
            if exclude is not None and (
                line.bound_point(1) is exclude or line.bound_point(2) is exclude
            ):
                continue
            proj = _closest_on_segment(scene_pos, line.display_line())
            d = QLineF(scene_pos, proj).length()
            if d <= best_d:
                best_d = d
                best = proj
        return best

    def show_snap_indicator(self, center: QPointF) -> None:
        if self._snap_indicator is None:
            r = 9.0
            ring = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
            ring.setPen(QPen(QColor("#ff7f0e"), 2))
            ring.setBrush(Qt.NoBrush)
            ring.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            ring.setZValue(50)
            self.addItem(ring)
            self._snap_indicator = ring
        self._snap_indicator.setPos(center)
        self._snap_indicator.setVisible(True)

    def hide_snap_indicator(self) -> None:
        if self._snap_indicator is not None:
            self._snap_indicator.setVisible(False)

    # -- Mouse handling ----------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            # A right-click opens a context menu; don't let it change the
            # selection (otherwise a two-point selection collapses to the one
            # clicked, and selection-based menu items disappear).
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        pos = event.scenePos()

        if self._tool == Tool.POINT:
            snapped = self.snap_position(pos)
            self.add_point(snapped if snapped is not None else pos)
            self.hide_snap_indicator()
            self.commit_undo()
            event.accept()
            return

        if self._tool == Tool.LINE:
            self._handle_line_click(pos)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._tool == Tool.LINE:
            pos = event.scenePos()
            exclude = (
                (self._line_start_point,) if self._line_start_point else ()
            )
            snap = self.snap_target(pos, exclude=exclude)
            target = snap.center() if snap else pos
            if snap:
                self.show_snap_indicator(snap.center())
            else:
                self.hide_snap_indicator()
            if self._preview_line is not None:
                self._preview_line.setLine(
                    self._line_start.x(),
                    self._line_start.y(),
                    target.x(),
                    target.y(),
                )
        elif self._tool == Tool.POINT:
            snapped = self.snap_position(event.scenePos())
            if snapped is not None:
                self.show_snap_indicator(snapped)
            else:
                self.hide_snap_indicator()
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._cancel_line()
            self.hide_snap_indicator()
        super().keyPressEvent(event)

    # -- Drawing helpers ---------------------------------------------------

    def add_point(self, pos: QPointF) -> PointItem:
        point = PointItem(pos)
        self._apply_default_point_style(point)
        self._tag(point)
        self.addItem(point)
        return point

    def _apply_default_point_style(self, point: PointItem) -> None:
        """Give a newly created point the scene's display defaults, if set."""
        if self._point_style:
            point.set_display(**self._point_style)

    def apply_point_style_to_all(self, style: dict) -> int:
        """Apply display properties to every point, and to points created later.

        Args:
            style: Keyword arguments accepted by :meth:`PointItem.set_display`.

        Returns:
            The number of points updated.
        """
        self._point_style = dict(style)
        count = 0
        for item in self.items():
            if isinstance(item, PointItem):
                item.set_display(**style)
                count += 1
        self.commit_undo()
        return count

    def add_line(self, start: QPointF, end: QPointF) -> LineItem:
        line = LineItem(start, end)
        self._tag(line)
        self.addItem(line)
        return line

    def add_point_at(self, across: float, down: float) -> PointItem:
        """Add a point placed by fractions of the reference frame.

        Args:
            across: 0 at the canvas's left edge, 1 at its right.
            down: 0 at the canvas's top, 1 at its bottom.

        Returns:
            The new point.
        """
        rect = self.reference_rect()
        point = self.add_point(
            QPointF(
                rect.left() + across * rect.width(),
                rect.top() + down * rect.height(),
            )
        )
        self.commit_undo()
        return point

    def add_point_on_line(self, line: LineItem, fraction: float) -> PointItem | None:
        """Add a point a fraction of the way across a line.

        The span is measured where the line crosses the reference frame (the
        fully zoomed-out canvas): 0 is its left-hand end, 1 its right-hand end
        (top and bottom for a vertical line). The point is anchored to the
        line, so it stays on it.

        Args:
            line: The line to place the point on.
            fraction: Position along the span, from 0 to 1.

        Returns:
            The new point, or None if the line doesn't cross the canvas.
        """
        span = line.span_in_rect(self.reference_rect())
        if span is None:
            return None
        a, b = span
        pos = QPointF(
            a.x() + (b.x() - a.x()) * fraction,
            a.y() + (b.y() - a.y()) * fraction,
        )
        point = self.add_point(pos)
        point.set_anchor_line(line)
        self.recompute_intersections()
        self.commit_undo()
        return point

    def add_free_point(self, scene_pos: QPointF) -> PointItem:
        """Add a point at a position on the canvas, attached to nothing.

        The counterpart to :meth:`add_point_on_line_at`: the point is free to
        be dragged anywhere, rather than anchored to a line.

        Args:
            scene_pos: Where to put it, in scene coordinates.

        Returns:
            The new point.
        """
        point = self.add_point(scene_pos)
        self.recompute_intersections()
        self.commit_undo()
        return point

    def point_on_line_command(self, line: LineItem, scene_pos: QPointF) -> None:
        """Put a point on a line at a click, as the console command for it.

        Falls back to doing it directly when the console isn't available or
        the line doesn't cross the frame, which is what the fraction in the
        command is measured against.

        Args:
            line: The line to put the point on.
            scene_pos: Where the user clicked.
        """
        fraction = self.fraction_along_line(line, scene_pos)
        if fraction is not None and self.run_as_command(
            f"(point {self.line_id(line)} {_number(fraction)})"
        ):
            return
        self.add_point_on_line_at(line, scene_pos)

    def add_point_on_line_at(
        self, line: LineItem, scene_pos: QPointF
    ) -> PointItem:
        """Add a point on a line, where a click lands on it.

        The click is projected onto the line, so the point sits exactly on it
        rather than merely near it, and is anchored there — dragging it slides
        it along, as with :meth:`add_point_on_line`. Unlike that method this
        takes a position rather than a fraction, so it works anywhere along an
        infinite line, including outside the reference frame.

        Args:
            line: The line to place the point on.
            scene_pos: Where the user clicked, in scene coordinates.

        Returns:
            The new point.
        """
        point = self.add_point(line.closest_scene_point(scene_pos))
        point.set_anchor_line(line)
        self.recompute_intersections()
        self.commit_undo()
        return point

    def add_line_between(self, a: PointItem, b: PointItem) -> LineItem | None:
        """Add an infinite line through two points, bound to both.

        Each endpoint is bound to a point, so the line stays through them as
        they move. Returns None if the two points coincide.
        """
        if a is b or a.center() == b.center():
            return None
        line = self.add_line(a.center(), b.center())
        line.bind_endpoint(1, a)
        line.bind_endpoint(2, b)
        self.on_line_changed(line)
        self.commit_undo()
        return line

    def selected_points(self):
        """Selected points a line can be built on, in order.

        Crossings included: a line can now be bound to a computed point, and
        joining two crossings is a staple of projective construction.
        """
        return sorted(
            (it for it in self.selectedItems() if isinstance(it, PointItem)),
            key=lambda it: getattr(it, "_seq", 0),
        )

    def add_line_through(self, point: PointItem, angle_degrees: float) -> LineItem:
        """Add one infinite line through ``point`` at a given angle.

        Args:
            point: The point the line runs through; the line is pinned to it.
            angle_degrees: Direction, in degrees clockwise from horizontal.

        Returns:
            The new line.
        """
        return self.add_projectivity(point, [angle_degrees])[0]

    def add_horizon(self, fraction: float) -> LineItem:
        """Add a horizontal, orientation-locked line across the canvas.

        Args:
            fraction: Where to place it down the reference frame, from 0 (the
                top of the canvas) to 1 (the bottom).

        Returns:
            The new line.
        """
        rect = self.reference_rect()
        return self._add_horizon_at_y(rect.top() + fraction * rect.height())

    def set_command_runner(self, runner: Callable | None) -> None:
        """Let canvas actions go through the console.

        Given a ``run_command(text)`` callable, a canvas action that has a
        console equivalent is performed *as* that command — echoed in the
        console and recorded into the next script saved, so a figure built by
        clicking can be replayed as one built by typing.

        Args:
            runner: Callable taking one command line, or None to go direct.
        """
        self._run_command = runner

    def run_as_command(self, text: str) -> bool:
        """Run a console command on the canvas's behalf, if one can be run.

        Args:
            text: The command line, e.g. ``(add horizon 1/3)``.

        Returns:
            Whether it went through the console; False means the caller should
                do the work itself.
        """
        if self._run_command is None:
            return False
        self._run_command(text)
        return True

    def horizon_fraction_at(self, y: float) -> float:
        """Where a height sits down the reference frame, as a fraction.

        The inverse of what :meth:`add_horizon` does with its argument. Values
        outside 0-1 mean above or below the frame, which is allowed — the
        canvas is bigger than the frame.

        Args:
            y: A height in scene coordinates.

        Returns:
            The fraction.
        """
        rect = self.reference_rect()
        return (y - rect.top()) / rect.height()

    def add_horizon_at(self, scene_pos: QPointF) -> LineItem:
        """Add a horizon through a position on the canvas.

        The same thing :meth:`add_horizon` makes, placed where you clicked
        rather than at a fraction of the reference frame — so it can be put
        against the geometry already on the canvas instead of measured out.

        Args:
            scene_pos: Where to put it, in scene coordinates; only the height
                matters, since the line is horizontal.

        Returns:
            The new line.
        """
        return self._add_horizon_at_y(scene_pos.y())

    def _add_horizon_at_y(self, y: float) -> LineItem:
        rect = self.reference_rect()
        line = self.add_line(QPointF(rect.left(), y), QPointF(rect.right(), y))
        line.set_orientation_locked(True)
        self.on_line_changed(line)
        self.commit_undo()
        return line

    def _tag(self, item) -> None:
        """Stamp a creation sequence number for stable auto-label ordering."""
        self._seq_counter += 1
        item._seq = self._seq_counter

    def _handle_line_click(self, pos: QPointF) -> None:
        if self._line_start is None:
            snap = self.snap_target(pos)
            start = snap.center() if snap else pos
            self._line_start = start
            self._line_start_point = snap
            self._preview_line = LineItem(start, start)
            preview_pen = QPen(QColor("#999999"), 1, Qt.DashLine)
            preview_pen.setCosmetic(True)
            self._preview_line.setPen(preview_pen)
            self.addItem(self._preview_line)
            self.statusMessage.emit("Line: click the end point (Esc to cancel).")
        else:
            snap = self.snap_target(pos, exclude=self._start_exclude())
            end = snap.center() if snap else pos
            start = self._line_start
            start_point = self._line_start_point
            self._cancel_line()
            if start != end:
                line = self.add_line(start, end)
                if start_point is not None:
                    line.bind_endpoint(1, start_point)
                if snap is not None:
                    line.bind_endpoint(2, snap)
                self.on_line_changed(line)
            self.hide_snap_indicator()
            self._emit_hint()
            self.commit_undo()

    def _start_exclude(self):
        return (self._line_start_point,) if self._line_start_point else ()

    def _cancel_line(self) -> None:
        if self._preview_line is not None:
            self.removeItem(self._preview_line)
            self._preview_line = None
        self._line_start = None
        self._line_start_point = None

    # -- Dependency propagation -------------------------------------------

    def on_point_moved(self, point: PointItem) -> None:
        """A point moved: bring everything computed from it up to date."""
        self.propagate_from(point)

    def propagate_from(self, changed: Changed) -> None:
        """Re-place everything downstream of ``changed``, in dependency order.

        The order comes from :class:`~prism.dependencies.DependencyGraph`, so
        each item is re-placed only once everything it is computed from has
        been. That replaces the old fixed sweep (points drive lines, lines
        drive anchored points, crossings last), which could only ever leave
        crossings as leaves.

        Args:
            changed: The item that moved, or several of them.
        """
        if self._syncing_anchors:
            return
        self._syncing_anchors = True
        try:
            graph = DependencyGraph(self)
            for item in graph.update_order(changed):
                self._replace(item, graph)
        finally:
            self._syncing_anchors = False
        self.recompute_intersections()
        self.settle_definitions()

    def would_cycle(self, dependent: Geometry, dependency: Geometry) -> bool:
        """Whether computing ``dependent`` from ``dependency`` would be circular.

        Ask before creating a dependency on something that already exists —
        binding an endpoint, pinning, anchoring. Making new geometry is always
        safe, since nothing can depend on it yet.

        Args:
            dependent: The item that would be computed from the other.
            dependency: The item it would be computed from.

        Returns:
            Whether the relationship would define a position in terms of
                itself.
        """
        return DependencyGraph(self).would_cycle(dependent, dependency)

    def settle_definitions(self) -> None:
        """Re-decide across the whole scene what currently has a position.

        The targeted walk in :meth:`propagate_from` settles everything
        downstream of a move; this catches the rest — markers created, revived
        or retired by :meth:`recompute_intersections` afterwards, and the state
        of a scene just rebuilt from a snapshot.
        """
        graph = DependencyGraph(self)
        for item in graph.full_order():
            self._set_defined(item, graph)

    def _set_defined(self, item, graph: DependencyGraph) -> bool:
        """Decide whether ``item`` still has a position, and mark it.

        Undefined-ness cascades: whatever is computed from something that has
        no position has none either.

        Args:
            item: The point or line to judge.
            graph: The dependency graph it belongs to.

        Returns:
            Whether the item is defined.
        """
        undefined = any(
            dependency.position_undefined()
            for dependency in graph.dependencies(item)
        )
        if not undefined and isinstance(item, PointItem) and item.has_anchor():
            undefined = item.anchor().position() is None
        item.set_position_undefined(undefined)
        return not undefined

    def _replace(self, item, graph: DependencyGraph) -> None:
        """Put one item back where its dependencies now say it belongs."""
        if not self._set_defined(item, graph):
            return  # nowhere to put it; it is hidden until its definition holds
        if isinstance(item, LineItem):
            for end in (1, 2):
                bound = item.bound_point(end)
                if bound is not None:
                    item.sync_from_point(bound)
            if item.pivot() is not None:
                item.sync_from_pivot()
            if item.range_anchor() is not None:
                item.prepareGeometryChange()
                item.update()
        elif isinstance(item, PointItem) and item.has_anchor():
            item.sync_to_anchor()

    def on_point_detached(self, point: PointItem) -> None:
        """A point's anchor released (e.g. an intersection point was dragged).

        Drop it from the managed intersection set so it becomes a free point;
        the crossing gets a fresh marker on the next recompute.
        """
        if point in self._meets:
            self._meets.remove(point)

    # -- Pencils (pinning lines through a point) --------------------------

    def pin_lines_through(self, point: PointItem) -> int:
        """Pin every unpinned line passing through ``point`` to pivot on it.

        Returns the number of lines newly pinned.
        """
        radius = self.snap_radius()
        count = 0
        skipped = 0
        for line in self._lines():
            if line.has_pivot():
                continue
            # Use the visible extent so any line drawn through the point
            # qualifies, not just one whose defining endpoints straddle it.
            proj = _closest_on_segment(point.center(), line.display_line())
            if QLineF(point.center(), proj).length() <= radius:
                if self.would_cycle(line, point):
                    skipped += 1
                    continue
                line.set_pivot(point)
                count += 1
        if skipped:
            self.statusMessage.emit(
                f"Skipped {skipped} line(s): the point is computed from them, "
                "so pinning them to it would be circular."
            )
        return count

    def unpin_lines_through(self, point: PointItem) -> int:
        count = 0
        for line in self._lines():
            if line.pivot() is point:
                line.clear_pivot()
                count += 1
        return count

    # -- Anchoring points to lines ----------------------------------------

    def selected_point_line_pair(self) -> tuple:
        """The selected points and the single selected line, if that's the mix.

        Returns:
            A ``(points, line)`` tuple, or ``(None, None)`` when the selection
                isn't exactly one line plus at least one point.
        """
        # A point the lines already pin completely has no freedom to give to
        # another line, so it isn't offered — not because of what kind of point
        # it is, but because of how it is constrained.
        points = [
            it
            for it in self.selectedItems()
            if isinstance(it, PointItem) and not it.is_determined()
        ]
        lines = [it for it in self.selectedItems() if isinstance(it, LineItem)]
        if points and len(lines) == 1:
            return points, lines[0]
        return None, None

    def anchor_points_to_line(self, points, line: LineItem) -> int:
        """Constrain each point to lie on ``line``. Returns how many anchored."""
        anchored = 0
        skipped = 0
        for point in points:
            if self.would_cycle(point, line):
                skipped += 1
                continue
            point.set_anchor_line(line)
            anchored += 1
        if skipped:
            self.statusMessage.emit(
                f"Skipped {skipped} point(s): that line is computed from them, "
                "so anchoring them to it would be circular."
            )
        self.recompute_intersections()
        self.settle_definitions()
        self.commit_undo()
        return anchored

    def _points_anchored_to(self, line: LineItem):
        # Line-anchored points only; intersection markers are cleaned up by the
        # recompute when a line goes away.
        return [
            it
            for it in self.items()
            if isinstance(it, PointItem)
            and not it.is_meet()
            and it.anchor_references_line(line)
        ]

    def add_projectivity(self, point: PointItem, angles) -> list:
        """Create a pencil of lines through ``point`` at the given angles.

        Angles are degrees clockwise from horizontal. Each line is infinite and
        pinned to ``point`` (so the pencil rotates about it).
        """
        center = point.center()
        half = 60.0  # defining half-length; rendering is infinite
        created = []
        for angle in angles:
            r = math.radians(angle)
            dx, dy = half * math.cos(r), half * math.sin(r)
            line = self.add_line(
                QPointF(center.x() - dx, center.y() - dy),
                QPointF(center.x() + dx, center.y() + dy),
            )
            line.set_pivot(point)
            created.append(line)
        self.recompute_intersections()
        self.commit_undo()
        return created

    def on_line_changed(self, line: LineItem) -> None:
        """A line's geometry changed: bring everything computed from it up to date."""
        self.propagate_from(line)

    def _lines(self):
        return [
            it
            for it in self.items()
            if isinstance(it, LineItem) and it is not self._preview_line
        ]

    # -- Naming (shared with the console) ----------------------------------

    def ordered_points(self):
        """All points, in the id order used for names (P1, P2, ...)."""
        return sorted(
            (it for it in self.items() if isinstance(it, PointItem)),
            key=lambda p: getattr(p, "_seq", 0),
        )

    def ordered_lines(self):
        """All lines, in the id order used for names (L1, L2, ...)."""
        return sorted(self._lines(), key=lambda ln: getattr(ln, "_seq", 0))

    def element_name(self, item) -> str:
        """A stable-ish display name: label if set, else a P#/L# id."""
        label = item.label_text() if hasattr(item, "label_text") else ""
        if isinstance(item, PointItem):
            base = f"P{self.ordered_points().index(item) + 1}" if item in self.ordered_points() else "P?"
        elif isinstance(item, LineItem):
            base = f"L{self.ordered_lines().index(item) + 1}" if item in self.ordered_lines() else "L?"
        else:
            return type(item).__name__
        return f'{base} "{label}"' if label else base

    def recompute_intersections(self) -> None:
        """Maintain one point wherever lines meet.

        Crossings are gathered first and then **grouped by place**: lines that
        concur give a single point carrying all of them, not one point per
        pair stacked on top of each other. A point keeps its identity — and so
        its label, selection and anything built on it — while at least two of
        its lines still meet there.
        """
        if self._updating:
            return
        self._updating = True
        try:
            self._apply_meets(self._gather_meeting_places())
        finally:
            self._updating = False

    def _gather_meeting_places(self) -> list:
        """Where lines currently meet, and which lines meet at each place.

        Returns:
            ``[[position, [lines…]], …]``, one entry per place.
        """
        # An undefined line has no position, so it crosses nothing.
        lines = [ln for ln in self._lines() if not ln.position_undefined()]
        tolerance = self.snap_radius()
        places: list = []
        for first in range(len(lines)):
            for second in range(first + 1, len(lines)):
                a, b = lines[first], lines[second]
                where = self._intersection_of(a, b)
                if where is None:
                    continue
                place = None
                for candidate in places:
                    if QLineF(candidate[0], where).length() <= tolerance:
                        place = candidate
                        break
                if place is None:
                    places.append([where, [a, b]])
                else:
                    for line in (a, b):
                        if not any(other is line for other in place[1]):
                            place[1].append(line)
        return places

    def _apply_meets(self, places: list) -> None:
        """Bring the scene's meet points into line with ``places``."""
        spare = list(self._meets)
        for where, lines in places:
            point = self._claim_meet(spare, lines)
            if point is None:
                point = PointItem(where)
                point.set_anchor(MeetAnchor(lines))
                self._apply_default_point_style(point)
                self._tag(point)
                self.addItem(point)
                self._meets.append(point)
            else:
                spare.remove(point)
                point.anchor().set_lines(lines)
                point.set_position_undefined(False)
                point.sync_to_anchor()
        for point in spare:
            if point.anchor() is None or point.anchor().kind != "meet":
                # Released (its anchor was removed): an ordinary point now, and
                # not the scene's to manage.
                self._meets.remove(point)
                continue
            if self._is_depended_on(point) or point.label_text() or not point.is_shown():
                # Something is built on this meet, or you have said something
                # about it, so it outlives the crossing: undefined, ready to
                # come back when the lines meet again.
                point.set_position_undefined(True)
            else:
                self._meets.remove(point)
                self.removeItem(point)

    @staticmethod
    def _claim_meet(candidates: list, lines: list):
        """The existing meet point that belongs to ``lines``, if any.

        Identity follows the lines: a point is the same point while two of the
        lines meeting there are still the ones that defined it. That keeps a
        label and anything built on it attached as other lines come and go.
        """
        for point in candidates:
            anchor = point.anchor()
            if anchor is None or anchor.kind != "meet":
                continue  # no longer a meet; it will be dropped below
            shared = sum(1 for line in lines if anchor.references_line(line))
            if shared >= 2:
                return point
        return None

    def items_at(self, scene_pos: QPointF) -> list:
        """Items under a scene position, topmost first.

        Hit-tests through the view's transform, which matters for points:
        they carry ``ItemIgnoresTransformations`` so their clickable radius is
        in *screen pixels*. Without the transform Qt reads that radius as scene
        units instead, which shrinks the target as you zoom out — a point was
        winning a click only within about one pixel at the default zoom.

        Args:
            scene_pos: Where to look, in scene coordinates.

        Returns:
            The items there, topmost first.
        """
        views = self.views()
        transform = views[0].viewportTransform() if views else QTransform()
        return self.items(
            scene_pos, Qt.IntersectsItemShape, Qt.DescendingOrder, transform
        )

    def selected_lines(self) -> list:
        """The selected lines, in the order they were created."""
        return sorted(
            (it for it in self.selectedItems() if isinstance(it, LineItem)),
            key=lambda it: getattr(it, "_seq", 0),
        )

    def meet_of(self, a: LineItem, b: LineItem) -> PointItem | None:
        """The point where two lines meet, if they meet on the canvas.

        There is no making one: a point is already kept wherever lines cross,
        so this finds it. It may be hidden — that is a choice about drawing,
        not about whether the point is there.

        Args:
            a: One line.
            b: The other.

        Returns:
            The meet point, or None when the two don't currently cross.
        """
        for point in self._meets:
            if point.position_undefined():
                continue
            anchor = point.anchor()
            if anchor.references_line(a) and anchor.references_line(b):
                return point
        return None

    def point_id(self, point: PointItem) -> str:
        """The console id for a point (``P1``), as ``(list)`` numbers them."""
        ordered = self.ordered_points()
        return f"P{ordered.index(point) + 1}" if point in ordered else "P?"

    def element_id(self, item) -> str:
        """The console id for a point or line."""
        if isinstance(item, PointItem):
            return self.point_id(item)
        if isinstance(item, LineItem):
            return self.line_id(item)
        return "?"

    def canvas_fractions(self, scene_pos: QPointF) -> tuple:
        """A position as the across/down fractions the console uses.

        The inverse of :meth:`add_point_at`, so a click can be expressed as
        the command that would place a point there.

        Args:
            scene_pos: A position in scene coordinates.

        Returns:
            An ``(across, down)`` pair; outside 0-1 means outside the frame.
        """
        rect = self.reference_rect()
        return (
            (scene_pos.x() - rect.left()) / rect.width(),
            (scene_pos.y() - rect.top()) / rect.height(),
        )

    def fraction_along_line(
        self, line: LineItem, scene_pos: QPointF
    ) -> float | None:
        """How far along a line's visible span a position lies.

        The inverse of :meth:`add_point_on_line`, so a click on a line can be
        expressed as the command that would put a point there.

        Args:
            line: The line.
            scene_pos: A position on (or beside) it.

        Returns:
            The fraction, or None if the line doesn't cross the frame.
        """
        span = line.span_in_rect(self.reference_rect())
        if span is None:
            return None
        start, end = span
        dx, dy = end.x() - start.x(), end.y() - start.y()
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            return None
        return (
            (scene_pos.x() - start.x()) * dx + (scene_pos.y() - start.y()) * dy
        ) / length_squared

    def line_id(self, line: LineItem) -> str:
        """The console id for a line (``L1``), as ``(list)`` numbers them."""
        ordered = self.ordered_lines()
        return f"L{ordered.index(line) + 1}" if line in ordered else "L?"

    def hidden_points(self) -> list:
        """Every point currently hidden by choice."""
        return [
            it
            for it in self.items()
            if isinstance(it, PointItem) and not it.is_shown()
        ]

    def show_all_points(self) -> int:
        """Show every hidden point again.

        Returns:
            How many were shown.
        """
        hidden = self.hidden_points()
        for point in hidden:
            point.set_shown(True)
        if hidden:
            self.commit_undo()
        return len(hidden)

    def _is_depended_on(self, item) -> bool:
        """Whether any geometry in the scene is computed from ``item``."""
        for other in self.items():
            if other is item or not isinstance(other, (PointItem, LineItem)):
                continue
            if any(d is item for d in dependencies_of(other)):
                return True
        return False

    def _intersection_of(self, a: LineItem, b: LineItem) -> QPointF | None:
        # Use the visible (drawn) segment so markers appear where lines cross.
        kind, point = a.display_line().intersects(b.display_line())
        if kind != QLineF.IntersectionType.BoundedIntersection:
            return None
        # One point per place: if something is already there, that point *is*
        # the meet, and a second one stacked on it would be the same point
        # twice. (N concurrent lines still leave N stacked — see CLAUDE.md.)
        radius = self.snap_radius()
        for item in self.items():
            if isinstance(item, PointItem) and not item.is_meet():
                if QLineF(point, item.center()).length() <= radius:
                    return None
        return point

    # -- Context menu / labeling ------------------------------------------

    def contextMenuEvent(self, event):
        # Route to the topmost label / point / line under the cursor; a blank
        # spot shows the scene-level menu.
        target = None
        for item in self.items_at(event.scenePos()):
            if isinstance(item, (LabelItem, PointItem, LineItem)):
                target = item
                break

        if target is not None:
            # Qt fills in pos() only when it delivers the event to an item
            # itself; routing it by hand leaves pos() at (0, 0), which silently
            # told handlers every click landed on the item's own origin.
            event.setPos(target.mapFromScene(event.scenePos()))
            target.contextMenuEvent(event)
            return

        menu = QMenu()
        # A click out here, but near a line you have selected, almost certainly
        # means that line — so offer both and let the menu ask.
        near_line = self.nearest_selected_line(event.scenePos())
        line_point_action = (
            menu.addAction("Add Point to Line") if near_line is not None else None
        )
        free_point_action = menu.addAction("Add Free Point")
        horizon_action = menu.addAction("Add Horizon")
        menu.addSeparator()
        hidden = self.hidden_points()
        show_action = (
            menu.addAction(f"Show {len(hidden)} Hidden Point(s)") if hidden else None
        )
        auto_action = menu.addAction("Auto-label Scene")
        clear_action = menu.addAction("Clear All Labels")
        chosen = menu.exec(event.screenPos())
        if line_point_action is not None and chosen is line_point_action:
            self.point_on_line_command(near_line, event.scenePos())
        elif chosen is free_point_action:
            across, down = self.canvas_fractions(event.scenePos())
            if not self.run_as_command(
                f"(add point {_number(across)} {_number(down)})"
            ):
                self.add_free_point(event.scenePos())
        elif chosen is horizon_action:
            fraction = self.horizon_fraction_at(event.scenePos().y())
            if not self.run_as_command(f"(add horizon {_number(fraction)})"):
                self.add_horizon_at(event.scenePos())
        elif show_action is not None and chosen is show_action:
            if not self.run_as_command("(show -all)"):
                self.show_all_points()
        elif chosen is auto_action:
            if not self.run_as_command("(label -auto)"):
                self.auto_label()
        elif chosen is clear_action:
            if not self.run_as_command("(label -clear)"):
                self.clear_labels()
        event.accept()

    def label_element(self, item: PointItem | LineItem, text: str) -> None:
        """Label one point or line, in the scene's convention.

        Points are set upright and lines italic, matching
        :meth:`auto_label`, so a labelled-by-hand element sits beside
        auto-labelled ones without looking out of place.

        Args:
            item: The point or line to label.
            text: The label; an empty string removes it.
        """
        item.set_label(text)
        self._set_label_italic(item, isinstance(item, LineItem))
        self.commit_undo()

    def auto_label(self) -> tuple[int, int]:
        """Label points A, B, C… (upright) and lines a, b, c… (italic).

        Every point is labelled, including the ones that mark where lines
        cross: a crossing is a point of the figure like any other, and in a
        construction it is usually the one you most need to name. An
        intersection marker keeps the same identity as its lines move, so its
        label stays with it.

        Returns:
            How many points and lines were labelled.
        """
        points = sorted(
            (it for it in self.items() if isinstance(it, PointItem)),
            key=lambda it: getattr(it, "_seq", 0),
        )
        lines = sorted(
            (
                it
                for it in self.items()
                if isinstance(it, LineItem) and it is not self._preview_line
            ),
            key=lambda it: getattr(it, "_seq", 0),
        )
        for i, point in enumerate(points):
            point.set_label(_letters(i).upper())
            self._set_label_italic(point, False)
        for i, line in enumerate(lines):
            line.set_label(_letters(i))
            self._set_label_italic(line, True)
        self.commit_undo()
        return len(points), len(lines)

    def clear_labels(self) -> int:
        """Remove every label on the canvas.

        Returns:
            How many labels were removed.
        """
        cleared = 0
        for item in self.items():
            if isinstance(item, (PointItem, LineItem)) and item.label_text():
                item.set_label("")
                cleared += 1
        self.commit_undo()
        return cleared

    @staticmethod
    def _set_label_italic(item, italic: bool) -> None:
        label = item.label_item()
        if label is None:
            return
        font = label.font()
        font.setItalic(italic)
        label.apply_style(font, label.brush().color())

    # -- Grouping ----------------------------------------------------------

    def group_selected(self) -> GroupItem | None:
        """Group the selected top-level items into a single unit."""
        items = [
            it
            for it in self.selectedItems()
            if isinstance(it, (PointItem, LineItem, GroupItem))
            and it.parentItem() is None
        ]
        if len(items) < 2:
            return None
        group = GroupItem()
        self.addItem(group)
        for it in items:
            group.addToGroup(it)
        self.clearSelection()
        group.setSelected(True)
        self.recompute_intersections()
        self.commit_undo()
        return group

    def ungroup_selected(self) -> int:
        """Break the selected groups back into their members."""
        groups = [it for it in self.selectedItems() if isinstance(it, GroupItem)]
        for group in groups:
            children = list(group.childItems())
            self.destroyItemGroup(group)
            # Reparented children aren't re-registered in the scene's selection
            # index; remove/re-add restores it (positions are preserved).
            for child in children:
                if child.scene() is self:
                    self.removeItem(child)
                    self.addItem(child)
                    child.setSelected(True)
        self.recompute_intersections()
        self.commit_undo()
        return len(groups)

    def on_group_moved(self, group: GroupItem) -> None:
        # Children moved rigidly with the group; re-baseline pivots so a later
        # independent pivot move doesn't double-apply this translation.
        for line in self._lines():
            line.refresh_pivot_reference()
        self.recompute_intersections()

    # -- Editing -----------------------------------------------------------

    def delete_selected(self) -> None:
        for item in list(self.selectedItems()):
            # A crossing can't be removed — the lines still meet there, and the
            # recompute would put it straight back. Hiding it is what deleting
            # one can honestly mean.
            if isinstance(item, PointItem) and item.is_meet():
                item.set_shown(False)
                continue
            self._remove_geometry(item)
        self.recompute_intersections()
        self.commit_undo()

    def remove_element(self, item: PointItem | LineItem | GroupItem) -> None:
        """Remove one item from the canvas, detaching whatever referenced it.

        Lines bound or pinned to a removed point stay on the canvas and simply
        come free — the same thing the Delete key does, so the console and the
        canvas agree.

        Args:
            item: The point, line or group to remove.
        """
        self._remove_geometry(item)
        self.recompute_intersections()
        self.commit_undo()

    def _remove_geometry(self, item) -> None:
        if isinstance(item, GroupItem):
            # Detach references to the group's child points, then remove the
            # group (which removes its children too).
            for child in item.childItems():
                self._detach_point_references(child)
            self.removeItem(item)
            return
        if isinstance(item, PointItem):
            self._detach_point_references(item)
        elif isinstance(item, LineItem):
            # Release any line-anchored points (they become free).
            for point in self._points_anchored_to(item):
                point.clear_anchor()
        self.removeItem(item)

    def _detach_point_references(self, point) -> None:
        """Unbind/unpin any lines that reference ``point``."""
        if not isinstance(point, PointItem):
            return
        for line in self._lines():
            for end in (1, 2):
                if line.bound_point(end) is point:
                    line.unbind_endpoint(end)
            if line.pivot() is point:
                line.clear_pivot()
            if line.range_anchor() is point:
                line.clear_visible_range()

    def clear_all(self) -> None:
        self._cancel_line()
        self.clear()
        self._meets.clear()
        self._snap_indicator = None
        self.commit_undo()
