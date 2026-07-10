"""Persistence for user-saved geometry templates."""

import json
import os

from PySide6.QtCore import QStandardPaths


def store_path() -> str:
    """Path to the user templates file (overridable via PRISM_TEMPLATE_STORE)."""
    override = os.environ.get("PRISM_TEMPLATE_STORE")
    if override:
        return override
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = os.path.expanduser("~/.prism")
    return os.path.join(base, "user_templates.json")


def load_user_templates() -> list:
    """Load saved templates; return [] if none or the file is unreadable."""
    path = store_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [
        t
        for t in data
        if isinstance(t, dict) and "points" in t and "lines" in t and "name" in t
    ]


def save_user_templates(templates: list) -> None:
    """Write templates atomically to the store."""
    path = store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(templates, fh, indent=2)
    os.replace(tmp, path)
