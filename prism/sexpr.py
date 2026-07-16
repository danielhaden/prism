"""A tiny S-expression reader for the console.

Commands are written as parenthesised forms, e.g.::

    (add horizon 1/3)
    (add line 260 (point L1 2/3))

Parsing yields nested lists of string atoms; the interpreter gives them
meaning. Several forms may appear in one line, which is what makes scripting
possible.
"""


class SexprError(Exception):
    """Raised when the text isn't well-formed."""


def tokenize(text: str) -> list:
    """Split text into parens, bare atoms, and "quoted atoms"."""
    tokens = []
    i = 0
    while i < len(text):
        char = text[i]
        if char in "()":
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
            tokens.append(text[i + 1 : end])
            i = end + 1
        else:
            start = i
            while i < len(text) and not text[i].isspace() and text[i] not in "()":
                i += 1
            tokens.append(text[start:i])
    return tokens


def parse(text: str) -> list:
    """Parse text into a list of top-level expressions."""
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
    if token != "(":
        return token, position + 1

    position += 1
    items = []
    while True:
        if position >= len(tokens):
            raise SexprError("missing ')'")
        if tokens[position] == ")":
            return items, position + 1
        item, position = _parse_one(tokens, position)
        items.append(item)
