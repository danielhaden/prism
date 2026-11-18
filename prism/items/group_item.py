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

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        scene = self.scene()
        if scene is not None and hasattr(scene, "begin_item_drag"):
            scene.begin_item_drag(self)

    def mouseMoveEvent(self, event):
        # Prism moves the selection itself, rather than letting Qt walk a raw
        # pointer list across our itemChange; see CanvasScene.drag_items.
        scene = self.scene()
        if (
            scene is not None
            and hasattr(scene, "drag_items")
            and scene.drag_items(event)
        ):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if scene is not None and hasattr(scene, "end_item_drag"):
            scene.end_item_drag()
        if scene is not None and hasattr(scene, "commit_undo"):
            scene.commit_undo()  # a group drag finished
