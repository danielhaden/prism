"""The dockable Scripts panel: saved console scripts, in one place.

The panel lists the scripts in the scripts folder and holds an editor for the
selected one, so a construction can be tweaked and re-run without leaving
Prism. **Run** executes what is in the editor rather than what is on disk, so
an edit can be tried before it is kept.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from prism.settings import list_scripts, load_script, scripts_dir, write_script

PATH_ROLE = Qt.UserRole


class ScriptsPanel(QDockWidget):
    """Lists the scripts in the scripts folder, and edits them."""

    def __init__(self, run_script, parent=None):
        """
        Args:
            run_script: Callable ``(name, text)`` that executes a script.
        """
        super().__init__("Scripts", parent)
        self.setObjectName("ScriptsPanel")
        self._run_script = run_script
        self._loaded_path: str | None = None
        self._dirty = False

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._run_item)
        self._list.currentItemChanged.connect(self._selection_changed)

        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)
        self._editor = QPlainTextEdit()
        self._editor.setFont(mono)
        self._editor.setPlaceholderText("Select a script to edit it here.")
        self._editor.setEnabled(False)
        self._editor.textChanged.connect(self._text_changed)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: gray; font-size: 11px;")

        self._folder_label = QLabel()
        self._folder_label.setWordWrap(True)
        self._folder_label.setStyleSheet("color: gray; font-size: 11px;")

        self._run_button = QPushButton("Run")
        self._run_button.setToolTip(
            "Run what's in the editor (or double-click a script)"
        )
        self._run_button.clicked.connect(self._run_selected)

        self._save_button = QPushButton("Save")
        self._save_button.setToolTip("Write the editor's contents back to the file")
        self._save_button.clicked.connect(self.save)
        self._save_button.setEnabled(False)

        self._revert_button = QPushButton("Revert")
        self._revert_button.setToolTip("Throw away edits and re-read the file")
        self._revert_button.clicked.connect(self.revert)
        self._revert_button.setEnabled(False)

        refresh_button = QPushButton("Refresh")
        refresh_button.setToolTip("Re-read the scripts folder")
        refresh_button.clicked.connect(self.refresh)

        buttons = QHBoxLayout()
        buttons.addWidget(self._run_button)
        buttons.addWidget(self._save_button)
        buttons.addWidget(self._revert_button)
        buttons.addWidget(refresh_button)

        split = QSplitter(Qt.Vertical)
        split.addWidget(self._list)
        split.addWidget(self._editor)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(split)
        layout.addWidget(self._status_label)
        layout.addLayout(buttons)
        layout.addWidget(self._folder_label)
        self.setWidget(container)

        self.refresh()

    # -- The list ----------------------------------------------------------

    def refresh(self) -> None:
        """Re-read the scripts folder, keeping the current selection if it survives."""
        keep = self._loaded_path
        self._list.blockSignals(True)
        self._list.clear()
        folder = scripts_dir()
        self._folder_label.setText(folder)
        self._folder_label.setToolTip(folder)
        restored = None
        for name, path in list_scripts():
            item = QListWidgetItem(name)
            item.setData(PATH_ROLE, path)
            item.setToolTip(path)
            self._list.addItem(item)
            if path == keep:
                restored = item
        if self._list.count() == 0:
            placeholder = QListWidgetItem("(no scripts yet)")
            placeholder.setFlags(Qt.NoItemFlags)
            self._list.addItem(placeholder)
        self._list.setCurrentItem(restored)
        self._list.blockSignals(False)
        if restored is None:
            # Whatever was open is no longer in the folder.
            self._clear_editor()

    def _selection_changed(self, current, _previous) -> None:
        path = current.data(PATH_ROLE) if current is not None else None
        if path == self._loaded_path:
            return
        if not self._confirm_discard():
            self._reselect_loaded()
            return
        if path is None:
            self._clear_editor()
        else:
            self._load(path, current.text())

    def _reselect_loaded(self) -> None:
        """Put the selection back on the script still open in the editor."""
        self._list.blockSignals(True)
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(PATH_ROLE) == self._loaded_path:
                self._list.setCurrentItem(item)
                break
        self._list.blockSignals(False)

    # -- The editor --------------------------------------------------------

    def _load(self, path: str, name: str) -> None:
        try:
            text = load_script(path)
        except OSError as exc:
            QMessageBox.warning(self, "Scripts", f"Couldn't read it: {exc}")
            self._clear_editor()
            return
        self._loaded_path = path
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        self._editor.setEnabled(True)
        self._set_dirty(False)

    def _clear_editor(self) -> None:
        self._loaded_path = None
        self._editor.blockSignals(True)
        self._editor.clear()
        self._editor.blockSignals(False)
        self._editor.setEnabled(False)
        self._set_dirty(False)

    def _text_changed(self) -> None:
        if self._loaded_path is not None:
            self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._save_button.setEnabled(dirty)
        self._revert_button.setEnabled(dirty)
        name = self._current_name()
        if name is None:
            self._status_label.setText("")
        else:
            self._status_label.setText(f"{name} — modified" if dirty else name)

    def _current_name(self) -> str | None:
        item = self._list.currentItem()
        if item is None or item.data(PATH_ROLE) is None:
            return None
        return item.text()

    def save(self) -> bool:
        """Write the editor back to the file it came from.

        Returns:
            Whether it was written.
        """
        if self._loaded_path is None:
            return False
        try:
            write_script(self._loaded_path, self._editor.toPlainText())
        except OSError as exc:
            QMessageBox.warning(self, "Scripts", f"Couldn't save it: {exc}")
            return False
        self._set_dirty(False)
        return True

    def revert(self) -> None:
        """Throw away unsaved edits and re-read the file."""
        if self._loaded_path is not None:
            self._load(self._loaded_path, self._current_name() or "")

    def _confirm_discard(self) -> bool:
        """Ask about unsaved edits. Returns whether to go ahead."""
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            f"Save your changes to {self._current_name()}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self.save()
        return True

    # -- Running -----------------------------------------------------------

    def _run_selected(self) -> None:
        if self._loaded_path is None:
            QMessageBox.information(self, "Run Script", "Select a script to run.")
            return
        self._run_script(self._current_name() or "script", self._editor.toPlainText())

    def _run_item(self, item: QListWidgetItem) -> None:
        if item.data(PATH_ROLE) is None:
            return
        self._list.setCurrentItem(item)
        if self._loaded_path == item.data(PATH_ROLE):
            self._run_selected()
