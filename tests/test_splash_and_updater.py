"""Unit tests for Cyphra Splash Screen and Auto-Updater subsystems."""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from cyphra_gui.pages import SettingsPage
from cyphra_gui.splash import SplashScreen, SplashWorker
from cyphra_gui.updater import CyphraUpdater


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# =========================================================================
# 1. CyphraUpdater Tests
# =========================================================================

def test_updater_is_online_mocked_offline():
    """Verify is_online returns False without raising an error when socket fails."""
    with patch("socket.create_connection", side_effect=socket.timeout):
        assert CyphraUpdater.is_online(timeout=0.1) is False

    with patch("socket.create_connection", side_effect=OSError("Network is unreachable")):
        assert CyphraUpdater.is_online(timeout=0.1) is False


def test_updater_check_and_update_offline_no_error(tmp_path):
    """Verify check_and_update returns cleanly with no errors when completely offline."""
    updater = CyphraUpdater(app_dir=tmp_path)
    status_calls = []
    progress_calls = []

    with patch.object(CyphraUpdater, "is_online", return_value=False):
        success, message = updater.check_and_update(
            status_callback=status_calls.append,
            progress_callback=progress_calls.append,
            force=True,
        )


    # Must return True (no error thrown or reported as fatal)
    assert success is True
    assert "offline" in message.lower()
    assert any("offline" in s.lower() for s in status_calls)
    assert 100 in progress_calls


def test_updater_git_up_to_date(tmp_path):
    """Verify git updater reports up-to-date when origin matches HEAD."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    updater = CyphraUpdater(app_dir=tmp_path)
    status_calls = []
    progress_calls = []

    mock_fetch = MagicMock(returncode=0, stdout="", stderr="")
    mock_rev_list = MagicMock(returncode=0, stdout="0\n", stderr="")

    def run_side_effect(cmd, **kwargs):
        if "fetch" in cmd:
            return mock_fetch
        if "rev-list" in cmd:
            return mock_rev_list
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(CyphraUpdater, "is_online", return_value=True), \
         patch("shutil.which", return_value="git"), \
         patch("subprocess.run", side_effect=run_side_effect):
        success, message = updater.check_and_update(
            status_callback=status_calls.append,
            progress_callback=progress_calls.append,
            force=True,
        )

    assert success is True
    assert "up to date" in message.lower()
    assert any("up to date" in s.lower() for s in status_calls)


def test_updater_git_fetch_timeout_fails_gracefully(tmp_path):
    """Verify git fetch timeout is caught cleanly without failing startup."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    updater = CyphraUpdater(app_dir=tmp_path)
    status_calls = []

    with patch.object(CyphraUpdater, "is_online", return_value=True), \
         patch("shutil.which", return_value="git"), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git fetch", timeout=5)):
        success, message = updater.check_and_update(
            status_callback=status_calls.append,
            force=True,
        )

    assert success is True
    assert "timed out" in message.lower() or "skipped" in message.lower()


def test_updater_http_offline_graceful_handling(tmp_path):
    """Verify standalone HTTP updater handles network drops without exception."""
    updater = CyphraUpdater(app_dir=tmp_path)
    status_calls = []

    with patch.object(CyphraUpdater, "is_online", return_value=True), \
         patch("shutil.which", return_value=None), \
         patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
        success, message = updater.check_and_update(
            status_callback=status_calls.append,
            force=True,
        )

    assert success is True
    assert "offline" in message.lower() or "skipped" in message.lower()


def test_updater_local_commit_reading(tmp_path):
    """Verify reading local commit from .cyphra_version file."""
    version_file = tmp_path / ".cyphra_version"
    version_file.write_text("abc1234567890", encoding="utf-8")

    updater = CyphraUpdater(app_dir=tmp_path)
    assert updater.get_local_commit() == "abc1234567890"


# =========================================================================
# 2. SplashScreen UI Tests
# =========================================================================

def test_splash_screen_widgets(qapp):
    """Verify SplashScreen initializes required branding, logo, and status widgets."""
    splash = SplashScreen()

    # Window flags
    assert splash.windowFlags() & Qt.WindowType.FramelessWindowHint

    # Branding & Status widgets
    assert splash.card is not None
    assert splash.logo_label is not None
    assert splash.status_label is not None
    assert splash.progress_bar is not None

    # Status update
    splash.set_status("Testing Engine Startup...")
    assert splash.status_label.text() == "Testing Engine Startup..."

    # Progress bar update
    splash.set_progress(45)
    assert splash.progress_bar.value() == 45

    # Clamping test
    splash.set_progress(150)
    assert splash.progress_bar.value() == 100
    splash.set_progress(-10)
    assert splash.progress_bar.value() == 0

    splash.close()


def test_splash_worker_lifecycle(qapp):
    """Verify SplashWorker runs and emits expected signals."""
    worker = SplashWorker(enable_updater=False)

    received_status = []
    received_progress = []
    finished_called = []

    worker.status_changed.connect(received_status.append)
    worker.progress_changed.connect(received_progress.append)
    worker.finished.connect(lambda: finished_called.append(True))

    worker.start()
    worker.wait(5000)
    qapp.processEvents()

    assert len(finished_called) == 1

    assert len(received_status) > 0
    assert 100 in received_progress
    assert any("ready" in s.lower() or "cyphra" in s.lower() for s in received_status)


# =========================================================================
# 3. SettingsPage & MainWindow Integration
# =========================================================================

def test_updater_cooldown_and_interval(tmp_path):
    """Verify updater respects cooldown and force flags."""
    import time
    from PySide6.QtCore import QSettings

    updater = CyphraUpdater(app_dir=tmp_path)
    settings = QSettings("Cyphra", "Cyphra")
    settings.setValue("auto_update", True)
    settings.setValue("update_frequency", 1)  # 4 Hours

    # Just checked now
    settings.setValue("last_update_check_time", time.time())
    assert updater.should_check_update(force=False) is False
    assert updater.should_check_update(force=True) is True

    # Checked 5 hours ago (expired)
    settings.setValue("last_update_check_time", time.time() - (5 * 3600))
    assert updater.should_check_update(force=False) is True

    # Display text check
    assert "Today" in updater.get_last_check_display() or "at" in updater.get_last_check_display()


def test_settings_page_has_updater_controls(qapp):
    """Verify SettingsPage contains auto-updater toggle, frequency selector, and status label."""
    page = SettingsPage()

    assert hasattr(page, "auto_update")
    assert hasattr(page, "update_freq")
    assert hasattr(page, "last_check_label")
    assert hasattr(page, "update_status")
    assert "https://github.com/Darsh4246/Cyphra" in page.update_status.text()

    # Test toggling
    initial = page.auto_update.isChecked()
    page.auto_update.setChecked(not initial)
    assert page.auto_update.isChecked() != initial

    # Test frequency selection
    assert page.update_freq.count() >= 4
    page.update_freq.setCurrentIndex(2)  # Daily
    assert page.settings.value("update_frequency", type=int) == 2

    # Test factory defaults restores it
    page._reset_defaults()
    assert page.auto_update.isChecked() is True
    assert page.update_freq.currentIndex() == 1  # Every 4 Hours


def test_main_window_has_update_badge_and_timer(qapp):
    """Verify MainWindow has update badge and background periodic check timer."""
    from cyphra_gui.main_window import MainWindow

    win = MainWindow()
    assert hasattr(win, "update_badge")
    assert win.update_badge.isHidden()
    assert hasattr(win, "update_timer")
    assert win.update_timer.isActive()

