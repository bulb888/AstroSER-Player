"""AstroSER Player application entry point."""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from .ui.theme import apply_dark_theme
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AstroSER Player")
    app.setOrganizationName("AstroSER")

    # Set application icon
    icon_path = Path(__file__).parent / "resources" / "icons" / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    apply_dark_theme(app)

    window = MainWindow()
    window.setAcceptDrops(True)
    window.show()

    # If a file was passed as argument, open it
    if len(sys.argv) > 1:
        window.open_file(sys.argv[1])

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
