# Points & Lines

## Points

Place points with the **Point** tool (++p++). Points stay a constant on-screen
size at any zoom.

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
  by contrast, slides along its line when dragged.) A line can't be *bound* to
  an anchored point, since its position is computed.

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

**Right-click anywhere on a line → Add Point Here.** A new point appears at
that spot, already anchored to the line. The click is projected onto the line,
so the point sits exactly on it however roughly you aimed, and it works
anywhere along the line — including out past the reference frame.

To anchor a point you already have:

1. Select **one line and one (or more) points** — click one, then ++shift++-click
   the other.
2. Right-click either of them → **Snap Point to Line**.

The point jumps onto the line and is now constrained to it:

- **Dragging the point** slides it *along* the line.
- **Moving or rotating the line** carries the point with it.

Right-click the point → **Remove Anchor** to release it. Deleting the line also
releases anything anchored to it.

### Point context menu (right-click)

- **Modify Display Properties…** — see [Display properties](#display-properties).
- **Snap Point to Line** / **Remove Anchor** — see
  [Anchoring](#anchoring-a-point-to-a-line).
- **Pin Lines Through Point / Unpin** — turn the lines currently passing
  through the point into a [pencil](projectivities.md) (or release them).
- **Add / Edit / Remove Label**, **Label Properties…** — see
  [Labels](#labels).

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

Lines are **infinite projective entities**. When you draw a line through two
points, it extends across the whole canvas; the two points you clicked become
its **defining handles**.

- **Drag the body** to move the whole line.
- **Drag an endpoint handle** (shown on hover/selection) to reorient it.
- **Snapping** — dragging an endpoint onto a point **binds** it there; the
  endpoint then follows that point when it moves.
- **Right-click → Add Point Here** puts a new point on the line where you
  clicked, [anchored](#anchoring-a-point-to-a-line) to it.

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

The [`add horizon`](console.md#add-horizon) console command creates a
horizontal line with its orientation locked; otherwise it's an ordinary
infinite line.

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
