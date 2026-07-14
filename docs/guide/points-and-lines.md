# Points & Lines

## Points

Place points with the **Point** tool (++p++). Points stay a constant on-screen
size at any zoom.

- **Drag** a point (Select tool) to move it. Anything attached to it follows.
- **Snapping** — while placing or dragging, a point snaps onto a nearby
  **existing point** or onto a **line** (an orange ring previews the target).
- **Intersection points** — where two visible lines cross, Prism maintains a
  derived point automatically (drawn in green). These are computed; you don't
  place or move them.

### Point context menu (right-click)

- **Pin Lines Through Point / Unpin** — turn the lines currently passing
  through the point into a [pencil](projectivities.md) (or release them).
- **Add / Edit / Remove Label**, **Label Properties…** — see
  [Labels](#labels).

## Lines

Lines are **infinite projective entities**. When you draw a line through two
points, it extends across the whole canvas; the two points you clicked become
its **defining handles**.

- **Drag the body** to move the whole line.
- **Drag an endpoint handle** (shown on hover/selection) to reorient it.
- **Snapping** — dragging an endpoint onto a point **binds** it there; the
  endpoint then follows that point when it moves.

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
