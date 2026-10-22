# Getting Started

## Requirements

- **Python 3.12** (3.10+ should work; 3.12 is what Prism is developed against)
- macOS, Windows, or Linux

## Install

From the project root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

You can also launch it from VS Code — the repo ships a **"Prism"** run
configuration in `.vscode/launch.json` (press **F5**).

## First steps

When Prism opens you'll see a blank canvas, a toolbar of tools, a **Library**
dock on the right, and a **Console** dock at the bottom.

1. Press **P** (Point tool) and click a few times to place points.
2. Press **L** (Line tool) and click two points — a line is drawn through them
   and extends across the whole canvas (lines are infinite).
3. Press **V** (Select tool) and drag things around.
4. Drag a **Triangle** out of the Library onto the canvas.

See [Tools & Canvas](tools.md) for the full set of tools and shortcuts.

## Your drawing is still there next time

Prism keeps the canvas when you quit and puts it back when you open it again —
points, lines, labels, what you've hidden, and the relationships between them,
including pencils pinned to a crossing. There's nothing to save.

It's written when you close the window, so a crash loses that session's work.
If the file is ever unreadable Prism opens with an empty canvas rather than
refusing to start.

## Building the documentation (optional)

This site is built with MkDocs:

```bash
pip install -r requirements-docs.txt
mkdocs serve      # live preview at http://localhost:8000
```
