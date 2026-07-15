"""A dialog for editing a point's display properties."""

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _PointPreview(QWidget):
    """Shows the point over a small pencil of lines, so the glow is visible."""

    BACKGROUND = "#fafafa"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(110)
        self._radius = 5.0
        self._color = QColor("#1f77b4")
        self._glow_radius = 0.0
        self._glow_color = QColor(self.BACKGROUND)

    def set_style(self, radius, color, glow_radius, glow_color):
        self._radius = radius
        self._color = QColor(color)
        self._glow_radius = glow_radius
        self._glow_color = QColor(glow_color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(self.BACKGROUND))

        center = QPointF(self.width() / 2, self.height() / 2)
        reach = max(self.width(), self.height())

        # A little pencil of lines through the center.
        painter.setPen(QPen(QColor("#333333"), 1))
        for angle in range(0, 180, 30):
            r = math.radians(angle)
            dx, dy = reach * math.cos(r), reach * math.sin(r)
            painter.drawLine(
                QPointF(center.x() - dx, center.y() - dy),
                QPointF(center.x() + dx, center.y() + dy),
            )

        if self._glow_radius > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(self._glow_color))
            painter.drawEllipse(center, self._glow_radius, self._glow_radius)

        painter.setBrush(QBrush(self._color))
        painter.setPen(QPen(QColor(self._color).darker(180), 1.5))
        painter.drawEllipse(center, self._radius, self._radius)
        painter.end()


class PointStyleDialog(QDialog):
    """Edit a point's radius, color, and glow (surround) properties."""

    def __init__(self, radius, color, glow_radius, glow_color, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Point Display Properties")
        self._color = QColor(color)
        self._glow_color = QColor(glow_color)
        self._apply_all = False

        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0.5, 100.0)
        self.radius_spin.setSingleStep(0.5)
        self.radius_spin.setDecimals(1)
        self.radius_spin.setSuffix(" px")
        self.radius_spin.setValue(radius)

        self.color_button = QPushButton("Choose…")
        self.color_button.clicked.connect(self._pick_color)

        self.glow_spin = QDoubleSpinBox()
        self.glow_spin.setRange(0.0, 200.0)
        self.glow_spin.setSingleStep(1.0)
        self.glow_spin.setDecimals(1)
        self.glow_spin.setSuffix(" px")
        self.glow_spin.setToolTip("Radius of the surround disc; 0 disables it")
        self.glow_spin.setValue(glow_radius)

        self.glow_color_button = QPushButton("Choose…")
        self.glow_color_button.clicked.connect(self._pick_glow_color)

        self.preview = _PointPreview()

        form = QFormLayout()
        form.addRow("Radius:", self.radius_spin)
        form.addRow("Color:", self.color_button)
        form.addRow("Glow radius:", self.glow_spin)
        form.addRow("Glow color:", self.glow_color_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.apply_all_button = buttons.addButton(
            "Apply to All Points", QDialogButtonBox.ActionRole
        )
        self.apply_all_button.setToolTip(
            "Apply these properties to every point on the canvas, and use them "
            "for points created later"
        )
        self.apply_all_button.clicked.connect(self._apply_to_all)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.preview)
        layout.addWidget(buttons)

        self.radius_spin.valueChanged.connect(self._update_preview)
        self.glow_spin.valueChanged.connect(self._update_preview)
        self._update_preview()

    # -- Result ------------------------------------------------------------

    def style(self) -> dict:
        return {
            "radius": self.radius_spin.value(),
            "color": QColor(self._color),
            "glow_radius": self.glow_spin.value(),
            "glow_color": QColor(self._glow_color),
        }

    def apply_to_all(self) -> bool:
        return self._apply_all

    @staticmethod
    def get_style(radius, color, glow_radius, glow_color, parent=None):
        """Show the dialog.

        Returns:
            A ``(style, apply_to_all)`` tuple on OK, or ``(None, False)`` if
            cancelled.
        """
        dialog = PointStyleDialog(radius, color, glow_radius, glow_color, parent)
        if dialog.exec() == QDialog.Accepted:
            return dialog.style(), dialog.apply_to_all()
        return None, False

    # -- Internal ----------------------------------------------------------

    def _apply_to_all(self):
        self._apply_all = True
        self.accept()

    def _pick_color(self):
        chosen = QColorDialog.getColor(self._color, self, "Point Color")
        if chosen.isValid():
            self._color = chosen
            self._update_preview()

    def _pick_glow_color(self):
        chosen = QColorDialog.getColor(self._glow_color, self, "Glow Color")
        if chosen.isValid():
            self._glow_color = chosen
            self._update_preview()

    def _update_preview(self):
        self.preview.set_style(
            self.radius_spin.value(),
            self._color,
            self.glow_spin.value(),
            self._glow_color,
        )
        self.color_button.setStyleSheet(f"background-color: {self._color.name()};")
        self.glow_color_button.setStyleSheet(
            f"background-color: {self._glow_color.name()};"
        )
