"""Text labels for canvas items, added via a right-click context menu.

Labels are draggable (to nudge them off the geometry), keep a constant
on-screen size, and expose display properties (font, size, color, bold,
italic, underline) through their own context menu.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSimpleTextItem,
    QInputDialog,
    QMenu,
)


class LabelItem(QGraphicsSimpleTextItem):
    """A constant-size, draggable text label anchored to its parent item.

    The item ignores view transformations, so it stays the same on-screen size
    at any zoom. It paints at ``_offset`` pixels from its anchor; dragging the
    label changes that offset.
    """

    DEFAULT_OFFSET = QPointF(8, -8)  # pixels, relative to the anchor

    def __init__(self, text: str, parent: QGraphicsItem):
        super().__init__(text, parent)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setBrush(QColor("#222222"))
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.OpenHandCursor)
        self.setZValue(20)

        font = self.font()
        font.setPointSize(11)
        self.setFont(font)

        self._offset = QPointF(self.DEFAULT_OFFSET)
        self._drag_last = None

    # -- Geometry / painting ----------------------------------------------

    def boundingRect(self) -> QRectF:
        return super().boundingRect().translated(self._offset)

    def paint(self, painter, option, widget=None):
        painter.translate(self._offset)
        super().paint(painter, option, widget)

    def apply_style(self, font, color) -> None:
        self.prepareGeometryChange()
        self.setFont(font)
        self.setBrush(color)
        self.update()

    def reset_offset(self) -> None:
        self.prepareGeometryChange()
        self._offset = QPointF(self.DEFAULT_OFFSET)
        self.update()

    # -- Dragging (updates the pixel offset, not the anchor) --------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_last = event.screenPos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_last is not None:
            cur = event.screenPos()
            delta = cur - self._drag_last
            self._drag_last = cur
            self.prepareGeometryChange()
            self._offset += QPointF(delta.x(), delta.y())
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_last is not None:
            self._drag_last = None
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -- Context menu ------------------------------------------------------

    def contextMenuEvent(self, event):
        owner = self.parentItem()
        menu = QMenu()
        props_action = menu.addAction("Label Properties…")
        reset_action = menu.addAction("Reset Position")
        menu.addSeparator()
        remove_action = menu.addAction("Remove Label")

        chosen = menu.exec(event.screenPos())
        if chosen is props_action and owner is not None:
            owner.open_label_style_dialog()
        elif chosen is reset_action:
            self.reset_offset()
        elif chosen is remove_action and owner is not None:
            owner.set_label("")
        event.accept()


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

    def label_item(self) -> LabelItem | None:
        return self._label

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
        props_action = menu.addAction("Label Properties…") if has_label else None
        remove_action = menu.addAction("Remove Label") if has_label else None

        chosen = menu.exec(event.screenPos())
        if chosen is None:
            return
        if chosen is edit_action:
            self._prompt_label()
        elif props_action is not None and chosen is props_action:
            self.open_label_style_dialog()
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

    def open_label_style_dialog(self) -> None:
        if self._label is None:
            return
        from prism.label_dialog import LabelStyleDialog

        scene = self.scene()
        parent = scene.views()[0] if (scene and scene.views()) else None
        font, color = LabelStyleDialog.get_style(
            self._label.font(), self._label.brush().color(), parent
        )
        if font is not None:
            self._label.apply_style(font, color)
