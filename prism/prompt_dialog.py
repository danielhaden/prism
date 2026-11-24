"""Writing the Assistant's instructions: the system prompts, by name.

What is edited here is the **role** — what the assistant is for, how to
answer, what not to do. The command reference is not here and cannot be
taken out: it is read off the interpreter and appended to whichever role is
in force, every turn, so no prompt written here can go stale against the
language (see :func:`prism.agent.prompt.system_prompt`).

Prism's own instructions are the first entry and are read-only. **New**
copies whatever is shown, so the way to a prompt of your own is to select
Prism's, press New, and edit — rather than face an empty box and have to
remember what the panel needs from a reply.
"""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from prism.agent.prompt import BUILTIN_PROMPT_NAME

#: What a new prompt is called before it is named something better.
NEW_PROMPT_NAME = "My instructions"


class PromptDialog(QDialog):
    """Make, rename, rewrite and delete the Assistant's system prompts.

    Nothing is written to the settings here. The dialog hands back the whole
    set and which one to use, and the panel stores them — so Cancel means
    what it says, however much was typed.
    """

    def __init__(self, prompts: list, chosen: str = "", parent: QWidget = None):
        """
        Args:
            prompts: The stored prompts, ``[{"name": …, "text": …}, …]``.
            chosen: The name in force, or ``""`` for Prism's own.
            parent: The usual.
        """
        super().__init__(parent)
        self.setWindowTitle("Assistant Instructions")
        self.resize(780, 560)

        #: The working copy: the built-in first, with ``text`` None, then the
        #: user's. Edited in place and only handed back on OK.
        self._prompts = [{"name": BUILTIN_PROMPT_NAME, "text": None}] + [
            {"name": entry["name"], "text": entry["text"]} for entry in prompts
        ]

        self._names = QListWidget()
        self._names.setMaximumWidth(220)
        self._names.currentRowChanged.connect(self._show_row)

        self._new_button = QPushButton("New")
        self._new_button.setToolTip("A new set of instructions, copied from these")
        self._new_button.clicked.connect(self.new_prompt)
        self._rename_button = QPushButton("Rename")
        self._rename_button.clicked.connect(self.rename_prompt)
        self._delete_button = QPushButton("Delete")
        self._delete_button.clicked.connect(self.delete_prompt)

        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(12)
        self._text = QPlainTextEdit()
        self._text.setFont(mono)
        self._text.setTabChangesFocus(True)
        self._text.textChanged.connect(self._text_edited)

        self._note = QLabel()
        self._note.setWordWrap(True)
        self._note.setStyleSheet("color: gray; font-size: 11px;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        side = QVBoxLayout()
        side.addWidget(self._names, 1)
        side.addWidget(self._new_button)
        side.addWidget(self._rename_button)
        side.addWidget(self._delete_button)

        editor = QVBoxLayout()
        editor.addWidget(self._text, 1)
        editor.addWidget(self._note)

        columns = QHBoxLayout()
        columns.addLayout(side)
        columns.addLayout(editor, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(columns, 1)
        layout.addWidget(buttons)

        self._refill(self._row_of(chosen))

    # -- The list ----------------------------------------------------------

    def _refill(self, row: int = 0) -> None:
        """Rebuild the list of names and select one.

        Args:
            row: Which to select; clamped into the list.
        """
        self._names.blockSignals(True)
        self._names.clear()
        self._names.addItems([entry["name"] for entry in self._prompts])
        self._names.setCurrentRow(max(0, min(row, len(self._prompts) - 1)))
        self._names.blockSignals(False)
        self._show_row(self._names.currentRow())

    def _row_of(self, name: str) -> int:
        """Where a prompt sits in the list now.

        Args:
            name: Its name, or ``""`` for Prism's own.

        Returns:
            The row, or 0 — Prism's own, which is what a name that is no
                longer there falls back to.
        """
        for row, entry in enumerate(self._prompts):
            if row and entry["name"] == name:
                return row
        return 0

    def _show_row(self, row: int) -> None:
        """Put a prompt in the editor.

        Args:
            row: Which one. Row 0 is Prism's own, shown read-only.
        """
        if not 0 <= row < len(self._prompts):
            return
        entry = self._prompts[row]
        builtin = entry["text"] is None
        self._text.blockSignals(True)
        self._text.setPlainText(self._shipped_text() if builtin else entry["text"])
        self._text.blockSignals(False)
        self._text.setReadOnly(builtin)
        self._rename_button.setEnabled(not builtin)
        self._delete_button.setEnabled(not builtin)
        self._note.setText(
            "Prism's own instructions, kept read-only — press New to start a"
            " set of your own from them. Prism's command reference is added"
            " to these every turn."
            if builtin else
            "Prism's command reference is added to this every turn, so there"
            " is no need to describe the language. Keep the part asking for"
            " one fenced “prism” block, though, or Send Script to"
            " Editor will have nothing to find."
        )

    def _text_edited(self) -> None:
        """Keep what is typed, so switching away and back does not lose it."""
        row = self._names.currentRow()
        if 0 < row < len(self._prompts):
            self._prompts[row]["text"] = self._text.toPlainText()

    def _shipped_text(self) -> str:
        """The instructions Prism ships, read from the code every time."""
        from prism.agent.prompt import ROLE

        return ROLE

    # -- Making and unmaking -----------------------------------------------

    def new_prompt(self) -> bool:
        """Add a set of instructions, copied from the one on screen.

        Copied rather than blank: the panel needs a reply in a particular
        shape — prose, then at most one fenced block — and the surest way to
        keep that is to start from text that already says so.

        Returns:
            Whether one was made.
        """
        name = self._ask_name("New Instructions", self._free_name())
        if name is None:
            return False
        self._prompts.append({"name": name, "text": self._text.toPlainText()})
        self._refill(len(self._prompts) - 1)
        self._text.setFocus()
        return True

    def rename_prompt(self) -> bool:
        """Give the selected instructions another name.

        Returns:
            Whether it was renamed.
        """
        row = self._names.currentRow()
        if not 0 < row < len(self._prompts):
            return False
        name = self._ask_name(
            "Rename Instructions", self._prompts[row]["name"], keeping=row
        )
        if name is None:
            return False
        self._prompts[row]["name"] = name
        self._refill(row)
        return True

    def delete_prompt(self) -> bool:
        """Forget the selected instructions.

        Returns:
            Whether it was deleted.
        """
        row = self._names.currentRow()
        if not 0 < row < len(self._prompts):
            return False
        answer = QMessageBox.question(
            self,
            "Delete Instructions",
            f"Delete “{self._prompts[row]['name']}”?\n\n"
            "The text goes with it.",
        )
        if answer != QMessageBox.Yes:
            return False
        del self._prompts[row]
        self._refill(min(row, len(self._prompts) - 1))
        return True

    def _ask_name(self, title: str, suggestion: str, keeping: int = -1):
        """Ask for a name, and keep asking while it won't do.

        A name must be something, must not be the built-in's — which would
        hide the one set that cannot be lost — and must not already be
        taken, since the panel's picker and the stored choice both go by
        name.

        Args:
            title: The dialog's title.
            suggestion: What to offer.
            keeping: A row allowed to keep its own name, for a rename that
                changes nothing but the capitals.

        Returns:
            The name, or None if the ask was cancelled.
        """
        while True:
            name, confirmed = QInputDialog.getText(
                self, title, "Name:", text=suggestion
            )
            if not confirmed:
                return None
            name = name.strip()
            taken = {
                entry["name"]
                for row, entry in enumerate(self._prompts)
                if row != keeping
            }
            if not name:
                complaint = "A set of instructions needs a name."
            elif name == BUILTIN_PROMPT_NAME:
                complaint = f"“{BUILTIN_PROMPT_NAME}” is Prism's own."
            elif name in taken:
                complaint = f"There is already a “{name}”."
            else:
                return name
            QMessageBox.information(self, title, complaint)
            suggestion = name

    def _free_name(self) -> str:
        """A name nothing has yet: ``My instructions``, then ``2``, ``3``…"""
        taken = {entry["name"] for entry in self._prompts}
        if NEW_PROMPT_NAME not in taken:
            return NEW_PROMPT_NAME
        number = 2
        while f"{NEW_PROMPT_NAME} {number}" in taken:
            number += 1
        return f"{NEW_PROMPT_NAME} {number}"

    # -- What comes back ---------------------------------------------------

    def prompts(self) -> list:
        """The user's prompts, Prism's own left out of it."""
        return [
            {"name": entry["name"], "text": entry["text"] or ""}
            for entry in self._prompts[1:]
        ]

    def chosen(self) -> str:
        """Which prompt was selected when OK was pressed, ``""`` for Prism's.

        The one being edited is the one wanted — having just written a set of
        instructions, nobody means to carry on without them.
        """
        row = self._names.currentRow()
        return "" if row <= 0 else self._prompts[row]["name"]

    @staticmethod
    def edit(prompts: list, chosen: str = "", parent: QWidget = None) -> tuple | None:
        """Show the dialog.

        Args:
            prompts: The stored prompts.
            chosen: The name in force, ``""`` for Prism's own.
            parent: The usual.

        Returns:
            ``(prompts, chosen)`` on OK, or None.
        """
        dialog = PromptDialog(prompts, chosen, parent)
        if dialog.exec() == QDialog.Accepted:
            return dialog.prompts(), dialog.chosen()
        return None
