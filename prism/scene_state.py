"""Capture and restore the full state of a canvas scene.

Used by undo/redo: rather than modelling every mutation as its own reversible
command, the scene is snapshotted after each action and rebuilt on undo. The
format is plain data (JSON-able), so it can also back save/load later.

Derived geometry (intersection markers) is not stored - it is recomputed. A
*label* put on one, or a decision to hide it, is the user's work rather than
derived, so that much is kept, keyed by the pair of lines whose crossing it
marks.
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPen

from prism.items import GroupItem, LineItem, PointItem


# -- Labels ---------------------------------------------------------------

def _capture_label(item) -> dict | None:
    label = item.label_item()
    if label is None:
        return None
    font = label.font()
    return {
        "text": label.text(),
        "font": {
            "family": font.family(),
            "size": font.pointSize(),
            "bold": font.bold(),
            "italic": font.italic(),
            "underline": font.underline(),
        },
        "color": label.brush().color().name(),
        "pos": [label.pos().x(), label.pos().y()],
    }


def _restore_label(item, data: dict | None) -> None:
    if not data:
        return
    item.set_label(data["text"])
    label = item.label_item()
    if label is None:
        return
    spec = data["font"]
    font = QFont(spec["family"])
    if spec["size"] > 0:
        font.setPointSize(spec["size"])
    font.setBold(spec["bold"])
    font.setItalic(spec["italic"])
    font.setUnderline(spec["underline"])
    label.apply_style(font, QColor(data["color"]))
    label.setPos(QPointF(*data["pos"]))


def _capture_point_style(style: dict | None) -> dict | None:
    if not style:
        return None
    return {
        "radius": style["radius"],
        "color": QColor(style["color"]).name(),
        "glow_radius": style["glow_radius"],
        "glow_color": QColor(style["glow_color"]).name(),
    }


def _restore_point_style(data: dict | None) -> dict | None:
    if not data:
        return None
    return {
        "radius": data["radius"],
        "color": QColor(data["color"]),
        "glow_radius": data["glow_radius"],
        "glow_color": QColor(data["glow_color"]),
    }


# -- Capture --------------------------------------------------------------

def capture(scene) -> dict:
    """Snapshot every user-authored element and relationship in ``scene``."""
    # Intersection points are recomputed, not stored.
    points = sorted(
        (
            it
            for it in scene.items()
            if isinstance(it, PointItem) and not it.is_meet()
        ),
        key=lambda it: getattr(it, "_seq", 0),
    )
    lines = sorted(scene._lines(), key=lambda it: getattr(it, "_seq", 0))
    p_index = {id(p): i for i, p in enumerate(points)}
    l_index = {id(ln): i for i, ln in enumerate(lines)}

    def point_ref(point):
        """How to name a point in the snapshot.

        A placed point is an index into the stored points. A **meet** has no
        index — meets are recomputed, not stored — so it is named by the lines
        that make it, and found again once the recompute has run.
        """
        if point is None:
            return None
        if id(point) in p_index:
            return p_index[id(point)]
        if point.is_meet():
            indices = [l_index.get(id(line)) for line in point.meeting_lines()]
            indices = [index for index in indices if index is not None]
            if len(indices) >= 2:
                return {"meet": sorted(indices)}
        return None

    point_data = []
    for point in points:
        style = point.display_style()
        anchor = None
        pt_anchor = point.anchor()
        if (
            pt_anchor is not None
            and pt_anchor.kind == "line"
            and id(pt_anchor.line) in l_index
        ):
            anchor = {"line": l_index[id(pt_anchor.line)], "t": pt_anchor.t}
        point_data.append(
            {
                "xy": [point.center().x(), point.center().y()],
                "radius": style["radius"],
                "color": style["color"].name(),
                "glow_radius": style["glow_radius"],
                "glow_color": style["glow_color"].name(),
                "label": _capture_label(point),
                "anchor": anchor,
                "shown": point.is_shown(),
            }
        )

    line_data = []
    for line in lines:
        seg = line.scene_line()
        pen = line.pen()
        visible_range = None
        if line.has_visible_range():
            anchor = line.range_anchor()
            if anchor is not None and point_ref(anchor) is not None:
                visible_range = {
                    "anchor": point_ref(anchor),
                    "neg": line._range_neg,
                    "pos": line._range_pos,
                }
        pivot = line.pivot()
        line_data.append(
            {
                "p1": [seg.x1(), seg.y1()],
                "p2": [seg.x2(), seg.y2()],
                "pen": {
                    "color": pen.color().name(),
                    "width": pen.widthF(),
                    "style": pen.style().value,
                },
                "bind": [
                    point_ref(line.bound_point(1)),
                    point_ref(line.bound_point(2)),
                ],
                "pivot": point_ref(pivot),
                "range": visible_range,
                "locked": line.is_orientation_locked(),
                "label": _capture_label(line),
            }
        )

    # Intersection markers are rebuilt by the recompute, so only their labels
    # need keeping — against the lines that produce them, since the markers
    # themselves won't be the same objects afterwards.
    crossing_labels = []
    for marker in getattr(scene, "_meets", []):
        anchor = marker.anchor()
        if anchor is None or anchor.kind != "meet":
            continue
        label = _capture_label(marker)
        shown = marker.is_shown()
        if label is None and shown:
            continue  # nothing about this one worth keeping
        indices = [l_index.get(id(line)) for line in anchor.lines]
        if any(index is None for index in indices) or len(indices) < 2:
            continue
        crossing_labels.append(
            {"lines": sorted(indices), "label": label, "shown": shown}
        )

    groups = []
    for group in (it for it in scene.items() if isinstance(it, GroupItem)):
        members = []
        for child in group.childItems():
            if id(child) in p_index:
                members.append(["p", p_index[id(child)]])
            elif id(child) in l_index:
                members.append(["l", l_index[id(child)]])
        if members:
            groups.append(members)

    return {
        "points": point_data,
        "lines": line_data,
        "groups": groups,
        "crossings": crossing_labels,
        "point_style": _capture_point_style(getattr(scene, "_point_style", None)),
    }


# -- Restore --------------------------------------------------------------

def restore(scene, state: dict) -> None:
    """Rebuild ``scene`` to match a snapshot from :func:`capture`."""
    scene.clear_all()
    scene._point_style = None  # don't let stale defaults tint rebuilt items

    points = []
    for data in state["points"]:
        point = scene.add_point(QPointF(*data["xy"]))
        point.set_display(
            radius=data["radius"],
            color=QColor(data["color"]),
            glow_radius=data["glow_radius"],
            glow_color=QColor(data["glow_color"]),
        )
        _restore_label(point, data["label"])
        point.set_shown(data.get("shown", True))
        points.append(point)

    lines = []
    for data in state["lines"]:
        line = scene.add_line(QPointF(*data["p1"]), QPointF(*data["p2"]))
        spec = data["pen"]
        pen = QPen(QColor(spec["color"]), spec["width"])
        pen.setStyle(Qt.PenStyle(spec["style"]))
        pen.setCosmetic(True)
        line.setPen(pen)
        line.set_orientation_locked(data.get("locked", False))
        _restore_label(line, data["label"])
        lines.append(line)

    # Wire relationships once both sides exist.
    _wire_lines(lines, points, state["lines"], meets_ready=False)

    from prism.anchors import LineAnchor

    for point, data in zip(points, state["points"]):
        if data["anchor"] is not None:
            line = lines[data["anchor"]["line"]]
            point.set_anchor(LineAnchor(line, data["anchor"]["t"]))

    for members in state.get("groups", []):
        group = GroupItem()
        scene.addItem(group)
        for kind, index in members:
            group.addToGroup(points[index] if kind == "p" else lines[index])

    scene._point_style = _restore_point_style(state.get("point_style"))
    scene.recompute_intersections()
    _restore_crossing_labels(scene, lines, state.get("crossings", []))
    # Meets exist only now, so relationships naming one are wired here. Doing
    # it earlier is why a pivot onto a crossing used to be dropped silently.
    _wire_lines(lines, points, state["lines"], meets_ready=True, scene=scene)
    # Undefined-ness is derived, never stored, so work it out afresh.
    scene.settle_definitions()


def _restore_crossing_labels(scene, lines, entries) -> None:
    """Put labels back on the intersection markers the recompute just made.

    Args:
        scene: The scene being rebuilt.
        lines: The restored lines, in snapshot order.
        entries: ``{"lines": [i, j], "label": …}`` records from the snapshot.
    """
    if not entries:
        return
    markers = []
    for marker in getattr(scene, "_meets", []):
        anchor = marker.anchor()
        if anchor is not None and anchor.kind == "meet":
            markers.append((frozenset(id(ln) for ln in anchor.lines), marker))
    for entry in entries:
        wanted = entry["lines"]
        if any(index >= len(lines) for index in wanted):
            continue
        ids = frozenset(id(lines[index]) for index in wanted)
        # Match on the lines they have in common: a meet is the same meet while
        # two of its lines are, even if others have joined or left since.
        marker = next(
            (m for key, m in markers if len(key & ids) >= 2), None
        )
        if marker is not None:
            _restore_label(marker, entry["label"])
            marker.set_shown(entry.get("shown", True))


def _resolve_point(ref, points, scene=None):
    """Turn a stored point reference back into a point.

    Args:
        ref: An index into the stored points, or ``{"meet": [line indices]}``.
        points: The restored points, in snapshot order.
        scene: Needed to find a meet; omit while meets don't exist yet.

    Returns:
        The point, or None if it can't be resolved yet.
    """
    if ref is None:
        return None
    if isinstance(ref, int):
        return points[ref] if ref < len(points) else None
    if scene is None:
        return None
    wanted = set(ref.get("meet", []))
    for meet in getattr(scene, "_meets", []):
        anchor = meet.anchor()
        if anchor is None or anchor.kind != "meet":
            continue
        held = {
            index
            for index, line in enumerate(scene.ordered_lines())
            if anchor.references_line(line)
        }
        if len(held & wanted) >= 2:
            return meet
    return None


def _wire_lines(lines, points, line_data, meets_ready: bool, scene=None) -> None:
    """Re-make each line's relationships to points.

    Called twice: once for placed points, and again once the recompute has
    built the meets, for the relationships that name one.

    Args:
        lines: The restored lines.
        points: The restored points.
        line_data: Their snapshot entries.
        meets_ready: Whether to wire the references that name a meet.
        scene: The scene, required when ``meets_ready``.
    """

    def wanted(ref) -> bool:
        is_meet_ref = isinstance(ref, dict)
        return ref is not None and is_meet_ref == meets_ready

    for line, data in zip(lines, line_data):
        for end, ref in zip((1, 2), data["bind"]):
            if wanted(ref):
                point = _resolve_point(ref, points, scene)
                if point is not None:
                    line.bind_endpoint(end, point)
        if wanted(data["pivot"]):
            point = _resolve_point(data["pivot"], points, scene)
            if point is not None:
                line.set_pivot(point)
        if data["range"] is not None and wanted(data["range"]["anchor"]):
            point = _resolve_point(data["range"]["anchor"], points, scene)
            if point is not None:
                line.set_visible_range(
                    point, data["range"]["neg"], data["range"]["pos"]
                )
