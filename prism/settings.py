"""Application settings, the on-disk script library, and the book.

The *default scripts folder* is where **Save Script** writes and where **File
> Open Prism Script…** starts looking. It defaults to a per-user
application-data directory, is set from **File > Set Default Script Folder…**,
and can be overridden with ``PRISM_SCRIPTS_DIR`` (used by tests). A script may
be opened from anywhere; the folder is a starting point, not a fence.

The scripts opened lately are remembered too, so **File > Open Recent** can
offer them by name wherever on disk they live.

The window's size and its dock layout are remembered the same way, so the
canvas comes back the shape you left it.

The *shelf* is the PDFs the Book panel can read — Olive Whicher's *Projective
Geometry*, Coxeter's, whatever else you add from **Settings > Add Book…**.
Each carries a display name and the page it was last left at, so switching
between two books loses neither one's place. ``PRISM_BOOK_PATH`` overrides the
shelf with a single book, which is what the tests use.
"""

import json
import os
import re

from PySide6.QtCore import QByteArray, QSettings, QStandardPaths

#: Extension for saved console scripts.
SCRIPT_SUFFIX = ".prism"

_SCRIPTS_DIR_KEY = "paths/scripts_dir"
_RECENT_SCRIPTS_KEY = "scripts/recent"
_EXPORT_DIR_KEY = "paths/export_dir"
_BOOK_PATH_KEY = "paths/book_path"
_WINDOW_GEOMETRY_KEY = "window/geometry"
_WINDOW_STATE_KEY = "window/state"
_BOOK_PAGE_KEY = "book/last_page"
_SHELF_KEY = "books/shelf"
_CURRENT_BOOK_KEY = "books/current"

#: Longest display name derived from a filename; longer ones are cut short.
BOOK_NAME_LIMIT = 48

#: How many recently opened scripts **File > Open Recent** remembers.
RECENT_LIMIT = 8


def default_scripts_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = os.path.expanduser("~/.prism")
    return os.path.join(base, "scripts")


def scripts_dir() -> str:
    """The default scripts folder: where saving writes and opening starts."""
    override = os.environ.get("PRISM_SCRIPTS_DIR")
    if override:
        return override
    return QSettings().value(_SCRIPTS_DIR_KEY, default_scripts_dir())


def set_scripts_dir(path: str) -> None:
    QSettings().setValue(_SCRIPTS_DIR_KEY, path)


def scripts_dir_is_fixed() -> bool:
    """Whether ``PRISM_SCRIPTS_DIR`` is standing in for the scripts folder.

    When it is, choosing another folder would be ignored on the next read, so
    the commands that set one are offered greyed out rather than appearing to
    work. Same bargain as :func:`shelf_is_fixed`.
    """
    return bool(os.environ.get("PRISM_SCRIPTS_DIR"))


def ensure_scripts_dir() -> str:
    path = scripts_dir()
    os.makedirs(path, exist_ok=True)
    return path


def write_script(path: str, text: str) -> None:
    """Write a script to an exact path.

    Always an exact path: every script Prism writes comes either from the
    file it was read from or from a Save As dialog, so there is no longer a
    name to turn into a filename and nothing to mangle on the way.

    Args:
        path: The file to write.
        text: Its new contents; a trailing newline is added if missing.
    """
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text if text.endswith("\n") else text + "\n")


def load_script(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


# -- Exporting -----------------------------------------------------------


def export_dir() -> str:
    """The folder an export dialog opens in.

    Remembered from the last one, because a drawing you export is a drawing
    you export again, and the second time should not start from wherever the
    app happened to be launched.

    Returns:
        A folder; the user's documents, or home, until one is used.
    """
    stored = QSettings().value(_EXPORT_DIR_KEY, "")
    if stored and os.path.isdir(stored):
        return stored
    base = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return base or os.path.expanduser("~")


def set_export_dir(path: str) -> None:
    """Remember the folder an export was written to."""
    QSettings().setValue(_EXPORT_DIR_KEY, path)


# -- Recently opened -----------------------------------------------------


def recent_scripts() -> list:
    """The scripts opened lately, newest first.

    Only files that are still there come back. A script you deleted or
    renamed should not sit in the menu offering to open nothing, and because
    :func:`remember_script` writes this list back, the stale entry is gone
    for good the next time one is opened.

    Returns:
        Absolute paths, newest first, at most :data:`RECENT_LIMIT` of them.
    """
    stored = QSettings().value(_RECENT_SCRIPTS_KEY, "")
    try:
        raw = json.loads(stored) if stored else []
    except ValueError:
        raw = []
    if not isinstance(raw, list):
        return []
    paths = [str(entry) for entry in raw if isinstance(entry, str)]
    return [path for path in paths if os.path.isfile(path)][:RECENT_LIMIT]


def remember_script(path: str) -> None:
    """Put a script at the top of the recently opened list.

    Args:
        path: The script's path. An entry already in the list moves up rather
            than appearing twice, and the oldest falls off the end.
    """
    path = os.path.abspath(path)
    kept = [other for other in recent_scripts() if other != path]
    QSettings().setValue(
        _RECENT_SCRIPTS_KEY, json.dumps([path] + kept[: RECENT_LIMIT - 1])
    )


def forget_script(path: str) -> None:
    """Drop a script from the recently opened list.

    For one that is still on disk but wouldn't open — a folder that lost its
    permissions, a file that isn't text. A missing file needs no help; it is
    filtered out on the way in.

    Args:
        path: The script to forget.
    """
    path = os.path.abspath(path)
    kept = [other for other in recent_scripts() if other != path]
    QSettings().setValue(_RECENT_SCRIPTS_KEY, json.dumps(kept))


def clear_recent_scripts() -> None:
    """Empty the recently opened list."""
    QSettings().remove(_RECENT_SCRIPTS_KEY)


# -- The shelf -----------------------------------------------------------


def book_name_for(path: str) -> str:
    """A display name for a book, read off its filename.

    Books come filed under whatever name they were downloaded with, which for
    a scan is often the whole bibliography run together. The stem is taken up
    to the first ``--`` separator and cut to :data:`BOOK_NAME_LIMIT`, so the
    dropdown stays readable without anyone having to rename a file.

    Args:
        path: The PDF's path.

    Returns:
        A short name, never empty.
    """
    stem = os.path.basename(path)
    if stem.lower().endswith(".pdf"):
        stem = stem[: -len(".pdf")]
    stem = re.split(r"\s+--\s+", stem)[0]
    stem = " ".join(stem.split())
    if len(stem) > BOOK_NAME_LIMIT:
        stem = stem[: BOOK_NAME_LIMIT - 1].rstrip() + "\u2026"
    return stem or "Untitled"


def books() -> list:
    """The shelf: ``[{"name": …, "path": …, "page": …}, …]``.

    A shelf that has never been written is built from the single book older
    versions kept, so an upgrade opens on the same page of the same PDF. The
    ``PRISM_BOOK_PATH`` override stands in for the whole shelf.

    Returns:
        The books, oldest first. The list is a copy; write it back with
            :func:`set_books`.
    """
    override = os.environ.get("PRISM_BOOK_PATH")
    if override:
        return [{
            "name": book_name_for(override),
            "path": override,
            "page": _stored_page(),
        }]
    stored = QSettings().value(_SHELF_KEY, "")
    shelf = []
    try:
        raw = json.loads(stored) if stored else []
    except ValueError:
        raw = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, dict) and entry.get("path"):
            shelf.append({
                "name": str(entry.get("name") or book_name_for(entry["path"])),
                "path": str(entry["path"]),
                "page": max(0, int(entry.get("page") or 0)),
            })
    if shelf:
        return shelf
    single = QSettings().value(_BOOK_PATH_KEY, "") or ""
    if single:
        return [{
            "name": book_name_for(single),
            "path": single,
            "page": _stored_page(),
        }]
    return []


def set_books(shelf: list) -> None:
    """Write the shelf back, keeping the current book in range.

    Args:
        shelf: Books as :func:`books` returns them.
    """
    QSettings().setValue(_SHELF_KEY, json.dumps(list(shelf)))
    set_current_book(current_book())


def current_book() -> int:
    """Which book the panel is reading, as an index into :func:`books`.

    Returns:
        The index, or ``-1`` when the shelf is empty.
    """
    shelf = books()
    if not shelf:
        return -1
    try:
        index = int(QSettings().value(_CURRENT_BOOK_KEY, 0) or 0)
    except (TypeError, ValueError):
        index = 0
    return max(0, min(index, len(shelf) - 1))


def set_current_book(index: int) -> None:
    QSettings().setValue(_CURRENT_BOOK_KEY, max(0, int(index)))


def add_book(path: str, name: str = None) -> int:
    """Put a PDF on the shelf and make it current.

    A path already on the shelf is not added twice — it is simply selected,
    which is what choosing it again means.

    Args:
        path: The PDF to add.
        name: A display name; derived from the filename when not given.

    Returns:
        The book's index on the shelf.
    """
    shelf = books()
    for index, entry in enumerate(shelf):
        if entry["path"] == path:
            set_current_book(index)
            return index
    shelf.append({"name": name or book_name_for(path), "path": path, "page": 0})
    QSettings().setValue(_SHELF_KEY, json.dumps(shelf))
    set_current_book(len(shelf) - 1)
    return len(shelf) - 1


def remove_book(index: int) -> None:
    """Take a book off the shelf, leaving the file alone."""
    shelf = books()
    if 0 <= index < len(shelf):
        del shelf[index]
        QSettings().setValue(_SHELF_KEY, json.dumps(shelf))
        set_current_book(min(index, max(0, len(shelf) - 1)))


def rename_book(index: int, name: str) -> None:
    """Change a book's display name; an empty name goes back to the filename."""
    shelf = books()
    if 0 <= index < len(shelf):
        shelf[index]["name"] = name.strip() or book_name_for(shelf[index]["path"])
        QSettings().setValue(_SHELF_KEY, json.dumps(shelf))


def book_path() -> str:
    """The PDF the Book panel reads, or ``""`` when the shelf is empty."""
    shelf = books()
    index = current_book()
    return shelf[index]["path"] if 0 <= index < len(shelf) else ""


def book_page() -> int:
    """The zero-based page the current book was last left open at."""
    shelf = books()
    index = current_book()
    return shelf[index]["page"] if 0 <= index < len(shelf) else 0


def set_book_page(page: int) -> None:
    """Remember where the current book is open.

    Kept per book, so going back to one returns to where it was left rather
    than to wherever the other book happens to be.
    """
    page = max(0, int(page))
    if os.environ.get("PRISM_BOOK_PATH"):
        QSettings().setValue(_BOOK_PAGE_KEY, page)
        return
    shelf = books()
    index = current_book()
    if 0 <= index < len(shelf) and shelf[index]["page"] != page:
        shelf[index]["page"] = page
        QSettings().setValue(_SHELF_KEY, json.dumps(shelf))


def shelf_is_fixed() -> bool:
    """Whether ``PRISM_BOOK_PATH`` is standing in for the shelf.

    When it is, the shelf is that one book and adding or removing has nothing
    to act on, so the panel offers neither.
    """
    return bool(os.environ.get("PRISM_BOOK_PATH"))


def _stored_page() -> int:
    """The page key older versions wrote, kept for the override and upgrades."""
    try:
        return max(0, int(QSettings().value(_BOOK_PAGE_KEY, 0) or 0))
    except (TypeError, ValueError):
        return 0


# -- Window layout -------------------------------------------------------


def window_geometry() -> QByteArray | None:
    """The saved window size and position, or None on a first run."""
    return QSettings().value(_WINDOW_GEOMETRY_KEY)


def set_window_geometry(data: QByteArray) -> None:
    QSettings().setValue(_WINDOW_GEOMETRY_KEY, data)


def window_state() -> QByteArray | None:
    """The saved dock layout — which panels are open, where, and how wide."""
    return QSettings().value(_WINDOW_STATE_KEY)


def set_window_state(data: QByteArray) -> None:
    QSettings().setValue(_WINDOW_STATE_KEY, data)


def clear_window_layout() -> None:
    """Forget the saved window layout, so the next launch uses the defaults."""
    stored = QSettings()
    stored.remove(_WINDOW_GEOMETRY_KEY)
    stored.remove(_WINDOW_STATE_KEY)


# -- The drawing ---------------------------------------------------------

#: File the canvas is kept in between sessions.
DRAWING_FILE = "canvas.json"


def drawing_path() -> str:
    """Where the canvas is kept between sessions."""
    override = os.environ.get("PRISM_DRAWING")
    if override:
        return override
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = os.path.expanduser("~/.prism")
    return os.path.join(base, DRAWING_FILE)


def save_drawing(data: dict) -> str:
    """Write the canvas out.

    Args:
        data: Plain data from :func:`prism.scene_state.capture`, wrapped with
            a version.

    Returns:
        The path written.
    """
    path = drawing_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    return path


def load_drawing() -> dict | None:
    """Read the saved canvas, or None if there isn't a usable one.

    A missing, unreadable or malformed file is not an error worth stopping
    for: it just means starting with an empty canvas.
    """
    try:
        with open(drawing_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
