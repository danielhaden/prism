"""Points at infinity (ideal points).

A point at infinity is a *direction*: the place where a family of parallel lines
"meets" in the projective plane. It is the dual of a pivot — a pivot is a finite
point that a pencil of *concurrent* lines turns about, while an infinite point is
a shared direction that a family of *parallel* lines share. Rotating the infinite
point swings the whole family together.

It has no finite location, so it is never drawn; the scene tracks it in a list and
lines reference it (see :meth:`LineItem.set_infinity`).
"""

import math


def normalize_angle(degrees: float) -> float:
    """Fold an angle into ``[0, 180)``.

    A direction and its opposite are the same ideal point, so orientation is
    taken modulo 180°.

    Returns:
        The equivalent angle in ``[0, 180)``.
    """
    return float(degrees) % 180.0


class InfinitePoint:
    """An ideal point: a shared direction for a family of parallel lines."""

    def __init__(self, angle: float = 0.0):
        self._angle = normalize_angle(angle)

    @property
    def angle(self) -> float:
        """The direction, in degrees clockwise from horizontal, in ``[0, 180)``."""
        return self._angle

    def set_angle(self, degrees: float) -> None:
        self._angle = normalize_angle(degrees)

    def direction(self) -> tuple:
        """The unit direction ``(dx, dy)`` for the current angle.

        Returns:
            The ``(cos, sin)`` of the angle (screen y grows downward, so a
            positive angle turns clockwise).
        """
        r = math.radians(self._angle)
        return (math.cos(r), math.sin(r))

    def __repr__(self) -> str:
        return f"<InfinitePoint {self._angle:g}°>"
