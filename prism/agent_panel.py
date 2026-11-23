"""The dockable Assistant: a conversation that writes scripts.

It never touches the canvas. What it produces is a **script**, which goes to
the Scripts panel for you to read and run — the same thing you would have
written yourself, and reviewable before anything happens. That is why this
needs no approval dialogs and cannot wreck a drawing.
"""

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from prism.agent.backends import ClaudeBackend
from prism.agent.prompt import canvas_context, extract_script, system_prompt
from prism.agent.worker import AgentWorker


class _AskInput(QPlainTextEdit):
    """A few lines to type in. Enter sends; Shift+Enter makes a new line."""

    submitted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(
            "Ask for a construction, or about the drawing. Enter to send."
        )
        self.setFixedHeight(64)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
                return
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class AgentPanel(QDockWidget):
    """Talk to Claude about the drawing; keep what it writes."""

    def __init__(self, interpreter_source: Callable, parent=None):
        """
        Args:
            interpreter_source: Callable returning the console's interpreter,
                which supplies both the command reference and the canvas
                listing. A callable rather than the object, so the panel can
                be built before the console if the order ever changes.
        """
        super().__init__("Assistant", parent)
        self.setObjectName("AgentPanel")
        self._interpreter_source = interpreter_source
        self._backend = ClaudeBackend()
        self._script_sink = None
        self._worker = None
        #: The conversation, as the API wants it.
        self._messages: list = []
        #: The script in the last reply, if it carried one.
        self._script: str | None = None
        self._pending_prose = ""

        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)

        self._transcript = QPlainTextEdit()
        self._transcript.setReadOnly(True)
        self._transcript.setFont(mono)

        self._input = _AskInput()
        self._input.setFont(mono)
        self._input.submitted.connect(self.send)

        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self.send)

        self._stop_button = QPushButton("Stop")
        self._stop_button.setToolTip("Give up on the reply being written")
        self._stop_button.clicked.connect(self.stop)
        self._stop_button.setEnabled(False)

        self._keep_button = QPushButton("Send Script to Editor")
        self._keep_button.setToolTip(
            "Put the script from the last reply in the Scripts panel, to read "
            "and run"
        )
        self._keep_button.clicked.connect(self.keep_script)
        self._keep_button.setEnabled(False)

        self._clear_button = QPushButton("New Chat")
        self._clear_button.setToolTip("Forget the conversation and start again")
        self._clear_button.clicked.connect(self.clear_chat)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: gray; font-size: 11px;")

        buttons = QHBoxLayout()
        buttons.addWidget(self._send_button)
        buttons.addWidget(self._stop_button)
        buttons.addWidget(self._keep_button)
        buttons.addWidget(self._clear_button)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._transcript)
        layout.addWidget(self._input)
        layout.addLayout(buttons)
        layout.addWidget(self._status)
        self.setWidget(container)

        self._greet()

    # -- Wiring ------------------------------------------------------------

    def set_script_sink(self, handler: Callable) -> None:
        """Say where a kept script goes.

        Args:
            handler: Callable taking the script's lines and returning the
                name of the script they went into, or None.
        """
        self._script_sink = handler

    def set_backend(self, backend) -> None:
        """Swap what answers — a test stands a fake in here."""
        self._backend = backend

    # -- The conversation --------------------------------------------------

    def send(self) -> bool:
        """Put the question to the assistant.

        Returns:
            Whether a turn was started.
        """
        if self._worker is not None:
            return False
        asked = self._input.toPlainText().strip()
        if not asked:
            return False
        self._input.clear()
        self._say("you", asked)
        context = canvas_context(self._interpreter())
        self._messages.append(
            {"role": "user", "content": f"{context}\n\n{asked}".strip()}
        )
        self._script = None
        self._keep_button.setEnabled(False)
        self._pending_prose = ""
        self._begin("Thinking…")
        self._worker = AgentWorker(
            self._backend, system_prompt(self._interpreter()), list(self._messages)
        )
        self._worker.chunk.connect(self._on_chunk)
        self._worker.thinking.connect(self._on_thinking)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._forget_worker)
        self._append("\nclaude  ")
        self._worker.start()
        return True

    def stop(self) -> None:
        """Give up on the reply being written."""
        if self._worker is None:
            return
        self._worker.cancel()
        # The turn is dropped rather than half-kept: a reply cut off mid-script
        # would be sent back as context next turn and read as a finished one.
        if self._messages and self._messages[-1]["role"] == "user":
            self._messages.pop()
        self._append("\n  — stopped.\n")
        self._end("Stopped.")

    def clear_chat(self) -> None:
        """Forget the conversation; the canvas is untouched."""
        if self._worker is not None:
            self.stop()
        self._messages.clear()
        self._script = None
        self._keep_button.setEnabled(False)
        self._transcript.clear()
        self._greet()

    def keep_script(self) -> bool:
        """Put the last reply's script in the Scripts panel.

        Returns:
            Whether it went anywhere.
        """
        if self._script is None or self._script_sink is None:
            return False
        lines = [line for line in self._script.splitlines() if line.strip()]
        name = self._script_sink(lines)
        if name is None:
            return False
        self._status.setText(f"{len(lines)} line(s) added to {name}.")
        return True

    def shutdown(self) -> None:
        """Stop a turn in flight, so the app can close without a warning."""
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(2000)

    # -- What came back ----------------------------------------------------

    def _on_chunk(self, text: str) -> None:
        self._pending_prose += text
        self._append(text)

    def _on_thinking(self, text: str) -> None:
        # Shown, and not kept: it is there so a long think doesn't read as a
        # hang, and it is the model's working rather than its answer.
        self._status.setText("Thinking… " + text.strip()[-90:])

    def _on_done(self, text: str, usage: dict) -> None:
        self._messages.append({"role": "assistant", "content": text})
        self._script = extract_script(text)
        self._keep_button.setEnabled(
            self._script is not None and self._script_sink is not None
        )
        self._append("\n")
        self._end(self._cost(usage))

    def _on_failed(self, message: str) -> None:
        # The question goes back out of the history: leaving it there would
        # send it again, unanswered, on top of the next one.
        if self._messages and self._messages[-1]["role"] == "user":
            self._messages.pop()
        self._append(f"\n  — {message}\n")
        self._end(message)

    def _forget_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()
        self._send_button.setEnabled(True)
        self._stop_button.setEnabled(False)

    # -- The transcript ----------------------------------------------------

    def _greet(self) -> None:
        self._append(
            "Prism assistant. Ask for a construction and it writes a script;\n"
            "read it, then send it to the Scripts panel to run.\n"
        )
        if not ClaudeBackend.looks_configured():
            self._status.setText(
                "No ANTHROPIC_API_KEY in the environment. Set one, or run "
                "`ant auth login`, then try — Prism never stores it."
            )
        else:
            self._status.setText(f"Claude · {self._backend.model}")

    def _say(self, who: str, text: str) -> None:
        self._append(f"\n{who:<7} {text}\n")

    def _append(self, text: str) -> None:
        cursor = self._transcript.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self._transcript.setTextCursor(cursor)
        self._transcript.ensureCursorVisible()

    def _begin(self, note: str) -> None:
        self._send_button.setEnabled(False)
        self._stop_button.setEnabled(True)
        self._status.setText(note)

    def _end(self, note: str) -> None:
        self._send_button.setEnabled(True)
        self._stop_button.setEnabled(False)
        self._status.setText(note)

    def _cost(self, usage: dict) -> str:
        """What the turn cost, as a line under the transcript.

        Args:
            usage: Token counts from the backend.

        Returns:
            A short line, or the plain model name when there are none.
        """
        if not usage:
            return f"Claude · {self._backend.model}"
        cached = f", {usage['cached']} cached" if usage.get("cached") else ""
        return (
            f"Claude · {self._backend.model} · "
            f"{usage.get('input', 0)} in{cached}, {usage.get('output', 0)} out"
        )

    def _interpreter(self):
        return self._interpreter_source()
