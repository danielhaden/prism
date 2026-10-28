"""A plain-text editor with numbered lines, for the Scripts panel.

A script is read as much as it is written — to find the step that drew a
line, or the round a net went wrong in — and talking about "line 12" needs
line 12 to be visible. The numbers sit in a gutter to the left, deliberately
**small and grey**: they are there to be referred to, not read.
"""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class _LineNumbers(QWidget):
    """The gutter. The editor owns the drawing; this is where it happens.

    A plain child widget rather than part of the editor's viewport, so it
    doesn't scroll horizontally with the text.
    """

    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event) -> None:
        self._editor.paint_line_numbers(self, event)


class ScriptEditor(QPlainTextEdit):
    """A QPlainTextEdit with a line-number gutter."""

    #: How much smaller than the text the numbers are drawn.
    NUMBER_SCALE = 0.75
    #: Never shrink past this, or they stop being legible at all.
    NUMBER_MIN_PT = 7.0
    NUMBER_COLOR = "#a0a0a0"
    #: The line the cursor is on, which is also drawn bold. Bold alone is
    #: too quiet a signal at this size.
    CURRENT_NUMBER_COLOR = "#555555"
    GUTTER_COLOR = "#f4f4f4"
    #: Space either side of the digits.
    GUTTER_PAD_PX = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._numbers = _LineNumbers(self)
        self.blockCountChanged.connect(self._fit_gutter)
        self.updateRequest.connect(self._gutter_follows)
        # The line that stops being current needs repainting as much as the
        # one that becomes it, so repaint the lot — it is a narrow strip.
        self.cursorPositionChanged.connect(self._numbers.update)
        self._fit_gutter()

    # -- Geometry ----------------------------------------------------------

    def number_font(self) -> QFont:
        """The text's font, shrunk — small enough to recede, still readable."""
        font = QFont(self.font())
        if font.pointSizeF() > 0:
            font.setPointSizeF(
                max(self.NUMBER_MIN_PT, font.pointSizeF() * self.NUMBER_SCALE)
            )
        else:
            font.setPixelSize(
                max(8, int(font.pixelSize() * self.NUMBER_SCALE))
            )
        return font

    def current_number_font(self) -> QFont:
        """The font for the line the cursor is on: the same, in bold."""
        font = self.number_font()
        font.setBold(True)
        return font

    def line_number_width(self) -> int:
        """How wide the gutter must be for the longest number in the script.

        Measured with the **bold** font, since that is the wider of the two:
        the gutter must not jostle as the cursor moves from line to line.
        """
        digits = max(2, len(str(max(1, self.blockCount()))))
        advance = QFontMetrics(self.current_number_font()).horizontalAdvance("9")
        return advance * digits + 2 * self.GUTTER_PAD_PX

    def _fit_gutter(self, *_) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _gutter_follows(self, rect, dy: int) -> None:
        """Keep the gutter in step with the text as it scrolls or changes."""
        if dy:
            self._numbers.scroll(0, dy)
        else:
            self._numbers.update(
                0, rect.y(), self._numbers.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self._fit_gutter()

    def setFont(self, font) -> None:
        super().setFont(font)
        # The panel sets the font after construction, and the gutter is
        # measured from it.
        if getattr(self, "_numbers", None) is not None:
            self._fit_gutter()
            self._numbers.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        area = self.contentsRect()
        self._numbers.setGeometry(
            QRect(area.left(), area.top(), self.line_number_width(), area.height())
        )

    # -- Drawing -----------------------------------------------------------

    def paint_line_numbers(self, gutter, event) -> None:
        """Draw the numbers of the blocks currently in view.

        Args:
            gutter: The widget being painted.
            event: Its paint event, whose rect bounds the work.
        """
        painter = QPainter(gutter)
        painter.fillRect(event.rect(), QColor(self.GUTTER_COLOR))
        plain = self.number_font()
        emphasised = self.current_number_font()
        quiet = QColor(self.NUMBER_COLOR)
        loud = QColor(self.CURRENT_NUMBER_COLOR)
        current = self.textCursor().blockNumber()

        block = self.firstVisibleBlock()
        number = block.blockNumber()
        offset = self.contentOffset()
        top = self.blockBoundingGeometry(block).translated(offset).top()
        width = gutter.width() - self.GUTTER_PAD_PX
        while block.isValid() and top <= event.rect().bottom():
            height = self.blockBoundingRect(block).height()
            if block.isVisible() and top + height >= event.rect().top():
                here = number == current
                painter.setFont(emphasised if here else plain)
                painter.setPen(loud if here else quiet)
                painter.drawText(
                    0,
                    int(top),
                    width,
                    int(height),
                    Qt.AlignRight | Qt.AlignVCenter,
                    str(number + 1),
                )
            block = block.next()
            top += height
            number += 1
