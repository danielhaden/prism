"""A dock that shows what's selected and where it is."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDockWidget, QPlainTextEdit

from prism.items import GroupItem, LineItem, PointItem


class SelectionPanel(QDockWidget):
    """Lists the selected elements with their names and positions.

    Updates when the selection changes and as selected elements move.
    """

    def __init__(self, scene, parent=None):
        super().__init__("Selection", parent)
        self.setObjectName("SelectionPanel")
        self._scene = scene

        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(mono)
        self.setWidget(self._text)

        scene.selectionChanged.connect(self._update)
        scene.changed.connect(self._on_scene_changed)
        self._update()

    def _on_scene_changed(self, _region=None) -> None:
        # Keep positions live while a selection is dragged; skip the work when
        # nothing is selected.
        try:
            if self._scene.selectedItems():
                self._update()
        except RuntimeError:
            pass  # scene torn down during shutdown

    def _update(self) -> None:
        try:
            selected = self._scene.selectedItems()
        except RuntimeError:
            return  # scene torn down during shutdown
        rows = [row for row in (self._describe(it) for it in selected) if row]
        if not rows:
            self._text.setPlainText("(nothing selected)")
            return
        header = f"{len(rows)} selected:"
        self._text.setPlainText(header + "\n" + "\n".join(rows))

    def _describe(self, item) -> str:
        if isinstance(item, PointItem):
            c = item.center()
            return f"  {self._scene.element_name(item)}  ({c.x():.1f}, {c.y():.1f})"
        if isinstance(item, LineItem):
            seg = item.scene_line()
            return (
                f"  {self._scene.element_name(item)}  "
                f"({seg.x1():.1f}, {seg.y1():.1f})->({seg.x2():.1f}, {seg.y2():.1f})"
                f"{self._line_tags(item)}"
            )
        if isinstance(item, GroupItem):
            return f"  Group ({len(item.childItems())} items)"
        return ""

    @staticmethod
    def _line_tags(line: LineItem) -> str:
        tags = []
        if line.is_orientation_locked():
            tags.append("locked")
        if line.has_visible_range():
            tags.append("range")
        if line.has_pivot():
            tags.append("pivot")
        return ("  " + " ".join(tags)) if tags else ""
