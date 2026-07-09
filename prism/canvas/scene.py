"""The drawing scene: turns mouse interaction into geometry items.

Beyond raw drawing, the scene coordinates dependent geometry:
  * line endpoints snap onto (and bind to) existing points, and
  * a derived point is maintained wherever two lines cross.
When a point or line moves, the scene propagates the change so bound
endpoints follow and intersections recompute.
"""

from PySide6.QtCore import QLineF, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsScene,
)

from prism.items import IntersectionPointItem, LineItem, PointItem
from prism.tools import Tool


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
            self.add_point(pos)
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
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._cancel_line()
            self.hide_snap_indicator()
        super().keyPressEvent(event)

    # -- Drawing helpers ---------------------------------------------------

    def add_point(self, pos: QPointF) -> PointItem:
        point = PointItem(pos)
        self.addItem(point)
        return point

    def add_line(self, start: QPointF, end: QPointF) -> LineItem:
        line = LineItem(start, end)
        self.addItem(line)
        return line

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
        """A point moved: update bound line endpoints and intersections."""
        for item in self.items():
            if isinstance(item, LineItem) and item is not self._preview_line:
                item.sync_from_point(point)
        self.recompute_intersections()

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
        kind, point = a.scene_line().intersects(b.scene_line())
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

    # -- Editing -----------------------------------------------------------

    def delete_selected(self) -> None:
        for item in list(self.selectedItems()):
            self._remove_geometry(item)
        self.recompute_intersections()

    def _remove_geometry(self, item) -> None:
        if isinstance(item, PointItem) and not item.is_derived:
            # Free any line endpoints that were bound to this point.
            for line in self._lines():
                for end in (1, 2):
                    if line.bound_point(end) is item:
                        line.unbind_endpoint(end)
        self.removeItem(item)

    def clear_all(self) -> None:
        self._cancel_line()
        self.clear()
        self._intersections.clear()
        self._snap_indicator = None
