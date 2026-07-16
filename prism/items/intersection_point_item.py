"""A point derived from the intersection of two lines."""

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem, QMenu

from prism.items.point_item import PointItem


class IntersectionPointItem(PointItem):
    """A computed point where two lines cross.

    Derived points can be *selected* like any other point, but their position
    is computed: the scene positions them directly, so they are not movable,
    not deletable, and not valid snap/binding targets. (They persist across
    recomputes as their lines move, so a selection sticks with them.)
    """

    RADIUS = 4.0
    DEFAULT_COLOR = "#2ca02c"
    DEFAULT_GLOW_RADIUS = 0.0  # derived markers stay glow-free and distinct
    is_derived = True

    def __init__(self, center: QPointF):
        super().__init__(center)

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
        self.unsetCursor()  # not draggable, so no open-hand cursor
        self.setZValue(9)  # just below user points

    def contextMenuEvent(self, event):
        # Derived points have no labels or pins - only display properties.
        menu = QMenu()
        display_action = menu.addAction("Modify Display Properties…")
        chosen = menu.exec(event.screenPos())
        if chosen is display_action:
            self.open_display_dialog()
        event.accept()
