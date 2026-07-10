"""A group that moves, selects, and deletes as a single unit."""

from PySide6.QtWidgets import QGraphicsItem, QGraphicsItemGroup


class GroupItem(QGraphicsItemGroup):
    """A composite of points/lines (and nested groups) handled as one object.

    Qt moves the group's children together and routes events to the group, so
    it selects and drags as a unit. On move we ask the scene to refresh
    dependent geometry (intersections, pivot references).
    """

    def __init__(self):
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(1)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            scene = self.scene()
            if scene is not None and hasattr(scene, "on_group_moved"):
                scene.on_group_moved(self)
        return super().itemChange(change, value)
