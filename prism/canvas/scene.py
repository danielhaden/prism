"""The drawing scene: turns mouse interaction into geometry items."""

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsScene

from prism.items import LineItem, PointItem
from prism.tools import Tool


class CanvasScene(QGraphicsScene):
    """A QGraphicsScene that draws points and lines based on the active tool.

    Interaction model:
      * SELECT — default Qt behaviour (rubber-band select, drag to move).
      * POINT  — one click places a point.
      * LINE   — first click sets the start, a preview follows the cursor,
                 second click sets the end and commits the line.
    """

    #: Emitted with a short hint for the status bar.
    statusMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-2000, -2000, 4000, 4000)

        self._tool = Tool.SELECT
        self._line_start: QPointF | None = None
        self._preview_line: LineItem | None = None

    # -- Tool management ---------------------------------------------------

    def set_tool(self, tool: Tool) -> None:
        """Switch the active tool, cancelling any in-progress drawing."""
        self._cancel_line()
        self._tool = tool
        self.clearSelection()
        self._emit_hint()

    def tool(self) -> Tool:
        return self._tool

    def _emit_hint(self) -> None:
        hints = {
            Tool.SELECT: "Select: click to select, drag to move.",
            Tool.POINT: "Point: click on the canvas to place a point.",
            Tool.LINE: "Line: click a start point, then an end point.",
        }
        self.statusMessage.emit(hints[self._tool])

    # -- Mouse handling ----------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        pos = event.scenePos()

        if self._tool == Tool.POINT:
            self.add_point(pos)
            event.accept()
            return

        if self._tool == Tool.LINE:
            self._handle_line_click(pos)
            event.accept()
            return

        # SELECT (and anything else): fall back to default behaviour.
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._tool == Tool.LINE and self._preview_line is not None:
            self._preview_line.setLine(
                self._line_start.x(),
                self._line_start.y(),
                event.scenePos().x(),
                event.scenePos().y(),
            )
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._cancel_line()
        super().keyPressEvent(event)

    # -- Drawing helpers ---------------------------------------------------

    def add_point(self, pos: QPointF) -> PointItem:
        point = PointItem(pos)
        self.addItem(point)
        return point

    def add_line(self, start: QPointF, end: QPointF) -> LineItem:
        line = LineItem(start, end)
        self.addItem(line)
        return line

    def _handle_line_click(self, pos: QPointF) -> None:
        if self._line_start is None:
            # First click: begin a line and show a live preview.
            self._line_start = pos
            self._preview_line = LineItem(pos, pos)
            preview_pen = QPen(QColor("#999999"), 1, Qt.DashLine)
            preview_pen.setCosmetic(True)
            self._preview_line.setPen(preview_pen)
            self.addItem(self._preview_line)
            self.statusMessage.emit("Line: click the end point (Esc to cancel).")
        else:
            # Second click: commit the line.
            start = self._line_start
            self._cancel_line()
            if start != pos:
                self.add_line(start, pos)
            self._emit_hint()

    def _cancel_line(self) -> None:
        if self._preview_line is not None:
            self.removeItem(self._preview_line)
            self._preview_line = None
        self._line_start = None

    # -- Editing -----------------------------------------------------------

    def delete_selected(self) -> None:
        for item in self.selectedItems():
            self.removeItem(item)

    def clear_all(self) -> None:
        self._cancel_line()
        self.clear()
