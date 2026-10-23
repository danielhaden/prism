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
(add-line 260 (point L1 2/3))
```

That reads: *add a line at 260°, through the point two-thirds of the way along
line L1.* The inner form makes the point; the outer form uses it.

You can also put several forms on one line, which is the seed of scripting:

```
(add horizon 1/3) (add-line 250 (point L1 1/3))
```

## Remarks

A **`;`** begins a remark that runs to the end of the line, as in lisp — in
the console as well as in a [script](#scripts):

```
; a horizon, and a point two-thirds along it
(add horizon 1/3)         ; locked to the horizontal
(add-line
  250                     ; degrees clockwise from horizontal
  (point L1 1/3))
```

A remark may sit inside a form, as above, and it ends an element's name as
well: `(rm P1;why)` reads as `(rm P1` — and so reports a missing `)`, since
the bracket was inside the remark. A `;` in `"quoted text"` is ordinary text,
so labels can contain one.

## Naming elements

Elements are referred to either by their **label** (`A`, `a` — matched
case-insensitively) or by the **id shown by [`list`](#list)** (`P1`, `L1`).

!!! note "Ids are positional"
    `P1` / `L1` are the numbers `list` prints *right now*; they shift as you
    add and remove elements. Labels are the stabler handle.

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
(add-line 45 (add point 1/2 1/2))
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
fully-zoomed-out canvas): **0 is the top, 1 is the bottom**. Values outside
that are allowed and mean above or below the frame — the canvas is larger than
it, and a construction can run off it.

!!! tip "The canvas runs this command too"
    **Right-click blank canvas → Add Horizon** doesn't do its own thing: it
    works out the fraction you clicked at and runs `(add horizon …)` for you.
    See [Clicking writes the script](#clicking-writes-the-script).

Otherwise it's an ordinary infinite line — style it, label it, hang pencils off
it, drag it up and down. Dragging an endpoint handle slides the whole line
rather than tilting it.

### `(add-line <points> <points>)`

Add infinite lines, in one of two forms. Both take **lists**, and a one-element
list is the plain case — one line.

**Joining points to points:**

```
(add-line (list A) (list B))             # the single line A-B
(add-line (list P1) (list P2 P3))        # P1-P2 and P1-P3
(add-line (list P1 P2) (list P3 P4))     # all four joins
(add-line P1 P2)                         # a bare point counts as a list of one
```

A line is drawn from **every** point of the first list to **every** point of
the second, which is how a net grows a round at a time:

```
(add-line (points-off L1 tri) (points-on L1 (points)))
```

Each endpoint is **bound** to its point, so the line follows them as they move.
A point paired with itself is skipped.

A pair the figure **already has a line through** is never drawn over — that
line comes back instead. Two distinct points determine one line, so if the
figure says both of them lie on one, that line *is* their join and there is
nothing to add. "Says" means the same recorded relation
[`(lines-through …)`](#lines-through-point) reads: bound, anchored, pinned, or
a crossing.

That is what makes the cross product do real work. Given a triangle and a
horizon, the horizon's crossings are each on one side already, so joining the
crossings to the vertices draws **only** the edges that are genuinely missing:

```
(add-line (points-on L1) (points-off L1 tri))
```

Each crossing is on the side that made it, hence already joined to that side's
two vertices — leaving exactly the third. Those are the
[cevians](#draw-cevians-triangle-line), and the sides come back alongside them
rather than being drawn twice.

The value is the line when only one came of it, and the list of lines
otherwise — so it feeds straight into [`(format …)`](#format-line-thickness-colour-style)
or [`(define …)`](#define-name-value).

**Through points, at an angle** (the first argument is a number):

```
(add-line 30 (list A))               # 30° through the point labelled A
(add-line -45 (list P1 P2))          # -45° through each of two points
(add-line 260 (point L1 2/3))        # through a point defined inline
```

- **angle** — degrees **clockwise from the horizontal** (the same convention as
  [projectivities](projectivities.md)). `0` is horizontal, `90` vertical.
- **points** — a label, an id, a nested form that yields a point, or a list of
  any of those.

Each line is **pinned** to its point, so it stays through it and rotates about
it. Repeating the command on one point builds a [pencil](projectivities.md)
line by line.

!!! note "It used to be `(add line …)`"
    Two words, and one point on each side. The form now always takes lists, so
    it is hyphenated — `(add-line …)`, a form in its own right rather than a
    kind of `add`. The old spelling says so if you type it.

### `(point <line> <fraction>)`

Make a point along a line, and return it.

```
(point L1 2/3)      # two-thirds along L1
(point a 0.5)       # the midpoint of line a
```

The span is measured where the line crosses the **reference frame**: `0` is its
**left-hand** end and `1` its **right-hand** end (top and bottom for a vertical
line). The point is **anchored** to the line, so it stays on it — drag it and
it slides along.

This form exists to be nested, so you can build in terms of existing geometry
rather than bare coordinates.

### `(point <line> <line>)`

The point where two lines meet.

```
(point L1 L2)       # where L1 crosses L2
(point a b)         # by label
```

Nothing is created: Prism already keeps a point wherever lines cross, so this
*finds* it — and shows it if you had [hidden](points-and-lines.md#hiding-a-point)
it. Making a second point there would be the same point twice.

If the two don't cross on the canvas — parallel, or meeting off it — the
command says so rather than inventing a point.

!!! tip "From the canvas"
    Select two lines and right-click either of them → **Add Point at
    Intersection** runs this command for you.

### `(label <element> <text>)`

Name a point or a line. The label is drawn on the canvas beside it, and becomes
a way to refer to it in later commands.

```
(label P1 A)              # by id
(label L1 a)              # lines take labels too
(label P2 "centre")       # quote anything with spaces
(label A "")              # empty text removes the label
```

Points are set upright and lines **italic**, the usual convention and the same
styling `(label -auto)` applies, so hand-labelled elements sit beside
auto-labelled ones without looking out of place. Intersection points can be
labelled — the label sticks across recomputes.

### `(label -auto)` and `(label -clear)`

```
(label -auto)       # points A, B, C… and lines a, b, c…, in creation order
(label -clear)      # remove every label on the canvas
```

`-auto` labels **every** point, including the ones marking where lines cross —
in a construction those are usually the points you most need to name. Both
forms are a single undo step, and both are the console equivalent of
**Auto-label Scene** and **Clear All Labels** on the canvas's right-click menu.

!!! note "A crossing's label lives as long as the crossing"
    An intersection marker keeps its identity while its lines move, so its
    label moves with it and survives undo and redo. But if the lines stop
    crossing the marker is gone, and bringing them back together produces a
    fresh, unlabelled one — the crossing is derived from the lines, not stored.

!!! tip "Labels outlast ids"
    Ids are positional, so `(rm P1)` renumbers everything after it. A label
    stays put. In a script that removes or reorders anything, label first and
    refer to elements by name:

    ```
    (add point 1/4 1/2)
    (label P1 A)
    (add-line 30 A)       ; still works however the ids shift
    ```

### `(draw-triangle <point> <point> <point>)`

Draw the three sides joining three points.

```
(draw-triangle P1 P2 P3)
(draw-triangle tri)            # or a list of three
```

Each side is a line **bound to its two vertices**, so the figure stays a
triangle as you drag them — move a vertex and the two sides through it follow.
The command returns the three sides as a list, so you can name them:

```
(define sides (draw-triangle tri))
(label sides s)                # s1, s2, s3
```

A side that is **already drawn is reused**, not drawn again. Triangles sharing
an edge — which is most of what a net is made of — therefore don't stack lines
on top of each other.

In the projective sense a triangle needs three points **not on a line**, so
collinear points are refused rather than given three copies of the same side.
The same goes for the same point twice.

### `(format <line> <thickness> [<colour>] [<style>])`

Change how a line is drawn.

```
(format L14 0.5 #d3d3d3 "dashed")
(format L2 3)                       # thickness alone
(format L2 1 grey)                  # a colour name works too
(format (lines) 0.25 #aabbcc "dotted")
```

Thickness is in **screen pixels** and stays that width at any zoom. Colour is
a hex code or any name Qt knows. The styles are `solid`, `dashed`, `dotted`,
`dash-dot` and `dash-dot-dot`.

Arguments after the line may be left off, so `(format L1 0.5)` changes only
the thickness. A **list** works in place of a single line, which is the useful
form for a net — dropping every construction line back to a pale hairline
leaves the figure you care about standing out:

```
(define scaffolding (lines))
… build …
(format scaffolding 0.5 #d3d3d3 "dashed")
```

Formatting is undoable and is kept with the drawing between sessions.

### `(draw-cevians <triangle> <line>)`

From each point where the line crosses the triangle, draw the edge that is
missing.

```
(draw-triangle P1 P2 P3)
(draw-cevians P1 P2 P3 L1)
(draw-cevians tri L1)          # a named list works too
```

Each side meets the line somewhere, and that crossing already lies on a side —
so it is already joined to *two* vertices. The third vertex is the one with no
edge to it, and that edge is what gets drawn: three in all, one per crossing.
They are the triangle's **cevians** through those points.

The three cevians do **not** meet in a point. They cross one another in three
places, forming a second triangle inside the first — which is what makes this
the start of a harmonic construction rather than a dead end.

A side parallel to the line never meets it, so there is no point to draw to;
the command says which side and stops rather than drawing something arbitrary.
Running it twice draws nothing new.

### `(rm <element>)`

Remove a point or a line from the canvas.

```
(rm P1)             # by id, as (ls) shows it
(rm A)              # by label
(rm L2)             # a line
```

Whatever referenced the removed element simply **comes free**, rather than
being removed in turn — a line bound to a deleted point keeps its position and
loses the binding, a line's pivot or visible-range anchor is cleared, and a
point anchored to a deleted line becomes an ordinary free point. This is
exactly what the ++delete++ key does on the canvas, so the console and the
canvas agree. One ++ctrl+z++ puts it back.

**Intersection points can't be removed.** They are computed from the lines that
cross there and would reappear immediately; remove one of those lines instead.

!!! warning "Ids shift"
    Ids are positional — `P1` is simply the first point. Removing `P1` renumbers
    everything after it, so re-run `(ls)` before leaning on an id again.
    Labels are stable, and worth using in a script that removes things.

### `(ls [-points | -lines])`

List the elements on the canvas.

```
(ls)            # everything
(ls -points)    # points only
(ls -lines)     # lines only
```

Points show coordinates, label, `on-line` if anchored, `[meet of …]` for a
point where lines cross, and `[hidden]`. Lines show their defining endpoints,
`infinite` or `range[…]`, plus `locked`, `pivot`, and their label.

!!! note "This used to be `(list)`"
    `(list …)` now gathers elements into a list value, so listing the canvas
    moved to `(ls)`. Typing the old spelling says so rather than doing
    something surprising. No saved script is affected — inspection commands
    were never recorded.

### `(list <element> …)`

Gather elements into a **list value**.

```
(list P1 P2 P3)       # a list of three points
(list L1 L2)          # lines work too
```

On its own a list isn't much use — name it with
[`(define …)`](#define-name-value) and then act on all of it at once. Lists
**flatten**, so they compose: `(list tri P4)` is a list of four points, not a
list containing a list.

### `(define <name> <value>)`

Give a value a name.

```
(define tri (list P1 P2 P3))
(define apex P4)
```

The name can then be used wherever the value could be, and a name you define
takes precedence over a label of the same text — you chose it deliberately.

Several commands take a list and act on each element:

```
(label tri V)     # labels them V1, V2, V3
(hide tri)
(show tri)
(rm tri)
```

`(label …)` numbers the elements, since one name across three points would be
ambiguous.

A name can outlive what it holds — clear the canvas, or remove one of the
points, and the list quietly shrinks to what is still there. If nothing is
left, using the name says so.

!!! warning "Names don't outlive the session"
    A definition lives as long as the app is open. The canvas persists between
    sessions but the names you gave it don't, so a script that defines what it
    needs is the durable form.

### `(lambda (<name> …) <body>)`

A **function**, as a value. The parameters are bare words in their own
parentheses; the body is one or more forms, run when the function is *called*
with the parameters bound to the arguments. Nothing in the body is evaluated
before then.

```
(lambda (q) (add-line (list q) (points-off L1 tri)))
```

Give it a name and it reads as a command of its own:

```
(define cevian (lambda (q) (add-line (list q) (points-off L1 tri))))
(cevian P4)
```

or write the two together, which means the same thing:

```
(define (cevian q) (add-line (list q) (points-off L1 tri)))
```

This is how the language grows **in itself**: a construction you work out at
the console becomes a form you can call, without anything being added to
Prism. The body's last value is the function's value, so a function that draws
gives back what it drew.

A function may also be called where it stands, with no name at all:

```
((lambda (q) (points-off q tri)) L1)
```

- Parameters **shadow** a `(define …)` name, which shadows a label — innermost
  wins, as in any lisp.
- A function made inside another call keeps that call's parameters, so
  `(define (maker a) (lambda (b) (list a b)))` gives functions that remember
  their `a`.
- A **built-in form always wins** over a name, so `(points)` can't be
  redefined out from under you.
- Unlike a list of elements, a function doesn't depend on the canvas, so
  clearing it leaves your functions intact.

!!! note "A function that calls itself"
    Allowed, but calls may not nest more than 50 deep; past that Prism says a
    function is probably calling itself without end, rather than falling over.

### `(map <function> <list>)`

Call a function on **each element** of a list, in turn:

```
(map cevian (points-on L1))
(map (lambda (q) (add-line (list q) (points-off L1 tri))) (points-on L1))
```

This is the form to reach for when the thing to draw **depends on** the
element. Where it doesn't — where you simply want every one of these joined to
every one of those — [`(add-line …)`](#add-line-points-points) already does
that in one go, and is the shorter way to say it.

The results are gathered into one **flat** list, as lists are everywhere else
here, so a function drawing several lines per element still gives back a list
of lines. The name of a built-in form works too, where it takes a single
argument:

```
(map hide (points-on L1))
```

### `(help)`

List the available commands.

## Enumerators: building without naming every step

Writing a net out by hand means chasing ids that Prism assigned — join two
points, see what the new crossing is called, join that, and so on. These forms
let you talk about the canvas instead.

| Form | Gives |
|------|-------|
| `(points)` / `(lines)` | everything on the canvas, as a list |
| `(meets <lines>)` | the points where those lines cross |
| `(lines-through <point>)` | the lines that point lies on |
| `(points-on <line> [<points>])` | of those, the ones on the line |
| `(points-off <line> [<points>])` | of those, the ones that aren't |
| `(join <points>)` | a line between every pair of them |
| `(without <list> <list>)` | the first list, minus the second |
| `(take <n> <list>)` / `(last <n> <list>)` | the first or last n |
| `(repeat <n> <form>)` | run a form n times |

`(repeat …)` re-evaluates its form each round, so anything reading the canvas
sees what the round before it made. **You never add the points** — Prism
already keeps one wherever lines cross, so growing a figure is only ever a
matter of joining points and letting the crossings appear.

```
(repeat 4 (join (last 4 (points))))
```

Each round joins the four newest points; their crossings become the newest
points for the round after. Starting from a triangle on a horizon:

| round | points | lines |
|-------|--------|-------|
| start | 6 | 4 |
| 1 | 10 | 10 |
| 2 | 10 | 16 |
| 3 | 14 | 19 |
| 4 | 15 | 25 |

`(last …)` is usually what you want: points come in creation order, so the
last of them are what the previous step produced. `(take …)` keeps re-joining
the seed you started from, which quickly does nothing at all.

!!! warning "Joining everything runs away"
    `n` points joined pairwise is `n(n-1)/2` lines — 20 points is 190, 30 is
    435 — and those lines cross in far more places again. `(join …)` refuses
    above 300 lines and tells you the count; narrow the list with
    `(take …)`, `(last …)` or `(without …)` and join a part of it. A net of
    harmonicity is a *disciplined* construction, not everything joined to
    everything.

`(lines-through …)` is the dual of `(meets …)`: one goes from lines to the
points they cross at, the other from a point to the lines through it. They
compose — `(meets (lines-through P1))` is every crossing on the pencil through
`P1`. A list of points gives the lines through any of them, each once.

A filter's result goes straight into another form, so these compose directly:

```
(add-line P6 (points-off L2 (list P1 P2 P3)))
```

`L2` is the side `P1P2`, so the only vertex off it is `P3` — and `P6` is
joined to it. If `P6` happens to be the crossing on the side through `P3`, the
answer is that side itself rather than a second line along it. Where a form
draws one thing *per* element,
[`(add-line …)`](#add-line-points-points) among them, a filter giving several
simply draws several. Where one element is wanted and a filter gives several,
the command says how many and shows them rather than guessing; if it gives
none, it says that too.

`(points-on …)` and `(points-off …)` are exact complements, and each is the
dual of `(lines-through …)` — one asks a point which lines it lies on, the
other asks a line which points lie on it. Given a list they filter it; given
none they take the whole canvas:

```
(points-off L1 (points))     # the triangle — none of it on the horizon
(points-on L1)               # every point on the horizon
(join (points-off L1 (points)))
```

!!! warning "They report relations, not geometry"
    A line counts as through a point when the figure **says** so: the point is
    its crossing, or the line is bound to it, pinned to pivot on it, anchored
    to it, or carries its visible range. Two lines that happen to cross
    exactly at a *placed* point are **not** reported — Prism makes no crossing
    point there (the point you placed is already the meet), so no relation was
    ever recorded:

    ```
    (lines-through P1)   ->   ()     # even with two lines visibly crossing at P1
    ```

    Build through a point — pin or bind to it — and the relation exists.

To reach exactly what a step created, keep a mark and subtract:

```
(define before (points))
(join (last 4 (points)))
(without (points) before)      # just the new crossings
```

## Clicking writes the script

A canvas command with a console equivalent **runs that command**. It appears in
the console as though you had typed it, and is recorded into the next script
you save — so a figure built by clicking replays as one built by typing. You
can work on the canvas and come away with the script for what you did.

| Canvas | runs |
|--------|------|
| Add Free Point | `(add point <across> <down>)` |
| Add Horizon | `(add horizon <fraction>)` |
| Add Point to Line | `(point <line> <fraction>)` |
| Add Point at Intersection | `(point <line> <line>)` |
| Add Line Through Point | `(add-line 45 (list <point>))` |
| Add Lines Through Point… | one `(add-line <angle> (list <point>))` per ray |
| Add Line Through Points | `(add-line (list <point>) (list <point>))` |
| Add / Edit / Remove Label | `(label <element> "…")` |
| Auto-label Scene / Clear All Labels | `(label -auto)` / `(label -clear)` |
| Delete Point / Hide Point | `(rm <element>)` |
| Show N Hidden Points | `(show -all)` |

Some canvas commands have no console form yet and so write nothing: **Modify
Display Properties…**, **Line Properties…**, **Define Visible Range…**, **Show
Full Line**, **Snap Point to Line**, **Lock to Line**, and **Pin Lines
Through Point**. A script of a session that used those will be
missing those steps.

!!! note "Ids shift"
    Commands are written with ids (`P1`, `L2`), and removing an element
    renumbers the ones after it. Deleting several points at once therefore
    writes them highest-first, so each `(rm …)` still names the point meant.
    For a script you intend to keep and edit, label things first and the names
    stay put.

## Scripts

Anything you build from the console can be saved and replayed.

### Saving

Click **Save Script…** next to the input and give it a name. The session's
**building** commands are written out in order — inspection commands
(`(ls)`, `(help)`) are left out, so the script is just the construction.

### The Scripts panel

**View → Show Scripts** opens a dock (tabbed with the Library) listing every
script in your scripts folder, with an **editor** below the list. Select a
script and its text appears there; drag the divider to give the list or the
editor more room.

| Button | What it does |
|--------|--------------|
| **Run** | Execute what's in the editor; commands and output are echoed to the console |
| **Save** | Write the editor back to the file |
| **Revert** | Throw away your edits and re-read the file |
| **Refresh** | Re-read the folder, so scripts you add by hand show up |

**Run uses the editor, not the file**, so you can try a change before keeping
it. Edit, run, look at the canvas, adjust — then **Save** when it does what you
want, or **Revert** when it doesn't. A script with unsaved edits is marked
*modified* under the editor, and selecting a different one asks before
discarding them. Double-clicking a script still runs it.

Replaying a script doesn't re-record its commands, so running one won't
duplicate it into the next thing you save.

### Where scripts live

Scripts are plain text files (`.prism`) in your **scripts folder**, so you can
edit them in any editor as well as in the panel. Choose the folder from **Settings → Scripts Folder…**;
it defaults to a per-user application-data directory, and the panel shows the
current path at the bottom.

Scripts may contain blank lines and [remarks](#remarks):

```
; a horizon with a vanishing point
(add horizon 1/3)
(add-line 250 (point L1 1/3))   ; the pencil's first ray
```

## Worked example

A horizon with two vanishing points, each carrying a pencil — no coordinates
and no hand-placed points:

```
(add horizon 1/3)
(add-line 250 (point L1 1/3))
(add-line 265 P1) (add-line 280 P1) (add-line 295 P1)
(add-line 230 (point L1 2/3))
(add-line 245 P2) (add-line 260 P2) (add-line 275 P2)
```
