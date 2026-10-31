"""The dockable Book panel: read a reference book beside the canvas.

Prism's constructions come out of the books — Olive Whicher's *Projective
Geometry: Creative Polarities in Space and Time*, Coxeter's *Projective
Geometry* — so the panel keeps a **shelf** of PDFs and a dropdown to pick
between them (:func:`prism.settings.books`). Each book remembers its own
page, so turning to the other one and back returns to where you were rather
than to wherever the other book happens to be open: a shelf of books rather
than a file viewer.
"""

import html
import os

from PySide6.QtCore import QPointF, Qt
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from prism import settings

#: How far one zoom step moves, as a multiple of the current zoom.
ZOOM_STEP = 1.25

#: Bounds on the custom zoom factor, so the book can't be lost off-scale.
MIN_ZOOM = 0.25
MAX_ZOOM = 8.0

_PLACEHOLDER, _READER = 0, 1

_ERRORS = {
    QPdfDocument.Error.FileNotFound: "that file isn't there any more",
    QPdfDocument.Error.InvalidFileFormat: "that isn't a PDF",
    QPdfDocument.Error.IncorrectPassword: "that PDF needs a password",
    QPdfDocument.Error.UnsupportedSecurityScheme: "that PDF is locked",
}


class BookPanel(QDockWidget):
    """A PDF reader docked beside the canvas, showing one book off a shelf."""

    def __init__(self, parent=None):
        super().__init__("Book", parent)
        self.setObjectName("BookPanel")

        self._document = QPdfDocument(self)
        self._syncing = False
        self._syncing_shelf = False
        #: True while a book is being swapped in, when the navigator reports
        #: pages belonging to neither book.
        self._loading = False

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_placeholder())
        self._stack.addWidget(self._build_reader())

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 0)
        layout.setSpacing(4)
        layout.addWidget(self._build_shelf_row())
        layout.addWidget(self._stack)
        self.setWidget(container)

        self.reload()

    # -- The shelf ---------------------------------------------------------

    def _build_shelf_row(self) -> QWidget:
        self._shelf_box = QComboBox()
        self._shelf_box.setToolTip("Which book to read")
        # activated, not currentIndexChanged: only a choice *you* made should
        # turn a page, and the box is reset from settings on every reload.
        self._shelf_box.activated.connect(self._on_book_chosen)

        menu = QMenu(self)
        self._add_action = menu.addAction("Add Book…", self.add_book)
        self._rename_action = menu.addAction("Rename…", self.rename_book)
        self._remove_action = menu.addAction("Remove from Shelf", self.remove_book)

        self._shelf_button = QToolButton()
        self._shelf_button.setText("\u2026")
        self._shelf_button.setToolTip("Add, rename or remove a book")
        self._shelf_button.setPopupMode(QToolButton.InstantPopup)
        # Match the page and zoom buttons below it, which are all 32 wide.
        self._shelf_button.setFixedWidth(32)
        self._shelf_button.setMenu(menu)

        self._shelf_row = QWidget()
        row = QHBoxLayout(self._shelf_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(self._shelf_box, 1)
        row.addWidget(self._shelf_button)
        return self._shelf_row

    def _refresh_shelf(self) -> None:
        """Bring the dropdown into line with the shelf in settings."""
        shelf = settings.books()
        self._syncing_shelf = True
        self._shelf_box.clear()
        for position, entry in enumerate(shelf):
            self._shelf_box.addItem(entry["name"])
            # The whole path is the tooltip: names are cut short to fit.
            self._shelf_box.setItemData(position, entry["path"], Qt.ToolTipRole)
        current = settings.current_book()
        if 0 <= current < len(shelf):
            self._shelf_box.setCurrentIndex(current)
        self._syncing_shelf = False

        fixed = settings.shelf_is_fixed()
        self._shelf_row.setVisible(bool(shelf))
        self._add_action.setEnabled(not fixed)
        self._rename_action.setEnabled(bool(shelf) and not fixed)
        self._remove_action.setEnabled(bool(shelf) and not fixed)

    def _on_book_chosen(self, index: int) -> None:
        if self._syncing_shelf or index < 0:
            return
        settings.set_current_book(index)
        self.reload()

    def rename_book(self) -> None:
        """Give the current book a shorter or clearer name on the shelf."""
        shelf, index = settings.books(), settings.current_book()
        if not 0 <= index < len(shelf):
            return
        name, confirmed = QInputDialog.getText(
            self, "Rename Book", "Name:", text=shelf[index]["name"]
        )
        if confirmed:
            settings.rename_book(index, name)
            self._refresh_shelf()

    def remove_book(self) -> None:
        """Take the current book off the shelf. The PDF is left alone."""
        shelf, index = settings.books(), settings.current_book()
        if not 0 <= index < len(shelf):
            return
        answer = QMessageBox.question(
            self,
            "Remove Book",
            f"Take \u201c{shelf[index]['name']}\u201d off the shelf?\n\n"
            "The PDF itself stays where it is.",
        )
        if answer == QMessageBox.Yes:
            settings.remove_book(index)
            self.reload()

    # -- UI construction ---------------------------------------------------

    def _build_placeholder(self) -> QWidget:
        self._placeholder_label = QLabel()
        self._placeholder_label.setTextFormat(Qt.RichText)
        self._placeholder_label.setWordWrap(True)
        self._placeholder_label.setAlignment(Qt.AlignCenter)
        self._placeholder_label.setStyleSheet("color: gray;")

        choose = QPushButton("Add Book…")
        choose.clicked.connect(self.add_book)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(choose)
        button_row.addStretch()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addStretch()
        layout.addWidget(self._placeholder_label)
        layout.addSpacing(12)
        layout.addLayout(button_row)
        layout.addStretch()
        return container

    def _build_reader(self) -> QWidget:
        self._view = QPdfView()
        self._view.setDocument(self._document)
        self._view.setPageMode(QPdfView.PageMode.MultiPage)
        self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

        self._navigator = self._view.pageNavigator()
        self._navigator.currentPageChanged.connect(self._on_page_changed)

        self._prev_button = QPushButton("◀")
        self._prev_button.setToolTip("Previous page")
        self._prev_button.setFixedWidth(32)
        self._prev_button.clicked.connect(lambda: self._step_page(-1))

        self._next_button = QPushButton("▶")
        self._next_button.setToolTip("Next page")
        self._next_button.setFixedWidth(32)
        self._next_button.clicked.connect(lambda: self._step_page(1))

        self._page_box = QSpinBox()
        self._page_box.setMinimum(1)
        self._page_box.setMaximum(1)
        self._page_box.setToolTip("Go to page")
        self._page_box.setFixedWidth(64)
        self._page_box.valueChanged.connect(self._on_page_requested)

        self._count_label = QLabel()
        self._count_label.setStyleSheet("color: gray;")

        zoom_out = QPushButton("−")
        zoom_out.setToolTip("Zoom out")
        zoom_out.setFixedWidth(32)
        zoom_out.clicked.connect(lambda: self._zoom_by(1 / ZOOM_STEP))

        zoom_in = QPushButton("+")
        zoom_in.setToolTip("Zoom in")
        zoom_in.setFixedWidth(32)
        zoom_in.clicked.connect(lambda: self._zoom_by(ZOOM_STEP))

        fit = QPushButton("Fit")
        fit.setToolTip("Fit the page to the panel's width")
        fit.clicked.connect(self.fit_width)

        controls = QHBoxLayout()
        controls.setSpacing(4)
        controls.addWidget(self._prev_button)
        controls.addWidget(self._page_box)
        controls.addWidget(self._count_label)
        controls.addWidget(self._next_button)
        controls.addStretch()
        controls.addWidget(zoom_out)
        controls.addWidget(zoom_in)
        controls.addWidget(fit)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.addLayout(controls)
        layout.addWidget(self._view)
        return container

    # -- Loading -----------------------------------------------------------

    def reload(self) -> None:
        """Re-read the selected book, or show the placeholder on an empty shelf."""
        self._refresh_shelf()
        path = settings.book_path()
        if not path:
            self._show_placeholder(
                "No books yet.<br><br>Add a PDF to read beside the canvas — "
                "Olive Whicher's <i>Projective Geometry</i>, Coxeter's, "
                "whatever you are working from — here, or from "
                "<b>Settings → Add Book…</b>."
            )
            return

        # Read the page *before* closing: closing the document reports a page
        # change, which would otherwise record the old book's last page — or
        # page one — against the book about to be opened.
        page = settings.book_page()
        self._loading = True
        try:
            self._document.close()
            error = self._document.load(path)
        finally:
            self._loading = False
        if error != QPdfDocument.Error.None_:
            reason = _ERRORS.get(error, "it couldn't be opened")
            name = html.escape(os.path.basename(path))
            self._show_placeholder(f"Couldn't open <b>{name}</b> — {reason}.")
            return

        pages = self._document.pageCount()
        self._page_box.setMaximum(max(1, pages))
        self._count_label.setText(f"/ {pages}")
        # The title doubles as the tab label when docked, so keep it short and
        # let the tooltip carry which file is open.
        self.setToolTip(path)
        self._stack.setCurrentIndex(_READER)
        self.go_to_page(min(page, max(0, pages - 1)))
        # Jumping to a page the navigator is already on emits nothing, so sync
        # the controls by hand rather than leaving them at their defaults.
        self._on_page_changed(self._navigator.currentPage())

    def _show_placeholder(self, html: str) -> None:
        self._document.close()
        self._placeholder_label.setText(html)
        self.setToolTip("")
        self._stack.setCurrentIndex(_PLACEHOLDER)

    def add_book(self) -> None:
        """Ask for a PDF, put it on the shelf, and turn to it."""
        current = settings.book_path()
        start = os.path.dirname(current) if current else os.path.expanduser("~")
        # All files first: QtPdf sniffs the content rather than the name, and a
        # book filed away by hand may well have no ".pdf" on the end.
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Add Book", start, "All files (*);;PDF files (*.pdf)"
        )
        if chosen:
            settings.add_book(chosen)
            self.reload()

    # -- Navigation --------------------------------------------------------

    def go_to_page(self, page: int) -> None:
        """Jump to a zero-based page."""
        if self._document.status() != QPdfDocument.Status.Ready:
            return
        page = max(0, min(page, self._document.pageCount() - 1))
        self._navigator.jump(page, QPointF(0, 0))

    def _step_page(self, delta: int) -> None:
        self.go_to_page(self._navigator.currentPage() + delta)

    def _on_page_requested(self, value: int) -> None:
        if not self._syncing:
            self.go_to_page(value - 1)

    def _on_page_changed(self, page: int) -> None:
        if self._loading:
            return  # between books: this page belongs to neither
        self._syncing = True
        self._page_box.setValue(page + 1)
        self._syncing = False
        self._prev_button.setEnabled(page > 0)
        self._next_button.setEnabled(page < self._document.pageCount() - 1)
        settings.set_book_page(page)

    # -- Zoom --------------------------------------------------------------

    def fit_width(self) -> None:
        """Scale the page to the panel's width."""
        self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def _zoom_by(self, factor: float) -> None:
        # Stepping the zoom leaves fit-to-width behind, so start from what the
        # fitted page is actually showing — otherwise the first step snaps to
        # 100% and the reader loses their place.
        current = self._view.zoomFactor()
        if self._view.zoomMode() != QPdfView.ZoomMode.Custom:
            current = self._fitted_zoom() or current
        self._view.setZoomMode(QPdfView.ZoomMode.Custom)
        self._view.setZoomFactor(max(MIN_ZOOM, min(current * factor, MAX_ZOOM)))

    def _fitted_zoom(self) -> float:
        """What fit-to-width is currently scaling by (``0`` if that's unknowable).

        `QPdfView` keeps its ``zoomFactor`` at the last *custom* value while
        fitting, so there's nothing to read back — this reconstructs it from the
        page width. Qt's own fit arithmetic differs by well under a percent,
        which is invisible as the base of a zoom step.
        """
        if self._document.status() != QPdfDocument.Status.Ready:
            return 0.0
        page_points = self._document.pagePointSize(
            self._navigator.currentPage()
        ).width()
        if page_points <= 0:
            return 0.0
        margins = self._view.documentMargins()
        width = self._view.viewport().width() - margins.left() - margins.right()
        return width / (page_points * self._view.logicalDpiX() / 72.0)
