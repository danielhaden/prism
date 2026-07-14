"""A dialog to add a projectivity (pencil of lines) at a point.

Angles are measured in degrees clockwise from the horizontal (the positive
x-axis, pointing right) — which reads as clockwise on screen. The pencil spans
from a start angle to an end angle, subdivided either by a line *count* or by a
fixed *splay* (degrees between adjacent lines).
"""

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)


class ProjectivityDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Projectivity")

        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(-360.0, 360.0)
        self.start_spin.setDecimals(1)
        self.start_spin.setSuffix("°")
        self.start_spin.setValue(0.0)

        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(-360.0, 360.0)
        self.end_spin.setDecimals(1)
        self.end_spin.setSuffix("°")
        self.end_spin.setValue(180.0)

        self.count_radio = QRadioButton("Count")
        self.count_radio.setChecked(True)
        self.splay_radio = QRadioButton("Splay")
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.count_radio)
        mode_group.addButton(self.splay_radio)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 1000)
        self.count_spin.setValue(6)

        self.splay_spin = QDoubleSpinBox()
        self.splay_spin.setRange(0.1, 360.0)
        self.splay_spin.setDecimals(1)
        self.splay_spin.setSuffix("°")
        self.splay_spin.setValue(15.0)

        self.count_radio.toggled.connect(self._update_enabled)
        self._update_enabled()

        count_row = QHBoxLayout()
        count_row.addWidget(self.count_radio)
        count_row.addWidget(self.count_spin)
        splay_row = QHBoxLayout()
        splay_row.addWidget(self.splay_radio)
        splay_row.addWidget(self.splay_spin)

        form = QFormLayout()
        form.addRow("Start angle:", self.start_spin)
        form.addRow("End angle:", self.end_spin)
        form.addRow("Subdivide by:", count_row)
        form.addRow("", splay_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _update_enabled(self):
        self.count_spin.setEnabled(self.count_radio.isChecked())
        self.splay_spin.setEnabled(self.splay_radio.isChecked())

    def angles(self) -> list:
        start = self.start_spin.value()
        end = self.end_spin.value()
        span = end - start
        if self.count_radio.isChecked():
            count = self.count_spin.value()
            if count <= 1:
                return [start]
            step = span / (count - 1)
            return [start + i * step for i in range(count)]
        splay = self.splay_spin.value()
        if splay <= 0:
            return [start]
        n = int(abs(span) // splay) + 1
        sign = 1.0 if span >= 0 else -1.0
        return [start + sign * i * splay for i in range(n)]

    @staticmethod
    def get_angles(parent=None):
        """Show the dialog; return the list of angles (deg) on OK, else None."""
        dialog = ProjectivityDialog(parent)
        if dialog.exec() == QDialog.Accepted:
            return dialog.angles()
        return None
