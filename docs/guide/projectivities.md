# Projectivities & Pivots

A **projectivity** in Prism is a *pencil* — a family of lines through a common
point. The defining behavior is that the lines stay **concurrent**: manipulating
one rotates it about the shared point rather than pulling it away.

## Pivots

A line can be **pinned** to a point (its *pivot*). While pinned:

- the line stays a full line **through** the point;
- dragging the line (anywhere) **rotates** it about the point;
- moving the point carries all its pinned lines along.

You can create pivots directly: right-click a point → **Pin Lines Through
Point** pins every line currently passing through it into a pencil. **Unpin
Lines From Point** releases them.

## Add Projectivity

To generate a fresh pencil on a line:

1. Right-click a line at the spot you want the pencil centered → **Add
   Projectivity…**
2. Fill in the dialog:
    - **Start angle** and **End angle** — degrees, measured **clockwise from the
      horizontal** (the positive x-axis, pointing right).
    - **Count** — the number of lines to spread evenly across the span, **or**
    - **Splay** — the fixed angle (in degrees) between adjacent lines.
3. Prism creates a **center point** at the clicked location (projected onto the
   line) and a pencil of infinite lines through it, all pinned to the center.

!!! tip "Count vs. splay"
    Use **count** when you want exactly *N* lines filling the span (endpoints
    included). Use **splay** when the angular *step* matters more than the total
    number of lines.

Because the pencil lines are pinned, you can then drag any one to rotate it
about the center, or drag the center to move the whole pencil — the foundation
for building perspective figures and harmonic nets.
