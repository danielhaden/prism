# Prism

A desktop application for creating mathematical drawings for projective geometry.

Built with Python and [PySide6](https://doc.qt.io/qtforpython/).

## Status

Early scaffold. Currently supports a drawing canvas where you can place **points**
and draw **lines**. Features will be refined and expanded iteratively.

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

## Project layout

```
prism/
├── main.py                  # entry point
├── requirements.txt
└── prism/
    ├── app.py               # QApplication bootstrap
    ├── main_window.py       # QMainWindow, toolbar, wiring
    ├── canvas/
    │   ├── scene.py         # QGraphicsScene: drawing logic + tool handling
    │   └── view.py          # QGraphicsView: pan/zoom, viewport config
    └── items/
        ├── point_item.py    # a drawable point
        └── line_item.py     # a drawable line
```

## Tools

- **Select** — click/drag to select and move items.
- **Point** — click on the canvas to place a point.
- **Line** — click a start point, then an end point, to draw a line.
