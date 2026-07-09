"""Text labels for canvas items, added via a right-click context menu."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSimpleTextItem,
    QInputDialog,
    QMenu,
)


class LabelItem(QGraphicsSimpleTextItem):
    """A constant-size text label anchored to (and offset from) its parent.

    The item ignores view transformations, so it stays the same on-screen size
    at any zoom, and it paints at a small pixel offset up-and-right of its
    anchor so it doesn't sit directly on the point or line.
    """

    OFFSET = QPointF(8, -8)  # pixels, relative to the anchor

    def __init__(self, text: str, parent: QGraphicsItem):
        super().__init__(text, parent)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setBrush(QColor("#222222"))
        self.setAcceptedMouseButtons(Qt.NoButton)  # clicks pass to the parent
        self.setZValue(20)

        font = self.font()
        font.setPointSizeF(11)
        self.setFont(font)

    def boundingRect(self) -> QRectF:
        return super().boundingRect().translated(self.OFFSET)

    def paint(self, painter, option, widget=None):
        painter.translate(self.OFFSET)
        super().paint(painter, option, widget)


class Labelable:
    """Mixin giving a QGraphicsItem a text label and a labeling context menu.

    Mixed in *before* the Qt item base, e.g. ``class PointItem(Labelable,
    QGraphicsEllipseItem)``. Items should initialise ``self._label = None`` in
    their own ``__init__`` and may override :meth:`_label_anchor`.
    """

    _label: LabelItem | None = None

    # -- Public API --------------------------------------------------------

    def label_text(self) -> str:
        return self._label.text() if self._label is not None else ""

    def set_label(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            self._remove_label()
            return
        if self._label is None:
            self._label = LabelItem(text, self)
        else:
            self._label.setText(text)
        self._reposition_label()

    # -- Positioning -------------------------------------------------------

    def _label_anchor(self) -> QPointF:
        """Anchor position in item-local coordinates (overridable)."""
        return QPointF(0, 0)

    def _reposition_label(self) -> None:
        if self._label is not None:
            self._label.setPos(self._label_anchor())

    def _remove_label(self) -> None:
        if self._label is not None:
            self._label.setParentItem(None)
            scene = self.scene()
            if scene is not None:
                scene.removeItem(self._label)
            self._label = None

    # -- Context menu ------------------------------------------------------

    def contextMenuEvent(self, event):
        menu = QMenu()
        has_label = self._label is not None
        edit_action = menu.addAction("Edit Label…" if has_label else "Add Label…")
        remove_action = menu.addAction("Remove Label") if has_label else None

        chosen = menu.exec(event.screenPos())
        if chosen is None:
            return
        if chosen is edit_action:
            self._prompt_label()
        elif remove_action is not None and chosen is remove_action:
            self.set_label("")
        event.accept()

    def _prompt_label(self) -> None:
        scene = self.scene()
        parent = scene.views()[0] if (scene and scene.views()) else None
        current = self.label_text()
        text, ok = QInputDialog.getText(
            parent, "Label", "Enter label text:", text=current
        )
        if ok:
            self.set_label(text)
