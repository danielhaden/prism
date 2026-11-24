"""The dockable Assistant: a conversation that writes scripts.

It never touches the canvas. What it produces is a **script**, which goes to
the Scripts panel for you to read and run — the same thing you would have
written yourself, and reviewable before anything happens. That is why this
needs no approval dialogs and cannot wreck a drawing.
"""

from typing import Callable

from PySide6.QtCore import QRectF, QRegularExpression, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QSyntaxHighlighter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from prism.agent.backends import (
    CLAUDE_MODELS,
    ClaudeBackend,
    OllamaBackend,
    ollama_models,
)
from prism.agent.prompt import (
    BUILTIN_PROMPT_NAME,
    canvas_context,
    check_script,
    extract_script,
    system_prompt,
)
from prism.agent.worker import AgentWorker
from prism.prompt_dialog import PromptDialog
from prism.settings import (
    assistant_choice,
    assistant_prompt_name,
    assistant_prompt_text,
    assistant_prompts,
    set_assistant_choice,
    set_assistant_prompt_name,
    set_assistant_prompts,
)


#: Prose, in order of preference. Anthropic's own text face is Tiempos
#: Text, which is licensed and not on anyone's machine by default; Charter
#: is the closest thing that is — Matthew Carter drew it for screens, and it
#: is a book serif of the same cast. The rest are fallbacks per platform.
PROSE_FAMILIES = (
    "Tiempos Text",
    "Charter",
    "Iowan Old Style",
    "Palatino",
    "Georgia",
    "serif",
)

#: Lines that are a speaker's name and nothing else; set in bold so a turn
#: can be found at a glance.
SPEAKERS = ("You", "Claude", "Ollama", "Assistant")

#: Scripts, which want the alignment and the unambiguous glyphs.
CODE_FAMILIES = ("Menlo", "SF Mono", "Consolas", "DejaVu Sans Mono", "monospace")

#: Prose is read; code is scanned. A point smaller keeps a long command on
#: one line in a narrow dock.
PROSE_POINT_SIZE = 14
CODE_POINT_SIZE = 12

#: The Claude desktop app's warm palette, matched by eye: a bone page, the
#: question in a light clay bubble, near-black warm ink rather than pure
#: black. Light only — Prism's other panels don't follow the system theme
#: either, and a half-done dark mode is worse than none.
PAPER = "#faf9f5"
BUBBLE = "#f0eee6"
CARD = "#f5f4ee"
CARD_EDGE = "#e7e4d9"
INK = "#141413"
QUIET = "#8a8780"
FENCE_INK = "#b8b5ab"

#: Which side of the conversation a line belongs to, kept as a property of
#: its **block format**. The highlighter already uses the block *state* for
#: fences, and Qt gives a block format arbitrary properties, so the two sit
#: side by side without either having to know about the other.
ROLE_PROPERTY = QTextFormat.UserProperty + 1
ASKED = 1       # the question: right, in a bubble
ANSWERED = 2    # the reply: left, on the page itself
NOTE = 3        # Prism's own words, neither side's

#: The bubble's padding, corner, and how much of the width it leaves alone
#: before a question wraps — a question that ran the full width would read
#: as the reply does, which is the one thing the bubble is there to prevent.
BUBBLE_PAD_X = 11
BUBBLE_PAD_Y = 7
BUBBLE_RADIUS = 14
BUBBLE_INSET = 64
#: Air between one turn and the next.
TURN_GAP = 12
#: A script sits on a card of its own, as it does in the desktop app.
CARD_RADIUS = 8
CARD_PAD_X = 9
CARD_PAD_Y = 5
#: Room down each side of the page, which is also what a card is padded into.
PAGE_MARGIN = 12


def _font(families, point_size: int) -> QFont:
    """A font from the first of ``families`` that exists.

    Args:
        families: Family names, most wanted first.
        point_size: The size to set.

    Returns:
        The font.
    """
    font = QFont()
    font.setFamilies(list(families))
    font.setPointSize(point_size)
    return font


class _Transcript(QSyntaxHighlighter):
    """Draws the parts of a reply in the faces they want.

    The transcript holds two kinds of writing at once — prose to read and a
    script to scan — and one font cannot serve both. A highlighter does it
    without the document ceasing to be plain text, so what is on screen is
    still exactly what came back.
    """

    #: What opens and closes a script in a reply.
    FENCE = QRegularExpression(r"^\s*```")

    #: Inside a fenced block, as a block state.
    IN_SCRIPT = 1
    #: The fence that **closes** one. It needs a state of its own so the card
    #: drawn behind a script can include it, while the line after it still
    #: reads the state before it as "not in a script".
    END_SCRIPT = 2

    def __init__(self, document):
        super().__init__(document)
        self._code = QTextCharFormat()
        self._code.setFontFamilies(list(CODE_FAMILIES))
        self._code.setFontPointSize(CODE_POINT_SIZE)

        self._fence = QTextCharFormat()
        self._fence.setFontFamilies(list(CODE_FAMILIES))
        self._fence.setFontPointSize(CODE_POINT_SIZE)
        self._fence.setForeground(QColor(FENCE_INK))

        # A label, not a heading: the desktop app shows no name at all, and
        # this one is here only because the answer may come from Claude or
        # from a model on this machine, and which it was is not a detail.
        self._speaker = QTextCharFormat()
        self._speaker.setFontWeight(QFont.Bold)
        self._speaker.setFontPointSize(11)
        self._speaker.setForeground(QColor(QUIET))

        self._aside = QTextCharFormat()
        self._aside.setForeground(QColor(QUIET))
        self._aside.setFontItalic(True)

    def highlightBlock(self, text: str) -> None:
        role = self.currentBlock().blockFormat().intProperty(ROLE_PROPERTY)
        if role == ASKED:
            # The question is the person's own words in their own bubble:
            # nothing in it is a speaker's name or a script of ours, and a
            # stray ``` they typed must not open a card.
            self.setCurrentBlockState(0)
            return
        if role == NOTE:
            self.setFormat(0, len(text), self._aside)
            self.setCurrentBlockState(0)
            return
        was_script = self.previousBlockState() == self.IN_SCRIPT
        if self.FENCE.match(text).hasMatch():
            self.setFormat(0, len(text), self._fence)
            self.setCurrentBlockState(
                self.END_SCRIPT if was_script else self.IN_SCRIPT
            )
            return
        self.setCurrentBlockState(self.IN_SCRIPT if was_script else 0)
        if was_script:
            self.setFormat(0, len(text), self._code)
        elif text in SPEAKERS:
            self.setFormat(0, len(text), self._speaker)
        elif text.startswith("  — ") or text.startswith("      "):
            # What Prism itself says about a reply, rather than the reply.
            self.setFormat(0, len(text), self._aside)


class _TranscriptView(QTextEdit):
    """The conversation: the question on the right, the reply on the left.

    Which side a line falls on is a property of its block format, so the
    document is still **plain text** — ``toPlainText()`` returns exactly what
    came back, which is what the Send Script to Editor path reads. Alignment
    and margins are Qt's; the rounded bubble is not, since no text block can
    have a corner radius, so it is painted behind the glyphs here.

    The bubble **hugs its text** rather than filling the column: it is drawn
    from the widest line in the run, not from the block width, which is why
    this walks the laid-out lines rather than taking a bounding rect.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fitting = False
        self.setReadOnly(True)
        self.setFrameShape(QFrame.NoFrame)
        # The page's own margin, and it has to be wide enough for a card to
        # be padded outwards into: a script's lines are laid out by the
        # document, so the only room its card has to breathe is here.
        self.document().setDocumentMargin(PAGE_MARGIN)
        self.setStyleSheet(
            f"QTextEdit {{ background: {PAPER}; color: {INK}; "
            f"selection-background-color: #e3ded0; "
            f"selection-color: {INK}; }}"
        )

    # -- Writing it --------------------------------------------------------

    def start_turn(self, role: int) -> None:
        """Begin a new turn, on the side `role` belongs to.

        Args:
            role: ASKED, ANSWERED or NOTE.
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self.document().isEmpty():
            cursor.insertBlock()
        cursor.setBlockFormat(self._shape(role, opening=True))
        cursor.setCharFormat(QTextCharFormat())
        self.setTextCursor(cursor)

    def add(self, text: str) -> None:
        """Put text at the end of the turn in progress.

        Newlines are inserted as blocks of their own rather than left to Qt,
        which would hand each one the opening block's top margin and space a
        bubble's own lines as though each were a new turn.

        Args:
            text: What to add; may hold newlines, and arrives a chunk at a
                time while a reply streams.
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        role = cursor.blockFormat().intProperty(ROLE_PROPERTY)
        for index, piece in enumerate(text.split("\n")):
            if index:
                cursor.insertBlock(self._shape(role, opening=False))
            cursor.insertText(piece)
        self.setTextCursor(cursor)
        if role == ASKED:
            self._fit_bubbles()
        self.ensureCursorVisible()

    def _shape(self, role: int, opening: bool) -> QTextBlockFormat:
        """How a line of this turn sits on the page.

        Args:
            role: ASKED, ANSWERED or NOTE.
            opening: Whether it is the turn's first line, which is the only
                one that carries the gap from the turn before.

        Returns:
            The block format.
        """
        shape = QTextBlockFormat()
        shape.setProperty(ROLE_PROPERTY, role)
        shape.setTopMargin(TURN_GAP if opening else 0)
        shape.setAlignment(Qt.AlignLeft)
        if role == ASKED:
            # Flush left *within the bubble*; what puts the bubble on the
            # right is the left margin, which _fit_bubbles then pulls in to
            # the width of this particular question.
            shape.setLeftMargin(BUBBLE_INSET)
            shape.setRightMargin(BUBBLE_PAD_X)
        return shape

    # -- Fitting a bubble to its question ----------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_bubbles()

    def _fit_bubbles(self) -> None:
        """Pull each question's bubble in to the width of its own text.

        A bubble hugs its text *and* its text reads flush left inside it, and
        no single block alignment gives both: right-aligning the lines hugs
        the bubble but leaves every line ragged down its left edge, which is
        the one thing a bubble is not. So the lines are set flush left and
        the **left margin** is what puts the bubble on the right.

        Each run is measured at full bubble width and then given the margin
        that leaves room for its widest line and no more. Widening a block
        can't make it wrap, so a single pass settles it; a question that
        wrapped anyway is already as wide as it is allowed to be.
        """
        if self._fitting:
            return
        self._fitting = True
        try:
            runs = list(self._question_runs())
            for run in runs:
                self._set_margin(run, BUBBLE_INSET)
            # Force the layout, so what is measured next is this width.
            self.document().documentLayout().documentSize()
            for run in runs:
                self._set_margin(run, self._margin_for(run))
        finally:
            self._fitting = False

    def _question_runs(self):
        """Each question, as the list of blocks it occupies."""
        run: list = []
        block = self.document().firstBlock()
        while block.isValid():
            if block.blockFormat().intProperty(ROLE_PROPERTY) == ASKED:
                run.append(block)
            elif run:
                yield run
                run = []
            block = block.next()
        if run:
            yield run

    def _margin_for(self, run: list) -> float:
        """How far from the left this question's bubble should start.

        Args:
            run: The question's blocks.

        Returns:
            The left margin in pixels.
        """
        if any(block.layout().lineCount() > 1 for block in run):
            return BUBBLE_INSET  # it filled the bubble; nothing to pull in
        widest = 0.0
        for block in run:
            layout = block.layout()
            for index in range(layout.lineCount()):
                widest = max(widest, layout.lineAt(index).naturalTextRect().width())
        document = self.document()
        room = (
            document.textWidth()
            - 2 * document.documentMargin()
            - BUBBLE_PAD_X
            - widest
            - 1  # a pixel of slack, so re-laying out can't wrap it
        )
        return max(BUBBLE_INSET, room)

    def _set_margin(self, run: list, margin: float) -> None:
        """Give every line of one question the same left margin.

        Args:
            run: The question's blocks.
            margin: The margin in pixels.
        """
        if not run or run[0].blockFormat().leftMargin() == margin:
            return
        cursor = QTextCursor(run[0])
        cursor.setPosition(
            run[-1].position() + max(run[-1].length() - 1, 0), QTextCursor.KeepAnchor
        )
        shape = QTextBlockFormat()
        shape.setLeftMargin(margin)
        cursor.mergeBlockFormat(shape)

    # -- Drawing it --------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        for rect, role in self._cards():
            if role == ASKED:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(BUBBLE))
                painter.drawRoundedRect(rect, BUBBLE_RADIUS, BUBBLE_RADIUS)
            else:
                painter.setPen(QColor(CARD_EDGE))
                painter.setBrush(QColor(CARD))
                painter.drawRoundedRect(
                    rect.adjusted(0.5, 0.5, -0.5, -0.5), CARD_RADIUS, CARD_RADIUS
                )
        painter.end()
        super().paintEvent(event)

    def _cards(self) -> list:
        """What to draw behind the text, as ``(rect, role)`` in viewport pixels.

        A run of consecutive lines of one kind is one shape — a question
        typed over three lines is a single bubble, not three — so this walks
        the document gathering runs and measures each as a whole.

        Returns:
            The shapes, in document order.
        """
        shapes: list = []
        run: list = []
        kind = None
        block = self.document().firstBlock()
        while block.isValid():
            here = self._kind_of(block)
            if here != kind:
                shapes.extend(self._shape_for(kind, run))
                run, kind = [], here
            if here is not None:
                run.append(block)
            block = block.next()
        shapes.extend(self._shape_for(kind, run))
        return shapes

    def _kind_of(self, block: object) -> object:
        """Which shape, if any, a line wants behind it.

        Args:
            block: The text block.

        Returns:
            ASKED, ANSWERED for a script of the reply's, or None.
        """
        role = block.blockFormat().intProperty(ROLE_PROPERTY)
        if role == ASKED:
            return ASKED
        if block.userState() in (_Transcript.IN_SCRIPT, _Transcript.END_SCRIPT):
            return ANSWERED
        return None

    def _shape_for(self, kind: object, run: list) -> list:
        """Measure one run of lines.

        Args:
            kind: ASKED, ANSWERED or None.
            run: The blocks, in order.

        Returns:
            A one-element ``[(rect, kind)]``, or nothing at all.
        """
        if kind is None or not run:
            return []
        hug = kind == ASKED
        extent = None
        for block in run:
            rect = self._extent_of(block, hug)
            if rect is None:
                continue
            extent = rect if extent is None else extent.united(rect)
        if extent is None or extent.isEmpty():
            return []
        if hug:
            # Only the *left* edge hugs the text. The right is the column's
            # own edge, so a question long enough to wrap is a rectangle
            # rather than a bubble with a ragged right side — the lines end
            # where they happen to break, and the shape behind them should
            # not.
            extent.setRight(max(extent.right(), self._column_right()))
            return [(extent.adjusted(-BUBBLE_PAD_X, -BUBBLE_PAD_Y,
                                     BUBBLE_PAD_X, BUBBLE_PAD_Y), kind)]
        return [(extent.adjusted(-CARD_PAD_X, -CARD_PAD_Y,
                                 CARD_PAD_X, CARD_PAD_Y), kind)]

    def _column_right(self) -> float:
        """The right edge a question is set against, in viewport pixels."""
        document = self.document()
        return (
            document.textWidth()
            - document.documentMargin()
            - BUBBLE_PAD_X
            - self.horizontalScrollBar().value()
        )

    def _extent_of(self, block: object, hug: bool) -> object:
        """Where a line's glyphs actually are, in viewport pixels.

        Args:
            block: The text block.
            hug: Whether to measure the glyphs (a bubble, which fits its
                text) or the whole column (a card, which does not).

        Returns:
            The rect, or None for a block with no layout yet.
        """
        box = self.document().documentLayout().blockBoundingRect(block)
        box = box.translated(
            -self.horizontalScrollBar().value(), -self.verticalScrollBar().value()
        )
        if not hug:
            return box
        layout = block.layout()
        extent = None
        for index in range(layout.lineCount()):
            line = layout.lineAt(index).naturalTextRect().translated(box.topLeft())
            if line.width() <= 0:
                continue
            extent = line if extent is None else extent.united(line)
        if extent is None:
            # An empty line inside a bubble still holds the bubble open.
            return QRectF(box.right(), box.top(), 0.0, box.height())
        return extent


class _AskInput(QPlainTextEdit):
    """A few lines to type in. Enter sends; Shift+Enter makes a new line."""

    submitted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(
            "Ask for a construction, or about the drawing. Enter to send."
        )
        self.setFixedHeight(68)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: #ffffff; color: {INK}; "
            f"border: 1px solid {CARD_EDGE}; border-radius: 12px; "
            f"padding: 7px 9px; }}"
        )

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
                return
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class _ModelBox(QComboBox):
    """The model picker. Re-asks Ollama what it has each time it is opened.

    Ollama may be started, stopped or pulled from while Prism is running, so
    a list built once at launch is wrong as often as not.
    """

    reopened = Signal()

    def showPopup(self):
        self.reopened.emit()
        super().showPopup()


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
        self._backend = None
        self._script_sink = None
        self._worker = None
        #: The conversation, as the API wants it.
        self._messages: list = []
        #: The script in the last reply, if it carried one.
        self._script: str | None = None
        self._pending_prose = ""

        prose = _font(PROSE_FAMILIES, PROSE_POINT_SIZE)

        self._transcript = _TranscriptView()
        self._transcript.setFont(prose)
        self._transcript.setViewportMargins(2, 4, 2, 4)
        self._highlighter = _Transcript(self._transcript.document())

        self._input = _AskInput()
        self._input.setFont(prose)
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

        self._prompts = QComboBox()
        self._prompts.setToolTip(
            "Which standing instructions the model is given — its system "
            "prompt. Prism's command reference is added to them every turn, "
            "whichever is chosen."
        )
        self._prompts.activated.connect(self._prompt_chosen)

        self._edit_prompts_button = QPushButton("Edit…")
        self._edit_prompts_button.setToolTip(
            "Write, rename or delete sets of instructions"
        )
        self._edit_prompts_button.clicked.connect(self.edit_prompts)

        self._models = _ModelBox()
        self._models.setToolTip(
            "Which model answers. Ollama runs on this machine and needs no "
            "account; Claude needs an API key in the environment."
        )
        self._models.reopened.connect(self._refresh_models)
        self._models.activated.connect(self._model_chosen)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: gray; font-size: 11px;")

        instructions = QHBoxLayout()
        instructions.setContentsMargins(0, 0, 0, 0)
        instructions.addWidget(self._prompts, 1)
        instructions.addWidget(self._edit_prompts_button)

        picker = QFormLayout()
        picker.setContentsMargins(0, 0, 0, 0)
        picker.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        picker.addRow("Model", self._models)
        picker.addRow("Instructions", instructions)

        buttons = QHBoxLayout()
        buttons.addWidget(self._send_button)
        buttons.addWidget(self._stop_button)
        buttons.addWidget(self._keep_button)
        buttons.addWidget(self._clear_button)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._transcript)
        layout.addLayout(picker)
        layout.addWidget(self._input)
        layout.addLayout(buttons)
        layout.addWidget(self._status)
        self.setWidget(container)

        self._refresh_models()
        self._refresh_prompts()
        self._greet()

    # -- Which model answers -----------------------------------------------

    def _refresh_models(self) -> None:
        """Rebuild the picker from what is actually available.

        Ollama first, because it needs no account and is what most people
        will have to hand; Claude after it, always offered, since a missing
        key is something to be told about rather than hidden from.
        """
        chosen = self._choice()
        self._models.blockSignals(True)
        self._models.clear()
        for name in ollama_models():
            self._models.addItem(f"Ollama · {name}", ("ollama", name))
        for name in CLAUDE_MODELS:
            self._models.addItem(f"Claude · {name}", ("claude", name))
        if self._models.count() == 0:
            self._models.addItem("No model available", None)
        index = self._index_of(chosen)
        self._models.setCurrentIndex(index)
        self._models.blockSignals(False)
        self._adopt(self._models.itemData(index))

    def _index_of(self, choice: str) -> int:
        """Where a remembered choice sits in the picker now.

        Args:
            choice: ``provider:model``.

        Returns:
            Its row, or 0 — the first Ollama model if there is one, which is
                the right default for someone with no API key.
        """
        if choice and ":" in choice:
            provider, model = choice.split(":", 1)
            for row in range(self._models.count()):
                if self._models.itemData(row) == (provider, model):
                    return row
        return 0

    def _choice(self) -> str:
        """The current choice as ``provider:model``, for remembering."""
        data = self._models.itemData(self._models.currentIndex())
        if data:
            return f"{data[0]}:{data[1]}"
        return assistant_choice()

    def _model_chosen(self, index: int) -> None:
        data = self._models.itemData(index)
        self._adopt(data)
        if data:
            set_assistant_choice(f"{data[0]}:{data[1]}")
        self._greet_status()

    def _adopt(self, data) -> None:
        """Make the backend the picker now names.

        Args:
            data: ``(provider, model)``, or None when nothing is available.
        """
        if not data:
            self._backend = None
            return
        provider, model = data
        self._backend = (
            OllamaBackend(model) if provider == "ollama" else ClaudeBackend(model)
        )

    # -- What it is told ---------------------------------------------------

    def _refresh_prompts(self) -> None:
        """Rebuild the instructions picker from what is stored.

        Prism's own are always the first row and are never stored, so there
        is always something to fall back to and the shipped text can never
        be shadowed by a stale copy of itself.
        """
        chosen = assistant_prompt_name()
        self._prompts.blockSignals(True)
        self._prompts.clear()
        self._prompts.addItem(BUILTIN_PROMPT_NAME, "")
        for entry in assistant_prompts():
            self._prompts.addItem(entry["name"], entry["name"])
        row = max(0, self._prompts.findData(chosen))
        self._prompts.setCurrentIndex(row)
        self._prompts.blockSignals(False)

    def _prompt_chosen(self, index: int) -> None:
        """Adopt the instructions the picker now names.

        They come into force on the **next** question, and the replies
        already in the transcript were given under the old ones. That is a
        fact of the conversation rather than a fault in it, so mid-chat the
        change is said in the transcript instead of being silent.

        Args:
            index: The row chosen.
        """
        name = self._prompts.itemData(index) or ""
        if name == assistant_prompt_name():
            return
        set_assistant_prompt_name(name)
        if self._messages:
            self._transcript.start_turn(NOTE)
            self._append(
                f"Instructions: {self._prompts.itemText(index)} — from "
                "the next question on."
            )
        self._status.setText(f"Instructions: {self._prompts.itemText(index)}")

    def edit_prompts(self) -> bool:
        """Write, rename or delete sets of instructions.

        Returns:
            Whether anything was changed.
        """
        outcome = PromptDialog.edit(assistant_prompts(), assistant_prompt_name(), self)
        if outcome is None:
            return False
        prompts, chosen = outcome
        set_assistant_prompts(prompts)
        self._refresh_prompts()
        row = max(0, self._prompts.findData(chosen))
        self._prompts.setCurrentIndex(row)
        self._prompt_chosen(row)
        return True

    def _role(self) -> str | None:
        """The instructions in force, or None for the ones Prism ships."""
        return assistant_prompt_text()

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
        if self._backend is None:
            self._status.setText(
                "No model to ask. Start Ollama (`ollama serve`) and pull one, "
                "or set ANTHROPIC_API_KEY for Claude."
            )
            return False
        self._input.clear()
        self._asked(asked)
        context = canvas_context(self._interpreter())
        self._messages.append(
            {"role": "user", "content": f"{context}\n\n{asked}".strip()}
        )
        self._script = None
        self._keep_button.setEnabled(False)
        self._pending_prose = ""
        self._begin("Thinking…")
        self._worker = AgentWorker(
            self._backend,
            system_prompt(self._interpreter(), self._role()),
            list(self._messages),
        )
        self._worker.chunk.connect(self._on_chunk)
        self._worker.thinking.connect(self._on_thinking)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._forget_worker)
        self._transcript.start_turn(ANSWERED)
        self._append(f"{self._speaker_name()}\n")
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
        self._append("\n  — stopped.")
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
        note = self._cost(usage)
        if self._script is not None:
            # Prism knows exactly which forms exist, so there is no reason to
            # let an invented one reach the editor unremarked. Said, not
            # blocked: it is still the person's script to keep or throw away.
            problems = check_script(self._interpreter(), self._script)
            if problems:
                self._append(
                    "  — that script won't all run:\n"
                    + "\n".join(f"      {line}" for line in problems)
                )
                note = f"{len(problems)} line(s) won't run — see above. " + note
        self._end(note)

    def _on_failed(self, message: str) -> None:
        # The question goes back out of the history: leaving it there would
        # send it again, unanswered, on top of the next one.
        if self._messages and self._messages[-1]["role"] == "user":
            self._messages.pop()
        self._append(f"\n  — {message}")
        self._end(message)

    def _forget_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()
        self._send_button.setEnabled(True)
        self._stop_button.setEnabled(False)

    # -- The transcript ----------------------------------------------------

    def _greet(self) -> None:
        self._transcript.start_turn(NOTE)
        self._append(
            "Ask for a construction and the assistant writes a script. Read "
            "it, then send it to the Scripts panel to run."
        )
        self._greet_status()

    def _speaker_name(self) -> str:
        """What to call whatever is answering.

        Returns:
            The provider's name — saying "Claude" over a local model's reply
                would be a plain lie about where the words came from.
        """
        if isinstance(self._backend, OllamaBackend):
            return "Ollama"
        if isinstance(self._backend, ClaudeBackend):
            return "Claude"
        return "Assistant"

    def _greet_status(self) -> None:
        """Say which model is answering, or why none is."""
        if self._backend is None:
            self._status.setText(
                "No model available. Start Ollama (`ollama serve`) and pull "
                "one, or set ANTHROPIC_API_KEY for Claude."
            )
            return
        if isinstance(self._backend, ClaudeBackend) and not (
            self._backend.looks_configured()
        ):
            self._status.setText(
                "No ANTHROPIC_API_KEY in the environment. Set one, or run "
                "`ant auth login` — Prism never stores it."
            )
            return
        self._status.setText(self._models.currentText())

    def _asked(self, text: str) -> None:
        """Put the question in its bubble, on the right.

        No "You" label: the bubble and the side it is on already say whose
        words they are, which is how the desktop app does it, and a label as
        well would be saying it twice.

        Args:
            text: What was asked.
        """
        self._transcript.start_turn(ASKED)
        self._append(text)

    def _append(self, text: str) -> None:
        self._transcript.add(text)

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
        who = self._models.currentText()
        if not usage:
            return who
        cached = f", {usage['cached']} cached" if usage.get("cached") else ""
        return (
            f"{who} · {usage.get('input', 0)} in{cached}, "
            f"{usage.get('output', 0)} out"
        )

    def _interpreter(self):
        return self._interpreter_source()
