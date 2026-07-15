"""The dockable Scripts panel: saved console scripts, in one place."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from prism.settings import list_scripts, load_script, scripts_dir

PATH_ROLE = Qt.UserRole


class ScriptsPanel(QDockWidget):
    """Lists the scripts in the scripts folder and runs them."""

    def __init__(self, run_script, parent=None):
        """
        Args:
            run_script: Callable ``(name, text)`` that executes a script.
        """
        super().__init__("Scripts", parent)
        self.setObjectName("ScriptsPanel")
        self._run_script = run_script

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._run_item)

        self._folder_label = QLabel()
        self._folder_label.setWordWrap(True)
        self._folder_label.setStyleSheet("color: gray; font-size: 11px;")

        run_button = QPushButton("Run")
        run_button.setToolTip("Run the selected script (or double-click it)")
        run_button.clicked.connect(self._run_selected)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)

        buttons = QHBoxLayout()
        buttons.addWidget(run_button)
        buttons.addWidget(refresh_button)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._list)
        layout.addLayout(buttons)
        layout.addWidget(self._folder_label)
        self.setWidget(container)

        self.refresh()

    def refresh(self) -> None:
        """Re-read the scripts folder."""
        self._list.clear()
        folder = scripts_dir()
        self._folder_label.setText(folder)
        self._folder_label.setToolTip(folder)
        for name, path in list_scripts():
            item = QListWidgetItem(name)
            item.setData(PATH_ROLE, path)
            item.setToolTip(path)
            self._list.addItem(item)
        if self._list.count() == 0:
            placeholder = QListWidgetItem("(no scripts yet)")
            placeholder.setFlags(Qt.NoItemFlags)
            self._list.addItem(placeholder)

    # -- Running -----------------------------------------------------------

    def _run_selected(self) -> None:
        item = self._list.currentItem()
        if item is None or item.data(PATH_ROLE) is None:
            QMessageBox.information(
                self, "Run Script", "Select a script to run."
            )
            return
        self._run_item(item)

    def _run_item(self, item: QListWidgetItem) -> None:
        path = item.data(PATH_ROLE)
        if path is None:
            return
        try:
            text = load_script(path)
        except OSError as exc:
            QMessageBox.warning(self, "Run Script", f"Couldn't read it: {exc}")
            return
        self._run_script(item.text(), text)
