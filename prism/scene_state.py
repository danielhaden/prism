"""Capture and restore the full state of a canvas scene.

Used by undo/redo: rather than modelling every mutation as its own reversible
command, the scene is snapshotted after each action and rebuilt on undo. The
format is plain data (JSON-able), so it can also back save/load later.

Derived geometry (intersection markers) is not stored - it is recomputed. A
*label* put on one is the user's work rather than derived, so that much is
kept, keyed by the pair of lines whose crossing it marks.
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
            if isinstance(it, PointItem) and not it.is_intersection()
        ),
        key=lambda it: getattr(it, "_seq", 0),
    )
    lines = sorted(scene._lines(), key=lambda it: getattr(it, "_seq", 0))
    p_index = {id(p): i for i, p in enumerate(points)}
    l_index = {id(ln): i for i, ln in enumerate(lines)}

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
            }
        )

    line_data = []
    for line in lines:
        seg = line.scene_line()
        pen = line.pen()
        visible_range = None
        if line.has_visible_range():
            anchor = line.range_anchor()
            if anchor is not None and id(anchor) in p_index:
                visible_range = {
                    "anchor": p_index[id(anchor)],
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
                    p_index.get(id(line.bound_point(1))) if line.bound_point(1) else None,
                    p_index.get(id(line.bound_point(2))) if line.bound_point(2) else None,
                ],
                "pivot": p_index.get(id(pivot)) if pivot is not None else None,
                "range": visible_range,
                "locked": line.is_orientation_locked(),
                "label": _capture_label(line),
            }
        )

    # Intersection markers are rebuilt by the recompute, so only their labels
    # need keeping — against the lines that produce them, since the markers
    # themselves won't be the same objects afterwards.
    crossing_labels = []
    for marker in getattr(scene, "_intersections", {}).values():
        anchor = marker.anchor()
        if anchor is None or anchor.kind != "intersection":
            continue
        label = _capture_label(marker)
        if label is None:
            continue
        first, second = l_index.get(id(anchor.a)), l_index.get(id(anchor.b))
        if first is None or second is None:
            continue
        crossing_labels.append(
            {"lines": sorted((first, second)), "label": label}
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
    for line, data in zip(lines, state["lines"]):
        bind1, bind2 = data["bind"]
        if bind1 is not None:
            line.bind_endpoint(1, points[bind1])
        if bind2 is not None:
            line.bind_endpoint(2, points[bind2])
        if data["pivot"] is not None:
            line.set_pivot(points[data["pivot"]])
        if data["range"] is not None:
            line.set_visible_range(
                points[data["range"]["anchor"]],
                data["range"]["neg"],
                data["range"]["pos"],
            )

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


def _restore_crossing_labels(scene, lines, entries) -> None:
    """Put labels back on the intersection markers the recompute just made.

    Args:
        scene: The scene being rebuilt.
        lines: The restored lines, in snapshot order.
        entries: ``{"lines": [i, j], "label": …}`` records from the snapshot.
    """
    if not entries:
        return
    markers = {}
    for marker in getattr(scene, "_intersections", {}).values():
        anchor = marker.anchor()
        if anchor is not None and anchor.kind == "intersection":
            markers[frozenset((id(anchor.a), id(anchor.b)))] = marker
    for entry in entries:
        first, second = entry["lines"]
        if first >= len(lines) or second >= len(lines):
            continue
        marker = markers.get(frozenset((id(lines[first]), id(lines[second]))))
        if marker is not None:
            _restore_label(marker, entry["label"])
