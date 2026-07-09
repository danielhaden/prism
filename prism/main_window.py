"""The Prism main window: canvas, toolbar, and menus."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QMainWindow

from prism.canvas import CanvasScene, CanvasView
from prism.tools import Tool


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prism")
        self.resize(1000, 720)

        self.scene = CanvasScene(self)
        self.view = CanvasView(self.scene, self)
        self.setCentralWidget(self.view)

        self._tool_actions: dict[Tool, QAction] = {}
        self._create_actions()
        self._build_toolbar()
        self._build_menu()

        self.scene.statusMessage.connect(self.statusBar().showMessage)
        self._select_tool(Tool.SELECT)

    # -- Actions -----------------------------------------------------------

    def _create_actions(self) -> None:
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
        self.clear_action.triggered.connect(self.scene.clear_all)

    # -- UI construction ---------------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Tools")
        toolbar.setMovable(False)

        for tool in (Tool.SELECT, Tool.POINT, Tool.LINE):
            toolbar.addAction(self._tool_actions[tool])

        toolbar.addSeparator()
        toolbar.addAction(self.delete_action)
        toolbar.addAction(self.clear_action)

    def _build_menu(self) -> None:
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.delete_action)
        edit_menu.addAction(self.clear_action)

    # -- Tool switching ----------------------------------------------------

    def _select_tool(self, tool: Tool) -> None:
        self._tool_actions[tool].setChecked(True)
        self.scene.set_tool(tool)
        self.view.apply_tool(tool)
