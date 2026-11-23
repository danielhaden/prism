# The Book

Prism's constructions come out of books — Olive Whicher's *Projective
Geometry: Creative Polarities in Space and Time*, Coxeter's *Projective
Geometry* — so the app can keep them open beside the canvas. The **Book**
panel is a PDF reader docked on the right, tabbed with the Library and
Scripts; toggle it from **View → Show Book**.

## The shelf

Prism doesn't ship any books. The first time you open the panel it asks for
one:

1. **Settings → Add Book…** (or the **Add Book…** button in the panel).
2. Pick the PDF.

Add as many as you read from. They appear in the **dropdown** at the top of
the panel, and choosing one turns to it. The **…** button beside the dropdown
adds another, renames the current one, or takes it off the shelf — removing a
book forgets it, and leaves the PDF itself exactly where it is.

Names are read off the filename: the `.pdf` goes, anything after a `--`
separator goes with it (which is what turns a download's whole bibliography
into *Projective Geometry, 2nd Edition*), and a long name is cut short to fit.
**Rename…** if the result isn't what you'd call it. The dropdown's tooltip
always carries the full path.

The chooser starts on **All files** rather than `*.pdf`, because a scan filed
away by hand often has no `.pdf` on the end — Prism goes by the file's
contents, not its name.

!!! tip "Overriding the shelf"
    Setting `PRISM_BOOK_PATH` in the environment stands in for the whole
    shelf: that one PDF, and no adding or removing. Handy for testing.

## Reading

| Control | What it does |
|---------|--------------|
| dropdown | Which book to read |
| **…** | Add, rename, or remove a book |
| **◀** / **▶** | Previous / next page |
| page box | Type a page number to jump there |
| **−** / **+** | Zoom out / in, in 25% steps |
| **Fit** | Scale the page to the panel's width (the default) |

Pages scroll continuously, so you can also just drag the scrollbar through a
chapter. Zooming in or out leaves **Fit** behind and holds the scale you chose
until you press **Fit** again.

**Every book keeps its own page.** Turn from one to the other and back and you
return to where you were, not to wherever the other book happens to be open —
a shelf of books with bookmarks in them, rather than a file viewer.
