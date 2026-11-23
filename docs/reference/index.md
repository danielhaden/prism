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
  pan and zoom           coordinates all geometry      Console, Scripts
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
- **Commands** (`prism.commands`) back the console.
- **Agent** (`prism.agent`) is the Assistant: the prompt it works from,
  the backend it asks, and the thread it asks on.

## Contributing docstrings

New or changed public classes and methods should carry **Google-style**
docstrings — a one-line summary, then `Args:` / `Returns:` where they add
clarity. mkdocstrings renders them here automatically.

## Modules

- [Items](items.md) — points, lines, intersections, groups, labels
- [Dependencies](dependencies.md) — what is computed from what
- [Canvas](canvas.md) — the scene and view
- [Console Commands](commands.md) — the CLI interpreter
- [Assistant](agent.md) — the script-writing chat
- [Application](app.md) — entry point, main window, tools
