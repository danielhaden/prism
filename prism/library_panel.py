"""The dockable Library panel: built-in and user-saved geometry templates."""

from PySide6.QtCore import QMimeData, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from prism.templates import (
    BUILTIN_TEMPLATES,
    TEMPLATE_MIME,
    render_thumbnail,
    serialize,
    serialize_selection,
)


class TemplateList(QListWidget):
    """An icon list whose items can be dragged out as templates."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(72, 72))
        self.setGridSize(QSize(96, 104))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSpacing(6)
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)

    def mimeData(self, items) -> QMimeData:
        mime = QMimeData()
        if items:
            template = items[0].data(Qt.UserRole)
            mime.setData(TEMPLATE_MIME, serialize(template))
        return mime


class LibraryPanel(QDockWidget):
    """A dock listing draggable templates, with a way to save selections."""

    def __init__(self, scene, parent=None):
        super().__init__("Library", parent)
        self.setObjectName("LibraryPanel")
        self._scene = scene

        self._list = TemplateList()

        self._save_button = QPushButton("Save Selection…")
        self._save_button.setToolTip("Save the selected canvas geometry as a template")
        self._save_button.clicked.connect(self._save_selection)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._list)
        layout.addWidget(self._save_button)
        self.setWidget(container)

        for template in BUILTIN_TEMPLATES:
            self._add_template(template)

    def _add_template(self, template: dict) -> None:
        item = QListWidgetItem(QIcon(render_thumbnail(template)), template["name"])
        item.setData(Qt.UserRole, template)
        item.setToolTip(template["name"])
        item.setTextAlignment(Qt.AlignHCenter)
        self._list.addItem(item)

    def _save_selection(self) -> None:
        items = [it for it in self._scene.selectedItems()]
        if not items:
            QMessageBox.information(
                self, "Save Selection",
                "Select one or more points/lines on the canvas first."
            )
            return
        name, ok = QInputDialog.getText(
            self, "Save to Library", "Template name:"
        )
        if ok and name.strip():
            template = serialize_selection(items, name.strip())
            if not template["points"] and not template["lines"]:
                QMessageBox.information(
                    self, "Save Selection",
                    "The selection has no points or lines to save."
                )
                return
            self._add_template(template)
