# Prism — project notes for Claude

Prism is a **PySide6 desktop app for projective-geometry drawings**. The goal is
to build complex projective constructions (pencils, complete quadrangles,
harmonic nets, perspective figures) through *composition* — snapping, pinning,
grouping, and a scripting console. The long-term target is
reproducing dense harmonic-net drawings.

Core philosophy: elements are **projective entities**. Lines are infinite by
default, there is **no metric grid or origin axes**, and a "metric" (if wanted)
is imposed *projectively* using the app's own elements.

## Running & environment

- Python **3.12** in `.venv` (rebuild it with `uv venv --python 3.12`; the old
  `/opt/homebrew/bin/python3.12` this was first made with is gone).
- Run the app: `python main.py` (or the VS Code "Prism" launch config, F5).
- App deps: `requirements.txt` (PySide6). Docs deps: `requirements-docs.txt`.

## Working conventions (IMPORTANT)

- **Feature-branch workflow, always**: branch off `main` as
  `feature/<description>` → commit → push → the user raises/merges the PR. Never
  commit feature work directly to `main`. After a merge, pull `main` and cut a
  fresh branch. (The user raises and merges PRs themselves.)
- Commit messages end with the `Co-Authored-By: Claude` trailer.
- **`STATUS.md` is gitignored** — never commit it.
- **Docs must stay green**: after any docstring/API change run
  `mkdocs build --strict` (exit 0). Recurring gotcha: a Google-style `Returns:`
  or `Args:` block that documents something **without a type annotation** fails
  griffe in strict mode — annotate both the return (e.g. `-> tuple`,
  `-> float | None`) and every parameter you list under `Args:`.
- **Headless testing**: verify behavior with
  `QT_QPA_PLATFORM=offscreen ./.venv/bin/python -u -c "..."`. Filter noise with
  `grep -v "propagateSizeHints\|font family"`. For rendering/visual checks,
  render the scene/view to a `QImage` and inspect pixels (state checks alone
  have hidden real rendering bugs — see below).
- The shell's working directory sometimes drifts; prefer `cd
  /Users/dhaden/projects/prism && …` in one-off commands.

## Architecture

```
main.py → prism/app.py → prism/main_window.py (QMainWindow)
  CanvasView (canvas/view.py)   — pan, wheel-zoom (capped)
  CanvasScene (canvas/scene.py) — the hub: owns geometry, propagates deps
  Docks: ConsolePanel, ScriptsPanel, ElementsPanel, BookPanel
```

- **`CanvasScene`** coordinates everything: snapping, endpoint bindings, pivots
  (pencils), point↔line anchors, automatic intersections, undo/redo, naming,
  grouping, labeling.
- **Items** (`prism/items/`): `PointItem` (+ `Labelable` mixin), `LineItem`,
  `GroupItem`, `LabelItem`. There is **one** point type.

### Points & anchors (recently refactored — read carefully)

- **All points are `PointItem`.** There is no `IntersectionPointItem` anymore.
- A point may carry an invisible **anchor** (`prism/anchors.py`) that *pins its
  position*. Anchors are pseudo-points, never drawn:
  - `MeetAnchor(lines)` — pins a point to where a **set** of lines meet. Two
    determine it; further concurrent lines **join the same anchor**, so three
    concurrent lines give one point, not three stacked (stage 3). Read the
    same relation from the other side with `LineItem.meets()`.
  - `LineAnchor(line, t, locked)` — keeps a point on a line; **dragging
    slides** it, unless `locked`, when it is held at `t`. A locked anchor's
    `constrain_drag` returns its current position: returning `None` means
    "the anchor let go", which is the opposite of locking. `locked` is
    persisted, and counts towards `is_determined()`.
- `PointItem.is_meet()` / `meeting_lines()` / `has_anchor()` / `set_anchor()` /
  `clear_anchor()` / `is_determined()`. `itemChange` applies the anchor's drag rule; a `_syncing`
  guard lets the scene reposition anchored points without detaching/churning.
- Default point styling: **radius 1, glow 7, black** (glow = a background-color
  disc drawn behind the dot but over the lines, so converging lines are cut
  away — the harmonic-net look).
- **Visibility is a property** (`Definable.is_shown`/`set_shown`, stage 1 of
  flattening the point model): an item is drawn only when it is both *defined*
  and *shown*. Hiding is a choice and changes nothing else — position, label
  and dependents all survive, and you can build on a hidden point. Delete and
  `(rm …)` on a crossing **hide** it rather than refusing, since the lines
  still meet there. `(hide …)`, `(show …)`, `(show -all)`, and a canvas-menu
  entry bring them back; `shown` is persisted for placed points and, like
  labels, for crossings keyed by their line pair.
- **Being a meet is no longer a gate** (stage 2; the predicate was then
  called `is_intersection()`). Where a limit is
  real it is now stated as a *constraint*: `PointItem.is_determined()` ("the
  lines pin it completely, so it has no freedom to give"), which is what
  "Snap Point to Line" tests. Grouping a crossing is allowed — a group moves
  its children, and a determined point simply stays where its lines put it.
  The meet test survives only where derivation genuinely matters: snapshots
  don't store meets (they are recomputed), `rm` hides rather
  than removes, and `(list)` describes one as `[meet of L1, L2, …]` — the
  relation, not a kind.
- **An anchored point cannot be set loose.** There is no "Remove Anchor"
  command any more, and `MeetAnchor.constrain_drag` returns its position
  rather than `None`, so dragging a crossing no longer detaches it into a free
  point. Hiding is the way to be rid of a point you don't want drawn. The
  removed command was also the **crash when dragging** from the session log:
  `clear_anchor()` left a released point in `scene._meets` with no anchor, and
  the next recompute (one per drag step) died in `_claim_meet` with
  `AttributeError: 'NoneType' has no attribute 'references_line'` — it
  vanished on restart because reopening rebuilds `_meets`. `clear_anchor()`
  now tells the scene and `_apply_meets` drops anchorless entries defensively,
  so the API is safe even though the menu no longer calls it.
- A point's menu also carries **Lock to Line / Unlock From Line** (only when
  it has a `LineAnchor`) and **Delete Point** — which reads **Delete N
  Points** for a multi-selection and **Hide Point** on a meet, since a meet
  can only be hidden.
- `PointItem.contextMenuEvent` shows **Add Line Through Points disabled, with
  the reason**, when the selection isn't exactly two ("3 points selected, need
  2", "right-click one of the two"). It used to vanish silently, which read as
  a bug — see the RCA in the session log. When the join *is* available the two
  single-point line commands are **omitted** (`joining` flag): with a pair
  selected, three ways to draw a line in one menu is noise.
- **Stage 3 (done):** meets are grouped **by place**, not by line pair.
  `_gather_meeting_places()` collects crossings and clusters them within
  `snap_radius()`; `_apply_meets()` reconciles them with the scene's `_meets`
  list, claiming an existing point when it shares **two** lines with a place
  (so a label and anything built on it stay attached as lines come and go).
  `PointItem.is_meet()`/`meeting_lines()` replace `is_intersection()`.
- **Relationships onto a meet survive persistence** (the gap stage 3 found,
  now closed): a meet has no index in the stored point list, so `capture()`
  names it `{"meet": [line indices]}` via `point_ref()`, and `restore()` wires
  those in a **second pass after the recompute** (`_wire_lines(meets_ready)`),
  because meets don't exist until then. Before this a pivot onto a crossing
  was silently dropped — `"pivot": None` — so a net built on crossings lost
  its pinning on every undo.
- **Geometry can now be built on a computed point** — endpoint binding, pin,
  add-line-through, joining two crossings, console `(add-line … (list X))`. Updates
  run in dependency order (see **Propagation**), so what you build follows.
  Still excluded, deliberately: anchoring a meet to a line (its position is
  already determined — `is_determined()`), `rm` of a meet (it hides instead,
  since the lines still meet), and storing meets in snapshots (they're
  recomputed). Grouping a meet **is** allowed as of stage 2.

### Lines (`LineItem`)

- **Infinite by default**, clipped to the scene rect for drawing/intersections
  (`display_line()`); the two defining endpoints are draggable handles.
- The clickable band is `HIT_PX` (12) **screen pixels**, converted with `_px()`
  — as endpoint grabbing and point radii already were. It used to be 12 *scene*
  units, which at the fully-zoomed-out default is 4.5px wide: miss a line by 3
  pixels and you got neither selection nor its context menu, just the canvas
  menu. Keep hit tolerances in screen pixels.
- **Endpoint binding**: an endpoint can bind to a `PointItem` and follow it.
- **Pivot**: pinned through a point → rotates about it (pencils/projectivities).
- **Visible range**, two forms, never both at once (each setter clears the
  other): an **anchor point + neg/pos extents** ("Define Visible Range…"), or
  **two points on the line** that the drawn part runs between
  (`set_segment_ends`, "Show Segment Between Points Only", `(segment L1 P2
  P3)`). The two-point form keeps the *points*, not their positions, so the
  segment follows them; `_live_segment_ends()` returns None when an end is
  deleted or undefined, and the line then draws in full rather than guessing.
  `has_visible_range()` covers both; `has_segment_ends()`/`segment_ends()`/
  `bounded_by()` are the two-point form alone. `scene.show_full_line()` undoes
  either, and removes an anchor point the dialog made (it was never part of the
  figure) while leaving two bounding points alone.
- **A segment must not decide where its own ends are.** `_intersection_of` and
  `MeetAnchor.position` ask `meeting_line(other)`, not `display_line()`. Two
  things it does: (1) grows the segment by `MEET_EPS` (1e-6) at each end, since
  a crossing *at* an end is the ordinary case and a zero-tolerance bounded test
  loses it to rounding — **measured, 1911 of 4000** random configurations; and
  (2) where `other` is a line that *makes* one of the bounding points, uses
  `unbounded_line()` instead. Without (2) there is a feedback loop, seen before
  it was fixed: drag the line outward, its crossing lands past the segment's
  end, the crossing is lost, the segment reopens, the crossing returns — the
  drawing a pass behind the drag. Crossings *not* bounding the segment do go
  away beyond the ends, which is the pre-existing "a crossing lives where the
  drawn parts meet" rule.
- **Segment ends are not dependencies.** `dependencies_of()` deliberately does
  not list them, though it does list the range *anchor*: a segment end is
  normally a point on the line (anchored to it, or a crossing of it), so the
  edge would close a cycle every time. The line's *position* isn't computed
  from them — only its drawing. The two consequences are handled by hand:
  `_detach_point_references` clears the segment when an end is deleted, and
  `_apply_meets` keeps a crossing that `_bounds_a_segment()`, alongside the
  labelled/hidden/depended-on cases.
- **Orientation lock**: `set_orientation_locked(True)` freezes direction (can
  move, can't rotate). The horizon and the vertical use this, and nothing
  else does — the mechanism is direction-agnostic, but there is no UI for
  locking a line at an arbitrary angle. Both are built by
  `_add_locked_line(start, end)`, which they share.
- Line properties dialog: color, thickness (cosmetic), dash style. The same
  thing from the console is `(format <element> <size> [<colour>] [<style or
  glow>])` → `LineItem.set_style()`, which the dialog now shares. Trailing
  arguments may be omitted, a **list** works, colours are hex or Qt names, and
  styles are `solid`/`dashed`/`dotted`/`dash-dot`/`dash-dot-dot`. The pen
  stays **cosmetic**, so thickness is screen pixels at any zoom.
- `(format …)` takes **points too** → `PointItem.set_display()`: size is the
  radius, and the fourth argument is the glow radius rather than a dash style.
  Which one it is is read off the argument — a number is a glow, anything else
  a style name — and a style with no line in the list (or a glow with no
  point) is refused rather than ignored. `(format (points) 3 red)` is the
  whole reason the form exists in that shape.
- **A crossing's formatting does not persist.** `scene_state.capture()` saves
  only points with no anchor; meets are recomputed on restore and come back
  in the default style. Formatting a free point survives, so the two behave
  differently through a reload. Pre-existing — the point dialog has always
  had it — but `(format (points) …)` makes it easy to hit. Fixing it means
  capturing each meet's style against its defining lines and reapplying after
  `recompute_intersections()`.
- Right-click a line → **Add Point to Line** adds a line-anchored point where
  you clicked (`CanvasScene.add_point_on_line_at`, which projects the click
  with `LineItem.closest_scene_point`). Unlike `add_point_on_line` it takes a
  position, not a fraction, so it works past the reference frame. Gated on
  `click_is_on_line()` only: **not** on selection, which was tried and removed
  — a new line isn't selected and any stray click clears the selection, so the
  natural flow (add a horizon, right-click it) never offered the command.
- The same entry appears in the **canvas** menu when the click is blank space
  within `CanvasScene.NEAR_LINE_PX` (40 screen px) of a selected line
  (`nearest_selected_line`, nearest wins). Without it the command is
  unreachable unless you hit the line's ~6px band, since a miss opens the
  canvas menu instead — which is what "the command doesn't appear" meant.
- **`(add-pencil <point> <count>)`** draws `count` lines through a point,
  evenly spaced, via `CanvasScene.add_pencil` → `add_projectivity`.
  **The step is 180°/count, not 360°/count, and that is geometry rather than
  a saving**: a line has no direction, so the line at 10° through a point and
  the line at 190° through it are the same line. The directions through a
  point fill half a turn. Dividing 360 would draw every line twice over for
  an even count — ten asked for, five drawn, each with a twin stacked exactly
  on it. The picture is unchanged: each line runs both ways, so n lines make
  2n rays evenly spaced right round, which is what "evenly spaced around the
  point" looks like. Verified with a pixel probe — a circle round the centre
  of a 12-line pencil crosses 24 bands.
  Hyphenated, not `(add pencil …)`, by the rule that split `add-line` off:
  `add`'s own subforms take numbers and this takes an element. `(add pencil
  …)` is kept as an error saying where it went, as `(add line …)` is.
  `PENCIL_LIMIT` is 360; the count must be whole.
- A point's menu offers **Add Line Through Point** (one line at
  `PointItem.NEW_LINE_ANGLE`, 45°), **Add Pencil…** (a count, defaulting to
  `PointItem.PENCIL_COUNT`, written as one `(add-pencil …)`) and **Add Lines
  Through Point…** (the `ProjectivityDialog` angles — the fuller form, with a
  start, an end and a splay, written as one `(add-line <angle> …)` per ray).
  All go through `add_projectivity`, so the
  lines are **pinned** to the point and it commits undo for them. Both are
  available on intersection points too: the lines are new, so nothing can
  depend on them yet and no cycle is possible. Note "Pin Lines Through Point" only pins *existing*
  lines — before this there was no way to *create* a line through a single
  point except the console.
- Select **two lines**, right-click either → **Add Point at Intersection**
  (`CanvasScene.meet_of`, console `(point <line> <line>)`). It *finds* the
  meet rather than creating one — since stage 3 a point already exists wherever
  lines cross — and shows it if hidden. Disabled with a reason when more than
  two lines are selected. Fires the console command, like Add Horizon.
- Right-click blank canvas → **Add Free Point** (`CanvasScene.add_free_point`)
  adds an unattached point there, **Add Horizon** a horizontal
  orientation-locked line at the clicked height, and **Add Vertical** the
  same a quarter turn round at the clicked width (`add_vertical_at`).
- **Dragging writes the script too** (`_log_drag`, called from
  `end_item_drag`). Menu actions were the easy half; the way a figure is
  actually made is by moving things, and a drag used to leave nothing behind
  — you could noodle your way into a diagram, save it, and find the script
  rebuilt everything in its first position. One command is written **when the
  gesture ends**, from the `(item, position at the press)` pairs
  `begin_item_drag` collected, not one per mouse-move; an item that ended
  where it started writes nothing. `end_item_drag` clears `_drag_items`
  *before* logging, so nothing the command sets off finds a drag apparently
  still in flight. The re-run lands the item where it already is, so
  `commit_undo`'s "nothing actually changed" check leaves a drag at **one**
  undo step — measured.
  **Only a point snapped to a line so far**
  (`PointItem.slides_on_line()` → `(move-snapped-point <point> <fraction>)`):
  its position is a single number, the fraction along its line, which is what
  the command takes. A free point, a label's offset and a group have no
  command to their name yet and are **passed over rather than guessed at** —
  that is the next piece, and the goal is every canvas action logged.
- `CanvasScene.slide_point_to(point, fraction)` moves the **anchor's
  parameter**, not the point; the point follows through `sync_to_anchor`, and
  `itemChange` notifies as usual so dependents come with it. It **honours a
  locked `LineAnchor`** and returns False — locking says "hold it here", and
  a command that moved it anyway would make the lock a suggestion. The form
  refuses first, with the remedy (Unlock From Line) in the message.
  `position_along_line()` is the exact inverse of `fraction_along_line()`,
  shared with `add_point_on_line`, so a position read off the canvas and one
  named in a command mean the same thing.
- **Canvas actions should run as console commands.** `MainWindow` hands the
  scene `console.run_command` via `set_command_runner()`; an action calls
  `scene.run_as_command("(…)")`, which returns False when no runner is set so
  the caller can fall back to doing the work directly (keeps the scene usable
  headless). **Every canvas action with a console equivalent now does this**
  — a figure built by clicking replays as one built by typing. Conversions
  live on the scene: `canvas_fractions()`, `horizon_fraction_at()`,
  `vertical_fraction_at()`,
  `fraction_along_line()`, `point_id()`/`line_id()`/`element_id()`. Deleting
  several points writes `(rm …)` **highest id first**, since removing one
  renumbers those after it. A label containing `"` is applied directly — the
  s-expression reader has no escapes. Still with no console form, so they
  write nothing: visible range, Snap Point to Line, Lock to Line, Pin Lines
  Through Point. (Show Full Line now writes `(segment <line> -full)`.) (Display properties now have one —
  `(format …)` — though the dialogs themselves still don't route through it.)
- `(add point …)` and `(point <line> <fraction>)` take fractions **outside
  0-1** too (`_as_canvas_fraction`), for the same reason `(add horizon …)`
  does: a click outside the frame is ordinary and the menu must be able to
  express it.
- `(add horizon …)` and `(add vertical …)` accept fractions **outside 0-1**
  (beyond the frame) via `_as_canvas_fraction`; `_as_fraction` stays strict
  for the other forms.
  Clicking outside the frame is ordinary, so the command had to allow it. The scene's `contextMenuEvent` routes to the
  topmost label/point/line first, so this is only reached on empty space.
- **Nothing may leave the scene while a mouse gesture is in flight, and Prism
  moves the selection itself.** A drag ran `PointItem.itemChange` →
  `recompute_intersections` → `_apply_meets`, which `removeItem()`d a marker
  whose lines had stopped meeting — freeing it while Qt was still working on
  it. The crash reports say exactly where: in `QGraphicsItem::setPos`, at the
  instruction after `itemChange(ItemPositionChange)` returns, reloading
  `this->d_ptr` to compare the new position with the old. `x0` is 0 there: the
  item was freed inside its own `itemChange` and its memory had been recycled.
  `EXC_BAD_ACCESS`, no traceback, the app simply dies. Two things keep that
  shut, and both are needed:
    * `drag_items` does the moving. Qt's own `QGraphicsItem::mouseMoveEvent`
      walks a **raw** `QList<QGraphicsItem*>` of the selected items, taken
      before it hands control to any `itemChange`. Prism walks its own list
      instead, holding the items as Python references — which is also what
      keeps a `removeItem`'d item alive, since that hands ownership back to
      Python — and skipping anything that has left the canvas. `PointItem`,
      `GroupItem` and `LabelItem` route their `mouseMoveEvent` through it;
      lines were never in that loop (`ItemIsMovable` is off) and handle their
      own drags.
    * `_retire_point` only *hides* a point while `_mid_gesture()` — any event
      being delivered, or a drag between press and release — and keeps a
      reference to it. `_sweep_retired_meets` removes them once the gesture
      is over. Before this, a drag over a busy figure destroyed markers
      between one move event and the next, dozens of times a gesture. Every
      removal of computed geometry goes through it: intersection markers, and
      a point at infinity whose last line has gone.
  Adding items mid-gesture is fine; freeing them is not. Anything new that
  deletes geometry from a signal or an `itemChange` has to go the same way.
- Testing gotcha: `QMenu.exec` **can't be monkeypatched** (it's a C++ method —
  the real modal menu opens and the test hangs). Patch the module's name
  instead: `prism.items.line_item.QMenu = FakeMenu`. And re-fetch items after
  an undo: the snapshot rebuild deletes the C++ objects behind stale wrappers.

### Intersections

- The scene auto-maintains one point per **place** where lines meet, in
  `_meets` (see **Stage 3** above). Reused across recomputes so a selection or
  label sticks; kept but undefined when the crossing goes and something
  depends on it, is labelled or is hidden; a crossing coincident with an
  existing point is skipped — that point *is* the meet.
- `auto_label` labels meets **too** (it used to skip them). A
  label follows its marker as the lines move and through undo/redo, but a
  crossing that stops existing takes its label with it — the marker that comes
  back is a new one.

### Undo/redo & persistence

- `prism/scene_state.py` snapshots/restores the **whole scene** as plain data
  (also groundwork for save/load). Undo = snapshot after each action + rebuild.
  Intersections are recomputed, not stored — **except their labels**, which are
  the user's work: `capture` stores them under `"crossings"` keyed by the pair
  of line indices, and `_restore_crossing_labels` re-applies them after the
  recompute. Without that, labelling a crossing didn't survive undo/redo. `CanvasScene.commit_undo()` is
  called from actions/drags/dialogs; it no-ops when state is unchanged.

## The console (S-expression CLI)

- Commands are **S-expressions**; forms **return the element they create**, so
  they compose: `(add-line 260 (point L1 2/3))`.
- Reader: `prism/sexpr.py`. `;` starts a remark to end of line, **and ends an
  atom**, as in lisp — so `(rm P1;why)` loses its `)` to the remark and reports
  a missing bracket, which is what lisp does too. A `;` inside `"quoted text"`
  is ordinary text, since the quote branch is tried first. Interpreter:
  `prism/commands.py` (`run()` returns `(output, ok)`; `is_recordable`).
- Commands so far: `(add point <across> <down>)`, `(add horizon <fraction>)`,
  `(add vertical <fraction>)`,
  `(add-line <angle> <points>)`, `(add-line <points> <points>)`,
  `(point <line> <fraction>)`, `(point <line> <line>)`, `(rm <element>)`,
  `(label <element> <text>)`, `(label -auto|-clear)`, `(hide …)`, `(show …)`,
  `(list <element> …)`, `(define <name> <value>)`, `(clear)`,
  `(add-pencil <point> <count>)`, `(style "<script>")`,
  `(canvas <property> <value>)`,
  `(format <element> -default)`,
  `(move-snapped-point <point> <fraction>)`,
  `(segment <line> <point> <point>)`, `(segment <line> -full)`,
  `(draw-triangle <p> <p> <p>)`, `(ls [-points|-lines])`, `(range <from>
  <to> <step>)`, `(help)`.
- **Numbers are values**, not only element names: `(list …)` gathers them,
  `(define tilt 30)` names one, and `(range <from> <to> <step>)` builds a
  list of them — which is what `(map …)` had no way to walk when the thing
  varying is a *position* rather than a point
  (`(map (lambda (d) (add point 3/10 d)) (range 2/10 9/10 1/10))`). Three
  things this touched: `_as_number()` reads fractions where `_as_float()`
  can't (`float("1/10")` raises); `_surviving()` must not prune numbers out
  of a named list, since `_on_canvas()` calls `.scene()` on them; and
  `_number_text()` (`:g`) keeps 0.30000000000000004 out of the echo.
  `(range …)` includes **both ends** (tolerance 1e-9 on the count, or 9/10
  by tenths from 2/10 stops one short), ignores the step's sign, walks
  either direction, and caps at `RANGE_LIMIT` (200).
- **`_angle_or_none()` must not evaluate its argument.** `(add-line …)`
  picks its form from the first argument, and the points branch evaluates
  that argument again — so evaluating it to test for a number would place
  two points for `(add-line (add point 1/2 1/2) …)`. It therefore only
  reads a literal number or a `_lookup()` of a bare word; a nested form
  yielding a number is deliberately not an angle.
- **Lists and names** (first step of triangle support): `(list …)` gathers
  elements into a Python list and **flattens** nested lists so they compose;
  `(define <name> <value>)` binds it in `CommandInterpreter._variables`.
  `_value()` resolves a bare word to a variable **before** falling through to
  labels/ids, so a defined name shadows a label of the same text. `_each()`
  applies a form to one element or to every element of a list — `rm`, `hide`,
  `show` and `label` use it (`label` numbers them: `V1 V2 V3`). `(rm <list>)`
  reads every name **before** removing anything, since ids are positional and
  would otherwise all print as `P1`.
  Variables are **in-memory only** — they don't survive a restart, while the
  canvas does. A script that defines what it needs is the durable form.
  A name outlives the elements it holds (clear the canvas, or `rm` a point),
  so `_surviving()` drops anything no longer on the canvas when the name is
  used, and says so plainly if nothing is left — otherwise the user sees
  `Internal C++ object (PointItem) already deleted`. `_on_canvas()` checks
  `shiboken6.isValid` **before** touching the wrapper at all.
- **`(add-line …)` always takes lists.** It replaced `(add line …)` outright
  — hyphenated, a form of its own rather than a kind of `add`, since `add`'s
  other subforms take numbers and this one takes elements. One-element lists
  are the plain case; longer ones draw the **cross product**, every point of
  the first list joined to every point of the second, which is how a net grows
  a round at a time. Bare points still work (`_flatten` treats one as a list of
  one), and the canvas menus emit the explicit list form so a recorded script
  teaches the shape. It reuses an existing side via `_join()`, skips a point
  paired with itself, and refuses above `JOIN_LIMIT` pairs.
  **`_existing_side()` is the dual of `lines-through`**: any line both points
  are *recorded* as lying on is their join, not just one bound to both (a line
  bound to both still wins). Two distinct points determine one line, so this is
  geometry, not a heuristic — and it needs no tolerance, since the relation is
  recorded rather than measured. The payoff is that the cross product needs no
  iteration form: `(add-line (points-on L1) (points-off L1 tri))` draws exactly
  the cevians, because each crossing is already joined to the two vertices of
  the side that made it. `add-line` and `(join …)` both **dedupe** their
  result, since one line can now answer for several pairs. `_only()` returns
  the bare line when just one came of it, so a single join prints and composes
  as it always did. `(add line …)` is kept **only** as an error that says where
  it went.
- **Functions** (`Lambda`, `(lambda …)`, `(map …)`): the language grows in
  itself rather than in Python. `_eval` evaluates a **list head** (inline
  application) and falls back to a *named* `Lambda` when the head isn't a
  built-in form — built-ins win, so the language can't be shadowed. Nothing
  needed adding to the reader: `_eval` never pre-evaluated arguments, so every
  form was already a special form and a lambda body is just the raw
  s-expressions kept for later.
  `_scope` is a stack of parameter frames; `_lookup()` walks it innermost-first
  then `_variables`, so parameters shadow defines which shadow labels. A
  `Lambda` captures `list(self._scope)` at creation and `_apply` **replaces**
  the stack with `callee.scope + [frame]` — lexical, not dynamic. That is why
  depth needs its own counter (`_depth` / `CALL_LIMIT`): the scope stack never
  grows for a function that calls itself, so counting frames would never catch
  runaway recursion (it dies inside Python instead).
  `_apply` also accepts a **built-in form's name**, so `(map hide …)` works;
  `map` flattens results and, when they are all strings, joins them as a
  message the way `_each` does. A `Lambda` is not a canvas item, so
  `_surviving()` must return it untouched — `shiboken6.isValid` on a non-Qt
  object is meaningless — and the Elements panel lists functions under their
  own **Functions** heading.
- `(clear)` empties the canvas but **keeps defined names and functions** — a
  list prunes itself through `_surviving()` on next use, and a `Lambda` never
  touched the canvas, so a script can clear and rebuild. The toolbar's Clear
  goes through `run_as_command("(clear)")` like the canvas menus, so it is
  written to the console; `clear_all()` already commits undo, so it is
  reversible.
- `(draw-triangle …)` takes three points **or a list of three** and joins
  them pairwise, returning the sides as a list. `_join()` **reuses an existing
  side** (a line bound to both points) rather than drawing a second one —
  triangles in a net share edges constantly. Collinear points and a repeated
  point are refused: in the projective sense three points on a line bound no
  triangle.
- The canvas inspector moved from `(list)` to **`(ls)`** so `(list …)` could
  be the constructor. `(list)` and `(list -points)` now explain the move
  rather than failing oddly. Nothing in saved scripts breaks: inspection
  commands were always in `NON_RECORDING`.
- `(label …)` delegates to `CanvasScene.label_element` / `auto_label` /
  `clear_labels`; the scene owns the convention (points upright, lines italic).
  `auto_label` and `clear_labels` now `commit_undo()` themselves — they didn't,
  so labelling from the canvas's right-click menu wasn't undoable and the next
  Ctrl+Z quietly rolled back a *real* action instead.
- `(rm <element>)` resolves points *or* lines (`resolve_element`) and delegates
  to `CanvasScene.remove_element`, which shares `_remove_geometry` with the
  Delete key: references come free rather than cascading. Intersection points
  are refused — they'd be recreated by the next recompute.
- Elements referenced by **label** (`A`, case-insensitive) or **`list` id**
  (`P1`, `L1`). Fractions accept `1/3` or `0.5`. Angles are **degrees clockwise
  from horizontal**. Canvas fractions: 0 = top/left, 1 = bottom/right, of the
  *reference frame*.
- **Scripts**: the console's **>>** button appends the session's *building*
  commands to the ScriptsPanel editor, which runs them.
  Opening, saving and the default folder are the **File menu**'s (see **The
  File menu (scripts)**; `prism/settings.py`, `PRISM_SCRIPTS_DIR` overrides;
  `.prism` text files).
  `prism/settings.py` also holds the book path/page (see **Panels → Book**) and
  the window layout.

## The File menu (scripts)

- **File** is the first menu, and every command in it acts on the **open
  script** — Prism's only documents are scripts, since the canvas keeps itself
  (see **The drawing, between sessions**). New Script / Open Prism Script… /
  Open Recent / Save Script / Save Script As… / Set Default Script Folder… /
  Use Current Script's Folder, on the standard `QKeySequence` shortcuts.
- **The menu settles itself in `aboutToShow`** (`_sync_file_menu`). What it
  offers depends on the open script's path, its dirty flag and what is on
  disk, none of which announces itself; reading those as the menu opens beats
  keeping four actions in step from afar. Open Recent is rebuilt there too.
- **The default scripts folder is a starting point, not a fence.**
  `settings.scripts_dir()` is where **Save Script As…** starts and where
  **Open** looks first; opening a script elsewhere changes nothing. Two ways to move
  it, both under File: a folder dialog, or **Use Current Script's Folder**,
  enabled only when the open script is somewhere else. It moved out of the
  Settings menu — one setting in two menus is only ever a question of which
  one is stale. `PRISM_SCRIPTS_DIR` still overrides, and
  `scripts_dir_is_fixed()` greys both commands out when it does (mirrors
  `shelf_is_fixed`).
- **Recent scripts** live in `settings.recent_scripts()` as a JSON list under
  `scripts/recent`, capped at `RECENT_LIMIT` (8). The getter **filters to
  files that still exist**, and `remember_script` writes that filtered list
  back, so a deleted script leaves for good rather than lingering. Menu text
  is the bare name, qualified with the parent folder only when two entries
  share one (`_recent_label`) — once scripts come from anywhere, two called
  `net` is ordinary.
- **The console's button is `>>`, and it appends to the buffer** rather than
  writing a file. `ConsolePanel.append_to_script()` hands `_recorded` to the
  handler `MainWindow` set with `set_append_handler` (a callable, not a
  signal, because the console needs the answer back — the script's name, or
  None); `ScriptsPanel.append_commands` puts the lines at the end of the
  editor, a blank line clear of what was there, and leaves the script
  **modified rather than written**. So a session can be read, tidied and
  thrown away before it reaches disk. `_recorded` is **cleared** on success,
  which is what makes a second press append only what came since.
  It replaced "Save Script…", which prompted for a name and wrote a file; the
  File menu does that now, and it did it better. With it went
  `ConsolePanel.scriptSaved` and `settings.save_script` / `script_path` /
  `safe_script_name` — the whole name-to-filename chain, since every script
  Prism writes now comes from the file it was read from or from a Save As
  dialog, and there is no name left to mangle.
- `settings.list_scripts()` is **gone** — nothing lists a folder any more.

## Canvas properties

- **`(canvas <property> <value>)`** is the one form for every property of the
  canvas itself; `(canvas)` lists them, `(canvas <property>)` reports one.
  One form rather than a `canvas-*` family, so the next property costs a name
  in `CANVAS_PROPERTIES` instead of a command. `(canvas-auto-intersect …)`
  and `(add auto-intersect …)` are both kept as errors saying where it went.
  `style` is **listed but not settable** here — it has `(style …)`, which
  reads the script and applies it.
- **`auto-intersect`** (`scene._auto_intersect`, persisted) decides whether
  `_apply_meets` **creates** a marker for a place no existing marker claims.
  Off, it skips creation and nothing else: markers already there are still
  claimed, updated and followed as their lines move, so what you asked for
  stays live.
- **`_meet_is_spoken_for()`** is the keep-rule, pulled out of `_apply_meets`
  and now used by both it and the sweep: depended on, bounds a segment,
  labelled, hidden, **or asked for by name**. Switching auto-intersect off
  clears everything else (`_clear_unasked_meets`), so the clearing loses no
  work and switching back on restores the rest with their labels.
- **`PointItem._asked_for`** is the new reason, set by `_mark_meet_of()`,
  which `meet_of` falls through to when auto-intersect is off. It finds the
  place the same way the sweep does, so a third line already concurrent there
  joins the same point rather than a second appearing on top of it.
- **It is persisted on the crossing record, and restore has to *make* the
  marker.** With auto-intersect off the recompute marks nothing, so
  `_restore_crossing_labels` — which used to only decorate markers the
  recompute had built — now calls `scene.meet_of(...)` for a recorded
  crossing it can't find. Without that, reloading lost every crossing you had
  named. `capture` keeps a crossing that is labelled, hidden **or asked for**.
  `scene._auto_intersect` is restored *before* `recompute_intersections()`,
  which is what reads it.
- This is **"Next steps" item 3** (intersection-marker visibility control)
  done, for the case that matters: a dense net can now be built without
  hundreds of dots that say nothing about the construction.

## The canvas's style

- **A style is an ordinary `.prism` script of `(format …)` commands**, and
  the canvas keeps its **path**, not its contents (`scene._style_path`,
  persisted under `"style"`). That is the whole of what makes it reusable:
  several drawings share one script, and editing the script reaches them
  all. Nothing new to open, save or manage — it is a script, so the File
  menu, the Scripts panel and the scripts folder already handle it.
- **It is a default, not a one-off.** `settle_style()` runs from the top of
  `commit_undo()`, *before* the snapshot, so what an action drew is already
  dressed when the state is captured and undo steps between states that each
  look right. The guard that keeps this cheap is `_styled_mark` against
  `_seq_counter`: nothing has been **created** since the style last ran, so
  there is nothing to dress — which is why a drag, a relabel or a format
  doesn't set a sweep running. Measured at ~8% on a 77-element build.
- **A style pass takes no undo steps.** `_form_format` commits one per
  command, so `commit_undo()` returns early while `_styling_depth` is
  non-zero; the action that set the pass going takes the one snapshot.
- **Style commands run through the scene's own `CommandInterpreter`**, made
  on first use, *not* the console's. Through the console they would be
  echoed on every action and recorded into the next script saved. It also
  keeps a style self-contained: it cannot see the console's `(define …)`
  names, and the scene stays usable headless.
- **Formatting by hand wins, and keeps winning.** `PointItem.set_display`
  and `LineItem.set_style` each ask `scene.applying_default_style()`: if a
  style is being applied and the item `is_styled_by_hand()`, they **return
  without doing anything**; if it is *not* being applied, they set that flag.
  One rule in one place per kind, so it catches the command, both display
  dialogs and anything added later. `(format <element> -default)` →
  `reset_display()` / `reset_style()` hands it back.
  `_styling_depth` is a **count, not a flag**: a creation default applied
  inside a style pass would otherwise clear it on the way out.
- **Persisted per element** as `own_style`, defaulting to **False** when
  absent — a drawing written before styles was drawn plain, and reading its
  elements as "the user's own" would leave a newly attached style with
  nothing it was allowed to touch.
- `restore_style()` puts the attachment back **without running it**: a
  snapshot already holds every element's look, so re-reading the file once
  per undo step would buy nothing. `MainWindow.__init__` calls
  `apply_style()` once after `_restore_drawing()`, since the script may have
  been edited since the drawing was saved.
- **This closes the "a crossing's formatting does not persist" gap** for
  anything a style covers: markers are recomputed and then dressed afresh
  every time. A crossing formatted *by hand* still doesn't survive a reload —
  `capture()` stores only points with no anchor — which is unchanged.
- **A style may only say how things are drawn** (`STYLE_FORMS` = `format`,
  `define`). `_read_style` parses each line and drops anything else,
  returning `(commands, refused)`. This is not tidiness: **a style runs on
  every action**, so a building command in one adds another copy of what it
  makes each time — measured before it was shut, one `(add point …)` in a
  style turned a single action into two new points. Attaching names what it
  skipped and why; a later change to the file is reported only when the set
  of refusals *changes*, since a standing complaint on every action is noise.
  An unparseable line is skipped the same way and the rest still runs.
- Known wart, older than styles and now more visible: `(define <name>
  <colour>)` fails — `_form_define` reads its value as an element or a
  number, and `#bbbbbb` is neither, so it reports "No element named". Numbers
  bind fine. Fixing it means letting `_form_define` bind a literal that
  `QColor` accepts, which would make palettes-in-a-style work.
- **Planes come free.** A style is whatever `(format …)` accepts, so it
  governs exactly the kinds that command knows. When planes land, extending
  `_form_format` (and adding a `(planes)` enumerator) reaches styles with no
  change here.
- The older `scene._point_style` ("apply to all" in the point dialog, a
  default for points made later) still works and is applied *as a default*,
  so it does not mark a new point as the user's own. A style asserted
  afterwards wins over it.

## Exporting (`prism/svg_export.py`)

- **File → Export as SVG…** (Ctrl+Shift+E) writes **what the view shows** —
  same pan, same zoom, lines clipped at the same edges. Fit to Frame first
  for the reference frame. `QSvgGenerator`, from PySide6's own QtSvg, so no
  new dependency.
- **It renders the scene, not the view.** `view.render()` would bring
  `drawForeground` with it, and the off-screen point markers are a way of
  finding points, not part of the drawing.
- **It must paint the background itself.** `setBackgroundBrush` is on the
  *view*, so `scene.render()` leaves it out — and a point's glow is a disc
  **in the background colour**, drawn over the lines to cut them away behind
  the dot. Without the fill those discs are grey blobs on transparency.
  Checked by rendering the file back with `QSvgRenderer` and reading the
  corner pixel.
- **It lifts the selection** for the duration and puts it back in a
  `finally`. Selected items paint highlighted, and nobody wants orange in an
  exported figure.
- `QSvgGenerator` writes `width`/`height` in **millimetres**; the `viewBox`
  carries the pixel coordinate system. A test that pins the size should pin
  the viewBox.
- No console form, and that is the rule rather than an omission: exporting
  does not *build* anything, so it belongs with `(ls)` rather than with the
  commands a script replays. If one is ever added it goes in
  `NON_RECORDING`.
- The folder is remembered (`settings.export_dir`), since a drawing you
  export is one you export again.

## The Assistant (`prism/agent/`, `prism/agent_panel.py`)

- **It writes scripts; it does not touch the canvas.** A reply's fenced
  `prism` block goes to the **Scripts panel** through the same
  `append_commands` path the console's `>>` uses, and the user reads it and
  runs it. That is the whole safety story — no tools, no approval dialogs,
  nothing happening to a drawing unreviewed — and it is why this was worth
  building before a tool-using agent.
- **The command reference is read off the interpreter** (`(help)`), not
  written out in the prompt. A hand-copied reference goes stale the first
  time a form is added, and a stale one is worse than none: the model writes
  commands that don't exist, confidently. `ConsolePanel.interpreter()` exists
  for this.
- **Canvas state goes in the user turn, not the system prompt**
  (`canvas_context` → `(ls)`). The system prompt carries one
  `cache_control: ephemeral` breakpoint, and caching is a prefix match — put
  the canvas in there and every turn throws the cache away.
- **Threading**: `AgentWorker` is a `QThread` that owns the request and hands
  text back through signals, which Qt delivers on the GUI thread. Nothing in
  `prism/agent/` touches a widget or the scene. Mode A has no tools, so there
  is no marshalling the other way — that is the thing to get right if tools
  are ever added (a tool handler must hop to the GUI thread with
  `BlockingQueuedConnection`, and the GUI thread must then never block on the
  worker, or the two deadlock).
- **A turn that fails or is stopped is taken back out of the history.**
  Leaving the question in would send it again, unanswered, stacked on the
  next one; a half-streamed reply would be sent back as though finished.
- **The API key is never Prism's.** The SDK reads it from the environment
  (`ANTHROPIC_API_KEY`, or an `ant auth login` profile). QSettings is a
  plaintext plist — nothing of the user's goes in it. `looks_configured()`
  only decides whether to show a hint; it never blocks a send, since a
  profile works with no environment variable at all.
- Model `claude-opus-5-5`, adaptive thinking with `display: "summarized"`
  (without it a long think is a silent pause that reads as a hang — the
  summary goes to the status line, not the transcript), `effort: medium`,
  streaming.
- `anthropic>=2.0` is the first dependency beyond PySide6. The panel degrades
  to a message if it is missing; Prism still runs.
- **This is "Mode A"** of the design we settled on: conversational, no tools.
  Mode B — the model driving the canvas through `run_prism_command`, with a
  `look_at_canvas` screenshot tool — is the next step, and `backends.py`'s
  seam is the **turn**, so a local model slots in by implementing
  `stream_turn` alone.

## Panels

- **Console** (bottom).
- **Elements** (`prism/elements_panel.py`; left): a `QTreeWidget` of the whole
  canvas — Points, Lines, Groups, and the names bound with `(define …)` (read
  through `ConsolePanel.variables()`). Rows carry the console's own names, and
  selection syncs **both ways** (a `_syncing` flag breaks the feedback loop).
  Rebuilt on a 120ms single-shot timer off `scene.changed`, since that signal
  fires per repaint and a drag is a flood of them.
  **A row stores a *key*, never the item.** Qt keeps item data as a raw
  pointer, so a row holding a scene item outlives it when the canvas is
  cleared — and merely reading that data back reconstructs a wrapper around
  freed memory, which **segfaults**, before any `shiboken6.isValid` check can
  run. The key is `f"{kind}{_seq}"` (the creation number, stamped once and
  stable, unlike positional ids), resolved against the live scene when
  needed. Clearing with something selected used to kill the app this way. A section that has not
  been shown before opens expanded; one shown before keeps its state
  (`_seen_sections`). Its **objectName is still `SelectionPanel`**, which is
  what Qt saves dock layouts against — renaming it would strand saved
  layouts, so it stays. It replaced the old selection-only panel.
- **Scripts** (right, tabbed with the Book): an editor over **one script at a
  time**. It used to list the scripts folder above the editor; the list is
  gone and **the File menu opens a script instead** — a script is an ordinary
  file that may live anywhere, so a list of one folder could only ever show
  some of them. The panel keeps the editing concerns (the open path, the
  dirty flag, reading and writing); `MainWindow` owns the commands and the
  dialogs. Saving an untitled script needs a dialog, so the panel's own Save
  button calls back through `set_save_handler(…)` — the same bargain as
  `CanvasScene.set_command_runner`, and it falls back to `save()` when no
  handler is set so the panel stays usable headless. The editor is
  `prism/script_editor.py`'s **`ScriptEditor`** — a `QPlainTextEdit` with a
  line-number gutter (`_LineNumbers`, a plain child widget so it doesn't
  scroll horizontally with the text). Numbers are drawn at `NUMBER_SCALE`
  (0.75) of the text's size with a `NUMBER_MIN_PT` floor, which at the default
  9pt means 7pt. Width is remeasured on `blockCountChanged` and whenever the
  font changes — `setFont` is overridden for it, guarded with `getattr` since
  Qt may call it before `_numbers` exists. The **current line's number is
  bold and darker** (`CURRENT_NUMBER_COLOR`; bold alone is too quiet at 7pt),
  repainted off `cursorPositionChanged` (the line losing currency
  needs redrawing as much as the one gaining it, so the whole strip is
  repainted). Width is measured with the **bold** font, the wider of the two,
  so the gutter doesn't jostle as the cursor moves. **Run** executes the
  *editor's* text, not the file, so an edit can be tried before it's kept;
  Save / Revert alongside (Refresh went with the list). Unsaved edits mark the
  script *modified* and prompt (Save / Discard / Cancel) before New, Open, and
  **on `closeEvent`** — the canvas keeps itself between sessions, but a script
  is a file, so Cancel there `event.ignore()`s the close. Saving goes through
  `settings.write_script(path, text)`,
  which writes the **exact path** the script was read from: deriving it from
  the display name would send a hand-named script like `net(1).prism` to
  `net1.prism` and leave the original behind.
- **Book** (`prism/book_panel.py`; right, tabbed with Scripts): a
  `QPdfView` reader over a **shelf** of PDFs — Whicher's *Projective
  Geometry*, Coxeter's — with a dropdown at the top to pick between them and
  a **…** button for Add / Rename / Remove. Added from **Settings → Add
  Book…**; `PRISM_BOOK_PATH` stands in for the whole shelf (one book, nothing
  to add or remove — `settings.shelf_is_fixed()` greys the menu out).
  Continuous pages, fit-to-width by default. Uses PySide6's **QtPdf /
  QtPdfWidgets** — part of PySide6, so no new dependency.
  The shelf lives in `settings.books()` as JSON under `books/shelf`, each
  entry `{name, path, page}`, with `books/current` the index. **Each book
  keeps its own page**, so turning to the other and back returns to where you
  were. A shelf that was never written is built from the old single
  `paths/book_path` + `book/last_page`, so an upgrade opens where it left off.
  Display names come off the filename (`book_name_for`): drop `.pdf`, cut at
  the first ` -- ` (which is what tames an Anna's-Archive download), truncate
  to `BOOK_NAME_LIMIT`. The full path is the dropdown's tooltip.
  Gotchas: `QPdfView.zoomFactor()` stays at its last *custom* value while
  fit-to-width is on, so a zoom step reconstructs the fitted scale from the page
  width (`_fitted_zoom`); `QPdfPageNavigator.jump()` to the page it's already on
  emits nothing, so the controls are synced by hand after a load; closing a
  document **re-emits a page change**, which would record the outgoing page
  against the incoming book — hence `_loading`, and reading the target page
  before the close. The combo uses `activated`, not `currentIndexChanged`, so
  only a choice the user made turns a page. The shelf row lives *outside* the
  placeholder/reader stack, so a book that has gone missing still leaves the
  dropdown there to switch away from it.
  Testing gotcha: **`QPdfView`'s viewport does not paint into an offscreen
  `QWidget.render()`** — only the chrome does, so a pixel count over the
  panel measures buttons and borders and passes on a blank page. Check the
  page at the document instead (`QPdfDocument.render(page, size)`), which
  also distinguishes two books by their content rather than their page count.
  Page rendering is **asynchronous**, so either way needs an event-pumping
  wait.

## The drawing, between sessions

- `MainWindow` writes the canvas to `settings.drawing_path()` on close
  (`canvas.json` in the app-data dir; `PRISM_DRAWING` overrides, as the tests
  use) and reads it back in `__init__` **before `init_history()`**, so undo
  starts from the restored drawing rather than from an empty canvas.
- It is `scene_state.capture()`/`restore()` wrapped with `DRAWING_VERSION`; a
  file from a different version, or one that is missing, unreadable or
  malformed, is ignored and Prism opens empty. A bad file must never stop the
  app opening.
- Saved **on close only**, so a crash loses the session. Fine for a
  convenience; a real save/load to a file of the user's choosing is still open
  (next steps).

## Window layout

- `MainWindow` saves `saveGeometry()`/`saveState()` to QSettings on close and
  restores them at the end of `__init__` (after the docks exist), so window
  size and the dock layout — including the right tab group's width and which
  tab is raised — persist between sessions. Keys live in `prism/settings.py`.
- `saveState()` silently skips anything without an `objectName`; every dock has
  one and the toolbar is `ToolsToolbar`. **A new dock must set one** or it
  won't be restored.
- `LAYOUT_VERSION` guards the state: bump it when the set of docks changes and
  Qt will ignore older saved layouts rather than restoring them badly.
- **Settings → Reset Window Layout** restores `_default_geometry`/
  `_default_state`, snapshotted in `__init__` *before* any saved layout is
  applied, and clears the stored keys.
- Testing gotcha: in a tabbed dock group **only the raised tab reports the
  group's width** — a hidden tab keeps a stale one, which reads as a layout bug
  that isn't there. Measure the dock whose `visibleRegion()` is non-empty. The
  offscreen platform's screen is 800x800 and Qt fits restored windows to the
  screen, so pass `offscreen:configfile=<json>` with a bigger screen when
  testing anything at realistic window sizes.
- Qt fits a restored window to the screen it reopens on, so a layout saved on a
  big display comes back usable on a small one (and headless tests see the
  offscreen 800x800 virtual screen clamp anything larger).

## Canvas behavior

- Opens **fully zoomed out** to a **reference frame** (`REFERENCE_SIZE = 1200`,
  separate from the 4000-unit scene rect so infinite-line ends stay off-screen);
  can zoom in but **not out** past it.
- **The view can still be panned off the frame** — the scene rect is 4000 units
  and scrolling isn't clamped — and with no grid, a drifted view looks exactly
  like an empty canvas. Console commands place geometry by fraction *of the
  frame*, so a successful `(add horizon 1/3)` can land off-screen and read as
  "nothing happened". Two ways back: `CanvasView.recenter_if_lost()` (a wheel
  notch out at the zoom floor) and **View → Fit to Frame** (Ctrl+0,
  `fit_reference_frame`). Suspect this first for any "it ran but I see
  nothing" report.
- **Right-click never changes the selection** (swallowed in
  `CanvasScene.mousePressEvent`) so selection-based menus survive.
- **Hit-test through the view transform**: `CanvasScene.items_at()` passes the
  viewport transform to `items()`. Points carry `ItemIgnoresTransformations`,
  so their clickable radius is in *screen pixels*; without the transform Qt
  reads it as scene units, shrinking the target as you zoom out. A point was
  winning a right-click only within ~1px at the default zoom (and ~4px zoomed
  in), so clicks meant for a point landed on the line under it. `PointItem`
  also has `HIT_PX = 6` — the drawn dot is radius 1, far too small to aim at.
- **Context menus are routed by hand**, so `CanvasScene.contextMenuEvent` must
  `event.setPos(target.mapFromScene(event.scenePos()))` before calling an
  item's handler. Qt fills `pos()` in only when *it* delivers the event; routed
  by hand it stays `(0, 0)`, which reads as "the click landed on the item's own
  origin". That silently broke **Add Point to Line** on every line except one
  passing through its item origin — a horizon at 1/2 worked, every other height
  failed. Tests that build a `QGraphicsSceneContextMenuEvent` and call the
  handler directly will not catch this: they set `pos()` themselves. Drive a
  real `QContextMenuEvent` at `view.viewport()` instead
  (`scratchpad/real_path_check.py` pattern).
- **Off-screen points are marked at the edge** (`CanvasView.drawForeground`
  → `_draw_offscreen_points`): an arrow plus the point's name, drawn in
  *device* coordinates (`setWorldMatrixEnabled(False)`) so it keeps its size.
  Placed where the point's defining line leaves the view
  (`_edge_towards` → `_rect_crossings`), falling back to straight out from the
  middle for a point on no line; `_defining_lines()[:1]` picks **one** line
  arbitrarily for a meet — refining that is open. Everything is drawn inside
  the viewport (a tip past the edge is just clipped) and nudged aside from the
  line so it doesn't sit on top of it. Hidden and undefined points get
  nothing.
- **A marker is clickable, and selects its point.** It is painted chrome, not
  a scene item, so Qt's hit-testing knows nothing about it: `drawForeground`
  records `(viewport rect, point)` per marker in `_offscreen_hits` (cleared at
  the top of every `_draw_offscreen_points`, including the early return), and
  `CanvasView.mousePressEvent` tests the click against that list before
  handing on. The press is **accepted** and its release swallowed
  (`_marker_press`), so no rubber band starts under the click and Qt doesn't
  warn about an unpaired release. Only with the Select tool — the view now
  tracks the tool in `_tool` — and Ctrl/Shift toggles rather than replaces. A
  selected marker is drawn in the items' own selection orange
  (`OFFSCREEN_SELECTED_COLOR`), and the cursor becomes a pointing hand over
  one. The hit list is only as fresh as the last repaint, so a point may be
  gone by the time it is clicked: `point_at_marker()` checks
  `shiboken6.isValid` before returning one, since reading a dead wrapper
  segfaults.
- The view uses `FullViewportUpdate`, because an edge marker can change from
  a scene change anywhere; the default partial updates left stale chrome.
- Multi-select: **Ctrl-click** or **rubber-band** (plain clicks replace).
- Delete/Backspace deletes; Ctrl+G/Ctrl+Shift+G group/ungroup; Ctrl+Z /
  Ctrl+Shift+Z undo/redo.

## Hard-won bugs / lessons

- **Init order**: set attributes read by `boundingRect()`/`itemChange()`
  **before** `super().__init__`/`setFlag`/`setPos` — Qt calls those overrides
  during construction and Shiboken *swallows* the resulting Python exception, so
  the item ends up silently broken (bit us on `LabelItem._offset` and point
  glow/anchor state).
- **Verify rendering with pixels, not just state.** A label that stored its text
  correctly still didn't paint (hit-testing/paint-offset mismatch). Render to a
  `QImage` and check pixels for visual features (glow masking lines, infinite
  lines spanning the view, etc.).
- QGraphicsItemGroup **clears/loses child registration** on ungroup — remove &
  re-add children so the scene re-registers them in its selection index.
- Enum access differs by PySide version: `QLineF.IntersectionType.Bounded…`.

## Next steps (deferred to future sessions)

1. **Propagation engine** — let geometry stay attached to *live intersection
   points* (lines through intersections that update): the real harmonic-net
   enabler. **Steps 1 and 2a of 4 are done.** (1) `prism/dependencies.py` reads
   the graph out of the scene (`DependencyGraph`: `dependencies`/`dependents`,
   `affected_by`, `update_order`, `cycles`, `would_cycle`). (2a)
   `CanvasScene.propagate_from()` now drives updates from `update_order` — the
   fixed sweep and `_sync_anchored_points` are gone, and `on_point_moved` /
   `on_line_changed` both funnel through it; `_replace()` re-places one item
   from its dependencies. Verified behaviour-identical against the old sweep
   (same coordinates, every relationship kind).
   (2b) `prism/items/definable.py` adds an **undefined** state (the `Definable`
   mixin on both item types): an item whose definition fails keeps its identity
   and relationships but is hidden, so Qt also drops it from hit-testing.
   `CanvasScene._set_defined` decides it and cascades (anything computed from
   something undefined is undefined too); `settle_definitions()` re-decides
   scene-wide after `recompute_intersections` and after a snapshot restore.
   A marker whose crossing is gone is now **kept** (undefined) when anything
   depends on it — dropping it would strand them. Undefined-ness is derived,
   never stored.
   (3) `CanvasScene.would_cycle()` guards the three places an existing item
   gains a dependency: `pin_lines_through`, `anchor_points_to_line` and
   endpoint-drag binding in `LineItem`. Making *new* geometry never needs the
   check — nothing can depend on it yet. (4) Guards lifted in `resolve_point`,
   `_as_point`, `selected_points`, `snap_target` and the point context menu.
   **This item is done.** What is left is polish, not plumbing: marker
   visibility control for dense nets, and deciding whether a crossing's label
   should outlive the crossing.
   Why it's blocked today, measured: a crossing marker is repositioned by
   `recompute_intersections` **last** and its movement notifies nobody, so a
   line force-bound to a crossing never moves at all (not even one update
   late). Decide before step 2: a crossing only exists where the *clipped*
   display segments meet (`_intersection_of` uses `BoundedIntersection`), so
   near-parallel lines meeting off-canvas have no marker — what should a line
   depending on a vanished crossing do?
2. **Higher-order console forms** — **done as enumerators**: `(points)`,
   `(lines)`, `(meets <lines>)`, `(join <points>)`, `(diff …)`,
   `(take n …)`, `(last n …)`, `(repeat n <form>)`, `(intersect …)`,
   `(lines-through <point>)` (→ `CanvasScene.lines_through`, the dual of
   `meets`), and its own dual pair `(points-on <line> [<points>])` /
   `(points-off …)`, which filter a list (or the whole canvas) by the same
   recorded-relation rule, so the three forms always agree.
   `_as_point`/`_as_line`/`_as_element` **unwrap a one-element list**
   (`_one()`), so a filter returning a single element composes where that
   element is wanted — `(point (take 1 (lines)) 1/2)`. Several or none
   is reported with the elements named; `_describe()` keeps a raw Python
   repr out of every message. `repeat` is a *special
   form*: it keeps its argument unevaluated and re-evaluates it each round, so
   `(points)` inside sees what the last round made. `(last …)` is the one that
   grows a net — points come in creation order, so the tail is what the
   previous step produced, while `(take …)` re-joins the seed and stalls.
   `(intersect a b)` is the exact dual of `(diff …)` — same shape, matching on
   `id()` — so the two **partition** the first list and
   `(list (intersect a b) (diff a b))` rebuilds it. Neither dedupes, since
   both filter the first list; `(list …)` concatenating without deduping is a
   separate open question. There is still no `union`, and `join` is geometric,
   not set-theoretic. **`(without …)` was renamed `(diff …)`** so the set
   forms read as a family; the old name is kept only as an error saying where
   it went, as `(add line …)` is.
   `join` reuses an existing side (shared `_join` with `draw-triangle`) and
   refuses above `JOIN_LIMIT` (300) lines, since n points pairwise is
   n(n-1)/2 and their crossings multiply again; `repeat` caps at
   `REPEAT_LIMIT` (100).
   `lines_through` reports **recorded relations** (meet, binding, pivot,
   range anchor, segment end, line anchor), not geometry — the user's call. Consequence
   worth knowing: two lines crossing exactly at a *placed* point report
   nothing, because `_intersection_of` skips making a meet where a point
   already sits, so no relation exists to find. Building *through* a point
   (pin or bind) records one.
   `(draw-cevians <triangle> <line>)` is the first net step: for each
   crossing of the line with a side, join it to the vertex *not* on that side
   (the one with no edge to it). Reuses existing edges via `_existing_side`,
   and refuses clearly when a side is parallel to the line or the triangle
   isn't drawn. The three cevians are **not** concurrent — they form a second
   triangle, which is the point of the construction.
   Still open: a form for the harmonic step itself
   (three collinear points → the fourth harmonic), which is what makes a net
   *disciplined* rather than merely dense.
3. Intersection-marker **visibility control** (dense nets get busy).
   **Done** as `(canvas auto-intersect false)` — see **Canvas
   properties**. What is left is finer grain than all-or-nothing:
   marking crossings of a chosen set of lines, say.
4. Save/load a drawing to a file (scene_state is most of the way there).
5. Possibly: promote/detach UX, snapping toggles, coordinate readout.

## Removed features

- **The Library panel and templates are gone** (`library_panel.py`,
  `templates.py`, `template_store.py`, and the view's drag-and-drop). The
  console does the job better: a template was a frozen figure you dropped on
  the canvas, while a script is one you can read, edit, parameterise and
  replay, and **clicking already writes the script**. The built-ins it
  carried all have console forms — `(draw-triangle …)`, `(add-line …)` for a
  quadrilateral, `(add-pencil …)` for a projectivity.
- `LAYOUT_VERSION` went to **2** for it: the right-hand tab group was
  anchored on the Library and is anchored on Scripts now, so a layout saved
  against the old group would restore with a tab that is not there.
- A user's saved templates are left on disk at
  `user_templates.json` in the app-data directory (the old
  `PRISM_TEMPLATE_STORE` override pointed at it). Nothing reads it; it is
  theirs to delete.

## Branch history (merged PRs → main)

canvas scaffold → canvas refinement → composability (groups, pivots) → library
tab → harmonic-nets groundwork (infinite lines, visible range, no grid, console
`list`, projectivity command) → docs (MkDocs site) → display properties
(point radius/color/glow, point↔line anchor, zoom cap, undo/redo) → expand CLI
(S-expressions, add horizon/line/point, scripts, settings) → refine canvas
behavior (default point style, line-through-two-points + CLI, selectable
intersections, Selection panel, **point/anchor unification**) → recenter a
drifted canvas (Fit to Frame, zoom-out rescue) → console `(rm <element>)` →
book viewer (QtPdf Book panel + Settings → Book (PDF)…).
