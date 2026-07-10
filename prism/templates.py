"""Geometry templates: serialize, instantiate, thumbnail, and built-ins.

A *template* is a plain dict (JSON-serializable) describing a small collection
of points and lines in a local coordinate system centered on the origin:

    {
      "name": "Triangle",
      "points": [ {"xy": [x, y], "label": ""}, ... ],
      "lines":  [ {"a": <end>, "b": <end>, "label": ""}, ... ],
    }

where each line ``<end>`` is either ``{"pt": i}`` (bound to points[i]) or
``{"xy": [x, y]}`` (a free endpoint). Templates back both the built-in catalog
and user-saved selections, and are what gets dragged onto the canvas.
"""

import json
import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem

from prism.items import LineItem, PointItem

#: MIME type used to carry a template during drag-and-drop.
TEMPLATE_MIME = "application/x-prism-template"


# -- Serialize (canvas selection -> template) -----------------------------

def serialize_selection(items, name: str) -> dict:
    """Build a template from selected scene items (points + lines)."""
    points = [it for it in items if isinstance(it, PointItem) and not it.is_derived]
    lines = [it for it in items if isinstance(it, LineItem)]
    index = {id(p): i for i, p in enumerate(points)}

    coords = [p.center() for p in points]
    for line in lines:
        seg = line.scene_line()
        if id(line.bound_point(1)) not in index:
            coords.append(seg.p1())
        if id(line.bound_point(2)) not in index:
            coords.append(seg.p2())

    ox, oy = _center(coords)

    tpoints = [
        {"xy": [p.center().x() - ox, p.center().y() - oy], "label": p.label_text()}
        for p in points
    ]

    tlines = []
    for line in lines:
        seg = line.scene_line()

        def endpoint(end, scene_pt):
            bound = line.bound_point(end)
            if bound is not None and id(bound) in index:
                return {"pt": index[id(bound)]}
            return {"xy": [scene_pt.x() - ox, scene_pt.y() - oy]}

        tlines.append(
            {
                "a": endpoint(1, seg.p1()),
                "b": endpoint(2, seg.p2()),
                "label": line.label_text(),
            }
        )

    return {"name": name, "points": tpoints, "lines": tlines}


def _center(coords):
    """Bounding-box center of a list of QPointF (origin if empty)."""
    if not coords:
        return 0.0, 0.0
    xs = [c.x() for c in coords]
    ys = [c.y() for c in coords]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


# -- Instantiate (template -> scene items) --------------------------------

def instantiate(scene, template: dict, at: QPointF):
    """Create the template's geometry on ``scene``, centered at ``at``.

    Returns the newly created items (which are left selected).
    """
    # Offset so the template's bounding-box center lands exactly on ``at``.
    cx, cy = _template_center(template)
    base = QPointF(at.x() - cx, at.y() - cy)

    created_points = []
    for entry in template["points"]:
        x, y = entry["xy"]
        point = scene.add_point(QPointF(base.x() + x, base.y() + y))
        if entry.get("label"):
            point.set_label(entry["label"])
        created_points.append(point)

    created = list(created_points)

    for entry in template["lines"]:
        start, start_pt = _resolve_end(entry["a"], created_points, base)
        end, end_pt = _resolve_end(entry["b"], created_points, base)
        line = scene.add_line(start, end)
        if start_pt is not None:
            line.bind_endpoint(1, start_pt)
        if end_pt is not None:
            line.bind_endpoint(2, end_pt)
        if entry.get("label"):
            line.set_label(entry["label"])
        scene.on_line_changed(line)
        created.append(line)

    scene.clearSelection()
    for item in created:
        if item.flags() & QGraphicsItem.ItemIsSelectable:
            item.setSelected(True)
    return created


def _resolve_end(end: dict, created_points, base: QPointF):
    """Return (scene point, bound PointItem or None) for a line endpoint."""
    if "pt" in end:
        point = created_points[end["pt"]]
        return point.center(), point
    x, y = end["xy"]
    return QPointF(base.x() + x, base.y() + y), None


def _template_center(template: dict):
    """Bounding-box center of all template coordinates."""
    pts = [QPointF(*d["xy"]) for d in template["points"]]
    for line in template["lines"]:
        for end in (line["a"], line["b"]):
            if "xy" in end:
                pts.append(QPointF(*end["xy"]))
    return _center(pts)


# -- Thumbnail ------------------------------------------------------------

def render_thumbnail(template: dict, size: int = 72) -> QPixmap:
    """Render a template's geometry into a small transparent pixmap."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    points = [QPointF(*d["xy"]) for d in template["points"]]

    def end_point(end):
        return points[end["pt"]] if "pt" in end else QPointF(*end["xy"])

    all_pts = list(points)
    for line in template["lines"]:
        all_pts.append(end_point(line["a"]))
        all_pts.append(end_point(line["b"]))
    if not all_pts:
        return pixmap

    xs = [p.x() for p in all_pts]
    ys = [p.y() for p in all_pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w = (maxx - minx) or 1.0
    h = (maxy - miny) or 1.0
    pad = 10.0
    scale = min((size - 2 * pad) / w, (size - 2 * pad) / h)
    off_x = (size - w * scale) / 2
    off_y = (size - h * scale) / 2

    def tx(p):
        return QPointF((p.x() - minx) * scale + off_x, (p.y() - miny) * scale + off_y)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#333333"), 1.5))
    for line in template["lines"]:
        painter.drawLine(tx(end_point(line["a"])), tx(end_point(line["b"])))
    painter.setPen(QPen(QColor("#0d3d61"), 1))
    painter.setBrush(QColor("#1f77b4"))
    for p in points:
        painter.drawEllipse(tx(p), 2.5, 2.5)
    painter.end()
    return pixmap


# -- Built-in catalog -----------------------------------------------------

def _pt(x, y):
    return {"xy": [x, y], "label": ""}


def _seg(a, b):
    return {"a": {"pt": a}, "b": {"pt": b}, "label": ""}


def _projectivity():
    """A pencil: four lines through a common point, splayed slightly apart."""
    half = 60.0
    lines = []
    for angle in (60, 80, 100, 120):  # fanned around vertical
        r = math.radians(angle)
        dx = round(half * math.cos(r), 2)
        dy = round(half * math.sin(r), 2)
        lines.append(
            {"a": {"xy": [-dx, -dy]}, "b": {"xy": [dx, dy]}, "label": ""}
        )
    return {
        "name": "Projectivity",
        # The center point sits at the crossing so the six concurrent
        # intersections aren't drawn as stacked markers.
        "points": [_pt(0, 0)],
        "lines": lines,
    }


def _builtins():
    segment = {
        "name": "Segment",
        "points": [_pt(-45, 0), _pt(45, 0)],
        "lines": [_seg(0, 1)],
    }
    triangle = {
        "name": "Triangle",
        "points": [_pt(0, -46), _pt(-40, 23), _pt(40, 23)],
        "lines": [_seg(0, 1), _seg(1, 2), _seg(2, 0)],
    }
    square = {
        "name": "Quadrilateral",
        "points": [_pt(-40, -40), _pt(40, -40), _pt(40, 40), _pt(-40, 40)],
        "lines": [_seg(0, 1), _seg(1, 2), _seg(2, 3), _seg(3, 0)],
    }
    complete_quadrangle = {
        "name": "Complete Quadrangle",
        "points": [_pt(-40, -40), _pt(40, -40), _pt(40, 40), _pt(-40, 40)],
        "lines": [
            _seg(0, 1), _seg(0, 2), _seg(0, 3),
            _seg(1, 2), _seg(1, 3), _seg(2, 3),
        ],
    }
    return [segment, triangle, square, complete_quadrangle, _projectivity()]


BUILTIN_TEMPLATES = _builtins()


def serialize(template: dict) -> bytes:
    return json.dumps(template).encode("utf-8")


def deserialize(data: bytes) -> dict:
    return json.loads(bytes(data).decode("utf-8"))
