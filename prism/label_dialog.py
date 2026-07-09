"""A dialog for editing a label's text display properties."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class LabelStyleDialog(QDialog):
    """Edit font family, size, color, and bold/italic/underline for a label."""

    def __init__(self, font: QFont, color: QColor, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Label Properties")
        self._color = QColor(color)

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(font)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 200)
        self.size_spin.setValue(font.pointSize() if font.pointSize() > 0 else 11)

        self.bold_check = QCheckBox("Bold")
        self.bold_check.setChecked(font.bold())
        self.italic_check = QCheckBox("Italic")
        self.italic_check.setChecked(font.italic())
        self.underline_check = QCheckBox("Underline")
        self.underline_check.setChecked(font.underline())

        self.color_button = QPushButton("Choose…")
        self.color_button.clicked.connect(self._pick_color)

        self.preview = QLabel("AaBbCc 123")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(48)

        style_row = QHBoxLayout()
        style_row.addWidget(self.bold_check)
        style_row.addWidget(self.italic_check)
        style_row.addWidget(self.underline_check)
        style_row.addStretch(1)

        form = QFormLayout()
        form.addRow("Font:", self.font_combo)
        form.addRow("Size:", self.size_spin)
        form.addRow("Style:", style_row)
        form.addRow("Color:", self.color_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.preview)
        layout.addWidget(buttons)

        for signal in (
            self.font_combo.currentFontChanged,
            self.size_spin.valueChanged,
            self.bold_check.toggled,
            self.italic_check.toggled,
            self.underline_check.toggled,
        ):
            signal.connect(self._update_preview)
        self._update_preview()

    # -- Result ------------------------------------------------------------

    def selected_font(self) -> QFont:
        font = QFont(self.font_combo.currentFont())
        font.setPointSize(self.size_spin.value())
        font.setBold(self.bold_check.isChecked())
        font.setItalic(self.italic_check.isChecked())
        font.setUnderline(self.underline_check.isChecked())
        return font

    def selected_color(self) -> QColor:
        return QColor(self._color)

    @staticmethod
    def get_style(font: QFont, color: QColor, parent=None):
        """Show the dialog; return (font, color) on OK, else (None, None)."""
        dialog = LabelStyleDialog(font, color, parent)
        if dialog.exec() == QDialog.Accepted:
            return dialog.selected_font(), dialog.selected_color()
        return None, None

    # -- Internal ----------------------------------------------------------

    def _pick_color(self):
        chosen = QColorDialog.getColor(self._color, self, "Text Color")
        if chosen.isValid():
            self._color = chosen
            self._update_preview()

    def _update_preview(self):
        self.preview.setFont(self.selected_font())
        self.preview.setStyleSheet(f"color: {self._color.name()};")
        self.color_button.setStyleSheet(f"background-color: {self._color.name()};")
