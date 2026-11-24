"""Both sides of the contract: what the assistant is told, and how it is read.

The command language is **read off the interpreter** rather than written out
here. A hand-copied reference goes stale the first time a form is added —
``(add-pencil …)`` was added this month — and a stale reference is worse than
none, because the assistant writes commands that no longer exist with every
sign of confidence.

A system prompt is therefore in two parts: a **role**, which is prose and is
the user's to rewrite, and the **reference**, which is read off the
interpreter and is appended to whatever the role says. :data:`ROLE` below is
the one Prism ships; others are kept in the settings and chosen in the
Assistant panel.
"""

import re

#: The fence the assistant is asked to put a construction in.
SCRIPT_FENCE = "prism"

#: What the instructions Prism ships are called in the panel's picker. Not a
#: name a custom set may take, so that the built-in one is always there.
BUILTIN_PROMPT_NAME = "Prism's own"

#: The role Prism ships: what the assistant is for, how Prism sees geometry,
#: how to write a script, and the mistakes that actually happen. Every line
#: of it was earned against a real failure. The command reference is *not*
#: here — :func:`system_prompt` appends that, to this role or to any other.
ROLE = """\
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

## Building from nothing

An empty canvas has no `L1` and no `P1`. Make what you need before you refer
to it.

Two forms that are easy to confuse:

- **`(add point <across> <down>)`** *places* a point anywhere on the canvas.
- **`(point <line> <fraction>)`** *finds* one on a line that already exists.
  It cannot make the line.

So a triangle on a blank canvas places its vertices first:

```prism
; three placed points, joined
(draw-triangle (add point 1/5 4/5) (add point 4/5 4/5) (add point 1/2 1/5))
```

and a pencil through the middle places its centre first:

```prism
(add-pencil (add point 1/2 1/2) 6)
```

## Mistakes to avoid

These are the ones that actually happen:

- **`add` with a space, or a hyphenated name — never both.** `add` followed
  by a space makes something from *numbers*: `(add point 1/2 1/2)`,
  `(add horizon 1/3)`, `(add vertical 2/3)`. Forms that take *elements* are
  hyphenated and are not `add` at all: `(add-line …)`, `(add-pencil …)`,
  `(draw-triangle …)`, `(move-snapped-point …)`. There is no
  `(add-horizon …)` and no `(add-point …)`.
- **Parentheses mean a command.** A number is written bare: `(point L1 2/3)`,
  never `(point L1 (2/3))`. `2/3` is a value, not a form to call.
- **Don't invent forms.** If it isn't in the reference below, it doesn't
  exist. Say so and suggest the nearest thing that does.
- **Check your ids.** `(add horizon 1/3)` makes `L1` on an empty canvas, but
  `L2` if a line is already there — the canvas listing above each question
  tells you which. When in doubt, `(label …)` what you make and use the name.
- **One script per reply**, in one fenced block tagged `prism`. Nothing but
  commands and `;` remarks inside it.

## The command language

Everything you may write is below. If a form is not here, it does not exist
— say so rather than inventing one.

"""


def system_prompt(interpreter: object, role: str = None) -> str:
    """The assistant's standing instructions, with the language reference.

    The reference is appended whatever the role says, and is not the user's
    to remove: a model shown no reference invents forms, and one shown a
    stale reference invents them with a citation. Rewriting the role is
    rewriting *instructions*; the language itself is not up for discussion.

    Args:
        interpreter: The console's :class:`~prism.commands.CommandInterpreter`,
            asked for its own help text so the reference cannot drift from
            the forms that actually exist.
        role: The instructions to put in front of the reference; :data:`ROLE`,
            the ones Prism ships, when not given.

    Returns:
        The system prompt.
    """
    try:
        reference = interpreter.execute("(help)")
    except Exception:  # a broken help is no reason to have no assistant
        reference = "(The command reference could not be read.)"
    role = ROLE if role is None else role
    if role and not role.endswith("\n"):
        role += "\n\n"
    return role + reference


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


def check_script(interpreter: object, script: str) -> list:
    """Read a script without running it, and say what won't work.

    A small model gets the language *nearly* right — it invents
    ``(add-horizon …)`` where Prism has ``(add horizon …)`` — and the reply
    reads perfectly well either way. Prism knows exactly which forms exist,
    so there is no reason to let that reach the editor unremarked.

    Only the **head of each top-level form** is checked, plus whether the
    line parses at all. Nested heads would catch more and also flag a
    lambda's parameter list, and a check with false positives is one people
    learn to ignore.

    Args:
        interpreter: The console's interpreter, asked which forms exist.
        script: The commands to read.

    Returns:
        One plain-English complaint per bad line, in order; empty when the
            script is sound as far as this can tell.
    """
    from prism.sexpr import SexprError, parse

    try:
        known = set(interpreter.command_names())
    except Exception:
        return []
    problems = []
    for number, raw in enumerate(script.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        try:
            forms = parse(line)
        except SexprError as exc:
            problems.append(f"line {number}: {exc}")
            continue
        for form in forms:
            if not isinstance(form, list) or not form:
                problems.append(f"line {number}: not a command")
                continue
            head = form[0]
            if isinstance(head, str) and head.lower() not in known:
                problems.append(f"line {number}: there is no ({head} …)")
    return problems
