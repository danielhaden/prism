"""Text labels for canvas items, added via a right-click context menu.

Labels are child items of the element they annotate, so they move with it.
They keep a constant on-screen size (ignore zoom), are draggable to reposition
(via Qt's built-in item movement), and expose display properties (font, size,
color, bold, italic, underline) through their own context menu.
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSimpleTextItem,
    QInputDialog,
    QMenu,
)


class LabelItem(QGraphicsSimpleTextItem):
    """A constant-size, draggable text label, child of the item it labels.

    Position (relative to the parent) carries the label's offset; dragging the
    label moves it, and because it is a child it follows the parent when the
    parent moves.
    """

    DEFAULT_OFFSET = QPointF(8, -8)  # pixels from the anchor

    def __init__(self, text: str, parent: QGraphicsItem):
        super().__init__(text, parent)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setBrush(QColor("#222222"))
        self.setCursor(Qt.OpenHandCursor)
        self.setZValue(20)

        font = self.font()
        font.setPointSize(11)
        self.setFont(font)

    def apply_style(self, font, color) -> None:
        self.setFont(font)
        self.setBrush(color)
        self.update()

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
        elif chosen is reset_action and owner is not None:
            owner.reset_label_position()
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
    _last_anchor: QPointF | None = None

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
            self._last_anchor = None  # fresh placement uses the default offset
        else:
            self._label.setText(text)
        self._reposition_label()

    # -- Positioning -------------------------------------------------------

    def _label_anchor(self) -> QPointF:
        """Anchor position in item-local coordinates (overridable)."""
        return QPointF(0, 0)

    def _reposition_label(self) -> None:
        """Keep the label following its anchor while preserving its offset."""
        if self._label is None:
            return
        anchor = self._label_anchor()
        if self._last_anchor is None:
            self._label.setPos(anchor + LabelItem.DEFAULT_OFFSET)
        else:
            delta = anchor - self._last_anchor
            if not delta.isNull():
                self._label.moveBy(delta.x(), delta.y())
        self._last_anchor = anchor

    def reset_label_position(self) -> None:
        if self._label is None:
            return
        self._last_anchor = self._label_anchor()
        self._label.setPos(self._last_anchor + LabelItem.DEFAULT_OFFSET)

    def _remove_label(self) -> None:
        if self._label is not None:
            self._label.setParentItem(None)
            scene = self.scene()
            if scene is not None:
                scene.removeItem(self._label)
            self._label = None
            self._last_anchor = None

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
