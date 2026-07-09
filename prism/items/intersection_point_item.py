"""A point derived from the intersection of two lines."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsItem

from prism.items.point_item import PointItem


class IntersectionPointItem(PointItem):
    """A computed point where two lines cross.

    Derived points are managed entirely by the scene: they are not movable,
    selectable, or valid snap targets, and they don't emit move notifications
    (the scene positions them directly).
    """

    RADIUS = 4.0
    is_derived = True

    def __init__(self, center: QPointF):
        super().__init__(center)

        self.setBrush(QBrush(QColor("#2ca02c")))
        self.setPen(QPen(QColor("#155715"), 1.2))

        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
        self.unsetCursor()
        self.setZValue(9)  # just below user points
