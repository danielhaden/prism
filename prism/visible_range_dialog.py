"""A dialog to set a line's visible range (extent each way from its anchor)."""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QVBoxLayout,
)


class VisibleRangeDialog(QDialog):
    """Enter how far the line is drawn behind and ahead of its anchor point."""

    def __init__(self, neg: float, pos: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Visible Range")

        self.neg_spin = QDoubleSpinBox()
        self.neg_spin.setRange(0.0, 100000.0)
        self.neg_spin.setDecimals(1)
        self.neg_spin.setValue(neg)

        self.pos_spin = QDoubleSpinBox()
        self.pos_spin.setRange(0.0, 100000.0)
        self.pos_spin.setDecimals(1)
        self.pos_spin.setValue(pos)

        form = QFormLayout()
        form.addRow("Negative extent:", self.neg_spin)
        form.addRow("Positive extent:", self.pos_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self):
        return self.neg_spin.value(), self.pos_spin.value()

    @staticmethod
    def get_range(neg: float, pos: float, parent=None):
        """Show the dialog; return (neg, pos) on OK, else None."""
        dialog = VisibleRangeDialog(neg, pos, parent)
        if dialog.exec() == QDialog.Accepted:
            return dialog.values()
        return None
