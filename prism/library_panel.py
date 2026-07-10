"""The dockable Library panel: built-in and user-saved geometry templates."""

from PySide6.QtCore import QMimeData, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from prism.template_store import load_user_templates, save_user_templates
from prism.templates import (
    BUILTIN_TEMPLATES,
    TEMPLATE_MIME,
    render_thumbnail,
    serialize,
    serialize_selection,
)

TEMPLATE_ROLE = Qt.UserRole
BUILTIN_ROLE = Qt.UserRole + 1


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
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def mimeData(self, items) -> QMimeData:
        mime = QMimeData()
        if items:
            template = items[0].data(TEMPLATE_ROLE)
            mime.setData(TEMPLATE_MIME, serialize(template))
        return mime


class LibraryPanel(QDockWidget):
    """A dock listing draggable templates, with save/rename/delete."""

    def __init__(self, scene, parent=None):
        super().__init__("Library", parent)
        self.setObjectName("LibraryPanel")
        self._scene = scene

        self._list = TemplateList()
        self._list.customContextMenuRequested.connect(self._show_context_menu)

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
            self._add_template(template, builtin=True)
        for template in load_user_templates():
            self._add_template(template, builtin=False)

    # -- Items -------------------------------------------------------------

    def _add_template(self, template: dict, builtin: bool) -> QListWidgetItem:
        item = QListWidgetItem(QIcon(render_thumbnail(template)), template["name"])
        item.setData(TEMPLATE_ROLE, template)
        item.setData(BUILTIN_ROLE, builtin)
        item.setToolTip(
            ("Built-in: " if builtin else "") + template["name"]
        )
        item.setTextAlignment(Qt.AlignHCenter)
        self._list.addItem(item)
        return item

    def _user_templates(self) -> list:
        return [
            self._list.item(i).data(TEMPLATE_ROLE)
            for i in range(self._list.count())
            if not self._list.item(i).data(BUILTIN_ROLE)
        ]

    def _persist(self) -> None:
        save_user_templates(self._user_templates())

    # -- Save --------------------------------------------------------------

    def _save_selection(self) -> None:
        items = list(self._scene.selectedItems())
        if not items:
            QMessageBox.information(
                self, "Save Selection",
                "Select one or more points/lines on the canvas first."
            )
            return
        name, ok = QInputDialog.getText(self, "Save to Library", "Template name:")
        if not (ok and name.strip()):
            return
        template = serialize_selection(items, name.strip())
        if not template["points"] and not template["lines"]:
            QMessageBox.information(
                self, "Save Selection",
                "The selection has no points or lines to save."
            )
            return
        self._add_template(template, builtin=False)
        self._persist()

    # -- Rename / delete (user templates only) ----------------------------

    def _show_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None or item.data(BUILTIN_ROLE):
            return  # built-ins are not editable
        menu = QMenu(self._list)
        rename_action = menu.addAction("Rename…")
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen is rename_action:
            self._rename(item)
        elif chosen is delete_action:
            self._delete(item)

    def _rename(self, item: QListWidgetItem) -> None:
        template = item.data(TEMPLATE_ROLE)
        name, ok = QInputDialog.getText(
            self, "Rename Template", "New name:", text=template["name"]
        )
        if not (ok and name.strip()):
            return
        template = dict(template)
        template["name"] = name.strip()
        item.setData(TEMPLATE_ROLE, template)
        item.setText(name.strip())
        item.setToolTip(name.strip())
        self._persist()

    def _delete(self, item: QListWidgetItem) -> None:
        confirm = QMessageBox.question(
            self, "Delete Template", f'Delete "{item.text()}"?'
        )
        if confirm != QMessageBox.Yes:
            return
        self._list.takeItem(self._list.row(item))
        self._persist()
