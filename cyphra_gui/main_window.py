"""Cyphra main window with custom frameless title bar, Inter typography, and modern dark styling."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizeGrip,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .core_adapter import CryptoAdapter
from .pages import HashPage, HomePage, OperationPage, SettingsPage
from .updater import CyphraUpdater
from .workers import OperationWorker

ASSETS_DIR = Path(__file__).resolve().parent / "assets"



def get_asset_path(name: str) -> Path:
    """Return path to an asset in cyphra_gui/assets/."""
    return ASSETS_DIR / name


def ensure_inter_font() -> str:
    """Register Inter font into QFontDatabase and return active font family name."""
    font_path = Path(__file__).parent / "fonts" / "Inter-Variable.ttf"
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
    families = QFontDatabase.families()
    if "Inter" in families:
        return "Inter"
    for candidate in ("Segoe UI Variable Text", "Segoe UI", "Segoe UI Semibold"):
        if candidate in families:
            return candidate
    return "sans-serif"


def enable_windows_dwm_shadow(window: QMainWindow) -> None:
    """Extend DWM frame into client area for native Windows aero drop shadow on frameless windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class MARGINS(ctypes.Structure):
            _fields_ = [
                ("cxLeftWidth", wintypes.INT),
                ("cxRightWidth", wintypes.INT),
                ("cyTopHeight", wintypes.INT),
                ("cyBottomHeight", wintypes.INT),
            ]

        hwnd = int(window.winId())
        margins = MARGINS(1, 1, 1, 1)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
    except Exception:  # noqa: BLE001
        pass


class WindowResizeFilter(QObject):
    """Enables edge-dragging resize on frameless windows."""

    def __init__(self, window: QMainWindow, margin: int = 6) -> None:
        self.window = window
        self.margin = margin
        self.drag_edge: str | None = None
        self.press_pos = None
        self.press_geom = None
        super().__init__(window)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        target = getattr(self, "window", None)
        if target is None or obj != target or target.isMaximized():
            return False

        if event.type() == QEvent.Type.MouseMove:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            if event.buttons() == Qt.MouseButton.LeftButton and self.drag_edge:
                self._do_resize(event.globalPosition().toPoint())
                return True
            self._update_cursor(pos)

        elif event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                edge = self._get_edge(pos)
                if edge:
                    self.drag_edge = edge
                    self.press_pos = event.globalPosition().toPoint()
                    self.press_geom = self.window.geometry()
                    return True

        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self.drag_edge:
                self.drag_edge = None
                return True

        return False

    def _get_edge(self, pos) -> str | None:
        w = self.window.width()
        h = self.window.height()
        m = self.margin
        left = pos.x() <= m
        right = pos.x() >= w - m
        top = pos.y() <= m
        bottom = pos.y() >= h - m

        if left and top:
            return "top_left"
        if right and top:
            return "top_right"
        if left and bottom:
            return "bottom_left"
        if right and bottom:
            return "bottom_right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None

    def _update_cursor(self, pos) -> None:
        edge = self._get_edge(pos)
        if edge in ("top_left", "bottom_right"):
            self.window.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge in ("top_right", "bottom_left"):
            self.window.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edge in ("left", "right"):
            self.window.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge in ("top", "bottom"):
            self.window.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.window.unsetCursor()

    def _do_resize(self, global_pos) -> None:
        delta = global_pos - self.press_pos
        geom = QRect(self.press_geom)
        min_w = self.window.minimumWidth()
        min_h = self.window.minimumHeight()

        if "right" in self.drag_edge:
            geom.setWidth(max(min_w, self.press_geom.width() + delta.x()))
        if "bottom" in self.drag_edge:
            geom.setHeight(max(min_h, self.press_geom.height() + delta.y()))
        if "left" in self.drag_edge:
            new_w = max(min_w, self.press_geom.width() - delta.x())
            geom.setLeft(self.press_geom.right() - new_w)
        if "top" in self.drag_edge:
            new_h = max(min_h, self.press_geom.height() - delta.y())
            geom.setTop(self.press_geom.bottom() - new_h)

        self.window.setGeometry(geom)


class CustomTitleBar(QFrame):
    """Themed frameless window title bar with dragging, double-click maximize, and custom controls."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.window_ref = window
        self._drag_pos = None
        self.setObjectName("customTitleBar")
        self.setFixedHeight(38)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(10)

        # App Brand & Title
        self.logo_icon = QLabel()
        self.logo_icon.setObjectName("titleBarIcon")
        emblem_path = get_asset_path("cyphra_emblem.png")
        if emblem_path.exists():
            pix = QPixmap(str(emblem_path))
            scaled = pix.scaled(20, 23, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_icon.setPixmap(scaled)
        else:
            self.logo_icon.setText("🛡️")
        layout.addWidget(self.logo_icon)

        brand = QLabel("CYPHRA")
        brand.setObjectName("titleBarBrand")
        layout.addWidget(brand)

        sep = QLabel("—")
        sep.setObjectName("titleBarSep")
        layout.addWidget(sep)

        title = QLabel("High-Assurance Local File Vault")
        title.setObjectName("titleBarText")
        layout.addWidget(title)

        layout.addStretch(1)

        # Minimize, Maximize, Close window controls
        self.min_btn = QPushButton("—")
        self.min_btn.setObjectName("winMinButton")
        self.min_btn.setToolTip("Minimize")
        self.min_btn.clicked.connect(self.window_ref.showMinimized)
        layout.addWidget(self.min_btn)

        self.max_btn = QPushButton("□")
        self.max_btn.setObjectName("winMaxButton")
        self.max_btn.setToolTip("Maximize / Restore")
        self.max_btn.clicked.connect(self._toggle_maximize)
        layout.addWidget(self.max_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("winCloseButton")
        self.close_btn.setToolTip("Close")
        self.close_btn.clicked.connect(self.window_ref.close)
        layout.addWidget(self.close_btn)

    def _toggle_maximize(self) -> None:
        if self.window_ref.isMaximized():
            self.window_ref.showNormal()
            self.max_btn.setText("□")
        else:
            self.window_ref.showMaximized()
            self.max_btn.setText("❐")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window_ref.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            if self.window_ref.isMaximized():
                self.window_ref.showNormal()
                self.max_btn.setText("□")
                self._drag_pos = event.globalPosition().toPoint() - self.window_ref.frameGeometry().topLeft()
            self.window_ref.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()


STYLESHEET_TEMPLATE = """
* {{
    font-family: "{font_family}";
    font-size: 13.5px;
    outline: none;
}}

QMainWindow {{
    background-color: #0b0f19;
    border: 1px solid #1a2233;
}}

#mainContent {{
    background-color: #0b0f19;
    color: #e2e8f0;
}}

QLabel {{
    background: transparent;
    color: #e2e8f0;
}}

/* Custom Window Title Bar */
#customTitleBar {{
    background-color: #080c14;
    border-bottom: 1px solid #161e2e;
}}

#titleBarIcon {{
    font-size: 14px;
    background: transparent;
}}

#titleBarBrand {{
    color: #ffffff;
    font-weight: 800;
    font-size: 13px;
    letter-spacing: 0.8px;
    background: transparent;
}}

#titleBarSep {{
    color: #334155;
    font-size: 12px;
    background: transparent;
}}

#titleBarText {{
    color: #94a3b8;
    font-size: 12px;
    font-weight: 500;
    background: transparent;
}}

#winMinButton, #winMaxButton, #winCloseButton {{
    background-color: transparent;
    border: none;
    color: #94a3b8;
    font-size: 13px;
    font-weight: 600;
    width: 44px;
    height: 38px;
    border-radius: 0;
    padding: 0;
}}

#winMinButton:hover, #winMaxButton:hover {{
    background-color: #161f30;
    color: #f8fafc;
}}

#winCloseButton:hover {{
    background-color: #e11d48;
    color: #ffffff;
}}

/* Sidebar */
#sidebar {{
    background-color: #0d121d;
    border-right: 1px solid #1a2233;
}}

#brandContainer {{
    padding: 12px 14px 14px;
    background: transparent;
}}

#brand {{
    color: #ffffff;
    font-size: 21px;
    font-weight: 800;
    letter-spacing: 0.5px;
}}

#brandTag {{
    color: #38bdf8;
    font-size: 8.5px;
    font-weight: 700;
    letter-spacing: 0.8px;
}}

#navLabel {{
    color: #64748b;
    font-size: 11.5px;
    font-weight: 750;
    letter-spacing: 1.2px;
    padding: 18px 14px 8px;
    background: transparent;
}}

#nav {{
    background: transparent;
    border: none;
    outline: none;
    padding: 4px;
    font-size: 15px;
    font-weight: 600;
}}

#nav::item {{
    color: #94a3b8;
    border-radius: 9px;
    padding: 12px 16px;
    margin: 3px 0;
}}

#nav::item:hover {{
    background-color: #141c2c;
    color: #f1f5f9;
}}

#nav::item:selected {{
    background-color: #1c2438;
    color: #ffffff;
    font-weight: 650;
    border-left: 3px solid #6366f1;
}}

#sidebarFooter {{
    border-top: 1px solid #1a2233;
    padding: 16px 14px;
    background: transparent;
}}

#sidebarFooterText {{
    color: #10b981;
    font-size: 12px;
    font-weight: 650;
}}

#sidebarVersion {{
    color: #64748b;
    font-size: 11.5px;
}}

/* Topbar */
#topbar {{
    background-color: #0b0f19;
    border-bottom: 1px solid #161e2e;
}}

#breadcrumbs {{
    color: #94a3b8;
    font-size: 13.5px;
    font-weight: 500;
}}

#coreBadge {{
    background-color: #0d231e;
    color: #34d399;
    border: 1px solid #065f46;
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}

#updateBadge {{
    background-color: #1e1b4b;
    color: #a5b4fc;
    border: 1px solid #4338ca;
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}


/* Page Titles and Subtitles */
#pageTitle {{
    color: #f8fafc;
    font-size: 24px;
    font-weight: 750;
    letter-spacing: -0.4px;
}}

#pageSubtitle {{
    color: #94a3b8;
    font-size: 13.5px;
    font-weight: 400;
    line-height: 1.4;
}}

/* Step Progress Header */
#stepHeader {{
    background-color: #0f1422;
    border: 1px solid #1a2233;
    border-radius: 10px;
}}

#stepPill {{
    border-radius: 6px;
    background: transparent;
}}

#stepPill:hover {{
    background-color: #161d2d;
    border: 1px solid #28374d;
}}

#stepPill[status="active"] {{
    background-color: #1e223d;
    border: 1px solid #4338ca;
}}

#stepPill[status="active"]:hover {{
    background-color: #262c54;
    border: 1px solid #6366f1;
}}

#stepPill[status="done"] {{
    background-color: #0d1f1c;
    border: 1px solid #065f46;
}}

#stepPill[status="done"]:hover {{
    background-color: #132e29;
    border: 1px solid #10b981;
}}

#stepPill[status="pending"] {{
    background: transparent;
    border: 1px solid transparent;
}}

#stepNumber {{
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
}}

#stepPill[status="active"] #stepNumber {{
    background-color: #6366f1;
    color: #ffffff;
}}

#stepPill[status="done"] #stepNumber {{
    background-color: #10b981;
    color: #ffffff;
}}

#stepPill[status="pending"] #stepNumber {{
    background-color: #1a2233;
    color: #64748b;
}}

#stepTitle {{
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}}

#stepPill[status="active"] #stepTitle {{
    color: #e0e7ff;
}}

#stepPill[status="done"] #stepTitle {{
    color: #6ee7b7;
}}

#stepPill[status="pending"] #stepTitle {{
    color: #64748b;
}}

#stepLine {{
    background-color: #1a2233;
}}

#stepLine[status="done"] {{
    background-color: #10b981;
}}

/* Cards */
#card {{
    background-color: #111624;
    border: 1px solid #1c2438;
    border-radius: 12px;
}}

#card:hover {{
    border-color: #26334d;
}}

#cardTitle {{
    color: #f8fafc;
    font-size: 15px;
    font-weight: 650;
    background: transparent;
}}

#cardSubtitle {{
    color: #94a3b8;
    font-size: 13px;
    line-height: 1.4;
    background: transparent;
}}

#mutedLabel {{
    color: #94a3b8;
    font-size: 12px;
    background: transparent;
}}

#fieldLabel {{
    color: #cbd5e1;
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}}

/* Forms & Inputs */
QLineEdit, QComboBox, QSpinBox {{
    background-color: #0c101a;
    color: #f1f5f9;
    border: 1px solid #232d42;
    border-radius: 8px;
    padding: 8px 14px;
    min-height: 22px;
    selection-background-color: #4f46e5;
    font-size: 13px;
}}

QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid #6366f1;
    background-color: #0e1320;
}}

QLineEdit[readOnly="true"] {{
    background-color: #0a0e16;
    color: #93c5fd;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
}}

QTextEdit {{
    background-color: #0c101a;
    color: #f1f5f9;
    border: 1px solid #232d42;
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 75px;
    selection-background-color: #4f46e5;
    font-size: 13px;
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

/* Custom Sleek Scrollbars */
QScrollBar:vertical {{
    background: #0c1220;
    width: 9px;
    margin: 0px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: #334155;
    min-height: 30px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: #6366f1;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

/* Buttons */
QPushButton {{
    color: #e2e8f0;
    background-color: #182030;
    border: 1px solid #26334a;
    border-radius: 8px;
    padding: 9px 16px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: #212b40;
    border-color: #374663;
    color: #ffffff;
}}

QPushButton:pressed {{
    background-color: #121824;
}}

#primaryButton {{
    background-color: #6366f1;
    border: 1px solid #818cf8;
    color: #ffffff;
    font-weight: 600;
}}

#primaryButton:hover {{
    background-color: #4f46e5;
    border-color: #a5b4fc;
}}

#primaryButton:disabled {{
    background-color: #272a45;
    border-color: #363b5e;
    color: #6b7280;
}}

#decryptButton {{
    background-color: #0284c7;
    border: 1px solid #38bdf8;
    color: #ffffff;
    font-weight: 600;
}}

#decryptButton:hover {{
    background-color: #0369a1;
    border-color: #7dd3fc;
}}

#decryptButton:disabled {{
    background-color: #162a3d;
    border-color: #1e3d59;
    color: #6b7280;
}}

#secondaryButton {{
    background-color: #151c2a;
    border: 1px solid #243046;
    color: #e2e8f0;
}}

#secondaryButton:hover {{
    background-color: #1e283c;
    border-color: #364766;
}}

#generatorButton {{
    background-color: #1a1e38;
    border: 1px solid #3d3b7a;
    color: #c7d2fe;
    padding: 8px 14px;
}}

#generatorButton:hover {{
    background-color: #262c54;
    border-color: #6366f1;
    color: #ffffff;
}}

#dangerButton {{
    background-color: #2e1017;
    border: 1px solid #7f1d2d;
    color: #fda4af;
    padding: 8px 14px;
}}

#dangerButton:hover {{
    background-color: #4c1320;
    border-color: #be123c;
    color: #ffe4e6;
}}

#copyButton {{
    background-color: #111d2b;
    border: 1px solid #1e3a5a;
    color: #38bdf8;
    padding: 7px 14px;
}}

#copyButton:hover {{
    background-color: #172a3d;
    border-color: #0284c7;
}}

#togglePasswordButton {{
    background-color: #151c2a;
    border: 1px solid #243046;
    color: #a5b4fc;
    font-weight: 600;
}}

#togglePasswordButton:hover {{
    background-color: #1e283c;
    border-color: #6366f1;
    color: #ffffff;
}}

/* DropZone */
#dropZone {{
    background-color: #0e131f;
    border: 2px dashed #243147;
    border-radius: 12px;
}}

#dropZone:hover, #dropZone[dragging="true"] {{
    border-color: #6366f1;
    background-color: #141a2e;
}}

#dropIcon {{
    font-size: 28px;
    background: transparent;
}}

#dropTitle {{
    color: #f1f5f9;
    font-size: 15px;
    font-weight: 650;
    background: transparent;
}}

#dropSubtitle {{
    color: #64748b;
    font-size: 12px;
    background: transparent;
}}

/* FilePill */
#filePill {{
    background-color: #111726;
    border: 1px solid #1c273c;
    border-radius: 8px;
}}

#filePill:hover {{
    border-color: #2a3b59;
}}

#filePillName {{
    color: #e2e8f0;
    font-size: 13px;
    font-weight: 550;
    background: transparent;
}}

#filePillSize {{
    color: #64748b;
    font-size: 12px;
    background: transparent;
}}

#pillRemoveButton {{
    background: transparent;
    border: none;
    color: #64748b;
    font-size: 18px;
    font-weight: 700;
}}

#pillRemoveButton:hover {{
    color: #f43f5e;
}}

/* Badges */
#badge_cyphra {{
    background-color: #083344;
    color: #22d3ee;
    border: 1px solid #0e7490;
    font-size: 10px;
    font-weight: 700;
    border-radius: 4px;
    padding: 3px 7px;
}}

#badge_vault {{
    background-color: #2e1065;
    color: #c084fc;
    border: 1px solid #6b21a8;
    font-size: 10px;
    font-weight: 700;
    border-radius: 4px;
    padding: 3px 7px;
}}

#badge_dir {{
    background-color: #451a03;
    color: #fbbf24;
    border: 1px solid #92400e;
    font-size: 10px;
    font-weight: 700;
    border-radius: 4px;
    padding: 3px 7px;
}}

QLabel[badge="true"] {{
    background-color: #172033;
    color: #94a3b8;
    border: 1px solid #283754;
    font-size: 10px;
    font-weight: 700;
    border-radius: 4px;
    padding: 3px 7px;
}}

/* Progress & Results */
#progressPanel {{
    background-color: #111624;
    border: 1px solid #1c253b;
    border-radius: 12px;
}}

#progressStatus {{
    color: #f8fafc;
    font-size: 15px;
    font-weight: 650;
    background: transparent;
}}

#progressPercent {{
    color: #6366f1;
    font-size: 14px;
    font-weight: 700;
    background: transparent;
}}

QProgressBar {{
    background-color: #1a2233;
    border: none;
    border-radius: 5px;
    height: 10px;
}}

QProgressBar::chunk {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #38bdf8);
    border-radius: 5px;
}}

#resultBanner {{
    background-color: #0c1d1a;
    border: 1px solid #0d5f4c;
    border-radius: 12px;
}}

#resultBanner[state="error"] {{
    background-color: #220f15;
    border-color: #7f1d2d;
}}

#resultIcon {{
    background-color: #064e3b;
    color: #34d399;
    font-size: 18px;
    font-weight: 700;
    border-radius: 18px;
}}

#resultBanner[state="error"] #resultIcon {{
    background-color: #4c1320;
    color: #f43f5e;
}}

#resultTitle {{
    color: #f8fafc;
    font-size: 16px;
    font-weight: 700;
    background: transparent;
}}

#resultMessage {{
    color: #94a3b8;
    font-size: 13px;
    line-height: 1.4;
    background: transparent;
}}

#warningLabel {{
    color: #fbbf24;
    background-color: #1f1908;
    border: 1px solid #78350f;
    border-radius: 8px;
    padding: 12px 14px;
    font-size: 12px;
    line-height: 1.4;
}}

/* Tabs */
QTabWidget::pane {{
    border: 1px solid #1c253b;
    border-radius: 8px;
    top: -1px;
    background-color: #0f1422;
}}

QTabBar::tab {{
    color: #94a3b8;
    background-color: #0b0f19;
    border: none;
    padding: 10px 22px;
    font-weight: 600;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}

QTabBar::tab:hover {{
    color: #f1f5f9;
    background-color: #111726;
}}

QTabBar::tab:selected {{
    color: #ffffff;
    background-color: #0f1422;
    border-bottom: 2px solid #6366f1;
}}

/* Security Guarantee Banner */
#securityBadge {{
    background-color: #0a171d;
    border: 1px solid #114e4b;
    border-radius: 10px;
}}

#securityBadgeIcon {{
    font-size: 26px;
    background: transparent;
}}

#securityBadgeTitle {{
    color: #2dd4bf;
    font-size: 13px;
    font-weight: 700;
    background: transparent;
}}

#securityBadgeDesc {{
    color: #94a3b8;
    font-size: 12px;
    line-height: 1.35;
    background: transparent;
}}

/* Review text */
#reviewText {{
    color: #e2e8f0;
    font-size: 13px;
    line-height: 1.5;
    background: transparent;
}}

/* Password strength */
#passwordStrengthLabel {{
    color: #94a3b8;
    font-size: 12px;
    background: transparent;
}}

#hashStatusLabel {{
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}}

#aboutTitle {{
    color: #f8fafc;
    font-size: 14px;
    font-weight: 600;
    background: transparent;
}}
"""


class Sidebar(QFrame):
    page_selected = Signal(str)

    def __init__(self, font_family: str = "Inter", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 18, 16, 16)
        layout.setSpacing(6)

        # Brand header
        brand_box = QFrame()
        brand_box.setObjectName("brandContainer")
        brand_layout = QHBoxLayout(brand_box)
        brand_layout.setContentsMargins(0, 4, 0, 10)
        brand_layout.setSpacing(12)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("sidebarLogo")
        emblem_path = get_asset_path("cyphra_emblem.png")
        if emblem_path.exists():
            pix = QPixmap(str(emblem_path))
            scaled = pix.scaled(36, 42, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(scaled)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        brand = QLabel("CYPHRA")
        brand.setObjectName("brand")
        tag = QLabel("AUTHENTICATED VAULT")
        tag.setObjectName("brandTag")

        text_layout.addWidget(brand)
        text_layout.addWidget(tag)

        brand_layout.addWidget(self.logo_label)
        brand_layout.addLayout(text_layout, 1)
        layout.addWidget(brand_box)

        # Main Nav
        label = QLabel("WORKSPACE")
        label.setObjectName("navLabel")
        layout.addWidget(label)

        self.navigation = QListWidget()
        self.navigation.setObjectName("nav")
        self.navigation.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.navigation.setSpacing(4)

        nav_font = QFont(font_family, 11)
        nav_font.setWeight(QFont.Weight.DemiBold)

        entries = [
            ("⌂   Dashboard", "home"),
            ("🔒  Encrypt Files", "encrypt"),
            ("🔓  Decrypt Files", "decrypt"),
            ("⚡  Hash & Verify", "hash"),
        ]
        for text, key in entries:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFont(nav_font)
            item.setSizeHint(QSize(220, 44))
            self.navigation.addItem(item)
        self.navigation.setFixedHeight(204)
        layout.addWidget(self.navigation)

        # Settings
        label2 = QLabel("PREFERENCES")
        label2.setObjectName("navLabel")
        layout.addWidget(label2)

        self.settings_nav = QListWidget()
        self.settings_nav.setObjectName("nav")
        self.settings_nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        item = QListWidgetItem("⚙   Settings")
        item.setData(Qt.ItemDataRole.UserRole, "settings")
        item.setFont(nav_font)
        item.setSizeHint(QSize(220, 44))
        self.settings_nav.addItem(item)
        self.settings_nav.setFixedHeight(54)
        layout.addWidget(self.settings_nav)

        layout.addStretch()

        # Footer
        footer_box = QFrame()
        footer_box.setObjectName("sidebarFooter")
        footer_layout = QVBoxLayout(footer_box)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(3)

        footer = QLabel("● Local Protected")
        footer.setObjectName("sidebarFooterText")
        v_label = QLabel("Cyphra v0.2.0 · Zero Telemetry")
        v_label.setObjectName("sidebarVersion")


        footer_layout.addWidget(footer)
        footer_layout.addWidget(v_label)
        layout.addWidget(footer_box)

        self.navigation.itemClicked.connect(
            lambda clicked: self._nav_clicked(clicked.data(Qt.ItemDataRole.UserRole))
        )
        self.settings_nav.itemClicked.connect(
            lambda clicked: self._settings_clicked(clicked.data(Qt.ItemDataRole.UserRole))
        )

    def _nav_clicked(self, key: str) -> None:
        self.settings_nav.clearSelection()
        self.page_selected.emit(key)

    def _settings_clicked(self, key: str) -> None:
        self.navigation.clearSelection()
        self.page_selected.emit(key)

    def select(self, key: str) -> None:
        if key == "settings":
            self.navigation.clearSelection()
            self.settings_nav.setCurrentRow(0)
            return
        self.settings_nav.clearSelection()
        for index in range(self.navigation.count()):
            item = self.navigation.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                self.navigation.setCurrentItem(item)
                return


class MainWindow(QMainWindow):
    """Top-level Cyphra window with themed custom title bar and responsive layouts."""

    def __init__(self, adapter: CryptoAdapter | None = None) -> None:
        super().__init__()
        self.adapter = adapter or CryptoAdapter()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowTitle("Cyphra — High-Assurance Local File Vault")
        self.setMinimumSize(980, 680)
        self.resize(1180, 760)

        icon_path = get_asset_path("cyphra_icon.ico")
        if not icon_path.exists():
            icon_path = get_asset_path("cyphra_icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.font_family = ensure_inter_font()
        base_font = QFont(self.font_family, 10)
        base_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        QApplication.setFont(base_font)

        self.setStyleSheet(STYLESHEET_TEMPLATE.format(font_family=self.font_family))
        self._build()

        self.resize_filter = WindowResizeFilter(self)
        self.installEventFilter(self.resize_filter)
        enable_windows_dwm_shadow(self)

    def _build(self) -> None:
        central = QWidget()
        root_vbox = QVBoxLayout(central)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        # Custom Themed Window Title Bar (replaces native Windows OS top bar)
        self.title_bar = CustomTitleBar(self)
        root_vbox.addWidget(self.title_bar)

        # Body Container
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = Sidebar(font_family=self.font_family)
        self.sidebar.page_selected.connect(self.show_page)
        body_layout.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("mainContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Internal App Topbar (Breadcrumbs + Core status)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(54)
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(32, 0, 32, 0)

        self.breadcrumbs = QLabel("Workspace  ›  Dashboard")
        self.breadcrumbs.setObjectName("breadcrumbs")

        self.update_badge = QLabel("●  Update Ready (Restart to apply)")
        self.update_badge.setObjectName("updateBadge")
        self.update_badge.setToolTip("Latest code changes were pulled from GitHub. Restart Cyphra to run the updated version.")
        self.update_badge.setVisible(False)

        self.core_status = QLabel("●  Crypto Core Active" if self.adapter.available else "●  Adapter Mode")
        self.core_status.setObjectName("coreBadge")

        top_layout.addWidget(self.breadcrumbs)
        top_layout.addStretch()
        top_layout.addWidget(self.update_badge)
        top_layout.addWidget(self.core_status)
        content_layout.addWidget(topbar)

        # Periodic background check timer while app is running
        self.updater = CyphraUpdater()
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(30 * 60 * 1000)  # Check every 30 minutes
        self.update_timer.timeout.connect(self._check_periodic_updates)
        self.update_timer.start()


        # Pages
        self.pages = QStackedWidget()
        self.page_map: dict[str, QWidget] = {}
        self._add_page("home", HomePage())
        self._add_page("encrypt", OperationPage(self.adapter, "encrypt"))
        self._add_page("decrypt", OperationPage(self.adapter, "decrypt"))
        self._add_page("hash", HashPage(self.adapter))
        self._add_page("settings", SettingsPage())

        content_layout.addWidget(self.pages, 1)
        body_layout.addWidget(content, 1)
        root_vbox.addWidget(body, 1)

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

        # If user clicks the active page or returns to a finished/failed operation,
        # automatically reset back to step 0 (file upload) so user is never trapped in saved state
        if isinstance(page, OperationPage):
            if self.pages.currentWidget() == page or page.stack.currentIndex() == 4:
                page.reset()

        self.pages.setCurrentWidget(page)
        page_names = {
            "home": "Dashboard",
            "encrypt": "Encrypt Files",
            "decrypt": "Decrypt Files",
            "hash": "Hash & Integrity",
            "settings": "Settings",
        }
        name = page_names.get(key, key.title())
        self.breadcrumbs.setText(f"Workspace  ›  <span style='color: #f8fafc; font-weight: 600;'>{name}</span>")
        self.sidebar.select(key)

    def _check_periodic_updates(self) -> None:
        """Periodically check for updates in background while app remains open."""
        if hasattr(self, "updater") and self.updater.should_check_update(force=False):
            def _bg_check(**kwargs) -> bool:
                ok, msg = self.updater.check_and_update()
                if ok and any(word in msg.lower() for word in ("updated", "pulled", "commits")):
                    return True
                return False

            worker = OperationWorker(_bg_check, self)

            def _on_done(has_update: bool) -> None:
                if has_update and hasattr(self, "update_badge"):
                    self.update_badge.setVisible(True)

            worker.succeeded.connect(_on_done)
            self._bg_update_worker = worker
            worker.start()

