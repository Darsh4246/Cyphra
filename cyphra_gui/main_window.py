"""Cyphra main window and application-wide dark styling."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .core_adapter import CryptoAdapter
from .pages import HashPage, HomePage, OperationPage, SettingsPage


STYLESHEET = """
* {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 14px;
}
QMainWindow, QWidget { background: #0b0d13; color: #f1f5f9; }
#sidebar { background: #11141d; border-right: 1px solid #252a38; }
#brand { color: #f8fafc; font-size: 21px; font-weight: 700; padding: 12px 8px 22px; }
#brandDot { color: #8b5cf6; }
#navLabel { color: #64748b; font-size: 11px; font-weight: 700; letter-spacing: 1px; padding: 14px 10px 6px; }
#nav {
    background: transparent; border: none; outline: none; padding: 4px;
}
#nav::item {
    color: #94a3b8; border-radius: 8px; padding: 11px 12px; margin: 2px 0;
}
#nav::item:hover { background: #1e2230; color: #e2e8f0; }
#nav::item:selected { background: #282343; color: #c4b5fd; font-weight: 600; }
#mainContent { background: #0b0d13; }
#topbar { border-bottom: 1px solid #252a38; }
#breadcrumbs { color: #94a3b8; font-size: 13px; }
#status { color: #64748b; font-size: 12px; }
.pageTitle { color: #f8fafc; font-size: 28px; font-weight: 700; padding-top: 2px; }
.pageSubtitle { color: #94a3b8; font-size: 14px; padding-bottom: 2px; }
#card {
    background: #141822; border: 1px solid #252a38; border-radius: 12px;
}
#cardTitle { color: #f8fafc; font-size: 16px; font-weight: 650; }
#mutedLabel, .mutedLabel { color: #94a3b8; }
#fieldLabel { color: #cbd5e1; font-size: 13px; font-weight: 600; }
QLineEdit, QTextEdit, QComboBox, QSpinBox {
    background: #0f121a; color: #e2e8f0; border: 1px solid #303747;
    border-radius: 8px; padding: 10px 12px; selection-background-color: #6d4dd8;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #8b5cf6; }
QComboBox::drop-down { border: none; width: 24px; }
QPushButton {
    color: #e2e8f0; background: #202636; border: 1px solid #303747;
    border-radius: 8px; padding: 10px 16px; font-weight: 600;
}
QPushButton:hover { background: #2a3144; border-color: #475569; }
QPushButton:pressed { background: #18202d; }
#primaryButton { background: #7c3aed; border-color: #8b5cf6; color: white; }
#primaryButton:hover { background: #8b5cf6; }
#primaryButton:disabled { background: #302852; color: #8d84aa; border-color: #3a315c; }
#secondaryButton { background: #202636; }
#copyButton { background: #252d40; color: #c4b5fd; }
#copyButton:hover { background: #313b54; border-color: #8b5cf6; }
#copyButton:pressed { background: #1d2433; }
#textButton, #iconButton { background: transparent; border: none; color: #a78bfa; padding: 5px; }
#textButton:hover, #iconButton:hover { color: #c4b5fd; }
#dropZone {
    background: #10131d; border: 1px dashed #475569; border-radius: 12px;
}
#dropZone:hover, #dropZone[dragging="true"] { border-color: #a78bfa; background: #17152a; }
#dropIcon { color: #a78bfa; font-size: 32px; font-weight: 300; }
#dropTitle { color: #e2e8f0; font-size: 16px; font-weight: 600; }
#filePill { background: #1a1f2b; border: 1px solid #303747; border-radius: 7px; }
#progressPanel { background: #141822; border: 1px solid #303747; border-radius: 10px; }
QProgressBar { background: #252a38; border: none; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #8b5cf6; border-radius: 4px; }
#resultBanner { background: #11231d; border: 1px solid #1f6b4c; border-radius: 10px; padding: 4px; }
#resultBanner[state="error"] { background: #28161d; border-color: #7f2939; }
#resultIcon { color: #4ade80; font-size: 22px; font-weight: 700; }
#resultBanner[state="error"] #resultIcon { color: #fb7185; }
#warningLabel { color: #fbbf24; background: #251e0d; border: 1px solid #604c1d; border-radius: 7px; padding: 10px; }
QTabWidget::pane { border: 1px solid #252a38; border-radius: 8px; top: -1px; }
QTabBar::tab { color: #94a3b8; background: #141822; border: none; padding: 10px 18px; }
QTabBar::tab:selected { color: #c4b5fd; border-bottom: 2px solid #8b5cf6; }
QTextEdit { line-height: 1.4; }
QLineEdit[readOnly="true"] {
    color: #c4b5fd;
    font-family: "Cascadia Mono", "Consolas", monospace;
    letter-spacing: 0.3px;
}
QLabel#mutedLabel { line-height: 1.35; }
QScrollBar:vertical { background: #11141d; width: 8px; }
QScrollBar::handle:vertical { background: #303747; border-radius: 4px; min-height: 30px; }
"""


class Sidebar(QFrame):
    page_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(4)
        brand = QLabel("C<span style='color:#8b5cf6'>y</span>phra")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        label = QLabel("WORKSPACE")
        label.setObjectName("navLabel")
        layout.addWidget(label)
        self.navigation = QListWidget()
        self.navigation.setObjectName("nav")
        self.navigation.setSpacing(2)
        entries = [
            ("⌂   Home", "home"),
            ("↗   Encrypt", "encrypt"),
            ("↙   Decrypt", "decrypt"),
            ("⌁   Hash & verify", "hash"),
        ]
        for text, key in entries:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.navigation.addItem(item)
        layout.addWidget(self.navigation)
        label = QLabel("PREFERENCES")
        label.setObjectName("navLabel")
        layout.addWidget(label)
        settings = QListWidget()
        settings.setObjectName("nav")
        item = QListWidgetItem("⚙   Settings")
        item.setData(Qt.ItemDataRole.UserRole, "settings")
        settings.addItem(item)
        settings.itemClicked.connect(lambda clicked: self.page_selected.emit(clicked.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(settings)
        layout.addStretch()
        footer = QLabel("LOCAL-FIRST PROTECTION\nv0.1.0")
        footer.setObjectName("status")
        footer.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(footer)
        self.navigation.itemClicked.connect(
            lambda clicked: self.page_selected.emit(clicked.data(Qt.ItemDataRole.UserRole))
        )

    def select(self, key: str) -> None:
        for index in range(self.navigation.count()):
            item = self.navigation.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                self.navigation.setCurrentItem(item)
                return


class MainWindow(QMainWindow):
    """Top-level Cyphra window.

    Pass a ``CryptoAdapter`` to inject a parallel-developed core implementation
    (or a fake adapter in tests).  With no argument, the adapter discovers the
    conventional core modules automatically.
    """

    def __init__(self, adapter: CryptoAdapter | None = None) -> None:
        super().__init__()
        self.adapter = adapter or CryptoAdapter()
        self.setWindowTitle("Cyphra — Private file protection")
        self.setMinimumSize(980, 680)
        self.resize(1180, 760)
        self.setStyleSheet(STYLESHEET)
        self._build()

    def _build(self) -> None:
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = Sidebar()
        self.sidebar.page_selected.connect(self.show_page)
        outer.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("mainContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 0, 28, 24)
        content_layout.setSpacing(0)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(54)
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(0, 0, 0, 0)
        self.breadcrumbs = QLabel("Home")
        self.breadcrumbs.setObjectName("breadcrumbs")
        self.core_status = QLabel("●  Core ready" if self.adapter.available else "●  Core adapter mode")
        self.core_status.setObjectName("status")
        top_layout.addWidget(self.breadcrumbs)
        top_layout.addStretch()
        top_layout.addWidget(self.core_status)
        content_layout.addWidget(topbar)
        self.pages = QStackedWidget()
        self.page_map: dict[str, QWidget] = {}
        self._add_page("home", HomePage())
        self._add_page("encrypt", OperationPage(self.adapter, "encrypt"))
        self._add_page("decrypt", OperationPage(self.adapter, "decrypt"))
        self._add_page("hash", HashPage(self.adapter))
        self._add_page("settings", SettingsPage())
        content_layout.addWidget(self.pages, 1)
        outer.addWidget(content, 1)
        self.setCentralWidget(central)
        self.show_page("home")

    def _add_page(self, key: str, page: QWidget) -> None:
        if hasattr(page, "navigate"):
            page.navigate.connect(self.show_page)
        self.page_map[key] = page
        self.pages.addWidget(page)

    def show_page(self, key: str) -> None:
        page = self.page_map.get(key)
        if page is None:
            return
        self.pages.setCurrentWidget(page)
        self.breadcrumbs.setText(key.replace("_", " ").title())
        self.sidebar.select(key)
