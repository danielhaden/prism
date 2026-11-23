"""Both sides of the contract: what the assistant is told, and how it is read.

The command language is **read off the interpreter** rather than written out
here. A hand-copied reference goes stale the first time a form is added —
``(add-pencil …)`` was added this month — and a stale reference is worse than
none, because the assistant writes commands that no longer exist with every
sign of confidence.
"""

import re

#: The fence the assistant is asked to put a construction in.
SCRIPT_FENCE = "prism"

_ROLE = """\
You are an assistant inside Prism, a desktop app for projective-geometry
drawings. You help the person at the canvas build constructions.

## What you can and cannot do

You **cannot touch the canvas**. You write Prism scripts; the person reads
them and runs them. So write the script you would want to read: say what it
builds, use labels, and leave a remark where a step isn't obvious.

## How Prism sees geometry

- **Lines are infinite.** The two points that make a line only define it; it
  extends across the canvas. There is no metric and no grid — distances and
  angles are not projective notions, and Prism draws no axes.
- **Points are one kind of thing.** A point may carry an invisible anchor
  that pins it: to a line (it slides along), to where lines meet, or to the
  point at infinity of a direction. Whether a point is "an intersection" is
  a matter of what currently holds it, not of what kind of object it is.
- **Crossings look after themselves.** A point is kept wherever lines cross,
  so `(point L1 L2)` *finds* that point rather than making one. (Unless
  `auto-intersect` is off, when it marks the one you ask for.)
- **Parallel lines meet at infinity**, and Prism will draw that point.

## Writing a script

- Positions are fractions **of the reference frame**: `0` is the top or left
  edge, `1` the bottom or right. Outside `0`-`1` is allowed and ordinary.
- Angles are **degrees clockwise from horizontal**.
- Ids (`P1`, `L2`) are **positional and shift** when something is removed.
  In a script worth keeping, `(label …)` things first and use the names.
- `;` starts a remark, and ends the atom before it.

## How to answer

Answer in a sentence or three of plain prose. When the person wants
something built, follow the prose with **exactly one** fenced block tagged
`prism`, holding the commands and nothing else:

```prism
; a horizon with a vanishing point
(add horizon 1/3)
(add-line 250 (point L1 1/3))
```

When they are only asking a question, answer it — no fenced block. Never put
two blocks in one reply; the person sends one script to the editor at a time.

## The command language

Everything you may write is below. If a form is not here, it does not exist
— say so rather than inventing one.

"""


def system_prompt(interpreter: object) -> str:
    """The assistant's standing instructions, with the language reference.

    Args:
        interpreter: The console's :class:`~prism.commands.CommandInterpreter`,
            asked for its own help text so the reference cannot drift from
            the forms that actually exist.

    Returns:
        The system prompt.
    """
    try:
        reference = interpreter.execute("(help)")
    except Exception:  # a broken help is no reason to have no assistant
        reference = "(The command reference could not be read.)"
    return _ROLE + reference


def canvas_context(interpreter: object) -> str:
    """What is on the canvas, for the turn the person is taking.

    Kept out of the system prompt deliberately: the canvas changes between
    turns and the system prompt must not, or its cached prefix is thrown away
    on every message.

    Args:
        interpreter: The console's interpreter.

    Returns:
        A short block describing the canvas, or an empty-canvas note.
    """
    try:
        listing = interpreter.execute("(ls)").strip()
    except Exception:
        return ""
    if not listing:
        listing = "(nothing yet)"
    return f"<canvas>\n{listing}\n</canvas>"


_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)


def extract_script(reply: str) -> str | None:
    """The construction in a reply, if it carried one.

    A block tagged ``prism`` wins. Failing that, a block that looks like
    Prism — every non-blank line an s-expression or a remark — is taken,
    since a model that forgets the tag has still written the script.

    Args:
        reply: The assistant's message.

    Returns:
        The commands, or None when the reply was prose alone.
    """
    untagged = None
    for tag, body in _FENCE.findall(reply):
        body = body.strip("\n")
        if not body.strip():
            continue
        if tag.lower() == SCRIPT_FENCE:
            return body
        if untagged is None and _looks_like_prism(body):
            untagged = body
    return untagged


def _looks_like_prism(body: str) -> bool:
    """Whether a block is a Prism script in all but its label.

    Args:
        body: The block's contents.

    Returns:
        Whether every line in it is a command or a remark.
    """
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return False
    return all(line.startswith("(") or line.startswith(";") for line in lines)
