# The Console

The **Console** is a dockable command line (bottom; toggle via **View → Show
Console**) for inspecting — and, over time, scripting — the canvas.

Type a command into the input line and press ++enter++. Use ++up++ / ++down++ to
walk through your command history.

## Commands

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
