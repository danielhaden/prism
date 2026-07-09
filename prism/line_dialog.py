"""A dialog for editing a line's display properties (color, width, style)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _LinePreview(QWidget):
    """A small strip that draws a sample line with the chosen pen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(44)
        self._pen = QPen()

    def set_pen(self, pen: QPen) -> None:
        self._pen = QPen(pen)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self._pen)
        pen.setCosmetic(True)
        painter.setPen(pen)
        y = self.height() // 2
        painter.drawLine(12, y, self.width() - 12, y)
        painter.end()


class LineStyleDialog(QDialog):
    """Edit a line's color, thickness, and dash style."""

    STYLES = [
        ("Solid", Qt.SolidLine),
        ("Dashed", Qt.DashLine),
        ("Dotted", Qt.DotLine),
        ("Dash-Dot", Qt.DashDotLine),
    ]

    def __init__(self, color: QColor, width: float, style, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Line Properties")
        self._color = QColor(color)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.5, 20.0)
        self.width_spin.setSingleStep(0.5)
        self.width_spin.setValue(width if width > 0 else 1.0)

        self.style_combo = QComboBox()
        for name, pen_style in self.STYLES:
            self.style_combo.addItem(name, pen_style)
        for i, (_, pen_style) in enumerate(self.STYLES):
            if pen_style == style:
                self.style_combo.setCurrentIndex(i)
                break

        self.color_button = QPushButton("Choose…")
        self.color_button.clicked.connect(self._pick_color)

        self.preview = _LinePreview()

        form = QFormLayout()
        form.addRow("Color:", self.color_button)
        form.addRow("Thickness:", self.width_spin)
        form.addRow("Style:", self.style_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.preview)
        layout.addWidget(buttons)

        self.width_spin.valueChanged.connect(self._update_preview)
        self.style_combo.currentIndexChanged.connect(self._update_preview)
        self._update_preview()

    # -- Result ------------------------------------------------------------

    def selected_color(self) -> QColor:
        return QColor(self._color)

    def selected_width(self) -> float:
        return self.width_spin.value()

    def selected_style(self):
        return self.style_combo.currentData()

    @staticmethod
    def get_style(color: QColor, width: float, style, parent=None):
        """Show the dialog; return (color, width, style) on OK, else (None,)*3."""
        dialog = LineStyleDialog(color, width, style, parent)
        if dialog.exec() == QDialog.Accepted:
            return (
                dialog.selected_color(),
                dialog.selected_width(),
                dialog.selected_style(),
            )
        return None, None, None

    # -- Internal ----------------------------------------------------------

    def _pick_color(self):
        chosen = QColorDialog.getColor(self._color, self, "Line Color")
        if chosen.isValid():
            self._color = chosen
            self._update_preview()

    def _update_preview(self):
        pen = QPen(self._color, self.width_spin.value())
        pen.setStyle(self.style_combo.currentData())
        self.preview.set_pen(pen)
        self.color_button.setStyleSheet(
            f"background-color: {self._color.name()};"
        )
