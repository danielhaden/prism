"""A drawable line (segment) on the canvas."""

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainterPath,
    QPainterPathStroker,
    QPen,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem, QMenu

from prism.items.label import Labelable


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


class LineItem(Labelable, QGraphicsLineItem):
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

    #: Width (scene units) of the invisible band around the line that still
    #: counts as a "hit", so the thin line is easy to click and drag.
    HIT_WIDTH = 12.0

    #: On-screen pixel radius for grabbing an endpoint / drawing its handle.
    ENDPOINT_GRAB_PX = 10.0
    HANDLE_PX = 5.0

    def __init__(self, start: QPointF, end: QPointF):
        super().__init__(QLineF(start, end))

        pen = QPen(QColor("#333333"), 2)
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

        # Visible range: the line is infinite by default; when an anchor point
        # and extents are set, only a segment of it is drawn.
        self._range_anchor = None
        self._range_neg = 0.0
        self._range_pos = 0.0

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
        menu = QMenu()
        line_props_action = menu.addAction("Line Properties…")
        proj_action = menu.addAction("Add Projectivity…")
        range_action = menu.addAction("Define Visible Range…")
        show_full_action = (
            menu.addAction("Show Full Line") if self.has_visible_range() else None
        )

        # Anchor a point to this line when the selection is one line + point(s).
        scene = self.scene()
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
        if chosen is line_props_action:
            self.open_line_style_dialog()
        elif snap_action is not None and chosen is snap_action:
            scene.anchor_points_to_line(sel_points, sel_line)
        elif chosen is proj_action:
            self._add_projectivity_at(event.pos())
        elif chosen is range_action:
            self.open_visible_range_dialog()
        elif show_full_action is not None and chosen is show_full_action:
            self._show_full_line()
        elif chosen is not None:
            self.handle_label_action(chosen, label_actions)
        event.accept()

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

    def _show_full_line(self) -> None:
        anchor = self._range_anchor
        self.clear_visible_range()
        scene = self.scene()
        if scene is not None:
            if anchor is not None:
                scene._remove_geometry(anchor)
            scene.recompute_intersections()
            scene.commit_undo()

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
        self._range_anchor = anchor
        self._range_neg = abs(neg)
        self._range_pos = abs(pos)
        self.prepareGeometryChange()
        self._reposition_label()
        self.update()

    def clear_visible_range(self) -> None:
        """Revert to a full (infinite) line."""
        self._range_anchor = None
        self.prepareGeometryChange()
        self._reposition_label()
        self.update()

    def has_visible_range(self) -> bool:
        return self._range_anchor is not None

    def range_anchor(self):
        return self._range_anchor

    def _direction(self) -> QPointF | None:
        """Unit direction of the line (local coords), or None if degenerate."""
        line = self.line()
        dx, dy = line.x2() - line.x1(), line.y2() - line.y1()
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1e-9:
            return None
        return QPointF(dx / length, dy / length)

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
        """The drawn segment in scene coordinates (for intersections)."""
        seg = self._display_segment()
        if seg is None:
            return self.scene_line()
        return QLineF(self.mapToScene(seg[0]), self.mapToScene(seg[1]))

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
        stroker.setWidth(self.HIT_WIDTH)
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
            max(self.HIT_WIDTH / 2, self._px(self.ENDPOINT_GRAB_PX))
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

        if self.isSelected() or self._hover_end is not None:
            self._paint_handles(painter)

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
