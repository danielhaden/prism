# Tools & Canvas

## Tools

The toolbar holds three drawing tools, plus editing actions. Each tool has a
one-key shortcut.

| Tool | Shortcut | What it does |
|------|----------|--------------|
| **Select** | ++v++ | Click to select, drag to move, rubber-band to multi-select. |
| **Point** | ++p++ | Click to place a point (snaps to nearby points/lines). |
| **Line** | ++l++ | Click a start, then an end, to draw a line. A dashed preview follows the cursor; ++esc++ cancels. |

## Editing

| Action | Shortcut | Notes |
|--------|----------|-------|
| Undo | ++ctrl+z++ | Step back to before the previous action. |
| Redo | ++ctrl+shift+z++ | Re-apply an undone action. |
| Delete | ++delete++ / ++backspace++ | Removes the selected elements. |
| Clear | — | Empties the whole canvas. |
| Group | ++ctrl+g++ | Combines selected elements into one unit. |
| Ungroup | ++ctrl+shift+g++ | Breaks a group back into its members. |

!!! note "Selection lives in Select mode"
    Selecting and moving happen with the **Select** tool. In Point or Line
    mode, clicks are reserved for drawing.

## Undo & redo

**Undo** (++ctrl+z++) steps back to before your previous action; **Redo**
(++ctrl+shift+z++) re-applies it. Both are on the toolbar and the Edit menu, and
grey out when there's nothing to undo/redo.

History covers everything: drawing, dragging, deleting, grouping, styling,
labelling, anchoring, and pencils — including the *relationships* between
elements, not just their positions.

## The Elements panel

A dock (left side; **View → Show Elements**) is a tree of everything on the
canvas, under **Points**, **Lines**, **Groups** and **Lists**:

```
Points (5)
  P1 "apex"  (-300.0, 300.0)
  P2  (300.0, 300.0)  [hidden]
  P4  (-150.0, 0.0)  [meet of L3, L4]
Lines (4)
  L4  (-600, 0)->(600, 0)  [locked]
Lists (1)
  tri = (P1 P2 P3)
```

Each row carries its name — the `P1` / `L1` id, or its label — and position,
plus what's true of it: a point says what lines it is the *meet* of, whether
it's *on line*, *locked to line*, *hidden* or *undefined*; a line says
*locked*, *range*, *pivot*, *hidden*. **Lists** are the names you've bound
with [`(define …)`](console.md#define-name-value). The names match the ones
the [console](console.md) uses, so the tree is a good way to find what to
type.

Selection works both ways: click a row and that element is selected on the
canvas; select on the canvas and its rows highlight. In a dense figure that's
often the easiest way to reach a particular point.

The tree keeps up as the canvas changes, refreshing shortly after things
settle rather than on every frame of a drag.

## Points off the edge

A construction reaches a long way off the canvas — a vanishing point can sit
thousands of units out — and a point you can't see is easy to forget. Any
defined point outside the view gets a small marker at the edge: an arrow
pointing its way, with its name.

The marker is placed where the **line that point sits on leaves the view**, so
you can follow that line out to it. Zoom out, or drag along the line, and you
arrive. A point that lies on no line is marked straight out from the middle
instead.

A point that is [hidden](points-and-lines.md#hiding-a-point) gets no marker —
hidden means hidden.

### Selecting one

**Click a marker** — the name or its arrow — and the point it names is
selected, exactly as if you had clicked the point itself. The marker turns the
selection orange, the row highlights in the **Elements** panel, and everything
that works on a selection now reaches a point you cannot see: delete it, label
it, draw a line through it, or pick two and join them.

The cursor becomes a pointing hand over a marker, so you can tell which bits of
the edge are live.

++ctrl++-click adds a marker's point to the selection or takes it back out, the
same as ++ctrl++-clicking on the canvas. Markers are only clickable with the
**Select** tool — in Point or Line mode a click is for drawing.

!!! note "One line is picked for you"
    A point where several lines cross could be marked against any of them.
    Prism picks one for now.

## Navigating the canvas

- **Zoom** — mouse wheel (anchored under the cursor).
- **Pan** — drag with the **middle mouse button**.
- **Fit to Frame** — ++ctrl+0++, or **View → Fit to Frame**.

The canvas opens **fully zoomed out**, fitted to the *reference frame* — the
working area. You can zoom **in** from there, but not further out, so the frame
always fills the viewport (and infinite lines always run off the edges rather
than showing their ends).

!!! tip "If the canvas looks empty when it shouldn't"
    The scene is much larger than the reference frame, so panning (or zooming
    in at one spot and out at another) can leave you looking at empty space
    well outside the frame — and with no grid to steer by, that looks exactly
    like a blank canvas. Console commands place geometry by *canvas fraction*,
    measured against the frame, so they can land somewhere you aren't looking.

    Two ways back: press ++ctrl+0++, or just keep **zooming out** — once you
    are at the frame's zoom floor, another notch out re-centres on the frame.

There is deliberately **no grid and no origin axes** — a metric has no place on
a projective canvas. If you want a scale, construct one projectively from the
elements themselves. See [Projective Basics](../concepts/projective-basics.md).

## The window remembers itself

Prism saves the window's size and position, and the whole dock layout, when you
quit — which panels are open, where they sit, the width of the right-hand tab
group (**Library** / **Scripts** / **Book**), and which of those tabs was on
top. Open it again and you get the canvas back the shape you left it.

Size the Book panel once for comfortable reading and it stays that way.

If a layout ever comes back awkwardly, **Settings → Reset Window Layout** puts
the window and its panels back to the size and places Prism ships with, both
straight away and on the next launch.

!!! note "When it won't come back exactly"
    A window larger than the display it reopens on is fitted to that display —
    so unplugging an external monitor leaves you with a usable window rather
    than one that runs off the edge.

## Grouping

Select several elements and press ++ctrl+g++ to **group** them. A group moves,
selects, and deletes as a single unit. Press ++ctrl+shift+g++ to **ungroup**.
Grouping is handy for moving a whole construction without disturbing its
internal relationships.
