"""Drawing tools available on the canvas."""

from enum import Enum, auto


class Tool(Enum):
    """The active interaction mode for the canvas."""

    SELECT = auto()
    POINT = auto()
    LINE = auto()
