"""Cyphra GUI entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow, ensure_inter_font, get_asset_path
from .splash import SplashScreen, SplashWorker


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

    # Parse command line options
    args = sys.argv[1:]
    no_splash = "--no-splash" in args
    no_update = "--no-update" in args or "--skip-update" in args
    check_update = "--check-update" in args
    file_args = [a for a in args if not a.startswith("--")]

    # Check update settings
    settings = QSettings("Cyphra", "Cyphra")
    auto_update_setting = settings.value("auto_update", True, type=bool)
    should_update = (auto_update_setting or check_update) and not no_update

    def _setup_window() -> MainWindow:
        win = MainWindow()
        if file_args:
            initial_path = Path(file_args[0])
            if initial_path.exists():
                resolved = str(initial_path.resolve())
                if initial_path.suffix.lower() in (".cyphra", ".cyphra-vault"):
                    win.show_page("decrypt")
                    win.page_map["decrypt"]._files_selected([resolved])
                else:
                    win.show_page("encrypt")
                    win.page_map["encrypt"]._files_selected([resolved])
        return win

    if no_splash:
        window = _setup_window()
        window.show()
        return app.exec()

    # Create & display async splash screen
    splash = SplashScreen(font_family=font_family)
    splash.fade_in()

    worker = SplashWorker(enable_updater=should_update, force_update=check_update)
    splash._worker = worker  # Prevent garbage collection


    worker.status_changed.connect(splash.set_status)
    worker.progress_changed.connect(splash.set_progress)

    def _on_splash_finished() -> None:
        window = _setup_window()
        splash.finish_and_launch(window)

    worker.finished.connect(_on_splash_finished)
    worker.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

