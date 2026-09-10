"""Cyphra modern async splash screen with dynamic status and animated progress."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEventLoop,
    QPropertyAnimation,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from .main_window import enable_windows_dwm_shadow, ensure_inter_font, get_asset_path
from .updater import CyphraUpdater


class SplashWorker(QThread):
    """Background worker that performs updater checks and core initialization."""

    status_changed = Signal(str)
    progress_changed = Signal(int)

    def __init__(
        self,
        enable_updater: bool = True,
        force_update: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.enable_updater = enable_updater
        self.force_update = force_update
        self.updater = CyphraUpdater()

    def run(self) -> None:
        try:
            self.status_changed.emit("Initializing Cyphra Engine...")
            self.progress_changed.emit(10)
            self.msleep(100)

            if self.enable_updater:
                if self.updater.should_check_update(force=self.force_update):
                    self.status_changed.emit("Checking for updates...")
                    self.progress_changed.emit(20)

                    # Run update check / pull (guaranteed safe & offline resilient)
                    self.updater.check_and_update(
                        status_callback=self.status_changed.emit,
                        progress_callback=self.progress_changed.emit,
                        force=self.force_update,
                    )
                    self.msleep(150)
                else:
                    self.status_changed.emit("Cyphra Engine Ready")
                    self.progress_changed.emit(60)
                    self.msleep(50)


            # Core pre-verification
            self.status_changed.emit("Loading cryptographic core...")
            self.progress_changed.emit(90)
            self.msleep(150)

            self.status_changed.emit("Ready")
            self.progress_changed.emit(100)
            self.msleep(250)

        except Exception:
            # Absolute failsafe: startup must never block or crash
            self.status_changed.emit("Starting Cyphra...")
            self.progress_changed.emit(100)



class SplashScreen(QWidget):
    """Sleek, dark frameless splash screen with branding, animated progress, and status."""

    def __init__(self, font_family: str | None = None) -> None:
        super().__init__()
        self.font_family = font_family or ensure_inter_font()
        self._fade_anim: QPropertyAnimation | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.SplashScreen
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Cyphra")
        self.resize(490, 330)

        # Center on primary screen
        screen = QApplication.primaryScreen()
        if screen:
            screen_geom = screen.availableGeometry()
            x = screen_geom.center().x() - self.width() // 2
            y = screen_geom.center().y() - self.height() // 2
            self.move(x, y)

        self._build_ui()
        enable_windows_dwm_shadow(self)

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(14, 14, 14, 14)

        # Card container
        self.card = QFrame()
        self.card.setObjectName("splashCard")
        self.card.setStyleSheet(f"""
            #splashCard {{
                background-color: #080c14;
                border: 1px solid #1a2333;
                border-radius: 16px;
            }}
            QLabel {{
                font-family: "{self.font_family}";
                background: transparent;
            }}
            #brandTitle {{
                color: #ffffff;
                font-size: 26px;
                font-weight: 800;
                letter-spacing: 2px;
            }}
            #brandSubtitle {{
                color: #38bdf8;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.4px;
            }}
            #badgeText {{
                color: #10b981;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.8px;
            }}
            #versionText {{
                color: #64748b;
                font-size: 10.5px;
                font-weight: 600;
            }}
            #splashStatus {{
                color: #cbd5e1;
                font-size: 12px;
                font-weight: 500;
            }}
            #footerText {{
                color: #475569;
                font-size: 10.5px;
            }}
            QProgressBar {{
                background-color: #111827;
                border: 1px solid #1f293d;
                border-radius: 3px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                border-radius: 2px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6366f1,
                    stop:0.5 #38bdf8,
                    stop:1 #10b981
                );
            }}
        """)

        # Soft drop shadow for frameless depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(0, 8)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 22, 28, 22)
        card_layout.setSpacing(0)

        # Header Row: Engine status badge & Version
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)

        badge = QLabel("●  SECURE VAULT ENGINE")
        badge.setObjectName("badgeText")
        header_row.addWidget(badge)

        header_row.addStretch()

        version = QLabel("v0.2.0")
        version.setObjectName("versionText")
        header_row.addWidget(version)

        card_layout.addLayout(header_row)

        card_layout.addSpacing(16)

        # Center Brand Icon & Titles
        center_box = QVBoxLayout()
        center_box.setSpacing(6)
        center_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Logo Emblem
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        emblem_path = get_asset_path("cyphra_emblem.png")
        if not emblem_path.exists():
            emblem_path = get_asset_path("cyphra_icon.png")
        if emblem_path.exists():
            pix = QPixmap(str(emblem_path))
            scaled = pix.scaled(
                56,
                64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.logo_label.setPixmap(scaled)
        center_box.addWidget(self.logo_label)

        title = QLabel("CYPHRA")
        title.setObjectName("brandTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_box.addWidget(title)

        subtitle = QLabel("AUTHENTICATED ZERO-KNOWLEDGE CONTAINER")
        subtitle.setObjectName("brandSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_box.addWidget(subtitle)

        card_layout.addLayout(center_box)

        card_layout.addSpacing(20)

        # Status Label & Progress Bar
        self.status_label = QLabel("Starting Cyphra...")
        self.status_label.setObjectName("splashStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.status_label)

        card_layout.addSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(10)
        card_layout.addWidget(self.progress_bar)

        card_layout.addSpacing(16)

        # Footer
        footer = QLabel("Multi-Cipher Local Security · Open Source")
        footer.setObjectName("footerText")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(footer)

        outer_layout.addWidget(self.card)

    def set_status(self, text: str) -> None:
        """Update the splash status message in a thread-safe manner."""
        self.status_label.setText(text)

    def set_progress(self, value: int) -> None:
        """Update the progress bar value (0-100)."""
        self.progress_bar.setValue(max(0, min(100, value)))

    def fade_in(self, duration: int = 220) -> None:
        """Animate smooth opacity fade in."""
        self.setWindowOpacity(0.0)
        self.show()
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(duration)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

    def finish_and_launch(
        self,
        main_window: QWidget,
        fade_duration: int = 240,
    ) -> None:
        """Fade out the splash screen and transition smoothly into the main window."""
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(fade_duration)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InQuad)

        def on_fade_out() -> None:
            self.close()
            main_window.show()
            main_window.raise_()
            main_window.activateWindow()

        self._fade_anim.finished.connect(on_fade_out)
        self._fade_anim.start()
