# Prism — project notes for Claude

Prism is a **PySide6 desktop app for projective-geometry drawings**. The goal is
to build complex projective constructions (pencils, complete quadrangles,
harmonic nets, perspective figures) through *composition* — snapping, pinning,
grouping, templates, and a scripting console. The long-term target is
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
  CanvasView (canvas/view.py)   — pan, wheel-zoom (capped), template drops
  CanvasScene (canvas/scene.py) — the hub: owns geometry, propagates deps
  Docks: LibraryPanel, ConsolePanel, ScriptsPanel, SelectionPanel
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
  - `IntersectionAnchor(a, b)` — pins a point to the crossing of two lines.
    **Dragging detaches** it (becomes a free point; the crossing gets a fresh
    marker).
  - `LineAnchor(line, t)` — keeps a point on a line; **dragging slides** it.
- `PointItem.is_intersection()` / `has_anchor()` / `set_anchor()` /
  `clear_anchor()`. `itemChange` applies the anchor's drag rule; a `_syncing`
  guard lets the scene reposition anchored points without detaching/churning.
- Default point styling: **radius 1, glow 7, black** (glow = a background-color
  disc drawn behind the dot but over the lines, so converging lines are cut
  away — the harmonic-net look).
- **Boundary**: operations that build *hard dependencies* (endpoint binding,
  pin, add-line-through, grouping) **exclude intersection points**, because a
  computed point can't yet propagate its motion. See "Next steps".

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
- **Visible range**: right-click → "Define Visible Range…" adds an anchor point
  + neg/pos extents; only that segment is drawn.
- **Orientation lock**: `set_orientation_locked(True)` freezes direction (can
  move, can't rotate). The horizon uses this.
- Line properties dialog: color, thickness (cosmetic), dash style.
- Right-click a **selected** line → **Add Point to Line** adds a line-anchored
  point where you clicked (`CanvasScene.add_point_on_line_at`, which projects
  the click with `LineItem.closest_scene_point`). Unlike `add_point_on_line` it
  takes a position, not a fraction, so it works past the reference frame. The
  entry is gated on `isSelected()` and `click_is_on_line()`.
- The same entry appears in the **canvas** menu when the click is blank space
  within `CanvasScene.NEAR_LINE_PX` (40 screen px) of a selected line
  (`nearest_selected_line`, nearest wins). Without it the command is
  unreachable unless you hit the line's ~6px band, since a miss opens the
  canvas menu instead — which is what "the command doesn't appear" meant.
- A point's menu offers **Add Line Through Point** (one line at
  `PointItem.NEW_LINE_ANGLE`, 45°) and **Add Lines Through Point…** (the
  `ProjectivityDialog` angles). Both go through `add_projectivity`, so the
  lines are **pinned** to the point and it commits undo for them. Both are
  hidden on intersection points, like pinning, since a computed point can't
  drive what hangs off it. Note "Pin Lines Through Point" only pins *existing*
  lines — before this there was no way to *create* a line through a single
  point except the console.
- Right-click blank canvas → **Add Free Point** (`CanvasScene.add_free_point`)
  adds an unattached point there. The scene's `contextMenuEvent` routes to the
  topmost label/point/line first, so this is only reached on empty space.
- Testing gotcha: `QMenu.exec` **can't be monkeypatched** (it's a C++ method —
  the real modal menu opens and the test hangs). Patch the module's name
  instead: `prism.items.line_item.QMenu = FakeMenu`. And re-fetch items after
  an undo: the snapshot rebuild deletes the C++ objects behind stale wrappers.

### Intersections

- The scene auto-maintains an intersection point (a `PointItem` +
  `IntersectionAnchor`) for every crossing pair, in `_intersections` (keyed by
  ordered line-id pair). Reused across recomputes (so selection/label sticks);
  removed when the crossing is gone; a crossing coincident with a placed point
  is skipped.
- `auto_label` labels intersection points **too** (it used to skip them). A
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
  they compose: `(add line 260 (point L1 2/3))`.
- Reader: `prism/sexpr.py` (supports `;` comments). Interpreter:
  `prism/commands.py` (`run()` returns `(output, ok)`; `is_recordable`).
- Commands so far: `(add point <across> <down>)`, `(add horizon <fraction>)`,
  `(add line <angle> <point>)`, `(add line <point> <point>)`,
  `(point <line> <fraction>)`, `(rm <element>)`, `(label <element> <text>)`,
  `(label -auto|-clear)`, `(list [-points|-lines])`, `(help)`.
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
- **Scripts**: Console "Save Script…" records the session's *building* commands;
  ScriptsPanel lists/runs them. Location set via **Settings → Scripts Folder…**
  (`prism/settings.py`, `PRISM_SCRIPTS_DIR` overrides; `.prism` text files).
  `prism/settings.py` also holds the book path/page (see **Panels → Book**) and
  the window layout.

## Panels

- **Library** (right): built-in templates (Triangle, Quadrilateral, Complete
  Quadrangle, Projectivity) + user-saved; drag onto canvas; save selection;
  right-click rename/delete; persisted via `prism/template_store.py`.
- **Console** (bottom), **Scripts** (right, tabbed with Library), **Selection**
  (left; live names + positions, matches console naming via
  `CanvasScene.element_name`).
- **Book** (`prism/book_panel.py`; right, tabbed with Library/Scripts): a
  `QPdfView` reader for *one* PDF — Olive Whicher's *Projective Geometry* —
  pointed at from **Settings → Book (PDF)…** (`PRISM_BOOK_PATH` overrides).
  Continuous pages, fit-to-width by default, and the last page read is
  remembered (reset when the book is re-pointed). Uses PySide6's **QtPdf /
  QtPdfWidgets** — part of PySide6, so no new dependency.
  Gotchas: `QPdfView.zoomFactor()` stays at its last *custom* value while
  fit-to-width is on, so a zoom step reconstructs the fitted scale from the page
  width (`_fitted_zoom`); `QPdfPageNavigator.jump()` to the page it's already on
  emits nothing, so the controls are synced by hand after a load; page rendering
  is **asynchronous**, so a pixel check needs an event-pumping wait.

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
   enabler. **Step 1 of 4 is done**: `prism/dependencies.py` reads the graph
   out of the scene (`DependencyGraph`: `dependencies`/`dependents`,
   `affected_by`, `update_order`, `cycles`, `would_cycle`). It is pure
   observation — nothing consumes it yet, so behaviour is unchanged. Remaining:
   (2) drive updates from `update_order` instead of the fixed sweep in
   `on_point_moved`/`on_line_changed`/`_sync_anchored_points`; (3) refuse
   cycles at bind time with `would_cycle`; (4) lift the intersection guards in
   `resolve_point`/`_as_point`, `selected_points`,
   `selected_point_line_pair`, `snap_target`, pin and group.
   Why it's blocked today, measured: a crossing marker is repositioned by
   `recompute_intersections` **last** and its movement notifies nobody, so a
   line force-bound to a crossing never moves at all (not even one update
   late). Decide before step 2: a crossing only exists where the *clipped*
   display segments meet (`_intersection_of` uses `BoundedIntersection`), so
   near-parallel lines meeting off-canvas have no marker — what should a line
   depending on a vanished crossing do?
2. **Higher-order console forms** — `fold`/map to build pencils/projectivities
   programmatically.
3. Intersection-marker **visibility control** (dense nets get busy).
4. Save/load a drawing to a file (scene_state is most of the way there).
5. Possibly: promote/detach UX, snapping toggles, coordinate readout.

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
