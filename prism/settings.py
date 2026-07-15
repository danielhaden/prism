"""Application settings and the on-disk script library.

The scripts folder is where saved console scripts live. It defaults to a
per-user application-data directory, is configurable from **Settings > Scripts
Folder…**, and can be overridden with ``PRISM_SCRIPTS_DIR`` (used by tests).
"""

import os
import re

from PySide6.QtCore import QSettings, QStandardPaths

#: Extension for saved console scripts.
SCRIPT_SUFFIX = ".prism"

_SCRIPTS_DIR_KEY = "paths/scripts_dir"


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
