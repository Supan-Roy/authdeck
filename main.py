from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> int:
    """Application entrypoint for AuthDeck."""
    app = QApplication(sys.argv)
    app.setApplicationName("AuthDeck")
    app.setOrganizationName("AuthDeck")

    if getattr(sys, "frozen", False):
        bundle_dir = Path(getattr(sys, "_MEIPASS", Path.cwd()))
        icon_path = bundle_dir / "assets" / "icon.png"
    else:
        icon_path = Path(__file__).resolve().parent / "assets" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    if not window.require_pin_on_startup():
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
