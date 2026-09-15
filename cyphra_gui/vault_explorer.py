"""Vault Explorer — full file-manager experience inside a .cyphra-vault.

Features
--------
* Browse folders with breadcrumb navigation (click any segment to go back)
* Double-click a folder to navigate into it; double-click a file to open it
  in its native application
* File watcher: detects when an opened file is saved externally and prompts
  to write the changes back into the vault
* Add files / folders via toolbar or drag-and-drop from the OS
* Create new empty folders
* Rename entries with F2 or the context menu (inline edit)
* Remove entries with Del or the context menu
* Cut / Copy / Paste entries within the tree
* Extract selected entries to a real directory without full extraction
* All modifications are staged (green=added, red=removed, yellow=renamed)
  until the user clicks "Save Vault" which calls Vault.rebuild()
* Unsaved-changes badge warns before leaving the page
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QFileSystemWatcher,
    QMimeData,
    QSize,
    Qt,
    QUrl,
    Signal,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .core_adapter import CryptoAdapter
from .widgets import KeySourceSelector, ProgressPanel, ResultBanner, card
from .workers import OperationWorker

if TYPE_CHECKING:
    pass  # VaultEntry is used via str annotations only


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit not in ("B", "KB") else f"{n:,.0f} {unit}"
        n /= 1024
    return str(n)


def _fmt_time(ns: int) -> str:
    if not ns:
        return "—"
    try:
        import datetime
        dt = datetime.datetime.fromtimestamp(ns / 1e9)
        return dt.strftime("%Y-%m-%d  %H:%M")
    except Exception:  # noqa: BLE001
        return "—"


def _file_icon(name: str, is_dir: bool) -> str:
    if is_dir:
        return "📁"
    ext = Path(name).suffix.lower()
    return {
        ".pdf": "📑", ".doc": "📝", ".docx": "📝", ".txt": "📄", ".md": "📄",
        ".jpg": "🖼", ".jpeg": "🖼", ".png": "🖼", ".gif": "🖼", ".svg": "🖼",
        ".mp4": "🎬", ".mov": "🎬", ".avi": "🎬", ".mkv": "🎬",
        ".mp3": "🎵", ".wav": "🎵", ".flac": "🎵",
        ".zip": "🗜", ".tar": "🗜", ".gz": "🗜", ".7z": "🗜", ".rar": "🗜",
        ".py": "🐍", ".js": "📜", ".html": "🌐", ".css": "🎨",
        ".exe": "⚙", ".dll": "⚙", ".sh": "⚙",
        ".cyphra": "🔒", ".cyphra-vault": "🗄",
        ".cyphra-key": "🗝",
    }.get(ext, "📄")


# ---------------------------------------------------------------------------
# Drag-aware tree widget
# ---------------------------------------------------------------------------

class VaultFileTree(QTreeWidget):
    """QTreeWidget that accepts OS file drops."""

    files_dropped = Signal(list)  # list of real file paths

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            paths = [
                url.toLocalFile()
                for url in event.mimeData().urls()
                if url.isLocalFile() and Path(url.toLocalFile()).exists()
            ]
            if paths:
                self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

class VaultExplorerPage(QWidget):
    """Full file-manager explorer for .cyphra-vault containers."""

    navigate = Signal(str)

    _COL_NAME  = 0
    _COL_TYPE  = 1
    _COL_SIZE  = 2
    _COL_MTIME = 3

    # Item data roles
    _ROLE_VAULT_PATH  = Qt.ItemDataRole.UserRole
    _ROLE_IS_DIR      = Qt.ItemDataRole.UserRole + 1
    _ROLE_STATUS      = Qt.ItemDataRole.UserRole + 2  # 'existing'|'added'|'renamed'|'removed'
    _ROLE_SIZE        = Qt.ItemDataRole.UserRole + 3
    _ROLE_MTIME       = Qt.ItemDataRole.UserRole + 4

    def __init__(self, adapter: CryptoAdapter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.adapter = adapter

        # Vault state
        self._vault_path  = ""
        self._password    = ""
        self._vault_entries: list = []  # list[VaultEntry]

        # Navigation
        self._path_stack: list[str] = []  # e.g. ["docs", "reports"]

        # Staged changes
        self._staged_adds:    dict[str, str] = {}   # vault_path -> real_path
        self._staged_removes: set[str]       = set()
        self._staged_renames: dict[str, str] = {}   # old_vault_path -> new_vault_path

        # "Open with app" tracking
        self._file_watcher   = QFileSystemWatcher(self)
        self._watched_temps: dict[str, str] = {}    # tmp_file_path -> vault_path
        self._temp_dirs: list[str]          = []

        # Clipboard
        self._clipboard: list[str] = []  # vault paths
        self._clip_mode: str = ""        # 'copy' or 'cut'

        # Worker
        self._worker: OperationWorker | None = None

        self._build_ui()
        self._file_watcher.fileChanged.connect(self._on_watched_file_changed)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._main_stack = QStackedWidget()
        root.addWidget(self._main_stack)

        self._build_unlock_panel()
        self._build_explorer_panel()
        self._main_stack.setCurrentIndex(0)

    # ---- Unlock panel ----

    def _build_unlock_panel(self) -> None:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(32, 28, 32, 28)
        outer_layout.setSpacing(20)

        # Header
        title = QLabel("Vault Explorer")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Open a .cyphra-vault to browse, edit, add, remove, and open its "
            "contents without extracting the entire archive."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        outer_layout.addWidget(title)
        outer_layout.addWidget(subtitle)

        # Vault picker card
        vault_card, vault_layout = card(
            "Select Vault",
            "Choose the .cyphra-vault file you want to explore.",
        )
        pick_row = QHBoxLayout()
        pick_row.setSpacing(8)
        self._vault_path_edit = QLineEdit()
        self._vault_path_edit.setReadOnly(True)
        self._vault_path_edit.setPlaceholderText("No vault selected")
        pick_row.addWidget(self._vault_path_edit, 1)
        pick_row.addWidget(self._btn("Browse…", self._pick_vault))
        vault_layout.addLayout(pick_row)
        outer_layout.addWidget(vault_card)

        # Key source card
        key_card, key_layout = card(
            "Authentication",
            "Enter the password, keyfile, or both that protect this vault.",
        )
        self._unlock_key = KeySourceSelector(mode="decrypt")
        key_layout.addWidget(self._unlock_key)
        outer_layout.addWidget(key_card)

        # Action row
        action_row = QHBoxLayout()
        action_row.addStretch()
        unlock_btn = self._btn("🔓  Unlock Vault", self._unlock, primary=True)
        unlock_btn.setObjectName("primaryButton")
        action_row.addWidget(unlock_btn)
        outer_layout.addLayout(action_row)

        # Error label
        self._unlock_error = QLabel()
        self._unlock_error.setObjectName("warningLabel")
        self._unlock_error.setWordWrap(True)
        self._unlock_error.hide()
        outer_layout.addWidget(self._unlock_error)

        outer_layout.addStretch()
        self._main_stack.addWidget(outer)

    # ---- Explorer panel ----

    def _build_explorer_panel(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar: vault name + lock button
        top_bar = QFrame()
        top_bar.setObjectName("explorerTopBar")
        top_bar.setFixedHeight(46)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 0, 8, 0)
        top_layout.setSpacing(10)

        self._vault_name_label = QLabel()
        self._vault_name_label.setObjectName("explorerVaultName")
        top_layout.addWidget(self._vault_name_label)
        top_layout.addStretch()

        self._unsaved_badge = QLabel("● Unsaved changes")
        self._unsaved_badge.setObjectName("unsavedBadge")
        self._unsaved_badge.hide()
        top_layout.addWidget(self._unsaved_badge)

        lock_btn = self._btn("🔒  Lock & Close", self._lock_vault, object_name="dangerButton")
        top_layout.addWidget(lock_btn)
        layout.addWidget(top_bar)

        # Breadcrumb bar
        self._breadcrumb_bar = QFrame()
        self._breadcrumb_bar.setObjectName("breadcrumbBar")
        self._breadcrumb_bar.setFixedHeight(38)
        self._bc_layout = QHBoxLayout(self._breadcrumb_bar)
        self._bc_layout.setContentsMargins(16, 0, 16, 0)
        self._bc_layout.setSpacing(4)
        layout.addWidget(self._breadcrumb_bar)

        # Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("explorerToolbar")
        toolbar.setFixedHeight(50)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 6, 12, 6)
        tb_layout.setSpacing(6)

        tb_layout.addWidget(self._btn("📁  New Folder",    self._action_new_folder))
        tb_layout.addWidget(self._btn("➕  Add Files",     self._action_add_files))
        tb_layout.addWidget(self._btn("📂  Add Folder",    self._action_add_folder))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("toolbarSep")
        tb_layout.addWidget(sep)

        tb_layout.addWidget(self._btn("✏️  Rename",   self._action_rename,   object_name="secondaryButton"))
        tb_layout.addWidget(self._btn("✂️  Cut",      self._action_cut,      object_name="secondaryButton"))
        tb_layout.addWidget(self._btn("📋  Copy",     self._action_copy,     object_name="secondaryButton"))
        tb_layout.addWidget(self._btn("📋  Paste",    self._action_paste,    object_name="secondaryButton"))
        tb_layout.addWidget(self._btn("🗑  Remove",   self._action_remove,   object_name="dangerButton"))
        tb_layout.addStretch()

        self._save_btn = self._btn("💾  Save Vault", self._action_save_vault, primary=True)
        self._save_btn.setObjectName("primaryButton")
        tb_layout.addWidget(self._save_btn)
        layout.addWidget(toolbar)

        # File tree
        self._tree = VaultFileTree()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Name", "Type", "Size", "Modified"])
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.files_dropped.connect(self._on_files_dropped)
        layout.addWidget(self._tree, 1)

        # Status bar
        status_bar = QFrame()
        status_bar.setObjectName("explorerStatusBar")
        status_bar.setFixedHeight(28)
        sb_layout = QHBoxLayout(status_bar)
        sb_layout.setContentsMargins(16, 0, 16, 0)
        self._status_label = QLabel()
        self._status_label.setObjectName("explorerStatus")
        sb_layout.addWidget(self._status_label)
        sb_layout.addStretch()
        layout.addWidget(status_bar)

        # Progress / save result
        self._progress_panel = ProgressPanel()
        self._progress_panel.cancel_requested.connect(self._cancel_save)
        self._progress_panel.hide()
        layout.addWidget(self._progress_panel)

        self._main_stack.addWidget(panel)

        # Keyboard shortcuts
        QShortcut(QKeySequence("F2"),       self, self._action_rename)
        QShortcut(QKeySequence("Delete"),   self, self._action_remove)
        QShortcut(QKeySequence("Ctrl+A"),   self, self._tree.selectAll)
        QShortcut(QKeySequence("Ctrl+X"),   self, self._action_cut)
        QShortcut(QKeySequence("Ctrl+C"),   self, self._action_copy)
        QShortcut(QKeySequence("Ctrl+V"),   self, self._action_paste)
        QShortcut(QKeySequence("Backspace"),self, self._navigate_up)

    # ------------------------------------------------------------------
    # Helper factories
    # ------------------------------------------------------------------

    @staticmethod
    def _btn(text: str, slot, primary: bool = False, object_name: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(object_name or ("primaryButton" if primary else "secondaryButton"))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    # ------------------------------------------------------------------
    # Unlock / lock
    # ------------------------------------------------------------------

    def _pick_vault(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Vault",
            "",
            "Cyphra Vaults (*.cyphra-vault);;All Files (*)",
        )
        if path:
            self._vault_path_edit.setText(path)

    def _unlock(self) -> None:
        vault_path = self._vault_path_edit.text().strip()
        if not vault_path:
            self._show_unlock_error("Please select a .cyphra-vault file first.")
            return
        if not self._unlock_key.has_valid_credentials():
            self._show_unlock_error("Please provide a password, a keyfile, or both.")
            return

        try:
            effective_pw = self._unlock_key.get_effective_password()
        except ValueError as exc:
            self._show_unlock_error(str(exc))
            return

        def _do_list(progress, cancel_event):
            return self.adapter.vault_list(vault_path, effective_pw)

        self._unlock_error.hide()
        worker = OperationWorker(_do_list, self)
        worker.succeeded.connect(lambda result: self._on_unlocked(vault_path, effective_pw, result))
        worker.failed.connect(self._show_unlock_error)
        worker.start()

    def _on_unlocked(self, vault_path: str, password: str, result) -> None:
        _metadata, entries = result
        self._vault_path    = vault_path
        self._password      = password
        self._vault_entries = list(entries)

        # Reset staged changes
        self._staged_adds.clear()
        self._staged_removes.clear()
        self._staged_renames.clear()
        self._path_stack.clear()

        vault_name = Path(vault_path).name
        self._vault_name_label.setText(f"🗄  {vault_name}")
        self._main_stack.setCurrentIndex(1)
        self._populate_tree()

    def _show_unlock_error(self, msg: str) -> None:
        lower = msg.lower()
        if "authentication" in lower or "password" in lower or "tag" in lower:
            msg = "Authentication failed: incorrect password, keyfile, or the vault is corrupted."
        self._unlock_error.setText(f"⚠  {msg}")
        self._unlock_error.show()

    def _lock_vault(self) -> None:
        if self._has_unsaved_changes():
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Lock and discard them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Cleanup temp files
        self._cleanup_temps()

        self._vault_path = ""
        self._password   = ""
        self._vault_entries.clear()
        self._staged_adds.clear()
        self._staged_removes.clear()
        self._staged_renames.clear()
        self._path_stack.clear()
        self._tree.clear()
        self._unlock_key.clear()
        self._vault_path_edit.clear()
        self._unlock_error.hide()
        self._main_stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Virtual filesystem view
    # ------------------------------------------------------------------

    @property
    def _current_prefix(self) -> str:
        """Dot-separated current folder path, e.g. 'docs/reports'."""
        return "/".join(self._path_stack)

    def _build_virtual_entries(self) -> list[dict]:
        """Merge vault entries with staged changes into a unified list."""
        virtual: dict[str, dict] = {}

        for entry in self._vault_entries:
            orig  = entry.path
            final = self._staged_renames.get(orig, orig)
            if orig in self._staged_removes:
                continue
            status = "renamed" if orig in self._staged_renames else "existing"
            virtual[final] = {
                "vault_path":   final,
                "orig_path":    orig,
                "name":         final.split("/")[-1],
                "is_dir":       entry.is_dir,
                "size":         entry.size,
                "mtime_ns":     entry.mtime_ns,
                "status":       status,
            }

        for vp, rp in self._staged_adds.items():
            is_dir = os.path.isdir(rp)
            size   = 0 if is_dir else (os.path.getsize(rp) if os.path.isfile(rp) else 0)
            virtual[vp] = {
                "vault_path": vp,
                "orig_path":  None,
                "name":       vp.split("/")[-1],
                "is_dir":     is_dir,
                "size":       size,
                "mtime_ns":   0,
                "status":     "added",
                "real_path":  rp,
            }

        return list(virtual.values())

    def _get_display_entries(self) -> list[dict]:
        """Return direct children of the current folder, synthesising implicit dirs."""
        prefix = self._current_prefix
        virtual = self._build_virtual_entries()
        children: dict[str, dict] = {}

        for entry in virtual:
            ep = entry["vault_path"]
            if prefix:
                if not ep.startswith(prefix + "/"):
                    continue
                rel = ep[len(prefix) + 1:]
            else:
                rel = ep

            parts     = rel.split("/")
            child_key = parts[0]
            if child_key in children:
                continue

            if len(parts) == 1:
                children[child_key] = entry
            else:
                # Implicit directory containing this entry
                dir_vp = (prefix + "/" + child_key).lstrip("/")
                children[child_key] = {
                    "vault_path": dir_vp,
                    "orig_path":  None,
                    "name":       child_key,
                    "is_dir":     True,
                    "size":       0,
                    "mtime_ns":   0,
                    "status":     "existing",
                }

        result = list(children.values())
        result.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return result

    # ------------------------------------------------------------------
    # Tree population
    # ------------------------------------------------------------------

    def _populate_tree(self) -> None:
        self._tree.clear()
        self._tree.setSortingEnabled(False)
        entries = self._get_display_entries()

        for e in entries:
            icon    = _file_icon(e["name"], e["is_dir"])
            type_str = "Folder" if e["is_dir"] else Path(e["name"]).suffix.upper().lstrip(".") or "File"
            size_str = "—" if e["is_dir"] else _fmt_size(e["size"])
            time_str = _fmt_time(e["mtime_ns"])

            item = QTreeWidgetItem([
                f"{icon}  {e['name']}",
                type_str,
                size_str,
                time_str,
            ])
            item.setData(self._COL_NAME, self._ROLE_VAULT_PATH, e["vault_path"])
            item.setData(self._COL_NAME, self._ROLE_IS_DIR,     e["is_dir"])
            item.setData(self._COL_NAME, self._ROLE_STATUS,     e["status"])
            item.setData(self._COL_NAME, self._ROLE_SIZE,       e["size"])
            item.setData(self._COL_NAME, self._ROLE_MTIME,      e["mtime_ns"])

            # Color coding for staged changes
            status = e["status"]
            if status == "added":
                clr = QColor("#1a3d1e")
                fg  = QColor("#4ade80")
                item.setFont(0, QFont(item.font(0).family(), -1, -1, True))
            elif status == "renamed":
                clr = QColor("#2d2a10")
                fg  = QColor("#fbbf24")
                item.setFont(0, QFont(item.font(0).family(), -1, -1, True))
            else:
                clr = QColor(0, 0, 0, 0)
                fg  = QColor("#e2e8f0")

            for col in range(4):
                item.setBackground(col, clr)
                item.setForeground(col, fg)

            self._tree.addTopLevelItem(item)

        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(self._COL_NAME, Qt.SortOrder.AscendingOrder)
        self._update_breadcrumb()
        self._update_status()
        self._update_unsaved_badge()

    def _update_breadcrumb(self) -> None:
        # Clear
        while self._bc_layout.count():
            item = self._bc_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        vault_name = Path(self._vault_path).name.removesuffix(".cyphra-vault")
        segments   = [vault_name] + self._path_stack

        for idx, seg in enumerate(segments):
            btn = QPushButton(seg)
            btn.setObjectName("breadcrumbBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            depth = idx
            btn.clicked.connect(lambda _, d=depth: self._navigate_to_depth(d))
            self._bc_layout.addWidget(btn)

            if idx < len(segments) - 1:
                sep = QLabel("›")
                sep.setObjectName("breadcrumbSep")
                self._bc_layout.addWidget(sep)

        self._bc_layout.addStretch()

    def _navigate_to_depth(self, depth: int) -> None:
        """Navigate to the folder at *depth* in the breadcrumb (0 = root)."""
        self._path_stack = self._path_stack[:depth]
        self._populate_tree()

    def _navigate_up(self) -> None:
        if self._path_stack:
            self._path_stack.pop()
            self._populate_tree()

    def _update_status(self) -> None:
        entries = self._get_display_entries()
        n_dirs  = sum(1 for e in entries if e["is_dir"])
        n_files = sum(1 for e in entries if not e["is_dir"])
        total_size = sum(e["size"] for e in entries if not e["is_dir"])
        staged = len(self._staged_adds) + len(self._staged_removes) + len(self._staged_renames)
        parts  = [f"{n_dirs} folder(s)", f"{n_files} file(s)", _fmt_size(total_size)]
        if staged:
            parts.append(f"⚠ {staged} unsaved change(s)")
        self._status_label.setText("  ·  ".join(parts))

    def _update_unsaved_badge(self) -> None:
        self._unsaved_badge.setVisible(self._has_unsaved_changes())

    # ------------------------------------------------------------------
    # Navigation & open
    # ------------------------------------------------------------------

    def _on_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        is_dir    = item.data(self._COL_NAME, self._ROLE_IS_DIR)
        vault_path = item.data(self._COL_NAME, self._ROLE_VAULT_PATH)

        if is_dir:
            folder_name = vault_path.split("/")[-1]
            self._path_stack.append(folder_name)
            self._populate_tree()
        else:
            self._open_file_with_app(vault_path)

    def _open_file_with_app(self, vault_path: str) -> None:
        """Extract the entry to a temp dir and open it with the native app."""
        file_name = vault_path.split("/")[-1]
        tmp_dir   = tempfile.mkdtemp(prefix="cyphra_explorer_")
        self._temp_dirs.append(tmp_dir)
        tmp_path  = os.path.join(tmp_dir, file_name)

        # If it's a staged add (not yet saved), open the real file directly
        if vault_path in self._staged_adds:
            real = self._staged_adds[vault_path]
            QDesktopServices.openUrl(QUrl.fromLocalFile(real))
            return

        def _extract(progress, cancel_event):
            data = self.adapter.vault_extract_single(
                self._vault_path, vault_path, self._password
            )
            with open(tmp_path, "wb") as fh:
                fh.write(data)
            return tmp_path

        def _on_done(path: str) -> None:
            self._watched_temps[path] = vault_path
            self._file_watcher.addPath(path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

        def _on_fail(msg: str) -> None:
            QMessageBox.critical(self, "Cannot Open File", f"Failed to extract entry:\n{msg}")

        w = OperationWorker(_extract, self)
        w.succeeded.connect(_on_done)
        w.failed.connect(_on_fail)
        w.start()

    def _on_watched_file_changed(self, tmp_path: str) -> None:
        vault_path = self._watched_temps.get(tmp_path)
        if vault_path is None or not os.path.exists(tmp_path):
            return

        reply = QMessageBox.question(
            self, "File Modified",
            f"<b>{vault_path.split('/')[-1]}</b> was saved externally.<br><br>"
            "Write the changes back into the vault?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._staged_adds[vault_path] = tmp_path
            self._staged_removes.discard(vault_path)
            self._populate_tree()

    # ------------------------------------------------------------------
    # File actions
    # ------------------------------------------------------------------

    def _selected_vault_paths(self) -> list[str]:
        return [
            item.data(self._COL_NAME, self._ROLE_VAULT_PATH)
            for item in self._tree.selectedItems()
        ]

    def _action_add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Files to Vault")
        if paths:
            self._stage_add_paths(paths)

    def _action_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add Folder to Vault")
        if folder:
            self._stage_add_paths([folder])

    def _stage_add_paths(self, paths: list[str]) -> None:
        prefix = self._current_prefix
        for rp in paths:
            name = Path(rp).name
            vp   = (prefix + "/" + name).lstrip("/")
            self._staged_adds[vp]    = rp
            self._staged_removes.discard(vp)
        self._populate_tree()

    def _on_files_dropped(self, paths: list[str]) -> None:
        self._stage_add_paths(paths)

    def _action_new_folder(self) -> None:
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        name = name.strip()
        if not ok or not name:
            return
        if "/" in name or "\\" in name:
            QMessageBox.warning(self, "Invalid Name", "Folder names cannot contain slashes.")
            return
        prefix = self._current_prefix
        vp     = (prefix + "/" + name).lstrip("/")
        # Create a temp sentinel file so the folder is preserved
        tmp_dir = tempfile.mkdtemp(prefix="cyphra_folder_")
        self._temp_dirs.append(tmp_dir)
        # Store as a directory staged add (we use the temp dir itself)
        self._staged_adds[vp] = tmp_dir
        self._populate_tree()

    def _action_rename(self) -> None:
        items = self._tree.selectedItems()
        if len(items) != 1:
            return
        item = items[0]
        vault_path = item.data(self._COL_NAME, self._ROLE_VAULT_PATH)
        old_name   = vault_path.split("/")[-1]

        new_name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=old_name
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return
        if "/" in new_name or "\\" in new_name:
            QMessageBox.warning(self, "Invalid Name", "Names cannot contain slashes.")
            return

        parent_prefix = "/".join(vault_path.split("/")[:-1])
        new_vp = (parent_prefix + "/" + new_name).lstrip("/")

        # Staged add? Just remap.
        if vault_path in self._staged_adds:
            self._staged_adds[new_vp] = self._staged_adds.pop(vault_path)
        else:
            old_orig = vault_path
            # If already renamed before, chain from original
            for old_k, old_v in list(self._staged_renames.items()):
                if old_v == vault_path:
                    old_orig = old_k
                    del self._staged_renames[old_k]
                    break
            self._staged_renames[old_orig] = new_vp

        self._populate_tree()

    def _action_remove(self) -> None:
        selected = self._selected_vault_paths()
        if not selected:
            return

        names = "\n".join(f"• {p.split('/')[-1]}" for p in selected[:5])
        if len(selected) > 5:
            names += f"\n• …and {len(selected) - 5} more"

        reply = QMessageBox.question(
            self, "Remove Entries",
            f"Remove from vault (staged, not saved yet):\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for vp in selected:
            if vp in self._staged_adds:
                del self._staged_adds[vp]
            else:
                self._staged_removes.add(vp)
                # Also remove any rename pointing here
                for old, new in list(self._staged_renames.items()):
                    if new == vp:
                        del self._staged_renames[old]

        self._populate_tree()

    def _action_cut(self) -> None:
        self._clipboard = self._selected_vault_paths()
        self._clip_mode = "cut"

    def _action_copy(self) -> None:
        self._clipboard = self._selected_vault_paths()
        self._clip_mode = "copy"

    def _action_paste(self) -> None:
        if not self._clipboard:
            return
        prefix = self._current_prefix

        for src_vp in self._clipboard:
            name   = src_vp.split("/")[-1]
            dst_vp = (prefix + "/" + name).lstrip("/")

            if src_vp in self._staged_adds:
                self._staged_adds[dst_vp] = self._staged_adds[src_vp]
                if self._clip_mode == "cut":
                    del self._staged_adds[src_vp]
            else:
                if self._clip_mode == "cut":
                    self._staged_renames[src_vp] = dst_vp
                else:
                    # Copy = re-extract to temp then add
                    # For now, just mark as a "virtual copy" of an existing entry
                    # by staging an extract-on-save
                    self._staged_adds[dst_vp] = f"__copy__:{src_vp}"

        self._clipboard.clear()
        self._clip_mode = ""
        self._populate_tree()

    def _action_extract(self, vault_paths: list[str] | None = None) -> None:
        paths = vault_paths or self._selected_vault_paths()
        if not paths:
            return

        dest_dir = QFileDialog.getExistingDirectory(self, "Extract To…")
        if not dest_dir:
            return

        errors = []
        for vp in paths:
            try:
                fname   = vp.split("/")[-1]
                dst     = os.path.join(dest_dir, fname)
                if vp in self._staged_adds:
                    rp = self._staged_adds[vp]
                    if os.path.isdir(rp):
                        shutil.copytree(rp, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(rp, dst)
                else:
                    data = self.adapter.vault_extract_single(self._vault_path, vp, self._password)
                    Path(dst).write_bytes(data)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{vp}: {exc}")

        if errors:
            QMessageBox.warning(self, "Extraction Errors", "\n".join(errors))
        else:
            QMessageBox.information(self, "Extraction Complete",
                                    f"Extracted {len(paths)} item(s) to:\n{dest_dir}")

    # ------------------------------------------------------------------
    # Save vault
    # ------------------------------------------------------------------

    def _has_unsaved_changes(self) -> bool:
        return bool(self._staged_adds or self._staged_removes or self._staged_renames)

    def _action_save_vault(self) -> None:
        if not self._has_unsaved_changes():
            QMessageBox.information(self, "No Changes", "No staged changes to save.")
            return

        # Resolve any "virtual copy" entries (staged_adds value starting with __copy__:)
        for vp, rp in list(self._staged_adds.items()):
            if isinstance(rp, str) and rp.startswith("__copy__:"):
                src_vp = rp[len("__copy__:"):]
                tmp_dir = tempfile.mkdtemp(prefix="cyphra_copy_")
                self._temp_dirs.append(tmp_dir)
                tmp_path = os.path.join(tmp_dir, src_vp.split("/")[-1])
                try:
                    data = self.adapter.vault_extract_single(self._vault_path, src_vp, self._password)
                    Path(tmp_path).write_bytes(data)
                    self._staged_adds[vp] = tmp_path
                except Exception as exc:  # noqa: BLE001
                    QMessageBox.critical(self, "Save Error", f"Could not resolve copy of '{src_vp}':\n{exc}")
                    return

        adds    = dict(self._staged_adds)
        removes = set(self._staged_removes)
        renames = dict(self._staged_renames)

        def _do_rebuild(progress, cancel_event):
            self.adapter.vault_rebuild(
                self._vault_path,
                self._vault_path,
                self._password,
                adds=adds,
                removes=removes,
                renames=renames,
                progress=progress,
                cancel_event=cancel_event,
            )

        self._progress_panel.set_status("Saving vault…")
        self._progress_panel.set_progress(0)
        self._progress_panel.show()
        self._save_btn.setEnabled(False)

        self._worker = OperationWorker(_do_rebuild, self)
        self._worker.progress.connect(self._progress_panel.set_progress)
        self._worker.succeeded.connect(self._on_save_success)
        self._worker.failed.connect(self._on_save_failed)
        self._worker.cancelled.connect(lambda: self._on_save_failed("Save cancelled."))
        self._worker.start()

    def _on_save_success(self, _result) -> None:
        self._progress_panel.set_progress(100)
        self._staged_adds.clear()
        self._staged_removes.clear()
        self._staged_renames.clear()

        # Re-list the vault to refresh entries
        def _relist(progress, cancel_event):
            return self.adapter.vault_list(self._vault_path, self._password)

        w = OperationWorker(_relist, self)
        w.succeeded.connect(lambda r: self._refresh_after_save(r))
        w.start()

    def _refresh_after_save(self, result) -> None:
        _meta, entries = result
        self._vault_entries = list(entries)
        self._progress_panel.hide()
        self._save_btn.setEnabled(True)
        self._populate_tree()
        QMessageBox.information(self, "Saved", "Vault saved successfully.")

    def _on_save_failed(self, msg: str) -> None:
        self._progress_panel.hide()
        self._save_btn.setEnabled(True)
        QMessageBox.critical(self, "Save Failed", f"Could not save vault:\n{msg}")

    def _cancel_save(self) -> None:
        if self._worker:
            self._worker.cancel()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if not item:
            # Right-click on empty area
            menu = QMenu(self)
            menu.addAction("📁  New Folder",   self._action_new_folder)
            menu.addAction("➕  Add Files",    self._action_add_files)
            menu.addAction("📂  Add Folder",   self._action_add_folder)
            if self._clipboard:
                menu.addSeparator()
                menu.addAction("📋  Paste", self._action_paste)
            menu.exec(self._tree.mapToGlobal(pos))
            return

        vault_path = item.data(self._COL_NAME, self._ROLE_VAULT_PATH)
        is_dir     = item.data(self._COL_NAME, self._ROLE_IS_DIR)
        selected   = self._selected_vault_paths()

        menu = QMenu(self)

        if not is_dir:
            menu.addAction("🔍  Open", lambda: self._open_file_with_app(vault_path))
            menu.addAction("🖊  Open With…", lambda: self._open_with_dialog(vault_path))
            menu.addSeparator()

        if is_dir and vault_path not in self._staged_adds:
            menu.addAction("📂  Navigate Into", lambda: self._navigate_into(vault_path))

        menu.addAction("✏️  Rename",     self._action_rename)
        menu.addSeparator()
        menu.addAction("✂️  Cut",       self._action_cut)
        menu.addAction("📋  Copy",      self._action_copy)
        if self._clipboard:
            menu.addAction("📋  Paste", self._action_paste)
        menu.addSeparator()
        menu.addAction("📤  Extract to…", lambda: self._action_extract(selected))
        menu.addSeparator()
        menu.addAction("🗑  Remove",    self._action_remove)

        menu.exec(self._tree.mapToGlobal(pos))

    def _navigate_into(self, vault_path: str) -> None:
        self._path_stack = vault_path.split("/")
        self._populate_tree()

    def _open_with_dialog(self, vault_path: str) -> None:
        app_path, _ = QFileDialog.getOpenFileName(
            self, "Open With…", "",
            "Applications (*.exe *.app);;All Files (*)",
        )
        if not app_path:
            return
        # Extract to temp, then open with specified app
        file_name = vault_path.split("/")[-1]
        tmp_dir   = tempfile.mkdtemp(prefix="cyphra_openwith_")
        self._temp_dirs.append(tmp_dir)
        tmp_path  = os.path.join(tmp_dir, file_name)

        def _extract(progress, cancel_event):
            data = self.adapter.vault_extract_single(self._vault_path, vault_path, self._password)
            with open(tmp_path, "wb") as fh:
                fh.write(data)
            return tmp_path

        def _on_done(path: str) -> None:
            import subprocess
            subprocess.Popen([app_path, path])
            self._watched_temps[path] = vault_path
            self._file_watcher.addPath(path)

        w = OperationWorker(_extract, self)
        w.succeeded.connect(_on_done)
        w.start()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup_temps(self) -> None:
        for tp in list(self._watched_temps.keys()):
            self._file_watcher.removePath(tp)
        self._watched_temps.clear()
        for td in self._temp_dirs:
            try:
                shutil.rmtree(td, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass
        self._temp_dirs.clear()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._cleanup_temps()
        super().closeEvent(event)
