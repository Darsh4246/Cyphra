"""Reusable dark-theme controls and animated widgets for Cyphra."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class AnimatedStackedWidget(QStackedWidget):
    """QStackedWidget with smooth fade transition between views."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._anim: QPropertyAnimation | None = None
        self._active_effect_widget: QWidget | None = None

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if index == self.currentIndex() or index < 0 or index >= self.count():
            super().setCurrentIndex(index)
            return

        if self._anim and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
            if self._active_effect_widget:
                self._active_effect_widget.setGraphicsEffect(None)

        next_widget = self.widget(index)
        if not next_widget:
            super().setCurrentIndex(index)
            return

        super().setCurrentIndex(index)

        effect = QGraphicsOpacityEffect(next_widget)
        next_widget.setGraphicsEffect(effect)
        self._active_effect_widget = next_widget

        self._anim = QPropertyAnimation(effect, b"opacity")
        self._anim.setDuration(120)
        self._anim.setStartValue(0.4)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def cleanup() -> None:
            if self._active_effect_widget:
                self._active_effect_widget.setGraphicsEffect(None)
                self._active_effect_widget = None

        self._anim.finished.connect(cleanup)
        self._anim.start()

    def flush_animation(self) -> None:
        """Immediately finish any pending transition animation."""
        if self._anim and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        if self._active_effect_widget:
            self._active_effect_widget.setGraphicsEffect(None)
            self._active_effect_widget = None


class StepProgressHeader(QWidget):
    """Visual horizontal step progression indicator with clickable step navigation."""

    step_clicked = Signal(int)

    def __init__(self, steps: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("stepHeader")
        self.steps = steps
        self.step_labels: list[QLabel] = []
        self.step_num_labels: list[QLabel] = []
        self.step_containers: list[QFrame] = []
        self.connectors: list[QFrame] = []
        self._current_step = 0
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        for index, step_title in enumerate(self.steps):
            container = QFrame()
            container.setObjectName("stepPill")
            container.setCursor(Qt.CursorShape.PointingHandCursor)
            container.mousePressEvent = self._make_click_handler(index)

            c_layout = QHBoxLayout(container)
            c_layout.setContentsMargins(10, 5, 12, 5)
            c_layout.setSpacing(8)

            num_label = QLabel(str(index + 1))
            num_label.setObjectName("stepNumber")
            num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num_label.setFixedSize(20, 20)

            title_label = QLabel(step_title)
            title_label.setObjectName("stepTitle")

            c_layout.addWidget(num_label)
            c_layout.addWidget(title_label)

            self.step_containers.append(container)
            self.step_num_labels.append(num_label)
            self.step_labels.append(title_label)
            layout.addWidget(container)

            if index < len(self.steps) - 1:
                line = QFrame()
                line.setObjectName("stepLine")
                line.setMinimumWidth(20)
                line.setFixedHeight(2)
                line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self.connectors.append(line)
                layout.addWidget(line)

        self.set_step(0)

    def _make_click_handler(self, step_idx: int) -> Callable[[object], None]:
        def handler(event) -> None:
            if hasattr(event, "button") and event.button() == Qt.MouseButton.LeftButton:
                self.step_clicked.emit(step_idx)
        return handler

    def set_step(self, active_index: int) -> None:
        self._current_step = active_index
        for index, (container, num_label, title_label) in enumerate(
            zip(self.step_containers, self.step_num_labels, self.step_labels)
        ):
            if index < active_index:
                container.setProperty("status", "done")
                num_label.setText("✓")
            elif index == active_index:
                container.setProperty("status", "active")
                num_label.setText(str(index + 1))
            else:
                container.setProperty("status", "pending")
                num_label.setText(str(index + 1))

            container.style().unpolish(container)
            container.style().polish(container)
            num_label.style().unpolish(num_label)
            num_label.style().polish(num_label)
            title_label.style().unpolish(title_label)
            title_label.style().polish(title_label)

        for index, line in enumerate(self.connectors):
            state = "done" if index < active_index else "pending"
            line.setProperty("status", state)
            line.style().unpolish(line)
            line.style().polish(line)


class DropZone(QFrame):
    """A keyboard-accessible drag and drop target."""

    files_dropped = Signal(list)
    clicked = Signal()

    def __init__(self, title: str = "Drop files here to begin", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)
        layout.setContentsMargins(20, 18, 20, 18)

        self.icon_label = QLabel("📥")
        self.icon_label.setObjectName("dropIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("dropTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.subtitle_label = QLabel("Click to browse or drop files, folders, or Cyphra containers")
        self.subtitle_label.setObjectName("dropSubtitle")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for child in (self.icon_label, self.title_label, self.subtitle_label):
            layout.addWidget(child)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        files = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and Path(url.toLocalFile()).exists()
        ]
        if files:
            self.files_dropped.emit(files)
        event.acceptProposedAction()


class PasswordField(QWidget):
    """Password input with show/hide toggle and optional strength feedback."""

    value_changed = Signal(str)

    def __init__(
        self,
        label: str = "Password",
        mode: str = "encrypt",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.setObjectName("passwordField")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        caption = QLabel(label)
        caption.setObjectName("fieldLabel")

        row = QHBoxLayout()
        row.setSpacing(8)

        self.input = QLineEdit()
        if mode == "decrypt":
            self.input.setPlaceholderText("Enter the password for this file...")
        else:
            self.input.setPlaceholderText("Enter a strong password...")
        self.input.setEchoMode(QLineEdit.EchoMode.Password)
        self.input.textChanged.connect(self._changed)

        self.toggle = QPushButton("Show")
        self.toggle.setObjectName("togglePasswordButton")
        self.toggle.setCheckable(True)
        self.toggle.setFixedWidth(64)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.toggled.connect(self._toggle_visibility)

        row.addWidget(self.input, 1)
        row.addWidget(self.toggle)

        layout.addWidget(caption)
        layout.addLayout(row)

        self.strength = QLabel("Use 12+ characters with a mix of letters, numbers, and symbols")
        self.strength.setObjectName("passwordStrengthLabel")
        layout.addWidget(self.strength)

        # In decrypt mode, hide password strength meter completely
        if mode == "decrypt":
            self.strength.hide()

    def _toggle_visibility(self, visible: bool) -> None:
        self.input.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )
        self.toggle.setText("Hide" if visible else "Show")

    def _changed(self, value: str) -> None:
        if self.mode == "encrypt":
            score = 0
            if len(value) >= 8:
                score += 1
            if len(value) >= 14:
                score += 1
            if any(char.islower() for char in value) and any(char.isupper() for char in value):
                score += 1
            if any(char.isdigit() for char in value):
                score += 1
            if any(not char.isalnum() for char in value):
                score += 1

            labels = (
                "Enter a password to assess strength",
                "Very weak — easily guessed",
                "Weak — consider adding more characters",
                "Fair — decent, but could be stronger",
                "Strong — good cryptographic defense",
                "Excellent — highly resilient passphrase",
            )
            colors = ("#94a3b8", "#f43f5e", "#fb923c", "#facc15", "#34d399", "#10b981")
            self.strength.setText(
                labels[score] if value else "Use 12+ characters with a mix of letters, numbers, and symbols"
            )
            self.strength.setStyleSheet(f"color: {colors[score]};")

        self.value_changed.emit(value)

    def text(self) -> str:
        return self.input.text()

    def setText(self, value: str) -> None:  # noqa: N802
        self.input.setText(value)

    def clear(self) -> None:
        self.input.clear()


class ProgressPanel(QFrame):
    """Progress indicator panel shown during worker operations."""

    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("progressPanel")
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        header_row = QHBoxLayout()
        self.status = QLabel("Processing files…")
        self.status.setObjectName("progressStatus")
        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("progressPercent")
        header_row.addWidget(self.status, 1)
        header_row.addWidget(self.percent_label)
        layout.addLayout(header_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        layout.addWidget(self.progress)

        self.detail_label = QLabel("Please keep Cyphra open until the operation finishes.")
        self.detail_label.setObjectName("mutedLabel")
        layout.addWidget(self.detail_label)

        action_row = QHBoxLayout()
        self.cancel = QPushButton("Cancel Operation")
        self.cancel.setObjectName("dangerButton")
        self.cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel.clicked.connect(self.cancel_requested)
        action_row.addWidget(self.cancel, alignment=Qt.AlignmentFlag.AlignLeft)
        action_row.addStretch()
        layout.addLayout(action_row)

    def set_progress(self, value: int) -> None:
        clamped = max(0, min(value, 100))
        self.progress.setValue(clamped)
        self.percent_label.setText(f"{clamped}%")

    def set_status(self, text: str) -> None:
        self.status.setText(text)


class ResultBanner(QFrame):
    """Success or error state banner."""

    action_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        self.icon = QLabel("✓")
        self.icon.setObjectName("resultIcon")
        self.icon.setFixedSize(36, 36)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        self.title = QLabel()
        self.title.setObjectName("resultTitle")
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("resultMessage")
        text_layout.addWidget(self.title)
        text_layout.addWidget(self.message)

        self.action = QPushButton()
        self.action.setObjectName("primaryButton")
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.clicked.connect(self.action_clicked)

        layout.addWidget(self.icon)
        layout.addLayout(text_layout, 1)
        layout.addWidget(self.action)

    def show_success(self, title: str, message: str, action: str = "") -> None:
        self.setProperty("state", "success")
        self.icon.setText("✓")
        self.title.setText(title)
        self.message.setText(message)
        self.action.setText(action)
        self.action.setVisible(bool(action))
        self._refresh()

    def show_error(self, message: str) -> None:
        self.setProperty("state", "error")
        self.icon.setText("✕")
        self.title.setText("Operation could not be completed")
        self.message.setText(message)
        self.action.setVisible(False)
        self._refresh()

    def _refresh(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        self.icon.style().unpolish(self.icon)
        self.icon.style().polish(self.icon)
        self.show()


def card(title: str, subtitle: str = "", parent: QWidget | None = None) -> tuple[QFrame, QVBoxLayout]:
    """Create a styled card container."""
    frame = QFrame(parent)
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)

    heading = QLabel(title)
    heading.setObjectName("cardTitle")
    layout.addWidget(heading)

    if subtitle:
        detail = QLabel(subtitle)
        detail.setObjectName("cardSubtitle")
        detail.setWordWrap(True)
        layout.addWidget(detail)

    return frame, layout


class FilePill(QFrame):
    """A row representing a selected file with badge and remove action."""

    remove_requested = Signal(str)

    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.setObjectName("filePill")
        self.setToolTip(path)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(10)

        p = Path(path)
        badge_type = self._badge_type(p)

        if badge_type in ("CYPHRA", "VAULT"):
            icon_label = QLabel()
            ico_file = Path(__file__).resolve().parent / "assets" / "logo.ico"
            if not ico_file.exists():
                ico_file = Path(__file__).resolve().parent / "assets" / "cyphra_icon.ico"
            pix = QPixmap(str(ico_file))
            if not pix.isNull():
                icon_label.setPixmap(
                    pix.scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
                icon_label.setFixedSize(20, 20)
                layout.addWidget(icon_label)

        badge = QLabel(badge_type)
        badge.setObjectName(f"badge_{badge_type.lower()}")
        badge.setProperty("badge", True)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge)

        name = QLabel(p.name or path)
        name.setObjectName("filePillName")
        name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(name, 1)

        detail = QLabel(self._size_text())
        detail.setObjectName("filePillSize")
        layout.addWidget(detail)

        remove = QPushButton("×")
        remove.setObjectName("pillRemoveButton")
        remove.setFixedSize(26, 26)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.clicked.connect(lambda: self.remove_requested.emit(self.path))
        layout.addWidget(remove)

    def _badge_type(self, path: Path) -> str:
        if path.is_dir():
            return "DIR"
        suffix = path.suffix.lower()
        if suffix == ".cyphra":
            return "CYPHRA"
        if suffix == ".cyphra-vault":
            return "VAULT"
        if suffix:
            return suffix[1:6].upper()
        return "FILE"

    def _size_text(self) -> str:
        try:
            path_obj = Path(self.path)
            if path_obj.is_dir():
                count = sum(1 for _ in path_obj.rglob("*") if _.is_file())
                return f"{count} files"
            size = path_obj.stat().st_size
            for unit in ("B", "KB", "MB", "GB"):
                if size < 1024 or unit == "GB":
                    return f"{size:.1f} {unit}" if unit in ("MB", "GB") else f"{size:.0f} {unit}"
                size /= 1024
        except OSError:
            return "Unavailable"
        return ""


class AlgorithmInfoCard(QFrame):
    """Rich interactive card detailing cryptographic algorithm specifications, usage, and security status."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("algorithmInfoCard")
        self.setStyleSheet("""
            #algorithmInfoCard {
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #f8fafc;")

        self.badge_label = QLabel()
        self.badge_label.setStyleSheet("font-size: 10.5px; font-weight: 600; padding: 2px 8px; border-radius: 4px;")

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.badge_label)
        header_layout.addStretch(1)
        layout.addLayout(header_layout)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 12px; color: #cbd5e1; line-height: 1.4;")
        layout.addWidget(self.desc_label)

        self.usage_label = QLabel()
        self.usage_label.setWordWrap(True)
        self.usage_label.setStyleSheet("font-size: 11.5px; color: #38bdf8; font-weight: 500;")
        layout.addWidget(self.usage_label)

        self.specs_label = QLabel()
        self.specs_label.setWordWrap(True)
        self.specs_label.setStyleSheet("font-size: 11px; color: #94a3b8;")
        layout.addWidget(self.specs_label)

    def set_metadata(self, meta: dict[str, Any]) -> None:
        name = meta.get("title") or meta.get("name", "")
        self.title_label.setText(name)

        status = meta.get("status") or meta.get("tag", "")
        badge_color = meta.get("badge_color", "#38bdf8")
        self.badge_label.setText(status)
        self.badge_label.setStyleSheet(
            f"font-size: 10.5px; font-weight: 600; padding: 2px 8px; border-radius: 4px; "
            f"background-color: {badge_color}22; color: {badge_color}; border: 1px solid {badge_color}55;"
        )

        self.desc_label.setText(meta.get("description", ""))
        where_used = meta.get("where_used", "")
        if where_used:
            self.usage_label.setText(f"🌐 Industry Applications: {where_used}")
            self.usage_label.show()
        else:
            self.usage_label.hide()

        specs = []
        if "key_size" in meta:
            specs.append(f"Key: {meta['key_size']}")
        if "auth_tag" in meta:
            specs.append(f"Auth: {meta['auth_tag']}")
        if "memory" in meta:
            specs.append(f"RAM: {meta['memory']}")
        if "iterations" in meta:
            specs.append(f"Work: {meta['iterations']}")
        if "bits" in meta:
            specs.append(f"Digest: {meta['bits']} bits ({meta.get('hex_len', 0)} hex)")
        if "family" in meta:
            specs.append(f"Standard: {meta['family']}")

        if specs:
            self.specs_label.setText(" · ".join(specs))
            self.specs_label.show()
        else:
            self.specs_label.hide()
