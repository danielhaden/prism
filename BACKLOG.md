# Prism backlog

Issues noticed while using Prism, oldest first. They are logged from the
Assistant panel and worked through from the top: the first `open` one is
the next one up. Fixed entries stay, with the commit that closed them, so
the record of what was wrong does not vanish with the fix.

Each entry is a heading, a few fields, and prose. Nothing here is generated
— edit it by hand whenever that is easier. To close one, set its status to
`fixed` and add a `- **Fixed**:` line naming the commit; leave the entry
itself where it is.

Two reports of one fault are **folded into the older entry**: the newer one
keeps its id and its own words, takes the status `duplicate`, and gains a
`- **Duplicate of**:` line. Only `open` entries are in the queue, so a
folded report leaves it without being deleted — an id that has been written
in a commit message must never come back meaning something else.

## PB-1 · The Book panel loses its place when the panel is resized

- **Status**: fixed
- **Fixed**: e0d9908
- **Logged**: 2026-11-24, from Claude Code, at Daniel's report
- **Seen on**: 48330d0
- **Also reported as**: PB-2, the reading position not surviving a restart —
  the same fault, folded in here

Resizing the Book dock moves the reader off the page being read. The page it
lands on is then written down as the place to come back to, so the reading
position is lost across a restart as well.

Expected: the page stays where it was and only the rendering changes size,
and the page that comes back next session is the page that was being read.

Measured on 16bb87b, headless, fit-to-width on, Coxeter open at page 60:
narrowing the panel from 560px to 336px put the reader on page 106, and
widening it to 760px put it on page 43. Neither resize brought page 60 back.

Root cause: fit-to-width rescales the page on every resize, so the
continuous layout's total height changes while the scrollbar keeps its
*pixel* value — the same offset is then a different page.
`QPdfPageNavigator` reports the move as an ordinary page change and
`BookPanel._on_page_changed` writes it to settings, which is what carries
the symptom past the end of the session.

Reported in conversation rather than through the panel: the backlog was
built in answer to it, so it is the first thing in it.

Fixed by taking the reader's place in an event filter on the view and
putting it back once the new layout exists. The capture has to be in the
filter rather than the dock's `resizeEvent`: the reflow runs *inside*
`QWidget::resize`, so a hold taken from `resizeEvent` saves the place the
reflow has already moved to — it runs without error and fixes nothing. A
zoom step turned out to move the page the same way (60 to 32) and is held
too; scrolling is not, since that is the reader moving.

## PB-2 · The Book panel's page is lost on resize or restart

- **Status**: duplicate
- **Logged**: 2026-11-25, from the Assistant panel, drafted by Ollama · llama3.2:latest
- **Seen on**: 16bb87b
- **Duplicate of**: PB-1, fixed in e0d9908

The page the Book panel is on is not kept across a window resize or an app
restart. Expected: it keeps the page and the layout.

> Reported as: Can you log this issue?

Kept rather than removed. The second report is what established that the
fault is seen across restarts too, and the words above are the ones that
were actually said about it.
