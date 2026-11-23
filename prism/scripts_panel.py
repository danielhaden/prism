"""The dockable Scripts panel: the script you have open, and its editor.

The panel is an editor over **one script at a time**. Which script that is
comes from the File menu — Open, Open Recent, New — rather than from a list
kept here: a script may live anywhere on disk, so a list of one folder could
only ever show some of them, and the one you want would as often as not be
somewhere else. **Run** executes what is in the editor rather than what is on
disk, so an edit can be tried before it is kept.
"""

import os

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from prism.script_editor import ScriptEditor
from prism.settings import (
    SCRIPT_SUFFIX,
    load_script,
    scripts_dir,
    write_script,
)


class ScriptsPanel(QDockWidget):
    """Holds the script that is open, and edits it."""

    #: Shown for a script that has never been written to disk.
    UNTITLED = "untitled"

    def __init__(self, run_script, parent=None):
        """
        Args:
            run_script: Callable ``(name, text)`` that executes a script.
        """
        super().__init__("Scripts", parent)
        self.setObjectName("ScriptsPanel")
        self._run_script = run_script
        self._save_handler = None
        self._loaded_path: str | None = None
        self._dirty = False

        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)
        self._editor = ScriptEditor()
        self._editor.setFont(mono)
        self._editor.setPlaceholderText(
            "Open a script from the File menu, or start typing one here."
        )
        self._editor.textChanged.connect(self._text_changed)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: gray; font-size: 11px;")

        self._where_label = QLabel()
        self._where_label.setWordWrap(True)
        self._where_label.setStyleSheet("color: gray; font-size: 11px;")

        self._run_button = QPushButton("Run")
        self._run_button.setToolTip("Run what's in the editor")
        self._run_button.clicked.connect(self.run)

        self._save_button = QPushButton("Save")
        self._save_button.setToolTip("Write the editor's contents back to the file")
        self._save_button.clicked.connect(self._save_through_window)
        self._save_button.setEnabled(False)

        self._revert_button = QPushButton("Revert")
        self._revert_button.setToolTip("Throw away edits and re-read the file")
        self._revert_button.clicked.connect(self.revert)
        self._revert_button.setEnabled(False)

        buttons = QHBoxLayout()
        buttons.addWidget(self._run_button)
        buttons.addWidget(self._save_button)
        buttons.addWidget(self._revert_button)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._editor)
        layout.addWidget(self._status_label)
        layout.addLayout(buttons)
        layout.addWidget(self._where_label)
        self.setWidget(container)

        self._set_dirty(False)

    # -- What's open -------------------------------------------------------

    def current_path(self) -> str | None:
        """The file the editor's script came from, or None if it is untitled."""
        return self._loaded_path

    def current_name(self) -> str:
        """The open script's display name, or ``"untitled"``."""
        if self._loaded_path is None:
            return self.UNTITLED
        name = os.path.basename(self._loaded_path)
        if name.endswith(SCRIPT_SUFFIX):
            name = name[: -len(SCRIPT_SUFFIX)]
        return name or self.UNTITLED

    def is_dirty(self) -> bool:
        """Whether the editor holds changes that aren't on disk."""
        return self._dirty

    def text(self) -> str:
        """What is in the editor."""
        return self._editor.toPlainText()

    def set_save_handler(self, handler) -> None:
        """Hand the panel the window's Save command.

        Saving an untitled script needs a file dialog, and that belongs with
        the File menu rather than in here. Without a handler the panel falls
        back to :meth:`save`, which is enough to keep it usable headless —
        the same bargain as ``CanvasScene.set_command_runner``.

        Args:
            handler: Callable returning whether the script was written.
        """
        self._save_handler = handler

    # -- Opening and starting afresh ---------------------------------------

    def open_path(self, path: str) -> bool:
        """Read a script into the editor.

        The caller is expected to have cleared any unsaved edits with
        :meth:`confirm_discard` first; this one only reads.

        Args:
            path: The file to read.

        Returns:
            Whether it was read.
        """
        try:
            text = load_script(path)
        except OSError as exc:
            QMessageBox.warning(self, "Scripts", f"Couldn't read it: {exc}")
            return False
        self._loaded_path = os.path.abspath(path)
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        self._set_dirty(False)
        return True

    def new_script(self) -> None:
        """Empty the editor, with no file behind it yet."""
        self._loaded_path = None
        self._editor.blockSignals(True)
        self._editor.clear()
        self._editor.blockSignals(False)
        self._set_dirty(False)

    def forget_path(self) -> None:
        """Keep the text but lose the file it came from.

        For a script whose file has gone: the work is still in the editor and
        the next save asks where to put it, rather than writing to a path
        that is no longer there.
        """
        self._loaded_path = None
        self._set_dirty(True)

    # -- Saving ------------------------------------------------------------

    def save(self) -> bool:
        """Write the editor back to the file it came from.

        Returns:
            Whether it was written; False for an untitled script, which needs
                somewhere to be put first.
        """
        if self._loaded_path is None:
            return False
        return self.save_to(self._loaded_path)

    def save_to(self, path: str) -> bool:
        """Write the editor to a given file and keep it as the open one.

        Args:
            path: Where to write.

        Returns:
            Whether it was written.
        """
        try:
            write_script(path, self._editor.toPlainText())
        except OSError as exc:
            QMessageBox.warning(self, "Scripts", f"Couldn't save it: {exc}")
            return False
        self._loaded_path = os.path.abspath(path)
        self._set_dirty(False)
        return True

    def revert(self) -> None:
        """Throw away unsaved edits and re-read the file."""
        if self._loaded_path is not None:
            self.open_path(self._loaded_path)

    def confirm_discard(self) -> bool:
        """Ask about unsaved edits before they are lost.

        Returns:
            Whether to go ahead with whatever prompted the question.
        """
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            f"Save your changes to {self.current_name()}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self._save_through_window()
        return True

    def _save_through_window(self) -> bool:
        """Save by way of the File menu's command, so untitled gets a dialog."""
        if self._save_handler is not None:
            return bool(self._save_handler())
        return self.save()

    # -- Running -----------------------------------------------------------

    def run(self) -> None:
        """Execute what is in the editor."""
        if not self._editor.toPlainText().strip():
            QMessageBox.information(
                self, "Run Script", "Nothing to run — the editor is empty."
            )
            return
        self._run_script(self.current_name(), self._editor.toPlainText())

    # -- Captions ----------------------------------------------------------

    def refresh(self) -> None:
        """Re-read what the captions report; the default folder may have moved."""
        self._set_dirty(self._dirty)

    def _text_changed(self) -> None:
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        has_text = bool(self._editor.toPlainText().strip())
        self._save_button.setEnabled(
            dirty and (has_text or self._loaded_path is not None)
        )
        self._revert_button.setEnabled(dirty and self._loaded_path is not None)
        if self._loaded_path is None and not has_text and not dirty:
            self._status_label.setText("")
        else:
            name = self.current_name()
            self._status_label.setText(f"{name} — modified" if dirty else name)
        self._update_where()

    def _update_where(self) -> None:
        """Say where the open script lives, or where a new one would go."""
        folder = scripts_dir()
        if self._loaded_path is None:
            self._where_label.setText(f"Default folder: {folder}")
            self._where_label.setToolTip(
                f"New scripts are saved here by default:\n{folder}"
            )
            return
        self._where_label.setText(self._loaded_path)
        self._where_label.setToolTip(
            f"Open script:\n{self._loaded_path}\n\nDefault folder:\n{folder}"
        )
