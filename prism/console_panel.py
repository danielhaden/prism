"""The dockable console: a CLI for inspecting and manipulating the canvas."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QLineEdit,
    QPlainTextEdit,
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
    def __init__(self, scene, parent=None):
        super().__init__("Console", parent)
        self.setObjectName("ConsolePanel")
        self._interpreter = CommandInterpreter(scene)

        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(mono)

        self._input = _CommandInput(self._run)
        self._input.setFont(mono)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._output)
        layout.addWidget(self._input)
        self.setWidget(container)

        self._output.appendPlainText(
            "Prism console. Commands are S-expressions, e.g. (add horizon 1/3).\n"
            "Type (help) for the list."
        )

    def _run(self, line: str) -> None:
        self._output.appendPlainText(f"> {line}")
        result = self._interpreter.execute(line)
        if result:
            self._output.appendPlainText(result)
        self._output.verticalScrollBar().setValue(
            self._output.verticalScrollBar().maximum()
        )
