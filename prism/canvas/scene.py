"""The drawing scene: turns mouse interaction into geometry items.

Beyond raw drawing, the scene coordinates dependent geometry:
  * line endpoints snap onto (and bind to) existing points, and
  * a derived point is maintained wherever two lines cross.
When a point or line moves, the scene propagates the change so bound
endpoints follow and intersections recompute.
"""

import math

from PySide6.QtCore import QLineF, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsScene,
    QMenu,
)

from prism.items import GroupItem, IntersectionPointItem, LineItem, PointItem
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

    #: On-screen pixel radius within which an endpoint snaps to a point.
    SNAP_PX = 12.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-2000, -2000, 4000, 4000)

        self._tool = Tool.SELECT
        self._line_start: QPointF | None = None
        self._line_start_point: PointItem | None = None
        self._preview_line: LineItem | None = None

        # Derived intersection points, keyed by the (ordered id) line pair.
        self._intersections: dict[tuple[int, int], IntersectionPointItem] = {}
        self._snap_indicator: QGraphicsEllipseItem | None = None
        self._updating = False
        self._seq_counter = 0
        # Display properties applied to points created from now on (None = use
        # each item's own defaults). Set via apply_point_style_to_all().
        self._point_style: dict | None = None

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

    def snap_radius(self) -> float:
        """Snap threshold in scene units (constant on screen across zoom)."""
        views = self.views()
        scale = abs(views[0].transform().m11()) if views else 1.0
        return self.SNAP_PX / (scale or 1.0)

    def snap_target(self, scene_pos: QPointF, exclude=()) -> PointItem | None:
        """The nearest snappable point within the snap radius, or None."""
        radius = self.snap_radius()
        best = None
        best_d = radius
        for item in self.items():
            if (
                isinstance(item, PointItem)
                and not item.is_derived
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

        # 1) Nearest other user point wins.
        best = None
        best_d = radius
        for item in self.items():
            if (
                isinstance(item, PointItem)
                and not item.is_derived
                and item is not exclude
            ):
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
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        pos = event.scenePos()

        if self._tool == Tool.POINT:
            snapped = self.snap_position(pos)
            self.add_point(snapped if snapped is not None else pos)
            self.hide_snap_indicator()
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
        return count

    def add_line(self, start: QPointF, end: QPointF) -> LineItem:
        line = LineItem(start, end)
        self._tag(line)
        self.addItem(line)
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
        """A point moved: update bound endpoints, pinned lines, intersections."""
        for item in self._lines():
            item.sync_from_point(point)
            if item.pivot() is point:
                item.sync_from_pivot()
            if item.range_anchor() is point:
                item.prepareGeometryChange()
                item.update()
        self.recompute_intersections()

    # -- Pencils (pinning lines through a point) --------------------------

    def pin_lines_through(self, point: PointItem) -> int:
        """Pin every unpinned line passing through ``point`` to pivot on it.

        Returns the number of lines newly pinned.
        """
        radius = self.snap_radius()
        count = 0
        for line in self._lines():
            if line.has_pivot():
                continue
            # Use the visible extent so any line drawn through the point
            # qualifies, not just one whose defining endpoints straddle it.
            proj = _closest_on_segment(point.center(), line.display_line())
            if QLineF(point.center(), proj).length() <= radius:
                line.set_pivot(point)
                count += 1
        return count

    def unpin_lines_through(self, point: PointItem) -> int:
        count = 0
        for line in self._lines():
            if line.pivot() is point:
                line.clear_pivot()
                count += 1
        return count

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
        return created

    def on_line_changed(self, line: LineItem) -> None:
        """A line's geometry changed: recompute intersections."""
        self.recompute_intersections()

    def _lines(self):
        return [
            it
            for it in self.items()
            if isinstance(it, LineItem) and it is not self._preview_line
        ]

    def recompute_intersections(self) -> None:
        """Create/move/remove derived points at every line crossing."""
        if self._updating:
            return
        self._updating = True
        try:
            lines = self._lines()
            seen: set[tuple[int, int]] = set()
            for i in range(len(lines)):
                for j in range(i + 1, len(lines)):
                    a, b = lines[i], lines[j]
                    point = self._intersection_of(a, b)
                    if point is None:
                        continue
                    key = (min(id(a), id(b)), max(id(a), id(b)))
                    seen.add(key)
                    existing = self._intersections.get(key)
                    if existing is None:
                        marker = IntersectionPointItem(point)
                        self._apply_default_point_style(marker)
                        self.addItem(marker)
                        self._intersections[key] = marker
                    else:
                        existing.set_center(point)
            for key in list(self._intersections):
                if key not in seen:
                    self.removeItem(self._intersections.pop(key))
        finally:
            self._updating = False

    def _intersection_of(self, a: LineItem, b: LineItem) -> QPointF | None:
        # Use the visible (drawn) segment so markers appear where lines cross.
        kind, point = a.display_line().intersects(b.display_line())
        if kind != QLineF.IntersectionType.BoundedIntersection:
            return None
        # Skip crossings that coincide with an existing point (shared vertex),
        # so we don't stack a derived marker on top of a real point.
        radius = self.snap_radius()
        for item in self.items():
            if isinstance(item, PointItem) and not item.is_derived:
                if QLineF(point, item.center()).length() <= radius:
                    return None
        return point

    # -- Context menu / labeling ------------------------------------------

    def contextMenuEvent(self, event):
        # Route to the topmost label / point / line under the cursor; a blank
        # spot (or a derived point) shows the scene-level menu.
        target = None
        for item in self.items(event.scenePos()):
            if isinstance(item, (LabelItem, PointItem, LineItem)):
                target = item  # includes derived points (display properties)
                break

        if target is not None:
            target.contextMenuEvent(event)
            return

        menu = QMenu()
        auto_action = menu.addAction("Auto-label Scene")
        clear_action = menu.addAction("Clear All Labels")
        chosen = menu.exec(event.screenPos())
        if chosen is auto_action:
            self.auto_label()
        elif chosen is clear_action:
            self.clear_labels()
        event.accept()

    def auto_label(self) -> None:
        """Label points A, B, C… (upright) and lines a, b, c… (italic)."""
        points = sorted(
            (
                it
                for it in self.items()
                if isinstance(it, PointItem) and not it.is_derived
            ),
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

    def clear_labels(self) -> None:
        for item in self.items():
            if isinstance(item, (PointItem, LineItem)):
                item.set_label("")

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
            and not getattr(it, "is_derived", False)
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
            self._remove_geometry(item)
        self.recompute_intersections()

    def _remove_geometry(self, item) -> None:
        if isinstance(item, GroupItem):
            # Detach references to the group's child points, then remove the
            # group (which removes its children too).
            for child in item.childItems():
                self._detach_point_references(child)
            self.removeItem(item)
            return
        if isinstance(item, PointItem) and not item.is_derived:
            self._detach_point_references(item)
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
        self._intersections.clear()
        self._snap_indicator = None
