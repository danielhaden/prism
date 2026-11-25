"""The backlog: issues noticed while using Prism, written down where the
next person to work on Prism will find them.

One Markdown file in the repository, appended to and never rewritten. A
file rather than a tracker because the thing that reads it is a coding
session with the repository open, and because an issue and the commit that
fixes it then travel together through the same history.

The shape is fixed enough to parse and loose enough to write by hand:

.. code-block:: markdown

    ## PB-3 · The Book page changes when the tab is resized

    - **Status**: open
    - **Logged**: 2026-11-24, from the Assistant panel
    - **Seen on**: 48330d0

    Resizing the Book dock makes the page jump to another page.

Only the ``## PB-n ·`` heading and the ``Status`` line are read back; the
rest is prose for whoever picks it up. Entries are appended at the end, so
**the first open one from the top is the oldest open one** — which is what
"take the first issue in the backlog" means.

:data:`OPEN` is the only status in the queue. Anything else takes an entry
out of it without deleting it — ``fixed`` once it is repaired, ``duplicate``
once it has been folded into an older entry — so an id that has been written
in a commit message always means what it meant.
"""

import os
import re
from datetime import date

#: The file, in the repository root.
BACKLOG_FILE = "BACKLOG.md"

#: Issue ids. Not ``#3`` — a bare ``#3`` in a commit message is a link to
#: somebody's GitHub issue, and these are not those.
ID_PREFIX = "PB-"

#: What a freshly logged issue is waiting as.
OPEN = "open"

_HEADING = re.compile(r"^##\s+(" + ID_PREFIX + r"\d+)\s+·\s+(.*)$")
_STATUS = re.compile(r"^-\s+\*\*Status\*\*:\s*(.+?)\s*$")

_PREAMBLE = """\
# Prism backlog

Issues noticed while using Prism, oldest first. They are logged from the
Assistant panel and worked through from the top: the first `open` one is
the next one up. Fixed entries stay, with the commit that closed them, so
the record of what was wrong does not vanish with the fix.

Each entry is a heading, a few fields, and prose. Nothing here is generated
— edit it by hand whenever that is easier. To close one, set its status to
`fixed` and add a `- **Fixed**:` line naming the commit; leave the entry
itself where it is.

Two reports of one fault are **folded into the older entry**: the newer one
keeps its id and its own words, takes the status `duplicate`, and gains a
`- **Duplicate of**:` line. Only `open` entries are in the queue, so a
folded report leaves it without being deleted — an id that has been written
in a commit message must never come back meaning something else.
"""


def backlog_path() -> str:
    """Where the backlog lives.

    ``PRISM_BACKLOG`` overrides it, which is what the tests use. Otherwise
    it is :data:`BACKLOG_FILE` beside the ``prism`` package — the repository
    root, Prism being a thing run from its checkout.

    Returns:
        The path, whether or not anything is there yet.
    """
    override = os.environ.get("PRISM_BACKLOG")
    if override:
        return override
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, BACKLOG_FILE)


def read_backlog(path: str = None) -> str:
    """The whole file, or ``""`` when there isn't one yet.

    Args:
        path: Where to read; :func:`backlog_path` when not given.

    Returns:
        The text.
    """
    try:
        with open(path or backlog_path(), encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def entries(path: str = None) -> list:
    """Every issue in the backlog, in the order they were logged.

    Args:
        path: Where to read; :func:`backlog_path` when not given.

    Returns:
        ``[{"id": …, "title": …, "status": …}, …]``. An entry with no
            ``Status`` line counts as :data:`OPEN`, since somebody writing
            one by hand means it to be dealt with.
    """
    found = []
    for line in read_backlog(path).splitlines():
        heading = _HEADING.match(line)
        if heading:
            found.append({
                "id": heading.group(1),
                "title": heading.group(2).strip(),
                "status": OPEN,
            })
            continue
        status = _STATUS.match(line)
        if status and found:
            found[-1]["status"] = status.group(1).strip().lower()
    return found


def open_issues(path: str = None) -> list:
    """The issues still waiting, oldest first."""
    return [entry for entry in entries(path) if entry["status"] == OPEN]


def next_id(path: str = None) -> str:
    """The id the next issue gets.

    One past the highest there has ever been, rather than one past the
    count: an id that has been written in a commit message must never come
    back meaning something else.

    Args:
        path: Where to read; :func:`backlog_path` when not given.

    Returns:
        ``PB-1`` on an empty backlog, else ``PB-<highest + 1>``.
    """
    highest = 0
    for entry in entries(path):
        try:
            highest = max(highest, int(entry["id"][len(ID_PREFIX):]))
        except ValueError:
            continue
    return f"{ID_PREFIX}{highest + 1}"


def log_issue(title: str, body: str = "", source: str = "", path: str = None) -> dict:
    """Write an issue at the end of the backlog.

    Appended, never rewritten: the file is one Claude Code is likely to have
    open and be editing statuses in, and an append is the one kind of write
    that cannot lose somebody else's.

    Args:
        title: One line. Trimmed of its own ``#`` and whitespace.
        body: What happens, where, and what was expected instead. Markdown.
        source: Where it was logged from, for the ``Logged`` line.
        path: Where to write; :func:`backlog_path` when not given.

    Returns:
        ``{"id": …, "title": …, "path": …}`` for the entry written.

    Raises:
        ValueError: If the title is empty — an issue with no title is one
            nobody will ever pick up.
    """
    title = title.strip().lstrip("#").strip()
    if not title:
        raise ValueError("an issue needs a title")
    path = path or backlog_path()
    identifier = next_id(path)

    logged = date.today().isoformat()
    if source:
        logged += f", from {source}"
    lines = [
        f"## {identifier} · {title}",
        "",
        f"- **Status**: {OPEN}",
        f"- **Logged**: {logged}",
    ]
    commit = head_commit()
    if commit:
        lines.append(f"- **Seen on**: {commit}")
    body = body.strip()
    if body:
        lines += ["", body]
    lines.append("")

    existing = read_backlog(path)
    opening = "" if existing else _PREAMBLE + "\n"
    separator = "" if not existing or existing.endswith("\n\n") else (
        "\n" if existing.endswith("\n") else "\n\n"
    )
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(opening + separator + "\n".join(lines))
    return {"id": identifier, "title": title, "path": path}


def head_commit() -> str:
    """The commit Prism is running from, short, or ``""``.

    Read straight out of ``.git`` rather than by running git: an app that
    shells out on a button press is an app that hangs when the shell does,
    and this is only ever a note in a file.

    Returns:
        Seven characters of the current commit, or ``""`` if there is no
            repository to read — an installed copy, or a worktree laid out
            in some way this does not expect.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    git = os.path.join(root, ".git")
    try:
        if os.path.isfile(git):  # a worktree: .git is a file pointing at one
            with open(git, encoding="utf-8") as handle:
                git = handle.read().split("gitdir:", 1)[1].strip()
        with open(os.path.join(git, "HEAD"), encoding="utf-8") as handle:
            head = handle.read().strip()
        if not head.startswith("ref:"):
            return head[:7]
        reference = head.split(" ", 1)[1].strip()
        try:
            with open(os.path.join(git, reference), encoding="utf-8") as handle:
                return handle.read().strip()[:7]
        except OSError:  # packed refs, which is where a quiet branch ends up
            with open(os.path.join(git, "packed-refs"), encoding="utf-8") as handle:
                for line in handle:
                    if line.rstrip().endswith(" " + reference):
                        return line.split(" ", 1)[0][:7]
    except (OSError, IndexError):
        return ""
    return ""
