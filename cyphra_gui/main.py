"""Cyphra GUI entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow, ensure_inter_font, get_asset_path


def main() -> int:
    # Set Windows AppUserModelID so Windows taskbar displays the custom Cyphra icon
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("darsh.cyphra.vault.1.0")
        except Exception:
            pass

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Cyphra")
    app.setOrganizationName("Cyphra")

    icon_path = get_asset_path("cyphra_icon.ico")
    if not icon_path.exists():
        icon_path = get_asset_path("cyphra_icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    font_family = ensure_inter_font()
    app_font = QFont(font_family, 10)
    app_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(app_font)

    # Ensure Windows file associations (.cyphra, .cyphra-vault) with logo.ico
    if sys.platform == "win32":
        try:
            from .file_assoc import register_file_associations
            register_file_associations()
        except Exception:
            pass

    window = MainWindow()

    # If opened with a file argument (e.g. double-clicked from Windows Explorer)
    if len(sys.argv) > 1:
        initial_path = Path(sys.argv[1])
        if initial_path.exists():
            resolved = str(initial_path.resolve())
            if initial_path.suffix.lower() in (".cyphra", ".cyphra-vault"):
                window.show_page("decrypt")
                window.page_map["decrypt"]._files_selected([resolved])
            else:
                window.show_page("encrypt")
                window.page_map["encrypt"]._files_selected([resolved])

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
