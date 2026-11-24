# Prism backlog

Issues noticed while using Prism, oldest first. They are logged from the
Assistant panel and worked through from the top: the first `open` one is
the next one up. Fixed entries stay, with the commit that closed them, so
the record of what was wrong does not vanish with the fix.

Each entry is a heading, a few fields, and prose. Nothing here is generated
— edit it by hand whenever that is easier. To close one, set its status to
`fixed` and add a `- **Fixed**:` line naming the commit; leave the entry
itself where it is.

## PB-1 · The Book panel changes page when the dock is resized

- **Status**: open
- **Logged**: 2026-11-24, from Claude Code, at Daniel's report
- **Seen on**: 48330d0

Resizing the Book dock moves it off the page being read.

Expected: the page stays where it was and only the rendering changes size.

Reported in conversation rather than through the panel — the backlog
was built in answer to it, so it is the first thing in it.
