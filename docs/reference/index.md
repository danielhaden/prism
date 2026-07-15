# Developer Reference

This section is generated from the source docstrings, so it stays in step with
the code.

## Architecture at a glance

Prism is a PySide6 (Qt Graphics View) application.

```
main.py  →  prism.app.run()  →  prism.main_window.MainWindow
                                     │
        ┌────────────────────────────┼───────────────────────────┐
        │                            │                           │
  CanvasView (view)          CanvasScene (scene)          Dock panels
  pan / zoom / drops     coordinates all geometry      Library, Console
                                     │
                 ┌───────────────────┼───────────────────┐
              PointItem           LineItem          IntersectionPointItem
              (+ Labelable)   (bindings, pivots,     (derived points)
                               visible range)
```

- **[`CanvasScene`](canvas.md#prism.canvas.scene.CanvasScene)** is the hub: it
  owns the geometry items and propagates dependencies — snapping, endpoint
  bindings, pivots (pencils), and automatic intersections.
- **Items** (`prism.items`) are the drawable objects. `PointItem` and
  `LineItem` mix in `Labelable` for right-click labels.
- **Templates** (`prism.templates`) serialize/instantiate figures for the
  Library; `prism.template_store` persists user templates.
- **Commands** (`prism.commands`) back the console.

## Contributing docstrings

New or changed public classes and methods should carry **Google-style**
docstrings — a one-line summary, then `Args:` / `Returns:` where they add
clarity. mkdocstrings renders them here automatically.

## Modules

- [Items](items.md) — points, lines, intersections, groups, labels
- [Canvas](canvas.md) — the scene and view
- [Templates](templates.md) — the Library's figures and persistence
- [Console Commands](commands.md) — the CLI interpreter
- [Application](app.md) — entry point, main window, tools
