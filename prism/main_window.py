"""The Prism main window: canvas, toolbar, and menus."""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QFileDialog, QMainWindow

from prism.agent_panel import AgentPanel
from prism.book_panel import BookPanel
from prism.canvas import CanvasScene, CanvasView
from prism.console_panel import ConsolePanel
from prism.scripts_panel import ScriptsPanel
from prism.elements_panel import ElementsPanel
from prism.scene_state import capture, restore
from prism.svg_export import export_svg
from prism.settings import (
    SCRIPT_SUFFIX,
    export_dir,
    clear_recent_scripts,
    clear_window_layout,
    ensure_scripts_dir,
    forget_script,
    load_drawing,
    recent_scripts,
    remember_script,
    save_drawing,
    scripts_dir,
    scripts_dir_is_fixed,
    set_scripts_dir,
    set_export_dir,
    set_window_geometry,
    set_window_state,
    window_geometry,
    window_state,
)
from prism.tools import Tool


class MainWindow(QMainWindow):
    #: Bumped when the set of docks changes enough that an older saved layout
    #: would restore badly; Qt then ignores states saved under a lower number.
    #: 2: the Library dock went, and the right-hand tab group is anchored on
    #: Scripts instead — a layout saved against the old group would restore
    #: with a tab that no longer exists.
    #: 3: the Assistant dock joined that group.
    LAYOUT_VERSION = 3

    #: Bumped when the saved-canvas format changes in a way that can't be
    #: read back; an older file is then ignored rather than half-restored.
    DRAWING_VERSION = 1

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prism")
        self.resize(1000, 720)

        self.scene = CanvasScene(self)
        self.view = CanvasView(self.scene, self)
        self.setCentralWidget(self.view)

        self.console = ConsolePanel(self.scene, self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.console)
        # Canvas actions with a console equivalent run as that command, so the
        # two ways of working produce the same echo and the same script.
        self.scene.set_command_runner(self.console.run_command)

        self.elements = ElementsPanel(self.scene, self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.elements)
        # The console owns the interpreter, so the names come from there.
        self.elements.set_variables_source(self.console.variables)

        self.scripts = ScriptsPanel(self.console.run_script, self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.scripts)
        # Saving an untitled script needs the File menu's dialog, so the
        # panel's own Save button goes the same way as the menu command.
        self.scripts.set_save_handler(self._save_script)

        self.agent = AgentPanel(lambda: self.console.interpreter(), self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.agent)
        self.tabifyDockWidget(self.scripts, self.agent)
        # What the assistant writes goes where everything else written goes.
        self.agent.set_script_sink(self._append_to_script)

        self.book = BookPanel(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.book)
        self.tabifyDockWidget(self.scripts, self.book)
        self.scripts.raise_()
        # The console's >> hands the session over to the editor.
        self.console.set_append_handler(self._append_to_script)

        self._tool_actions: dict[Tool, QAction] = {}
        self._create_actions()
        self._build_toolbar()
        self._build_menu()

        self.scene.statusMessage.connect(self.statusBar().showMessage)
        self.scene.historyChanged.connect(self._update_history_actions)
        # Bring back last session's drawing before the first snapshot, so undo
        # starts from what's on screen rather than from an empty canvas.
        self._restore_drawing()
        # The drawing stores each element's look, so it comes back right —
        # but the style script may have been edited since it was saved, and
        # opening is the moment to pick that up.
        self.scene.apply_style()
        self.scene.init_history()
        self._select_tool(Tool.SELECT)
        # Snapshot the built-in layout before any saved one lands on top of it,
        # so "Reset Window Layout" has something exact to go back to.
        self._default_geometry = self.saveGeometry()
        self._default_state = self.saveState(self.LAYOUT_VERSION)
        self._restore_layout()

    # -- Window layout -----------------------------------------------------

    def _restore_layout(self) -> None:
        """Put the window back the size and shape it was last left.

        Called once the docks exist, so their saved widths and tab order can be
        applied; a first run has nothing saved and keeps the defaults.
        """
        geometry = window_geometry()
        if geometry:
            self.restoreGeometry(geometry)
        state = window_state()
        if state:
            self.restoreState(state, self.LAYOUT_VERSION)

    def reset_layout(self) -> None:
        """Go back to the layout Prism ships with, now and on the next launch."""
        clear_window_layout()
        self.restoreGeometry(self._default_geometry)
        self.restoreState(self._default_state, self.LAYOUT_VERSION)
        self.statusBar().showMessage("Window layout reset.", 4000)

    # -- The drawing -------------------------------------------------------

    def _restore_drawing(self) -> None:
        """Put back the canvas this app was last closed with."""
        data = load_drawing()
        if not data or data.get("version") != self.DRAWING_VERSION:
            return
        try:
            restore(self.scene, data["scene"])
        except Exception as exc:  # a bad file must not stop Prism opening
            self.scene.clear_all()
            self.statusBar().showMessage(
                f"Couldn't reopen the last drawing: {exc}", 8000
            )

    def _clear_canvas(self) -> None:
        """Clear from the toolbar, through the console, so it joins the script.

        Same bargain as the canvas menus: what you do by clicking is written
        as the command that would have done it, and clearing still happens if
        the console can't run it.
        """
        if not self.scene.run_as_command("(clear)"):
            self.scene.clear_all()

    def _save_drawing(self) -> None:
        """Keep the canvas for next time."""
        try:
            save_drawing(
                {"version": self.DRAWING_VERSION, "scene": capture(self.scene)}
            )
        except OSError:
            pass  # nothing useful to do about it while quitting

    def closeEvent(self, event):
        # The canvas keeps itself between sessions; a script is a file, and
        # unsaved edits to one have nowhere to come back from.
        if not self.scripts.confirm_discard():
            event.ignore()
            return
        # A turn still in flight would outlive the window Qt is tearing down.
        self.agent.shutdown()
        self._save_drawing()
        set_window_geometry(self.saveGeometry())
        set_window_state(self.saveState(self.LAYOUT_VERSION))
        super().closeEvent(event)

    # -- Actions -----------------------------------------------------------

    def _create_actions(self) -> None:
        self._create_script_actions()

        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusive(True)

        for tool, label, shortcut in (
            (Tool.SELECT, "Select", "V"),
            (Tool.POINT, "Point", "P"),
            (Tool.LINE, "Line", "L"),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(shortcut))
            action.setToolTip(f"{label} ({shortcut})")
            action.triggered.connect(lambda _=False, t=tool: self._select_tool(t))
            self._tool_group.addAction(action)
            self._tool_actions[tool] = action

        # A single shared delete action, bound to both the forward-delete key
        # and the Backspace-labeled key (the latter is what most keyboards,
        # notably on macOS, produce as "delete").
        self.delete_action = QAction("Delete", self)
        self.delete_action.setShortcuts(
            [QKeySequence(QKeySequence.Delete), QKeySequence(Qt.Key_Backspace)]
        )
        self.delete_action.setToolTip("Delete selected (Delete / Backspace)")
        self.delete_action.triggered.connect(self.scene.delete_selected)
        # Keep the shortcut live even when a child widget has focus.
        self.delete_action.setShortcutContext(Qt.WindowShortcut)
        self.addAction(self.delete_action)

        self.clear_action = QAction("Clear", self)
        self.clear_action.setToolTip("Clear the whole canvas")
        self.clear_action.triggered.connect(self._clear_canvas)

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setToolTip("Undo the previous action")
        self.undo_action.triggered.connect(self.scene.undo)
        self.undo_action.setEnabled(False)
        self.addAction(self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcuts(
            [QKeySequence.Redo, QKeySequence("Ctrl+Shift+Z")]
        )
        self.redo_action.setToolTip("Redo the last undone action")
        self.redo_action.triggered.connect(self.scene.redo)
        self.redo_action.setEnabled(False)
        self.addAction(self.redo_action)

        self.fit_action = QAction("Fit to Frame", self)
        self.fit_action.setShortcut(QKeySequence("Ctrl+0"))
        self.fit_action.setToolTip(
            "Zoom fully out and re-centre on the reference frame (Ctrl+0)"
        )
        self.fit_action.triggered.connect(self.view.fit_reference_frame)
        self.addAction(self.fit_action)

        self.group_action = QAction("Group", self)
        self.group_action.setShortcut(QKeySequence("Ctrl+G"))
        self.group_action.setToolTip("Group selected objects (Ctrl+G)")
        self.group_action.triggered.connect(self.scene.group_selected)
        self.addAction(self.group_action)

        self.ungroup_action = QAction("Ungroup", self)
        self.ungroup_action.setShortcut(QKeySequence("Ctrl+Shift+G"))
        self.ungroup_action.setToolTip("Ungroup selected group (Ctrl+Shift+G)")
        self.ungroup_action.triggered.connect(self.scene.ungroup_selected)
        self.addAction(self.ungroup_action)

    def _create_script_actions(self) -> None:
        """The File menu's commands, which all act on the open script."""
        self.new_script_action = QAction("New Script", self)
        self.new_script_action.setShortcut(QKeySequence.New)
        self.new_script_action.setToolTip(
            "Start an empty script in the Scripts panel (Ctrl+N)"
        )
        self.new_script_action.triggered.connect(self._new_script)
        self.addAction(self.new_script_action)

        self.open_script_action = QAction("Open Prism Script…", self)
        self.open_script_action.setShortcut(QKeySequence.Open)
        self.open_script_action.setToolTip(
            "Open a .prism script for editing and running (Ctrl+O)"
        )
        self.open_script_action.triggered.connect(self._open_script)
        self.addAction(self.open_script_action)

        self.save_script_action = QAction("Save Script", self)
        self.save_script_action.setShortcut(QKeySequence.Save)
        self.save_script_action.setToolTip(
            "Write the Scripts panel's editor back to its file (Ctrl+S)"
        )
        self.save_script_action.triggered.connect(self._save_script)
        self.addAction(self.save_script_action)

        self.save_script_as_action = QAction("Save Script As…", self)
        self.save_script_as_action.setShortcut(QKeySequence.SaveAs)
        self.save_script_as_action.setToolTip(
            "Write the editor to a new file (Ctrl+Shift+S)"
        )
        self.save_script_as_action.triggered.connect(self._save_script_as)
        self.addAction(self.save_script_as_action)

        self.export_svg_action = QAction("Export as SVG…", self)
        self.export_svg_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self.export_svg_action.setToolTip(
            "Write what the canvas is showing to an SVG file (Ctrl+Shift+E)"
        )
        self.export_svg_action.triggered.connect(self._export_svg)
        self.addAction(self.export_svg_action)

        self.default_folder_action = QAction("Set Default Script Folder…", self)
        self.default_folder_action.setToolTip(
            "Where Save Script writes, and where Open starts looking"
        )
        self.default_folder_action.triggered.connect(self._set_default_folder)

        self.adopt_folder_action = QAction("Use Current Script's Folder", self)
        self.adopt_folder_action.setToolTip(
            "Make the open script's folder the default one"
        )
        self.adopt_folder_action.triggered.connect(self._adopt_current_folder)

        self.attach_style_action = QAction("Attach Style…", self)
        self.attach_style_action.setToolTip(
            "Take the canvas's default look from a script of (format …) commands"
        )
        self.attach_style_action.triggered.connect(self._attach_style)

        self.detach_style_action = QAction("Detach Style", self)
        self.detach_style_action.setToolTip(
            "Stop taking a default look from a script"
        )
        self.detach_style_action.triggered.connect(self._detach_style)

    # -- UI construction ---------------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Tools")
        # saveState() skips (and warns about) anything unnamed.
        toolbar.setObjectName("ToolsToolbar")
        toolbar.setMovable(False)

        for tool in (Tool.SELECT, Tool.POINT, Tool.LINE):
            toolbar.addAction(self._tool_actions[tool])

        toolbar.addSeparator()
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        toolbar.addAction(self.fit_action)
        toolbar.addSeparator()
        toolbar.addAction(self.group_action)
        toolbar.addAction(self.ungroup_action)
        toolbar.addSeparator()
        toolbar.addAction(self.delete_action)
        toolbar.addAction(self.clear_action)

    def _build_menu(self) -> None:
        self._file_menu = self.menuBar().addMenu("&File")
        self._file_menu.addAction(self.new_script_action)
        self._file_menu.addAction(self.open_script_action)
        self._recent_menu = self._file_menu.addMenu("Open &Recent")
        self._file_menu.addSeparator()
        self._file_menu.addAction(self.save_script_action)
        self._file_menu.addAction(self.save_script_as_action)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self.export_svg_action)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self.default_folder_action)
        self._file_menu.addAction(self.adopt_folder_action)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self.attach_style_action)
        self._file_menu.addAction(self.detach_style_action)
        # What these offer depends on the open script and on what is on disk,
        # neither of which announces itself, so the menu settles its own
        # contents as it opens rather than being kept in step from afar.
        self._file_menu.aboutToShow.connect(self._sync_file_menu)
        self._sync_file_menu()

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.group_action)
        edit_menu.addAction(self.ungroup_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.delete_action)
        edit_menu.addAction(self.clear_action)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.fit_action)
        view_menu.addSeparator()
        toggle_console = self.console.toggleViewAction()
        toggle_console.setText("Show Console")
        view_menu.addAction(toggle_console)
        toggle_scripts = self.scripts.toggleViewAction()
        toggle_scripts.setText("Show Scripts")
        view_menu.addAction(toggle_scripts)
        toggle_elements = self.elements.toggleViewAction()
        toggle_elements.setText("Show Elements")
        view_menu.addAction(toggle_elements)
        toggle_agent = self.agent.toggleViewAction()
        toggle_agent.setText("Show Assistant")
        view_menu.addAction(toggle_agent)
        toggle_book = self.book.toggleViewAction()
        toggle_book.setText("Show Book")
        view_menu.addAction(toggle_book)

        settings_menu = self.menuBar().addMenu("&Settings")
        # The scripts folder lives under File now, beside the commands that
        # use it; one setting in two menus is only ever a question of which
        # one is stale.
        book_action = QAction("Add Book…", self)
        book_action.setToolTip("Put another PDF on the Book panel's shelf")
        book_action.triggered.connect(self._add_book)
        settings_menu.addAction(book_action)

        settings_menu.addSeparator()
        reset_layout_action = QAction("Reset Window Layout", self)
        reset_layout_action.setToolTip(
            "Put the window and its panels back to their default size and places"
        )
        reset_layout_action.triggered.connect(self.reset_layout)
        settings_menu.addAction(reset_layout_action)

    # -- Tool switching ----------------------------------------------------

    def _select_tool(self, tool: Tool) -> None:
        self._tool_actions[tool].setChecked(True)
        self.scene.set_tool(tool)
        self.view.apply_tool(tool)

    def _update_history_actions(self, can_undo: bool, can_redo: bool) -> None:
        self.undo_action.setEnabled(can_undo)
        self.redo_action.setEnabled(can_redo)

    # -- Scripts -----------------------------------------------------------

    def _sync_file_menu(self) -> None:
        """Settle the File menu against the open script and the recent list."""
        open_path = self.scripts.current_path()
        self.save_script_action.setEnabled(self.scripts.is_dirty())
        self.save_script_as_action.setEnabled(bool(self.scripts.text().strip()))
        fixed = scripts_dir_is_fixed()
        self.default_folder_action.setEnabled(not fixed)
        elsewhere = open_path is not None and (
            os.path.dirname(open_path) != os.path.abspath(scripts_dir())
        )
        self.adopt_folder_action.setEnabled(elsewhere and not fixed)
        attached = self.scene.style_path()
        self.attach_style_action.setText(
            f"Change Style… ({os.path.basename(attached)})"
            if attached
            else "Attach Style…"
        )
        self.detach_style_action.setEnabled(attached is not None)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        """Fill Open Recent from what is still on disk."""
        self._recent_menu.clear()
        paths = recent_scripts()
        if not paths:
            nothing = self._recent_menu.addAction("(nothing yet)")
            nothing.setEnabled(False)
            return
        for path in paths:
            action = self._recent_menu.addAction(self._recent_label(path, paths))
            action.setToolTip(path)
            action.triggered.connect(
                lambda _=False, chosen=path: self._open_remembered(chosen)
            )
        self._recent_menu.addSeparator()
        self._recent_menu.addAction("Clear Menu").triggered.connect(
            clear_recent_scripts
        )

    @staticmethod
    def _recent_label(path: str, among: list) -> str:
        """A recent script's menu text, qualified only when it has to be.

        Two scripts of the same name in different folders are an ordinary
        thing once scripts are opened from anywhere, and a menu offering
        "net" twice says nothing about which of them is which.

        Args:
            path: The script to name.
            among: The whole recent list, to spot a clash in.

        Returns:
            The script's name, with its folder appended when another entry
                shares that name.
        """
        base = os.path.basename(path)
        name = base[: -len(SCRIPT_SUFFIX)] if base.endswith(SCRIPT_SUFFIX) else base
        clashes = any(
            other != path and os.path.basename(other) == base for other in among
        )
        if not clashes:
            return name
        return f"{name} — {os.path.basename(os.path.dirname(path))}"

    def _new_script(self) -> None:
        if not self.scripts.confirm_discard():
            return
        self.scripts.new_script()
        self._show_scripts()

    def _open_script(self) -> None:
        if not self.scripts.confirm_discard():
            return
        # Start where the open script lives, falling back to the default
        # folder — which is created first, since a dialog pointed at a folder
        # that isn't there opens on the working directory instead.
        start = self.scripts.current_path() or ensure_scripts_dir()
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Open Prism Script",
            start,
            f"Prism scripts (*{SCRIPT_SUFFIX});;All files (*)",
        )
        if chosen:
            self._load_script(chosen)

    def _open_remembered(self, path: str) -> None:
        """Open a script chosen from Open Recent."""
        if not self.scripts.confirm_discard():
            return
        self._load_script(path)

    def _load_script(self, path: str) -> None:
        if not self.scripts.open_path(path):
            # Still on disk, but it wouldn't read; stop offering it.
            forget_script(path)
            return
        remember_script(path)
        self._show_scripts()
        self.statusBar().showMessage(f"Opened {path}", 4000)

    def _save_script(self) -> bool:
        """Write the open script back, asking where to put an untitled one.

        Returns:
            Whether it was written.
        """
        if self.scripts.current_path() is None:
            return self._save_script_as()
        if not self.scripts.save():
            return False
        self.statusBar().showMessage(f"Saved {self.scripts.current_path()}", 4000)
        return True

    def _save_script_as(self) -> bool:
        """Write the editor to a file of the user's choosing.

        Returns:
            Whether it was written.
        """
        suggested = self.scripts.current_path()
        if suggested is None:
            suggested = os.path.join(
                ensure_scripts_dir(), self.scripts.current_name() + SCRIPT_SUFFIX
            )
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "Save Script As",
            suggested,
            f"Prism scripts (*{SCRIPT_SUFFIX});;All files (*)",
        )
        if not chosen:
            return False
        # A name typed without any extension means a Prism script; one typed
        # with another is left as the user wrote it.
        if "." not in os.path.basename(chosen):
            chosen += SCRIPT_SUFFIX
        if not self.scripts.save_to(chosen):
            return False
        remember_script(chosen)
        self.statusBar().showMessage(f"Saved {chosen}", 4000)
        return True

    def _append_to_script(self, commands: list) -> str | None:
        """Put the console's session at the end of the open script.

        Args:
            commands: The command lines the console recorded.

        Returns:
            The script's name, or None if nothing was appended.
        """
        if not self.scripts.append_commands(commands):
            return None
        self._show_scripts()
        return self.scripts.current_name()

    def _show_scripts(self) -> None:
        """Bring the Scripts panel out from behind whichever tab is raised."""
        self.scripts.show()
        self.scripts.raise_()

    def _attach_style(self) -> None:
        """Choose the script the canvas takes its default look from."""
        start = self.scene.style_path() or ensure_scripts_dir()
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Attach Style",
            start,
            f"Prism scripts (*{SCRIPT_SUFFIX});;All files (*)",
        )
        if not chosen:
            return
        # Through the console, so the style a figure was drawn under is part
        # of the script that rebuilds it.
        if not self.scene.run_as_command(f'(style "{chosen}")'):
            try:
                self.scene.attach_style(chosen)
            except OSError as exc:
                self.statusBar().showMessage(f"Couldn't read that style: {exc}", 6000)

    def _detach_style(self) -> None:
        if not self.scene.run_as_command("(style -none)"):
            self.scene.detach_style()

    def _export_svg(self) -> bool:
        """Write what the canvas is showing to an SVG file.

        Returns:
            Whether it was written.
        """
        suggested = os.path.join(export_dir(), "prism-drawing.svg")
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Export as SVG", suggested, "SVG images (*.svg);;All files (*)"
        )
        if not chosen:
            return False
        if "." not in os.path.basename(chosen):
            chosen += ".svg"
        try:
            written = export_svg(self.view, chosen)
        except OSError as exc:
            self.statusBar().showMessage(f"Couldn't write the SVG: {exc}", 8000)
            return False
        if not written:
            self.statusBar().showMessage("There was nothing to export.", 5000)
            return False
        set_export_dir(os.path.dirname(chosen))
        self.statusBar().showMessage(f"Exported {chosen}", 5000)
        return True

    def _set_default_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose Default Script Folder", scripts_dir()
        )
        if chosen:
            self._adopt_folder(chosen)

    def _adopt_current_folder(self) -> None:
        """Make the open script's folder the default one."""
        path = self.scripts.current_path()
        if path is not None:
            self._adopt_folder(os.path.dirname(path))

    def _adopt_folder(self, folder: str) -> None:
        set_scripts_dir(folder)
        self.scripts.refresh()
        self.statusBar().showMessage(f"Scripts now default to {folder}", 5000)

    def _add_book(self) -> None:
        self.book.add_book()
        self.book.show()
        self.book.raise_()
