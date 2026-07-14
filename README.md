# Prism

A desktop application for creating mathematical drawings for **projective
geometry**.

Built with Python and [PySide6](https://doc.qt.io/qtforpython/).

Prism treats its elements as projective entities: lines are **infinite** by
default, there is **no metric grid**, and figures are built by **composition** —
snapping, pinning lines into pencils, grouping, and drag-and-drop templates.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
python main.py
```

## Documentation

Full user guide and developer reference are in [`docs/`](docs/), built with
MkDocs:

```bash
pip install -r requirements-docs.txt
mkdocs serve      # live preview at http://localhost:8000
```

Start with [`docs/index.md`](docs/index.md), or the
[Getting Started](docs/guide/getting-started.md) guide.

## Project layout

```
prism/
├── main.py                  # entry point
├── requirements.txt         # app dependencies
├── requirements-docs.txt    # documentation toolchain
├── mkdocs.yml               # docs site config
├── docs/                    # user guide, concepts, developer reference
└── prism/
    ├── app.py               # QApplication bootstrap
    ├── main_window.py       # window, toolbar, menus, dock panels
    ├── canvas/              # scene (geometry coordination) + view (pan/zoom)
    ├── items/               # points, lines, intersections, groups, labels
    ├── templates.py         # Library figures (serialize / instantiate)
    ├── template_store.py    # user-template persistence
    ├── library_panel.py     # the Library dock
    ├── console_panel.py     # the Console dock
    └── commands.py          # console command interpreter
```

## Highlights

- **Infinite lines** with an optional user-defined visible range.
- **Snapping** — points snap onto points and lines; line endpoints bind to points.
- **Projectivities** — pencils of lines pinned through a common point.
- **Automatic intersections** wherever visible lines cross.
- **Template library** of built-in figures plus your own saved constructions.
- **Console** for inspecting (and, increasingly, scripting) the canvas.
