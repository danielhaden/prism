# The Book

Prism's constructions come out of a book — Olive Whicher's *Projective
Geometry: Creative Polarities in Space and Time* — so the app can keep a copy of
it open beside the canvas. The **Book** panel is a PDF reader docked on the
right, tabbed with the Library and Scripts; toggle it from **View → Show Book**.

## Pointing Prism at the book

Prism doesn't ship the book. The first time you open the panel it asks for a
copy:

1. **Settings → Book (PDF)…** (or the **Choose Book…** button in the panel).
2. Pick the PDF.

The choice is remembered between sessions. The chooser starts on **All files**
rather than `*.pdf`, because a scan filed away by hand often has no `.pdf` on
the end — Prism goes by the file's contents, not its name.

!!! tip "Overriding the path"
    Setting `PRISM_BOOK_PATH` in the environment overrides the saved path,
    which is handy for testing or for keeping two copies around.

## Reading

| Control | What it does |
|---------|--------------|
| **◀** / **▶** | Previous / next page |
| page box | Type a page number to jump there |
| **−** / **+** | Zoom out / in, in 25% steps |
| **Fit** | Scale the page to the panel's width (the default) |

Pages scroll continuously, so you can also just drag the scrollbar through a
chapter. Zooming in or out leaves **Fit** behind and holds the scale you chose
until you press **Fit** again.

Prism remembers the page you were last on and opens there next time, so the
panel behaves like a book with a bookmark in it rather than a file you reopen.
Pointing Prism at a *different* book clears that bookmark.
