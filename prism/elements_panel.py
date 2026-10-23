"""A dock listing everything on the canvas, as a tree.

Points, lines, groups and the names bound with ``(define …)``, each under its
own heading. Selecting a row selects that element on the canvas, and selecting
on the canvas highlights the row, so the tree is a way to find and reach
geometry as well as to see what is there.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDockWidget, QTreeWidget, QTreeWidgetItem

from prism.items import GroupItem, LineItem, PointItem

#: Where an element is stashed on its row.
ITEM_ROLE = Qt.UserRole

#: How long to wait after a change before rebuilding, in milliseconds. The
#: scene reports every repaint, and a drag is a flood of them.
REFRESH_DELAY = 120


class ElementsPanel(QDockWidget):
    """A tree of the canvas: points, lines, groups and defined names."""

    def __init__(self, scene, parent=None):
        # The object name is what Qt saves dock layouts against, so it stays
        # as it was when this panel showed only the selection.
        super().__init__("Elements", parent)
        self.setObjectName("SelectionPanel")
        self._scene = scene
        self._variables_source = None
        self._syncing = False
        #: Sections the tree has shown before, so a new one opens rather than
        #: appearing collapsed because it wasn't in the last build.
        self._seen_sections: set = set()

        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFont(mono)
        self._tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self._tree.itemSelectionChanged.connect(self._tree_selection_changed)
        self.setWidget(self._tree)

        self._pending = QTimer(self)
        self._pending.setSingleShot(True)
        self._pending.setInterval(REFRESH_DELAY)
        self._pending.timeout.connect(self.refresh)

        scene.changed.connect(lambda *_: self._pending.start())
        scene.selectionChanged.connect(self._scene_selection_changed)
        self.refresh()

    def set_variables_source(self, source) -> None:
        """Tell the panel where to read defined names from.

        Args:
            source: Callable returning ``{name: value}``, or None.
        """
        self._variables_source = source
        self.refresh()

    # -- Building ----------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild the tree from the scene."""
        try:
            points = self._scene.ordered_points()
            lines = self._scene.ordered_lines()
        except RuntimeError:
            return  # scene torn down during shutdown

        expanded = self._expanded_sections()
        self._syncing = True
        self._tree.clear()

        self._section("Points", points, self._describe_point, expanded)
        self._section("Lines", lines, self._describe_line, expanded)

        groups = [it for it in self._scene.items() if isinstance(it, GroupItem)]
        if groups:
            parent = self._heading(f"Groups ({len(groups)})", expanded)
            for group in groups:
                children = group.childItems()
                row = QTreeWidgetItem(parent, [f"{len(children)} items"])
                row.setData(0, ITEM_ROLE, group)
                for child in children:
                    label = (
                        self._describe_point(child)
                        if isinstance(child, PointItem)
                        else self._describe_line(child)
                        if isinstance(child, LineItem)
                        else None
                    )
                    if label:
                        QTreeWidgetItem(row, [label]).setData(0, ITEM_ROLE, child)

        names = self._variables_source() if self._variables_source else {}
        if names:
            parent = self._heading(f"Lists ({len(names)})", expanded)
            for name, value in sorted(names.items()):
                QTreeWidgetItem(parent, [f"{name} = {self._describe_value(value)}"])

        self._syncing = False
        self._scene_selection_changed()

    def _section(self, title: str, items: list, describe, expanded: set) -> None:
        parent = self._heading(f"{title} ({len(items)})", expanded)
        for item in items:
            row = QTreeWidgetItem(parent, [describe(item)])
            row.setData(0, ITEM_ROLE, item)

    def _heading(self, text: str, expanded: set) -> QTreeWidgetItem:
        head = QTreeWidgetItem(self._tree, [text])
        head.setFlags(head.flags() & ~Qt.ItemIsSelectable)
        name = text.split(" (")[0]
        head.setExpanded(name in expanded or name not in self._seen_sections)
        self._seen_sections.add(name)
        return head

    def _expanded_sections(self) -> set:
        """Which headings are open, so a rebuild doesn't collapse them."""
        return {
            self._tree.topLevelItem(i).text(0).split(" (")[0]
            for i in range(self._tree.topLevelItemCount())
            if self._tree.topLevelItem(i).isExpanded()
        }

    # -- Describing --------------------------------------------------------

    def _describe_point(self, point: PointItem) -> str:
        centre = point.center()
        text = f"{self._scene.element_name(point)}  ({centre.x():.1f}, {centre.y():.1f})"
        tags = []
        if point.is_meet():
            tags.append(
                "meet of "
                + ", ".join(
                    sorted(self._scene.line_id(ln) for ln in point.meeting_lines())
                )
            )
        elif point.is_locked_to_line():
            tags.append("locked to line")
        elif point.has_anchor():
            tags.append("on line")
        if not point.is_shown():
            tags.append("hidden")
        if point.position_undefined():
            tags.append("undefined")
        return text + (f"  [{', '.join(tags)}]" if tags else "")

    def _describe_line(self, line: LineItem) -> str:
        seg = line.scene_line()
        text = (
            f"{self._scene.element_name(line)}  "
            f"({seg.x1():.0f}, {seg.y1():.0f})->({seg.x2():.0f}, {seg.y2():.0f})"
        )
        tags = []
        if line.is_orientation_locked():
            tags.append("locked")
        if line.has_visible_range():
            tags.append("range")
        if line.has_pivot():
            tags.append("pivot")
        if not line.is_shown():
            tags.append("hidden")
        if line.position_undefined():
            tags.append("undefined")
        return text + (f"  [{', '.join(tags)}]" if tags else "")

    def _describe_value(self, value) -> str:
        if isinstance(value, list):
            return "(" + " ".join(self._scene.element_id(it) for it in value) + ")"
        if isinstance(value, (PointItem, LineItem)):
            return self._scene.element_id(value)
        return str(value)

    # -- Selection, both ways ----------------------------------------------

    def _tree_selection_changed(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self._scene.clearSelection()
            for row in self._tree.selectedItems():
                item = row.data(0, ITEM_ROLE)
                if item is not None and item.scene() is self._scene:
                    item.setSelected(True)
        finally:
            self._syncing = False

    def _scene_selection_changed(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            selected = set(self._scene.selectedItems())
            for row in self._rows():
                item = row.data(0, ITEM_ROLE)
                row.setSelected(item is not None and item in selected)
        except RuntimeError:
            pass  # scene torn down during shutdown
        finally:
            self._syncing = False

    def _rows(self):
        for i in range(self._tree.topLevelItemCount()):
            yield from self._descendants(self._tree.topLevelItem(i))

    def _descendants(self, parent):
        for i in range(parent.childCount()):
            child = parent.child(i)
            yield child
            yield from self._descendants(child)
