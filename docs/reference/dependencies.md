# Dependencies

Geometry in Prism is rarely independent: a line's endpoint is **bound** to a
point, a line **pivots** on one, a point is **anchored** to a line, a point sits
at the **crossing** of two lines. Each relationship says that one thing's
position is computed from another's.

Taken together they form a graph. This module reads it out of the scene, so an
update can be ordered by what it actually depends on rather than run as a fixed
sweep. It only observes; nothing here moves anything.

The edge direction throughout is **dependent → dependency**: the thing being
computed points at what it is computed from, and a dependency is brought up to
date first.

::: prism.dependencies
