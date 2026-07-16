"""The dockable console: a CLI for inspecting and manipulating the canvas."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from prism.commands import CommandInterpreter
from prism.settings import save_script


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

    #: Emitted after a script is saved, so the Scripts panel can refresh.
    scriptSaved = Signal()

    def __init__(self, scene, parent=None):
        super().__init__("Console", parent)
        self.setObjectName("ConsolePanel")
        self._interpreter = CommandInterpreter(scene)
        #: Successful, building commands from this session, in order.
        self._recorded: list[str] = []
        self._recording = True

        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(mono)

        self._input = _CommandInput(self.run_command)
        self._input.setFont(mono)

        self._save_button = QPushButton("Save Script…")
        self._save_button.setToolTip(
            "Save this session's commands to the scripts folder"
        )
        self._save_button.clicked.connect(self._save_script)

        entry = QHBoxLayout()
        entry.addWidget(self._input)
        entry.addWidget(self._save_button)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._output)
        layout.addLayout(entry)
        self.setWidget(container)

        self._output.appendPlainText(
            "Prism console. Commands are S-expressions, e.g. (add horizon 1/3).\n"
            "Reference an element by quoting its id or label ('L1, 'A). "
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

    # -- Saving ------------------------------------------------------------

    def _save_script(self) -> None:
        if not self._recorded:
            QMessageBox.information(
                self,
                "Save Script",
                "Nothing to save yet — run some commands that build "
                "something first.",
            )
            return
        name, ok = QInputDialog.getText(self, "Save Script", "Script name:")
        if not (ok and name.strip()):
            return
        body = "\n".join(self._recorded)
        try:
            path = save_script(name.strip(), body)
        except OSError as exc:
            QMessageBox.warning(self, "Save Script", f"Couldn't save it: {exc}")
            return
        self._echo(f"Saved {len(self._recorded)} command(s) to {path}")
        self.scriptSaved.emit()

    # -- Internal ----------------------------------------------------------

    def _echo(self, text: str) -> None:
        self._output.appendPlainText(text)
        self._output.verticalScrollBar().setValue(
            self._output.verticalScrollBar().maximum()
        )

    # Kept for existing callers/tests.
    def _run(self, line: str) -> None:
        self.run_command(line)
