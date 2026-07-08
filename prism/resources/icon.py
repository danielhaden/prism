"""The Prism application icon: two overlapping equilateral triangles."""

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

# Fill colors for the two triangles.
_ORANGE = QColor("#F5921B")
_LIGHT_BLUE = QColor("#7EB6E0")
_BACKGROUND = QColor("#FFFFFF")

# Slight transparency so the overlapping region reads as a blend of both.
_FILL_ALPHA = 210

# Icon sizes macOS asks for (menu bar / Dock / window).
_SIZES = (16, 32, 64, 128, 256, 512)


def _triangle(cx: float, apex_y: float, side: float) -> list[QPointF]:
    """Return the three vertices of an upward equilateral triangle.

    ``cx`` is the horizontal center, ``apex_y`` the y of the top vertex, and
    ``side`` the edge length.
    """
    height = side * math.sqrt(3) / 2
    return [
        QPointF(cx, apex_y),                      # apex
        QPointF(cx - side / 2, apex_y + height),  # bottom-left
        QPointF(cx + side / 2, apex_y + height),  # bottom-right
    ]


def _render_triangles_pixmap(size: int) -> QPixmap:
    """Draw two overlapping equilateral triangles on a white square."""
    pixmap = QPixmap(size, size)
    pixmap.fill(_BACKGROUND)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)

    # Geometry as fractions of the icon size so it scales crisply.
    side = size * 0.52
    height = side * math.sqrt(3) / 2
    offset = size * 0.14  # vertical shift between the two triangles
    cx = size / 2

    top_margin = (size - (offset + height)) / 2

    orange = QColor(_ORANGE)
    orange.setAlpha(_FILL_ALPHA)
    blue = QColor(_LIGHT_BLUE)
    blue.setAlpha(_FILL_ALPHA)

    # Orange sits slightly higher; blue is offset down and overlaps it.
    painter.setBrush(orange)
    painter.drawPolygon(_triangle(cx, top_margin, side))

    painter.setBrush(blue)
    painter.drawPolygon(_triangle(cx, top_margin + offset, side))

    painter.end()
    return pixmap


def make_app_icon() -> QIcon:
    """Build a multi-resolution QIcon of the two overlapping triangles."""
    icon = QIcon()
    for size in _SIZES:
        icon.addPixmap(_render_triangles_pixmap(size))
    return icon
