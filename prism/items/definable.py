"""Geometry that can lose its position when what defines it goes away.

A point at the crossing of two lines has a position only while those lines
cross. A line bound to such a point has one only while the point does. When
the definition fails the item is **undefined**: it keeps its identity and its
relationships — so everything comes back the moment the definition holds
again — but it is not drawn, and cannot be clicked or selected.

Undefined-ness is *derived*, recomputed from the scene's dependencies rather
than stored, so it is never persisted or undone directly.
"""


class Definable:
    """Mixin giving an item an undefined state.

    Hiding is how "undefined" shows: an undefined item is not painted, and Qt
    leaves hidden items out of hit-testing, so it cannot be clicked, dragged or
    rubber-band selected either.
    """

    #: Class-level default so the flag reads correctly even before __init__
    #: runs — Qt calls overrides like itemChange during construction.
    _undefined = False

    def position_undefined(self) -> bool:
        """Whether this item currently has no position to be drawn at."""
        return self._undefined

    def set_position_undefined(self, undefined: bool) -> bool:
        """Mark the item defined or undefined.

        Args:
            undefined: Whether its definition currently fails.

        Returns:
            Whether this changed anything.
        """
        undefined = bool(undefined)
        if undefined == self._undefined:
            return False
        self._undefined = undefined
        if undefined and self.isSelected():
            self.setSelected(False)
        self.setVisible(not undefined)
        return True
