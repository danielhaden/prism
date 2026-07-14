# Prism

**Mathematical drawings for projective geometry.**

Prism is a desktop application (Python + [PySide6](https://doc.qt.io/qtforpython/))
for constructing projective-geometry figures — pencils of lines, complete
quadrangles, harmonic configurations, and the nets they generate.

Unlike a typical drawing tool, Prism treats its elements as **projective
entities**: lines are *infinite* by default, there is *no metric grid*, and
figures are built by **composition** — snapping, pinning, grouping, and
templating elements together.

## Highlights

- **Infinite lines** with an optional, user-defined visible range.
- **Points** that snap onto other points and onto lines.
- **Projectivities (pencils)** — lines pinned through a common point that
  rotate about it.
- **Automatic intersections** wherever visible lines cross.
- **A template library** of built-in figures plus your own saved constructions,
  inserted by drag-and-drop.
- **A console** for inspecting and (increasingly) scripting the canvas.

## Where to go next

<div class="grid cards" markdown>

- **[Getting Started](guide/getting-started.md)** — install and run Prism.
- **[Tools & Canvas](guide/tools.md)** — the toolbar, navigation, and shortcuts.
- **[Projective Basics](concepts/projective-basics.md)** — the ideas behind the app.
- **[Developer Reference](reference/index.md)** — the API, generated from the code.

</div>
