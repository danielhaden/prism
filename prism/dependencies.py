"""The dependency graph behind the canvas's geometry.

The scene already records, item by item, what each piece of geometry is built
on: a line endpoint **bound** to a point, a line **pivoting** on one, a line's
**visible range** anchored at one, a point **anchored** to a line, a point
sitting at the **crossing** of two lines. Those relationships are a graph, but
until now nothing read them as one — updates ran as a fixed sweep (points drive
lines, lines drive anchored points, crossings are recomputed last), which is
why nothing could depend on a crossing: it was always updated last, and its
movement notified nobody.

This module reads those relationships out in one place, so an update can be
ordered by what it actually depends on. It only *observes* the scene; nothing
here moves anything.

The edge direction throughout is **dependent → dependency**: the thing whose
position is computed points at the things it is computed from, and a dependency
must be brought up to date first.
"""

from prism.items import LineItem, PointItem

#: The kinds of thing the graph has an opinion about.
Geometry = PointItem | LineItem

#: One of those, or several.
Changed = Geometry | list


def dependencies_of(item: Geometry) -> list:
    """What ``item``'s position is computed from.

    Args:
        item: A point or line (anything else has no dependencies).

    Returns:
        The items that must be up to date before ``item`` can be placed, in no
        particular order and possibly with repeats collapsed.
    """
    found = []

    def add(other) -> None:
        if other is not None and not any(other is seen for seen in found):
            found.append(other)

    if isinstance(item, LineItem):
        for end in (1, 2):
            add(item.bound_point(end))
        add(item.pivot())
        add(item.range_anchor())
    elif isinstance(item, PointItem):
        anchor = item.anchor()
        if anchor is not None:
            if anchor.kind == "line":
                add(anchor.line)
            elif anchor.kind == "intersection":
                add(anchor.a)
                add(anchor.b)
    return found


class DependencyGraph:
    """Which pieces of geometry are computed from which others.

    Built by reading a scene; it is a snapshot, so rebuild it after the
    relationships change (moving things does not change them).
    """

    def __init__(self, scene=None):
        self._items: dict[int, object] = {}
        self._dependencies: dict[int, list] = {}
        self._dependents: dict[int, list] = {}
        if scene is not None:
            self.build(scene)

    # -- Building ----------------------------------------------------------

    def build(self, scene) -> None:
        """Read every relationship currently in ``scene``."""
        self._items.clear()
        self._dependencies.clear()
        self._dependents.clear()

        geometry = [
            it for it in scene.items() if isinstance(it, (PointItem, LineItem))
        ]
        for item in geometry:
            self._items[id(item)] = item
            self._dependencies.setdefault(id(item), [])
            self._dependents.setdefault(id(item), [])

        for item in geometry:
            for dependency in dependencies_of(item):
                if id(dependency) not in self._items:
                    continue  # not in this scene (a stale reference)
                self._dependencies[id(item)].append(dependency)
                self._dependents[id(dependency)].append(item)

    # -- Reading -----------------------------------------------------------

    def items(self) -> list:
        """Every point and line the graph covers."""
        return list(self._items.values())

    def dependencies(self, item) -> list:
        """What ``item`` is computed from (one step, not transitive)."""
        return list(self._dependencies.get(id(item), []))

    def dependents(self, item) -> list:
        """What is computed from ``item`` (one step, not transitive)."""
        return list(self._dependents.get(id(item), []))

    def affected_by(self, changed: Changed) -> list:
        """Everything that must be re-placed when ``changed`` moves.

        Args:
            changed: One item, or an iterable of them.

        Returns:
            The items reachable downstream, excluding the changed items
                themselves, in no particular order.
        """
        start = self._as_list(changed)
        seen = {id(it) for it in start}
        queue = list(start)
        out = []
        while queue:
            for dependent in self.dependents(queue.pop()):
                if id(dependent) not in seen:
                    seen.add(id(dependent))
                    out.append(dependent)
                    queue.append(dependent)
        return out

    def update_order(self, changed: Changed) -> list:
        """The items to re-place after ``changed`` moves, in dependency order.

        Each item appears only after everything it is computed from, so a
        single pass down the list leaves the scene consistent. Anything caught
        in a cycle is left out — see :meth:`cycles`.

        Args:
            changed: One item, or an iterable of them.

        Returns:
            The affected items, ordered.
        """
        affected = self.affected_by(changed)
        within = {id(it) for it in affected}
        remaining = {
            id(it): [
                d for d in self.dependencies(it) if id(d) in within
            ]
            for it in affected
        }
        ready = [it for it in affected if not remaining[id(it)]]
        ordered = []
        while ready:
            item = ready.pop(0)
            ordered.append(item)
            for dependent in self.dependents(item):
                pending = remaining.get(id(dependent))
                if pending is None:
                    continue
                remaining[id(dependent)] = [
                    d for d in pending if d is not item
                ]
                if not remaining[id(dependent)]:
                    ready.append(dependent)
        return ordered

    # -- Cycles ------------------------------------------------------------

    def cycles(self) -> list:
        """Items caught in a dependency cycle, if the graph has any.

        A cycle means a position defined in terms of itself, which no ordering
        can resolve.

        Returns:
            The items involved, or an empty list when the graph is sound.
        """
        remaining = {
            key: list(deps) for key, deps in self._dependencies.items()
        }
        ready = [key for key, deps in remaining.items() if not deps]
        settled = set()
        while ready:
            key = ready.pop()
            settled.add(key)
            for dependent in self._dependents.get(key, []):
                pending = remaining.get(id(dependent))
                if pending is None:
                    continue
                remaining[id(dependent)] = [
                    d for d in pending if id(d) != key
                ]
                if not remaining[id(dependent)]:
                    ready.append(id(dependent))
        return [
            self._items[key] for key in remaining if key not in settled
        ]

    def would_cycle(self, dependent: Geometry, dependency: Geometry) -> bool:
        """Whether making ``dependent`` depend on ``dependency`` closes a loop.

        Ask before binding, pinning or anchoring: if the answer is yes, the new
        relationship would define a position in terms of itself.

        Args:
            dependent: The item that would be computed from the other.
            dependency: The item it would be computed from.

        Returns:
            Whether the relationship would create a cycle.
        """
        if dependent is dependency:
            return True
        queue = [dependency]
        seen = {id(dependency)}
        while queue:
            for further in self.dependencies(queue.pop()):
                if further is dependent:
                    return True
                if id(further) not in seen:
                    seen.add(id(further))
                    queue.append(further)
        return False

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _as_list(items) -> list:
        if isinstance(items, (list, tuple, set)):
            return list(items)
        return [items]
