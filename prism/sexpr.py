"""A tiny S-expression reader for the console.

Commands are written as parenthesised forms, e.g.::

    (add horizon 1/3)
    (add line 260 (point 'L1 2/3))

Reading yields a tree built from four kinds of node:

* a Python ``list`` for a parenthesised form,
* a ``float`` for a numeric literal (``260``, ``-45``, ``2/3``, ``0.5``),
* a Python ``str`` for a quoted string literal (``"a label"``),
* a :class:`Symbol` for a bare name (``add``, ``horizon``, ``P1``, ``A``).

``'x`` is shorthand for ``(quote x)``. The interpreter (``prism/commands.py``)
gives these nodes meaning: numbers and strings evaluate to themselves, symbols
are looked up in the environment, and forms are dispatched on their head.
"""


class SexprError(Exception):
    """Raised when the text isn't well-formed."""


class Symbol:
    """A bare name in the source, resolved by the interpreter's environment."""

    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return self.name

    def __eq__(self, other) -> bool:
        return isinstance(other, Symbol) and other.name == self.name

    def __hash__(self) -> int:
        return hash(self.name)


class _String:
    """A tokenizer marker distinguishing ``"a"`` (literal) from ``a`` (symbol)."""

    __slots__ = ("value",)

    def __init__(self, value: str):
        self.value = value


def read_number(text: str) -> float | None:
    """Read a numeric literal: an int, a decimal, or an ``n/d`` fraction.

    Returns:
        The value as a float, or None if the text isn't a number (e.g. ``L1``,
        ``-points``).
    """
    text = text.strip()
    if "/" in text:
        parts = text.split("/")
        if len(parts) != 2:
            return None
        try:
            numerator, denominator = float(parts[0]), float(parts[1])
        except ValueError:
            return None
        if denominator == 0:
            return None
        return numerator / denominator
    try:
        return float(text)
    except ValueError:
        return None


def tokenize(text: str) -> list:
    """Split text into ``(``, ``)``, ``'``, quoted strings, and bare atoms.

    Quoted strings come back wrapped in :class:`_String` so the parser can tell
    ``"a"`` from the bare atom ``a``; everything else is a plain string token.

    Returns:
        The list of tokens.
    """
    tokens = []
    i = 0
    while i < len(text):
        char = text[i]
        if char in "()'":
            tokens.append(char)
            i += 1
        elif char.isspace():
            i += 1
        elif char == ";":  # comment to end of line
            newline = text.find("\n", i)
            i = len(text) if newline == -1 else newline + 1
        elif char == '"':
            end = text.find('"', i + 1)
            if end == -1:
                raise SexprError("unterminated quoted text")
            tokens.append(_String(text[i + 1 : end]))
            i = end + 1
        else:
            start = i
            while (
                i < len(text)
                and not text[i].isspace()
                and text[i] not in "()'\";"
            ):
                i += 1
            tokens.append(text[start:i])
    return tokens


def parse(text: str) -> list:
    """Parse text into a list of top-level expressions.

    Returns:
        The parsed expressions, in order.
    """
    tokens = tokenize(text)
    expressions = []
    position = 0
    while position < len(tokens):
        expression, position = _parse_one(tokens, position)
        expressions.append(expression)
    return expressions


def _parse_one(tokens: list, position: int):
    token = tokens[position]
    if token == ")":
        raise SexprError("unexpected ')'")
    if token == "'":
        if position + 1 >= len(tokens):
            raise SexprError("nothing to quote after \"'\"")
        quoted, position = _parse_one(tokens, position + 1)
        return [Symbol("quote"), quoted], position
    if token == "(":
        position += 1
        items = []
        while True:
            if position >= len(tokens):
                raise SexprError("missing ')'")
            if tokens[position] == ")":
                return items, position + 1
            item, position = _parse_one(tokens, position)
            items.append(item)
    return _atom(token), position + 1


def _atom(token):
    """Turn a single non-paren token into a value, symbol, or string literal."""
    if isinstance(token, _String):
        return token.value
    number = read_number(token)
    if number is not None:
        return number
    return Symbol(token)
