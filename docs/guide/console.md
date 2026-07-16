# The Console

The **Console** is a dockable command line (bottom; toggle via **View → Show
Console**) for building and inspecting the canvas.

Type a command and press ++enter++. Use ++up++ / ++down++ to walk through your
command history.

## Syntax

Commands are **S-expressions** — every command is wrapped in parentheses:

```
(add horizon 1/3)
(list -points)
(help)
```

The point of the parentheses is **composition**: a form returns the element it
creates, so forms nest. Instead of placing a point and then referring to it,
you can describe it inline:

```
(add line 260 (point 'L1 2/3))
```

That reads: *add a line at 260°, through the point two-thirds of the way along
line L1.* The inner form makes the point; the outer form uses it.

You can also put several forms on one line, which is the seed of scripting:

```
(add horizon 1/3) (add line 250 (point 'L1 1/3))
```

## Values, names, and quoting

The console is a small Lisp. Every argument is a **value**:

- **Numbers** stand for themselves — `260`, `-45`, `2/3`, `0.5`.
- A **bare word** is a **name**, looked up among the things you've bound with
  [`define`](#define) or [`let`](#let). An unbound word is an error.
- **`'x`** (a leading quote) is the name `x` *itself*, unevaluated. This is how
  you point at an existing element by its **label** (`'A`, `'a`) or by the
  **id shown by [`list`](#list)** (`'P1`, `'L1`):

```
(add line 30 'A)      # 30° through the point labelled A
(point 'L1 2/3)       # two-thirds along line L1
```

!!! note "Why the quote?"
    A bare `A` means *the value I named A*; `'A` means *the element called A on
    the canvas*. Quoting keeps the two apart — so a name you `define` never
    collides with an element's label or id.

!!! note "Ids are positional"
    `'P1` / `'L1` are the numbers `list` prints *right now*; they shift as you
    add and remove elements. A `define`d name, or a label, is the stabler handle.

## Commands

### `(add point <across> <down>)`

Place a point on the canvas.

```
(add point 1/3 1/3)     # a third across, a third down
(add point 1/2 1/2)     # the centre
(add point 0.75 .25)    # decimals work too
```

Both coordinates are fractions of the **reference frame** (the fully-zoomed-out
canvas): **across** is 0 at the left edge and 1 at the right; **down** is 0 at
the top and 1 at the bottom. So `0 0` is the top-left corner and `1 1` the
bottom-right.

The point it returns can be fed straight to other forms:

```
(add line 45 (add point 1/2 1/2))
```

### `(add horizon <fraction>)`

Add a **horizon**: a horizontal line across the canvas whose orientation is
**locked**, so it can be moved but never rotated.

```
(add horizon 1/2)     # halfway down the canvas
(add horizon 1/3)     # a third of the way down
(add horizon 0.25)    # decimals work too
```

The position is a fraction of the way down the **reference frame** (the
fully-zoomed-out canvas): **0 is the top, 1 is the bottom**.

Otherwise it's an ordinary infinite line — style it, label it, hang pencils off
it, drag it up and down. Dragging an endpoint handle slides the whole line
rather than tilting it.

### `(add line <angle> <point>)`

Add an infinite line, in one of two forms.

**Through a point, at an angle:**

```
(add line 30 'A)                  # 30° through the point labelled A
(add line -45 'P2)                # -45° through the point listed as P2
(add line 260 (point 'L1 2/3))    # through a point defined inline
```

- **angle** — degrees **clockwise from the horizontal** (the same convention as
  [projectivities](projectivities.md)). `0` is horizontal, `90` vertical.
- **point** — a bound name, a quoted label or id, or a nested form that yields a
  point.

The line is **pinned** to the point, so it stays through it and rotates about
it. Repeating the command on one point builds a [pencil](projectivities.md)
line by line.

**Through two points** (the first argument isn't a number):

```
(add line 'A 'B)                              # through points A and B
(add line 'P1 'P2)                            # through the listed points
(add line (point 'L1 1/4) (point 'L1 3/4))    # through two inline points
```

Each endpoint is **bound** to its point, so the line follows them as they move.
(This is also available by selecting two points and right-clicking.)

### `(point <line> <fraction>)`

Make a point along a line, and return it.

```
(point 'L1 2/3)     # two-thirds along L1
(point 'a 0.5)      # the midpoint of line a
```

The span is measured where the line crosses the **reference frame**: `0` is its
**left-hand** end and `1` its **right-hand** end (top and bottom for a vertical
line). The point is **anchored** to the line, so it stays on it — drag it and
it slides along.

This form exists to be nested, so you can build in terms of existing geometry
rather than bare coordinates.

### `(define <name> <value>)`

Give a value a **name** so you can reuse it, and return that value. The name is
a bare word; from then on, using it (unquoted) means *this value*:

```
(define O (add point 1/2 1/2))    # name the centre point O
(add line 0 O)                    # a horizontal line through O
(add line 90 O)                   # …and a vertical one, same point
```

Naming a construction once and referring to it many times is clearer — and
safer — than chasing its positional id (`'P3`) as the drawing grows. Bindings
last for the rest of the console session.

### `(let ((<name> <value>) …) <body> …)`

Bind names in a **local scope**, evaluate the body, and return the body's last
value. Bindings are **sequential**, so a later one can use an earlier one:

```
(let ((v (add point 1/2 1/3))       ; a vanishing point
      (base (point 'L1 2/3)))       ; a point on an existing line L1
  (add line v base))                ; join them (v, base are bindings)
```

Unlike `define`, the names disappear once the `let` finishes — use it for the
scaffolding of a single construction without cluttering the session.

### `(list [-points | -lines])`

List the elements on the canvas.

```
(list)            # everything
(list -points)    # points only
(list -lines)     # lines only
```

Points show coordinates, label, `on-line` if anchored, and `[intersection]` for
derived points. Lines show their defining endpoints, `infinite` or `range[…]`,
plus `locked`, `pivot`, and their label.

### `(help)`

List the available commands.

## Scripts

Anything you build from the console can be saved and replayed.

### Saving

Click **Save Script…** next to the input and give it a name. The session's
**building** commands are written out in order — inspection commands
(`(list)`, `(help)`) are left out, so the script is just the construction.

### The Scripts panel

**View → Show Scripts** opens a dock (tabbed with the Library) listing every
script in your scripts folder. **Double-click** one — or select it and hit
**Run** — to execute it; its commands and output are echoed to the console.
**Refresh** re-reads the folder, so scripts you add by hand show up too.

Replaying a script doesn't re-record its commands, so running one won't
duplicate it into the next thing you save.

### Where scripts live

Scripts are plain text files (`.prism`) in your **scripts folder**, so you can
edit them in any editor. Choose the folder from **Settings → Scripts Folder…**;
it defaults to a per-user application-data directory, and the panel shows the
current path at the bottom.

Scripts may contain blank lines and `;` comments:

```
; a horizon with a vanishing point
(add horizon 1/3)
(add line 250 (point 'L1 1/3))   ; the pencil's first ray
```

## Worked example

A horizon with two vanishing points, each carrying a pencil — no coordinates
and no hand-placed points. Naming the two vanishing points with `define` keeps
each pencil readable:

```
(add horizon 1/3)
(define V1 (point 'L1 1/3))
(add line 250 V1) (add line 265 V1) (add line 280 V1) (add line 295 V1)
(define V2 (point 'L1 2/3))
(add line 230 V2) (add line 245 V2) (add line 260 V2) (add line 275 V2)
```
