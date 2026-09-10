"""Cyphra GitHub auto-updater with offline resilience.

Checks and pulls code changes from https://github.com/Darsh4246/Cyphra at startup.
Supports both git repositories (via git fetch/pull) and standalone installations
(via GitHub API and archive extraction), and fails completely silently without
raising errors when offline or unable to connect.
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSettings

logger = logging.getLogger("cyphra.updater")

# Windows flag to suppress black console popup when invoking subprocesses
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

GITHUB_REPO_URL = "https://github.com/Darsh4246/Cyphra"
GITHUB_API_COMMITS_URL = "https://api.github.com/repos/Darsh4246/Cyphra/commits/main"
GITHUB_ZIP_URL = "https://github.com/Darsh4246/Cyphra/archive/refs/heads/main.zip"

# Update frequency map in hours: index -> interval
UPDATE_INTERVAL_HOURS: dict[int, float] = {
    0: 0.0,       # Every Launch
    1: 4.0,       # Every 4 Hours (Default / Recommended)
    2: 24.0,      # Daily (24 Hours)
    3: 168.0,     # Weekly (7 Days)
    4: -1.0,      # Manual Only
}



class CyphraUpdater:
    """Handles checking and pulling application updates from GitHub."""

    def __init__(self, app_dir: Path | None = None) -> None:
        if app_dir is None:
            # Resolves to the root Cyphra workspace/installation directory
            self.app_dir = Path(__file__).resolve().parent.parent
        else:
            self.app_dir = Path(app_dir).resolve()

        self.version_file = self.app_dir / ".cyphra_version"

    @staticmethod
    def is_online(timeout: float = 2.0) -> bool:
        """Check if internet connectivity to GitHub is available without hanging."""
        try:
            # Quick TCP handshake to github.com HTTPS port
            sock = socket.create_connection(("github.com", 443), timeout=timeout)
            sock.close()
            return True
        except (OSError, socket.timeout):
            return False

    def get_local_commit(self) -> str | None:
        """Return the current local commit hash (from git or recorded version file)."""
        # Try git first
        if (self.app_dir / ".git").is_dir():
            try:
                res = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(self.app_dir),
                    capture_output=True,
                    text=True,
                    timeout=3,
                    creationflags=CREATE_NO_WINDOW,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass

        # Fallback to .cyphra_version file
        if self.version_file.exists():
            try:
                return self.version_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        return None

    def get_last_check_timestamp(self) -> float:
        """Return unix timestamp of the last update check."""
        settings = QSettings("Cyphra", "Cyphra")
        return settings.value("last_update_check_time", 0.0, type=float)

    def get_last_check_display(self) -> str:
        """Return a human-readable string for the last update check time."""
        ts = self.get_last_check_timestamp()
        if ts <= 0:
            return "Never"
        dt = datetime.fromtimestamp(ts)
        now = datetime.now()
        if dt.date() == now.date():
            return f"Today at {dt.strftime('%I:%M %p').lstrip('0')}"
        return dt.strftime("%b %d, %Y at %I:%M %p")

    def record_check_time(self) -> None:
        """Record the current time as the last check timestamp."""
        try:
            settings = QSettings("Cyphra", "Cyphra")
            settings.setValue("last_update_check_time", time.time())
        except Exception:
            pass

    def should_check_update(self, force: bool = False) -> bool:
        """Determine whether an update check should run based on configured interval."""
        if force:
            return True

        settings = QSettings("Cyphra", "Cyphra")
        auto_update = settings.value("auto_update", True, type=bool)
        if not auto_update:
            return False

        freq_idx = settings.value("update_frequency", 1, type=int)
        interval_hours = UPDATE_INTERVAL_HOURS.get(freq_idx, 4.0)

        if interval_hours < 0:  # Manual Only
            return False
        if interval_hours == 0:  # Every Launch
            return True

        last_check = self.get_last_check_timestamp()
        if last_check <= 0:
            return True

        elapsed = time.time() - last_check
        return elapsed >= (interval_hours * 3600)

    def check_and_update(
        self,
        status_callback: Callable[[str], None] | None = None,
        progress_callback: Callable[[int], None] | None = None,
        force: bool = False,
    ) -> tuple[bool, str]:
        """Check for updates and apply them if available.

        Guaranteed not to raise errors if offline or network drops.
        """
        def report_status(msg: str) -> None:
            if status_callback:
                try:
                    status_callback(msg)
                except Exception:
                    pass

        def report_progress(val: int) -> None:
            if progress_callback:
                try:
                    progress_callback(val)
                except Exception:
                    pass

        # Check cooldown / interval unless force is requested
        if not self.should_check_update(force=force):
            logger.info("Update check cooldown active; skipping network check.")
            report_status("Cyphra is up to date.")
            report_progress(100)
            return True, "Cooldown active"

        report_status("Checking for updates...")
        report_progress(15)

        # Record check attempt timestamp
        self.record_check_time()


        # 1. Connectivity check
        try:
            if not self.is_online(timeout=2.0):
                logger.info("No internet connection; skipping update check.")
                report_status("Offline mode — Launching Cyphra...")
                report_progress(100)
                return True, "Offline mode"
        except Exception:
            report_status("Launching Cyphra...")
            report_progress(100)
            return True, "Offline mode"

        # 2. Decide between Git update vs HTTP archive update
        has_git_dir = (self.app_dir / ".git").is_dir()
        git_available = shutil.which("git") is not None

        try:
            if has_git_dir and git_available:
                return self._git_update(report_status, report_progress)
            return self._http_update(report_status, report_progress)
        except Exception as exc:
            # Failsafe: Never return an error or crash when updating fails
            logger.warning("Updater encountered non-fatal error: %s", exc)
            report_status("Starting Cyphra...")
            report_progress(100)
            return True, f"Skipped: {exc}"

    def _git_update(
        self,
        report_status: Callable[[str], None],
        report_progress: Callable[[int], None],
    ) -> tuple[bool, str]:
        """Perform update using Git."""
        report_status("Connecting to GitHub...")
        report_progress(30)

        # 1. Fetch remote tracking branch
        try:
            fetch_res = subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=str(self.app_dir),
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=CREATE_NO_WINDOW,
            )
            if fetch_res.returncode != 0:
                logger.info("Git fetch returned %d: %s", fetch_res.returncode, fetch_res.stderr)
                report_status("Ready — Launching Cyphra...")
                report_progress(100)
                return True, "Fetch skipped or offline"
        except subprocess.TimeoutExpired:
            logger.info("Git fetch timed out; continuing offline.")
            report_status("Launching Cyphra...")
            report_progress(100)
            return True, "Fetch timed out"

        report_progress(55)

        # 2. Check if local branch is behind origin/main
        try:
            rev_res = subprocess.run(
                ["git", "rev-list", "HEAD..origin/main", "--count"],
                cwd=str(self.app_dir),
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=CREATE_NO_WINDOW,
            )
            behind_count = int(rev_res.stdout.strip() or "0") if rev_res.returncode == 0 else 0
        except Exception:
            behind_count = 0

        if behind_count <= 0:
            report_status("Cyphra is up to date.")
            report_progress(100)
            return True, "Up to date"

        # 3. Check for uncommitted local changes before pulling
        try:
            diff_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.app_dir),
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=CREATE_NO_WINDOW,
            )
            has_dirty_files = bool(diff_res.stdout.strip())
        except Exception:
            has_dirty_files = False

        if has_dirty_files:
            # Preserve user's local uncommitted work and don't conflict
            report_status("Cyphra is up to date (local changes preserved).")
            report_progress(100)
            return True, "Local modifications present; pull deferred"

        # 4. Pull changes
        report_status(f"Pulling {behind_count} update(s) from GitHub...")
        report_progress(75)

        try:
            pull_res = subprocess.run(
                ["git", "pull", "--ff-only", "origin", "main"],
                cwd=str(self.app_dir),
                capture_output=True,
                text=True,
                timeout=12,
                creationflags=CREATE_NO_WINDOW,
            )
            if pull_res.returncode == 0:
                report_status("Updates applied successfully.")
                report_progress(100)
                return True, f"Successfully pulled {behind_count} commits"
            logger.warning("Git pull returned non-zero: %s", pull_res.stderr)
            report_status("Ready — Launching Cyphra...")
            report_progress(100)
            return True, "Pull skipped"
        except Exception as exc:
            logger.info("Git pull failed: %s", exc)
            report_status("Launching Cyphra...")
            report_progress(100)
            return True, "Pull deferred"

    def _http_update(
        self,
        report_status: Callable[[str], None],
        report_progress: Callable[[int], None],
    ) -> tuple[bool, str]:
        """Perform update using GitHub API and archive extraction."""
        report_status("Checking GitHub repository...")
        report_progress(35)

        req = urllib.request.Request(
            GITHUB_API_COMMITS_URL,
            headers={"User-Agent": "Cyphra-Vault-Updater/1.0", "Accept": "application/vnd.github.v3+json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status != 200:
                    report_status("Cyphra is up to date.")
                    report_progress(100)
                    return True, "API check bypassed"
                data = json.loads(resp.read().decode("utf-8"))
                remote_sha = data.get("sha", "")
        except Exception as exc:
            logger.info("GitHub API request skipped: %s", exc)
            report_status("Launching Cyphra...")
            report_progress(100)
            return True, "HTTP check offline"

        if not remote_sha:
            report_status("Cyphra is up to date.")
            report_progress(100)
            return True, "No SHA found"

        local_sha = self.get_local_commit()
        if local_sha and local_sha == remote_sha:
            report_status("Cyphra is up to date.")
            report_progress(100)
            return True, "Up to date"

        # Download update zipball
        report_status("Downloading updates from GitHub...")
        report_progress(60)

        zip_req = urllib.request.Request(
            GITHUB_ZIP_URL,
            headers={"User-Agent": "Cyphra-Vault-Updater/1.0"},
        )

        try:
            with urllib.request.urlopen(zip_req, timeout=15.0) as z_resp:
                zip_bytes = z_resp.read()
        except Exception as exc:
            logger.info("Failed to download zip archive: %s", exc)
            report_status("Launching Cyphra...")
            report_progress(100)
            return True, "Archive download skipped"

        report_status("Installing code changes...")
        report_progress(85)

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                # GitHub archives extract as Cyphra-main/...
                prefix = ""
                namelist = zf.namelist()
                if namelist:
                    first_part = namelist[0].split("/")[0]
                    if first_part:
                        prefix = first_part + "/"

                for member in zf.infolist():
                    rel_path = member.filename
                    if prefix and rel_path.startswith(prefix):
                        rel_path = rel_path[len(prefix):]
                    if not rel_path or rel_path.endswith("/"):
                        continue

                    # Only update core application packages
                    parts = Path(rel_path).parts
                    if not parts or parts[0] not in ("cyphra", "cyphra_gui"):
                        continue

                    target_file = self.app_dir / rel_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src_file, open(target_file, "wb") as dst_file:
                        shutil.copyfileobj(src_file, dst_file)

            # Record remote SHA
            try:
                self.version_file.write_text(remote_sha, encoding="utf-8")
            except Exception:
                pass

            report_status("Updates installed successfully.")
            report_progress(100)
            return True, f"Updated to {remote_sha[:7]}"

        except Exception as exc:
            logger.warning("Failed to extract update: %s", exc)
            report_status("Launching Cyphra...")
            report_progress(100)
            return True, "Extraction skipped"
