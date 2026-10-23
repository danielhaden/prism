# Points & Lines

## Points

Place points with the **Point** tool (++p++), or **right-click blank canvas →
Add Free Point** to drop one where you clicked without leaving the Select tool.
Points stay a constant on-screen size at any zoom.

A *free* point is attached to nothing and can be dragged anywhere — as opposed
to one [anchored to a line](#anchoring-a-point-to-a-line), which slides along
it.

- **Drag** a point (Select tool) to move it. Anything attached to it follows.
- **Snapping** — while placing or dragging, a point snaps onto a nearby
  **existing point** or onto a **line** (an orange ring previews the target).
- **Points are all the same.** Whether you place a point or one appears where
  two lines cross, it's the same kind of object — same styling, selection, and
  context menu.

- **Anchors.** A point may carry an invisible *anchor* that pins its position
  (these are never drawn). A point at a line **crossing** is simply a point
  anchored to that intersection; a point [anchored to a
  line](#anchoring-a-point-to-a-line) is one anchored to slide along it.
  **Dragging** an intersection point **detaches** it — it becomes an ordinary
  free point, and a fresh point re-marks the crossing. (A line-anchored point,
  by contrast, slides along its line when dragged.) Geometry **can** be built
  on a computed point: bind a line to a crossing, pin a pencil through it, join
  two crossings — updates run in dependency order, so what you build follows.

- **When a definition fails.** A crossing exists only while its two lines
  actually meet on the canvas. Slide them apart and the crossing — and
  everything built on it — **disappears**, rather than lingering somewhere
  meaningless. Nothing is lost: bring the lines back together and it all
  returns, still attached. Prism refuses a relationship that would be circular
  (pinning a line to a crossing that line helps make, say) and says so in the
  status bar.

### A line through two points

Select **two points** — click one, then **++ctrl++-click** the other (or drag a
**rubber-band box** around both). Right-click either point →
**Add Line Through Points**. An infinite line is drawn through both, with each
endpoint **bound** to its point, so the line stays through them as they move.

!!! tip "Selecting more than one thing"
    A plain click selects just what you clicked — a second click *replaces* the
    selection. To select several items, ++ctrl++-click each, or drag a box
    around them with the Select tool.

### Anchoring a point to a line

Snapping is transient — it releases as soon as you drag away. To make a point
*stay* on a line, **anchor** it. The quickest way is to make it there in the
first place:

**Select the line, then right-click on it → Add Point to Line.** A new point
appears at that spot, already anchored to the line. The click is projected onto
the line, so the point sits exactly on it however roughly you aimed, and it
works anywhere along the line — including out past the reference frame.

Right-clicking **on** the line is enough — the line's own menu opens, so which
line you mean is already settled. Nothing needs selecting first.

Your aim can be looser than that too: **select** a line and you can right-click
up to about 40 pixels away from it, on blank canvas, and the canvas menu offers
**Add Point to Line** beside **Add Free Point**. Selecting is what says which
line you mean out there, where the click alone doesn't. With several lines
selected, the point goes on the nearest one.

!!! tip "Vanishing points"
    Put a point on the horizon this way, then right-click *that point* →
    **Add Lines Through Point…** to fan a pencil out of it. The lines are
    pinned to the point, so they keep meeting there as you rotate them.

To anchor a point you already have:

1. Select **one line and one (or more) points** — click one, then ++shift++-click
   the other.
2. Right-click either of them → **Snap Point to Line**.

The point jumps onto the line and is now constrained to it:

- **Dragging the point** slides it *along* the line.
- **Moving or rotating the line** carries the point with it.

Right-click the point → **Lock to Line** to hold it where it is: it stays on
the line, but dragging no longer slides it along. **Unlock From Line** gives it
back its freedom. Locking is useful once a point is where you want it in a
construction and you'd rather not nudge it by accident while moving things
around it.

Right-click the point → **Remove Anchor** to release it from the line
altogether. Deleting the line also releases anything anchored to it.

### Hiding a point

A dense figure has a point at every crossing, and most of them are scaffolding
you'd rather not look at. **Hide** one and it stops being drawn — nothing else
changes. It keeps its position and its label, anything built on it carries on
working, and you can build on it while it's hidden.

```
(hide P3)       # stop drawing it
(show P3)       # draw it again
(show -all)     # bring back everything hidden
```

Pressing ++delete++ on a crossing, or `(rm P3)`, hides it too: the two lines
still meet there, so the point can't honestly be removed — but it can be got
out of the way. Right-click blank canvas for **Show N Hidden Point(s)** when
you want them back.

`(list)` marks hidden points `[hidden]`, so nothing disappears without trace.

### Point context menu (right-click)

- **Modify Display Properties…** — see [Display properties](#display-properties).
- **Add Line Through Point** — draw one line through it, at 45°, **pinned** to
  the point so dragging the line rotates it about the point rather than moving
  it away.
- **Add Lines Through Point…** — the same, for a whole
  [pencil](projectivities.md): choose a start angle, an end angle and how many
  lines. This is the quick way to fan lines out of a vanishing point.
- **Add Line Through Points** — joins **two** selected points, binding each
  endpoint to its point.

With two points selected, joining them is clearly what you mean, so the menu
offers **only** that: the two single-point commands stand down rather than
giving you three ways to draw a line at once. They come back as soon as the
selection isn't a pair. Select anything other than two and the join is still
listed, greyed out, saying what it needs.
- **Snap Point to Line** / **Remove Anchor** — see
  [Anchoring](#anchoring-a-point-to-a-line).
- **Pin Lines Through Point / Unpin** — turn the lines *already* passing
  through the point into a [pencil](projectivities.md) (or release them). This
  one draws nothing; use **Add Line(s) Through Point** to create lines.
- **Lock to Line / Unlock From Line** — on a point anchored to a line, hold it
  in place or let it slide again. See
  [Anchoring](#anchoring-a-point-to-a-line).
- **Delete Point** — remove it. With several points selected it reads
  **Delete N Points** and removes them all. On a crossing it reads **Hide
  Point** instead: the lines still meet there, so it can only be
  [hidden](#hiding-a-point).
- **Add / Edit / Remove Label**, **Label Properties…** — see
  [Labels](#labels). Intersection points can be labelled like any other.

### Display properties

Right-click any point — **including intersection points** — and choose
**Modify Display Properties…**:

| Property | Meaning |
|----------|---------|
| **Radius** | The dot's on-screen radius. |
| **Color** | The dot's fill color. |
| **Glow radius** | Radius of a disc drawn *around* the point. `0` disables it. |
| **Glow color** | Fill of that disc — typically the background color. |

**Glow** is the surround: a filled disc drawn *behind* the dot but *over* the
lines. Where many lines converge, a background-colored glow cuts them away near
the point so it reads cleanly instead of dissolving into a knot of ink.

!!! tip "Apply to All Points"
    The dialog's **Apply to All Points** button pushes the properties to every
    point on the canvas *and* makes them the default for points created later —
    including intersection points as they're recomputed.

## Lines

Right-click blank canvas → **Add Horizon** drops a horizontal,
[orientation-locked](#locked-orientation) line at the height you clicked. It
runs the [`(add horizon …)`](console.md#add-horizon-fraction) console command
to do it, so the command is echoed and recorded like any other.

Lines are **infinite projective entities**. When you draw a line through two
points, it extends across the whole canvas; the two points you clicked become
its **defining handles**.

- **Drag the body** to move the whole line.
- **Drag an endpoint handle** (shown on hover/selection) to reorient it.
- **Snapping** — dragging an endpoint onto a point **binds** it there; the
  endpoint then follows that point when it moves.
- **Select it, then right-click → Add Point to Line** puts a new point on the
  line where you clicked, [anchored](#anchoring-a-point-to-a-line) to it.

### Visible range

Although a line is infinite, you can restrict the **visible** portion:

1. Right-click the line → **Define Visible Range…**
2. A small **anchor point** is placed on the line, and you enter a **negative**
   and **positive** extent.
3. The line is now drawn only from `anchor − negative` to `anchor + positive`
   along its direction.

Drag the anchor to slide the visible window along the line. Right-click →
**Show Full Line** restores the infinite line (and removes the anchor). Deleting
the anchor also reverts the line.

### Locked orientation

A line's **orientation can be locked**, freezing its direction: it can still be
moved, but nothing rotates it — dragging an endpoint handle slides the whole
line through the cursor rather than tilting it, and pivot rotation is refused.

A **horizon** is such a line: horizontal, orientation-locked, otherwise an
ordinary infinite line. Make one by **right-clicking blank canvas → Add
Horizon**, which puts it at the height you clicked, or with the
[`(add horizon <fraction>)`](console.md#add-horizon-fraction) console command,
which measures a fraction down the reference frame instead. The menu is the one
to reach for when the height should sit against geometry already on the canvas;
the console form when you want it measured.

### Line properties

Right-click a line → **Line Properties…** to set its **color**, **thickness**,
and **style** (solid, dashed, dotted, dash-dot). Thickness stays constant
on-screen regardless of zoom.

## Labels

Right-click a point or line → **Add Label…** to attach text. Labels:

- are **draggable** (nudge them off the geometry) and follow their element;
- have **display properties** — right-click a label → **Label Properties…** for
  font, size, color, bold/italic/underline;
- can be generated for the whole scene at once (right-click empty canvas →
  **Auto-label Scene**): points get `A, B, C…`, lines get italic `a, b, c…`.
