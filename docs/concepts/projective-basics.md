# Projective Basics

A short orientation to the ideas that shape Prism's design. This is not a
textbook — just enough to explain *why the app behaves the way it does*.

## No metric, no grid

Projective geometry studies the properties of figures that survive
**projection** — incidence (which points lie on which lines), collinearity, and
concurrence. Distances, angles, and parallelism are **not** projective notions:
they can all change under projection.

That's why Prism has **no background grid and no origin axes**. Those impose a
metric that doesn't belong to the projective world. If you want a scale on a
drawing, you build it *projectively* from the elements Prism gives you.

## Lines are infinite

In the projective plane a line has no endpoints — it is an unbounded object, and
any two distinct lines meet in exactly **one** point (there are no "parallel"
lines that fail to meet; they meet at a point at infinity).

So in Prism, **lines are infinite by default.** The two points you click to
create a line merely *define* it (its position and direction); the line itself
extends across the canvas. The [visible range](../guide/points-and-lines.md#visible-range)
feature only controls how much of a line is *drawn* — the underlying line is
still infinite for the purpose of intersections.

## Pencils (projectivities)

A **pencil of lines** is the set of all lines through a common point — the dual
of a range of points on a line. Pencils are the raw material of perspective and
projective constructions.

Prism models this directly: lines can be **pinned** to a common point so they
stay concurrent and rotate about it. See
[Projectivities & Pivots](../guide/projectivities.md).

## Construction by composition

Classical projective results — the harmonic conjugate, the complete quadrangle,
nets of harmonicity — are built by **repeated incidence constructions**: draw
lines through points, mark where they cross, repeat. Prism is designed around
this: snapping, pinning, automatic intersections, grouping, and templates are
all in service of *composing* elements into larger figures.
