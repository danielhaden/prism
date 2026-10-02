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

## The Selection panel

A dock (left side; **View → Show Selection**) lists whatever is currently
selected — each element's name (its `P1` / `L1` id, or label) and position,
updating live as you move things. Lines also show their endpoints and any
`locked` / `range` / `pivot` tags. The names match the ones the
[console](console.md) uses.

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

!!! note "When it won't come back exactly"
    A window larger than the display it reopens on is fitted to that display —
    so unplugging an external monitor leaves you with a usable window rather
    than one that runs off the edge.

## Grouping

Select several elements and press ++ctrl+g++ to **group** them. A group moves,
selects, and deletes as a single unit. Press ++ctrl+shift+g++ to **ungroup**.
Grouping is handy for moving a whole construction without disturbing its
internal relationships.
