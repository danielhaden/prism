"""Application settings, the on-disk script library, and the book.

The scripts folder is where saved console scripts live. It defaults to a
per-user application-data directory, is configurable from **Settings > Scripts
Folder…**, and can be overridden with ``PRISM_SCRIPTS_DIR`` (used by tests).

The window's size and its dock layout are remembered the same way, so the
canvas comes back the shape you left it.

The *book* is the one PDF the Book panel reads — Olive Whicher's *Projective
Geometry* — pointed at from **Settings > Book (PDF)…**, overridable with
``PRISM_BOOK_PATH``. The page last read is remembered alongside it, and reset
whenever the book is pointed somewhere new.
"""

import os
import re

from PySide6.QtCore import QByteArray, QSettings, QStandardPaths

#: Extension for saved console scripts.
SCRIPT_SUFFIX = ".prism"

_SCRIPTS_DIR_KEY = "paths/scripts_dir"
_BOOK_PATH_KEY = "paths/book_path"
_WINDOW_GEOMETRY_KEY = "window/geometry"
_WINDOW_STATE_KEY = "window/state"
_BOOK_PAGE_KEY = "book/last_page"


def default_scripts_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = os.path.expanduser("~/.prism")
    return os.path.join(base, "scripts")


def scripts_dir() -> str:
    """The folder scripts are read from and saved to."""
    override = os.environ.get("PRISM_SCRIPTS_DIR")
    if override:
        return override
    return QSettings().value(_SCRIPTS_DIR_KEY, default_scripts_dir())


def set_scripts_dir(path: str) -> None:
    QSettings().setValue(_SCRIPTS_DIR_KEY, path)


def ensure_scripts_dir() -> str:
    path = scripts_dir()
    os.makedirs(path, exist_ok=True)
    return path


def safe_script_name(name: str) -> str:
    """Reduce a user-supplied name to something usable as a filename."""
    cleaned = re.sub(r"[^\w \-.]", "", name).strip().strip(".")
    return cleaned or "untitled"


def script_path(name: str) -> str:
    return os.path.join(scripts_dir(), safe_script_name(name) + SCRIPT_SUFFIX)


def save_script(name: str, text: str) -> str:
    """Write a script to the scripts folder; returns the path written."""
    ensure_scripts_dir()
    path = script_path(name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text if text.endswith("\n") else text + "\n")
    return path


def load_script(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def list_scripts() -> list:
    """Saved scripts as ``(name, path)`` pairs, sorted by name."""
    folder = scripts_dir()
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    found = [
        (n[: -len(SCRIPT_SUFFIX)], os.path.join(folder, n))
        for n in names
        if n.endswith(SCRIPT_SUFFIX)
    ]
    return sorted(found, key=lambda pair: pair[0].lower())


# -- The book ------------------------------------------------------------


def book_path() -> str:
    """The PDF the Book panel reads, or ``""`` when none is set yet."""
    override = os.environ.get("PRISM_BOOK_PATH")
    if override:
        return override
    return QSettings().value(_BOOK_PATH_KEY, "") or ""


def set_book_path(path: str) -> None:
    """Point the Book panel at a PDF, forgetting the previous book's page."""
    if path != book_path():
        set_book_page(0)
    QSettings().setValue(_BOOK_PATH_KEY, path)


def book_page() -> int:
    """The zero-based page the book was last left open at."""
    try:
        return max(0, int(QSettings().value(_BOOK_PAGE_KEY, 0) or 0))
    except (TypeError, ValueError):
        return 0


def set_book_page(page: int) -> None:
    QSettings().setValue(_BOOK_PAGE_KEY, max(0, int(page)))


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
