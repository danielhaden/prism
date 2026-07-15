# The Console

The **Console** is a dockable command line (bottom; toggle via **View → Show
Console**) for inspecting — and, over time, scripting — the canvas.

Type a command into the input line and press ++enter++. Use ++up++ / ++down++ to
walk through your command history.

## Commands

### `add horizon`

Add a **horizon**: a horizontal line across the canvas whose orientation is
**locked**, so it can be moved but never rotated.

```
add horizon 1/2     # halfway down the canvas
add horizon 1/3     # a third of the way down
add horizon 0.25    # decimals work too
```

The position is given as a fraction of the way down the **reference frame**
(the fully-zoomed-out canvas): **0 is the top, 1 is the bottom**. Fractions
(`1/3`) and decimals (`0.5`, `.25`) are both accepted.

Otherwise it's an ordinary infinite line — you can style it, label it, hang
pencils off it, and drag it up and down. Dragging one of its endpoint handles
slides the whole line instead of tilting it.

### `add line`

Add an infinite line through an existing point, at a given angle.

```
add line 30 A       # 30° through the point labelled A
add line -45 P2     # -45° through the point listed as P2
add line 90 A       # vertical
```

- **angle** — degrees **clockwise from the horizontal** (the same convention as
  [projectivities](projectivities.md)). `0` is horizontal, `90` vertical;
  negatives are fine.
- **point** — referenced by its **label** (`A`) or by the **id shown by
  [`list`](#list)** (`P1`). Labels are matched case-insensitively.

The line is **pinned** to the point, so it stays through it and rotates about
it. Repeating the command on the same point therefore builds up a
[pencil](projectivities.md) line by line:

```
add horizon 1/3
add line 65 V
add line 80 V
add line 100 V
```

!!! note "Intersection points can't anchor a line"
    Derived (intersection) points are recomputed as lines move, so they can't
    be used as the anchor; the command says so if you try.

### `list`

List the elements on the canvas.

```
list            # all elements
list -points    # points only
list -lines     # lines only
```

Points are shown with their coordinates, label, and an `[intersection]` marker
for derived points. Lines show their defining endpoints, whether they are
`infinite` or limited to a `range[…]`, whether they have a `pivot`, and their
label.

Example:

```
> list
Points (3):
  P1  (0.0, 0.0)  "A"
  P2  (100.0, 0.0)
  P3  (50.0, 0.0)
Lines (2):
  L1  (-10.0, 0.0)->(10.0, 0.0)  infinite  "a"
  L2  (0.0, -10.0)->(0.0, 10.0)  range[-40, +20]  pivot
```

### `help`

List the available commands.

!!! info "Growing surface"
    The console is intentionally small right now. It's built on an extensible
    command registry, so creation and manipulation commands (and running whole
    scripts) can be added incrementally. See
    [`CommandInterpreter`](../reference/commands.md).
