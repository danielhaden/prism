# The Library

The **Library** is a dockable panel (right side; toggle via **View → Show
Library**) of reusable **templates** — small constructions you insert by
drag-and-drop.

## Inserting a template

Drag any thumbnail from the Library onto the canvas. The figure is created
**centered on the cursor**, and its lines are bound to its points, so it behaves
as a proper construction the moment it lands.

## Built-in templates

| Template | Description |
|----------|-------------|
| **Triangle** | Three points and the three lines joining them. |
| **Quadrilateral** | Four points and their four edges. |
| **Complete Quadrangle** | Four points and all six lines joining them. |
| **Projectivity** | A pencil of four lines through a common center point (pinned, so they rotate about it). |

## Saving your own

1. Select the geometry on the canvas you want to reuse.
2. Click **Save Selection…** in the Library panel and give it a name.

The template captures the points, the lines, their point/endpoint **bindings**,
any **pivot** relationships, and label text — so a saved pencil stays a pencil
when you drag it back out.

Saved templates are **persisted to disk** and reload the next time you open
Prism. Right-click one of your saved templates to **Rename…** or **Delete** it.
(Built-in templates are read-only.)

!!! note "Where templates are stored"
    User templates live in your platform's application-data directory
    (e.g. `~/Library/Application Support/Prism/user_templates.json` on macOS).
