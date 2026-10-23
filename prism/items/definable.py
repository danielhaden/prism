"""Geometry that can lose its position when what defines it goes away.

A point at the crossing of two lines has a position only while those lines
cross. A line bound to such a point has one only while the point does. When
the definition fails the item is **undefined**: it keeps its identity and its
relationships — so everything comes back the moment the definition holds
again — but it is not drawn, and cannot be clicked or selected.

Undefined-ness is *derived*, recomputed from the scene's dependencies rather
than stored, so it is never persisted or undone directly.

Separately, an item may simply be **hidden**: a choice, not a consequence. A
dense net has a point at every crossing and most of them are scaffolding you
do not want drawn. Hiding one takes nothing away — it keeps its position, its
label and everything built on it, and can be shown again.

An item is drawn only when it is both defined and shown.
"""


class Definable:
    """Mixin giving an item an undefined state.

    Hiding is how "undefined" shows: an undefined item is not painted, and Qt
    leaves hidden items out of hit-testing, so it cannot be clicked, dragged or
    rubber-band selected either.
    """

    #: Class-level defaults so the flags read correctly even before __init__
    #: runs — Qt calls overrides like itemChange during construction.
    _undefined = False
    _shown = True

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
        self._apply_visibility()
        return True

    def is_shown(self) -> bool:
        """Whether this item is meant to be drawn, if it has a position."""
        return self._shown

    def set_shown(self, shown: bool) -> bool:
        """Show or hide the item.

        Hiding is a choice about clutter, nothing more: the item keeps its
        position and its relationships, and whatever is built on it is
        unaffected — unlike going undefined, which cascades.

        Args:
            shown: Whether it should be drawn.

        Returns:
            Whether this changed anything.
        """
        shown = bool(shown)
        if shown == self._shown:
            return False
        self._shown = shown
        self._apply_visibility()
        return True

    def _apply_visibility(self) -> None:
        visible = self._shown and not self._undefined
        if not visible and self.isSelected():
            self.setSelected(False)
        self.setVisible(visible)
