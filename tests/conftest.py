"""Shared test fixtures.

Qt needs a running ``QApplication`` and an offscreen platform plugin for the
scene/interpreter tests. Set the platform before PySide6 is imported.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def interp(qapp):
    """A fresh interpreter over a fresh scene."""
    from prism.canvas.scene import CanvasScene
    from prism.commands import CommandInterpreter

    return CommandInterpreter(CanvasScene())
