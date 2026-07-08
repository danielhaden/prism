"""QApplication bootstrap for Prism."""

import sys

from PySide6.QtWidgets import QApplication

from prism.main_window import MainWindow
from prism.resources import make_app_icon


def run() -> int:
    """Create the application, show the main window, and start the event loop."""
    app = QApplication(sys.argv)
    app.setApplicationName("Prism")
    app.setOrganizationName("Prism")

    icon = make_app_icon()
    app.setWindowIcon(icon)

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()

    return app.exec()
