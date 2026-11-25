"""The network call, off the GUI thread.

Qt's event loop must not block, and a turn can take a minute. The worker
owns the request and hands text back through signals, which Qt delivers on
the GUI thread — so nothing here ever touches the canvas or a widget.
"""

from PySide6.QtCore import QThread, Signal

from prism.agent.backends import AgentError


class AgentWorker(QThread):
    """One turn of the conversation, running away from the GUI thread."""

    #: A chunk of the reply.
    chunk = Signal(str)
    #: A chunk of the reasoning summary.
    thinking = Signal(str)
    #: The whole reply, and what it cost.
    done = Signal(str, dict)
    #: Something went wrong, said in a way worth showing.
    failed = Signal(str)

    def __init__(
        self, backend: object, system: str, messages: list, parent=None
    ):
        """
        Args:
            backend: What to ask; see :mod:`prism.agent.backends`.
            system: The standing instructions.
            messages: The conversation so far.
        """
        super().__init__(parent)
        self._backend = backend
        self._system = system
        self._messages = messages
        self._cancelled = False

    def cancel(self) -> None:
        """Ask the turn to stop at the next chunk."""
        self._cancelled = True

    def was_cancelled(self) -> bool:
        """Whether this turn was stopped rather than finished."""
        return self._cancelled

    def run(self) -> None:
        try:
            reply = self._backend.stream_turn(
                self._system,
                self._messages,
                self.chunk.emit,
                self.thinking.emit,
                lambda: self._cancelled,
            )
        except AgentError as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))
            return
        except Exception as exc:  # never take the app down with it
            if not self._cancelled:
                self.failed.emit(f"Unexpected error: {exc}")
            return
        if not self._cancelled:
            self.done.emit(reply["text"], reply["usage"])
