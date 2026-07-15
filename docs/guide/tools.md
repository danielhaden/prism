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
| Delete | ++delete++ / ++backspace++ | Removes the selected elements. |
| Clear | — | Empties the whole canvas. |
| Group | ++ctrl+g++ | Combines selected elements into one unit. |
| Ungroup | ++ctrl+shift+g++ | Breaks a group back into its members. |

!!! note "Selection lives in Select mode"
    Selecting and moving happen with the **Select** tool. In Point or Line
    mode, clicks are reserved for drawing.

## Navigating the canvas

- **Zoom** — mouse wheel (anchored under the cursor).
- **Pan** — drag with the **middle mouse button**.

There is deliberately **no grid and no origin axes** — a metric has no place on
a projective canvas. If you want a scale, construct one projectively from the
elements themselves. See [Projective Basics](../concepts/projective-basics.md).

## Grouping

Select several elements and press ++ctrl+g++ to **group** them. A group moves,
selects, and deletes as a single unit. Press ++ctrl+shift+g++ to **ungroup**.
Grouping is handy for moving a whole construction without disturbing its
internal relationships.
