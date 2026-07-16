"""A point derived from the intersection of two lines."""

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem

from prism.items.point_item import PointItem


class IntersectionPointItem(PointItem):
    """A computed point where two lines cross.

    Visually indistinguishable from a placed point (it inherits the same
    default styling), selectable and labelable like one, and it shares the same
    context menu. The only difference is that its position is *computed*: the
    scene positions it directly, so it is not movable, not deletable, and not a
    snap/binding target. It persists across recomputes as its lines move, so a
    selection or label sticks with it.
    """

    is_derived = True

    def __init__(self, center: QPointF):
        super().__init__(center)

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
        self.unsetCursor()  # not draggable, so no open-hand cursor
        self.setZValue(9)  # just below user points
