"""The dockable console: a CLI for inspecting and manipulating the canvas."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from prism.commands import CommandInterpreter


class _CommandInput(QLineEdit):
    """A single-line input with up/down command history."""

    def __init__(self, on_submit, parent=None):
        super().__init__(parent)
        self._on_submit = on_submit
        self._history: list[str] = []
        self._index = 0
        self.setPlaceholderText("Type a command, e.g. (add horizon 1/3) - Enter to run")
        self.returnPressed.connect(self._submit)

    def _submit(self):
        text = self.text()
        if text.strip():
            self._history.append(text)
        self._index = len(self._history)
        self.clear()
        self._on_submit(text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            self._recall(-1)
        elif event.key() == Qt.Key_Down:
            self._recall(1)
        else:
            super().keyPressEvent(event)

    def _recall(self, step: int):
        if not self._history:
            return
        self._index = max(0, min(len(self._history), self._index + step))
        self.setText(self._history[self._index] if self._index < len(self._history) else "")


class ConsolePanel(QDockWidget):
    """A command line over the canvas, with the session recordable as a script."""

    def __init__(self, scene, parent=None):
        super().__init__("Console", parent)
        self.setObjectName("ConsolePanel")
        self._interpreter = CommandInterpreter(scene)
        #: Successful, building commands from this session, in order.
        self._recorded: list[str] = []
        self._recording = True
        #: Set by MainWindow: where >> sends them. Callable taking the list
        #: and returning the name of the script it went into, or None.
        self._append_handler = None

        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(mono)

        self._input = _CommandInput(self.run_command)
        self._input.setFont(mono)

        self._append_button = QPushButton(">>")
        self._append_button.setFixedWidth(36)
        self._append_button.setToolTip(
            "Append this session's commands to the script in the Scripts "
            "panel, and start a fresh session"
        )
        self._append_button.clicked.connect(self.append_to_script)

        entry = QHBoxLayout()
        entry.addWidget(self._input)
        entry.addWidget(self._append_button)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._output)
        layout.addLayout(entry)
        self.setWidget(container)

        self._output.appendPlainText(
            "Prism console. Commands are S-expressions, e.g. (add horizon 1/3).\n"
            "Type (help) for the list."
        )

    # -- Running -----------------------------------------------------------

    def run_command(self, line: str) -> None:
        """Echo and execute one command line."""
        self._echo(f"> {line}")
        output, ok = self._interpreter.run(line)
        if output:
            self._echo(output)
        if ok and self._recording and self._interpreter.is_recordable(line):
            self._recorded.append(line.strip())

    def interpreter(self):
        """The command interpreter, for panels that read the language off it.

        The Assistant builds its reference from ``(help)`` and its canvas
        context from ``(ls)``, so the two cannot drift from the forms that
        actually exist.

        Returns:
            The :class:`~prism.commands.CommandInterpreter`.
        """
        return self._interpreter

    def variables(self) -> dict:
        """The names bound with ``(define …)``, for panels that show them."""
        return self._interpreter.variables()

    def run_script(self, name: str, text: str) -> None:
        """Execute a script's commands, echoing them to the console.

        A script's own commands aren't recorded, so replaying one doesn't
        duplicate it into the next thing you save.
        """
        self._echo(f"--- running script: {name} ---")
        self._recording = False
        try:
            for raw in text.splitlines():
                line = raw.strip()
                if not line or line.startswith(";"):
                    continue
                self.run_command(line)
        finally:
            self._recording = True
        self._echo(f"--- end of {name} ---")

    def recorded_commands(self) -> list:
        return list(self._recorded)

    # -- Handing the session on ---------------------------------------------

    def set_append_handler(self, handler) -> None:
        """Say where **>>** sends the session's commands.

        Args:
            handler: Callable taking the list of commands and returning the
                name of the script they went into, or None if they didn't.
        """
        self._append_handler = handler

    def append_to_script(self) -> bool:
        """Put the session's commands at the end of the open script.

        What you did by clicking and typing becomes text you can edit, run
        and keep. The session's record is **emptied** afterwards, so pressing
        it again appends only what you have done since rather than a second
        copy of everything.

        Returns:
            Whether anything was appended.
        """
        if not self._recorded:
            QMessageBox.information(
                self,
                "Append to Script",
                "Nothing to append yet — run some commands that build "
                "something first.",
            )
            return False
        if self._append_handler is None:
            QMessageBox.information(
                self,
                "Append to Script",
                "There is nowhere to put them: the Scripts panel isn't here.",
            )
            return False
        count = len(self._recorded)
        name = self._append_handler(list(self._recorded))
        if name is None:
            return False
        self._recorded.clear()
        self._echo(f"Appended {count} command(s) to {name}.")
        return True

    # -- Internal ----------------------------------------------------------

    def _echo(self, text: str) -> None:
        self._output.appendPlainText(text)
        self._output.verticalScrollBar().setValue(
            self._output.verticalScrollBar().maximum()
        )

    # Kept for existing callers/tests.
    def _run(self, line: str) -> None:
        self.run_command(line)
