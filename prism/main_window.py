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
        self._build_toolbar()
        self._build_menu()

        self.scene.statusMessage.connect(self.statusBar().showMessage)
        self._select_tool(Tool.SELECT)

    # -- UI construction ---------------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Tools")
        toolbar.setMovable(False)

        group = QActionGroup(self)
        group.setExclusive(True)

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
            group.addAction(action)
            toolbar.addAction(action)
            self._tool_actions[tool] = action

        toolbar.addSeparator()

        delete_action = QAction("Delete", self)
        delete_action.setShortcut(QKeySequence.Delete)
        delete_action.triggered.connect(self.scene.delete_selected)
        toolbar.addAction(delete_action)

        clear_action = QAction("Clear", self)
        clear_action.triggered.connect(self.scene.clear_all)
        toolbar.addAction(clear_action)

    def _build_menu(self) -> None:
        edit_menu = self.menuBar().addMenu("&Edit")

        delete_action = QAction("Delete Selected", self)
        delete_action.setShortcut(QKeySequence.Delete)
        delete_action.triggered.connect(self.scene.delete_selected)
        edit_menu.addAction(delete_action)

        clear_action = QAction("Clear Canvas", self)
        clear_action.triggered.connect(self.scene.clear_all)
        edit_menu.addAction(clear_action)

    # -- Tool switching ----------------------------------------------------

    def _select_tool(self, tool: Tool) -> None:
        self._tool_actions[tool].setChecked(True)
        self.scene.set_tool(tool)
        self.view.apply_tool(tool)
