"""A point derived from the intersection of two lines."""

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem, QMenu

from prism.items.point_item import PointItem


class IntersectionPointItem(PointItem):
    """A computed point where two lines cross.

    Derived points are managed entirely by the scene: they are not movable,
    selectable, or valid snap targets, and they don't emit move notifications
    (the scene positions them directly). Their display properties can still be
    edited via the right-click menu.
    """

    RADIUS = 4.0
    DEFAULT_COLOR = "#2ca02c"
    DEFAULT_GLOW_RADIUS = 0.0  # derived markers stay glow-free and distinct
    is_derived = True

    def __init__(self, center: QPointF):
        super().__init__(center)

        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
        self.unsetCursor()
        self.setZValue(9)  # just below user points

    def contextMenuEvent(self, event):
        # Derived points have no labels or pins - only display properties.
        menu = QMenu()
        display_action = menu.addAction("Modify Display Properties…")
        chosen = menu.exec(event.screenPos())
        if chosen is display_action:
            self.open_display_dialog()
        event.accept()
