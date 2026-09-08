"""Reusable dark-theme controls used by the Cyphra screens."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class DropZone(QFrame):
    """A keyboard-accessible drop target that also emits selected files."""

    files_dropped = Signal(list)
    clicked = Signal()

    def __init__(self, title: str = "Drop files here", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label = QLabel("↓")
        self.icon_label.setObjectName("dropIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("dropTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label = QLabel("or click to browse from your computer")
        self.subtitle_label.setObjectName("mutedLabel")
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
        files = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and Path(url.toLocalFile()).is_file()
        ]
        if files:
            self.files_dropped.emit(files)
        event.acceptProposedAction()


class PasswordField(QWidget):
    """Password input with a show/hide toggle and strength feedback."""

    value_changed = Signal(str)

    def __init__(self, label: str = "Password", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("passwordField")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        caption = QLabel(label)
        caption.setObjectName("fieldLabel")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Enter a strong password")
        self.input.setEchoMode(QLineEdit.EchoMode.Password)
        self.input.textChanged.connect(self._changed)
        self.toggle = QPushButton("Show")
        self.toggle.setObjectName("textButton")
        self.toggle.setCheckable(True)
        self.toggle.setFixedWidth(56)
        self.toggle.toggled.connect(self._toggle_visibility)
        row.addWidget(self.input)
        row.addWidget(self.toggle)
        self.strength = QLabel("Use 12+ characters with a mix of letters, numbers, and symbols")
        self.strength.setObjectName("mutedLabel")
        layout.addWidget(caption)
        layout.addLayout(row)
        layout.addWidget(self.strength)

    def _toggle_visibility(self, visible: bool) -> None:
        self.input.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )
        self.toggle.setText("Hide" if visible else "Show")

    def _changed(self, value: str) -> None:
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
        labels = ("", "Very weak", "Weak", "Fair", "Strong", "Excellent")
        colors = ("#94a3b8", "#fb7185", "#fb923c", "#facc15", "#4ade80", "#34d399")
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
    """Consistent progress/cancel panel shown during worker operations."""

    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("progressPanel")
        layout = QVBoxLayout(self)
        self.status = QLabel("Working…")
        self.status.setObjectName("cardTitle")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.cancel = QPushButton("Cancel operation")
        self.cancel.setObjectName("secondaryButton")
        self.cancel.clicked.connect(self.cancel_requested)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addWidget(self.cancel, alignment=Qt.AlignmentFlag.AlignLeft)

    def set_progress(self, value: int) -> None:
        self.progress.setValue(max(0, min(value, 100)))

    def set_status(self, text: str) -> None:
        self.status.setText(text)


class ResultBanner(QFrame):
    """Success or error state with a compact action row."""

    action_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultBanner")
        layout = QHBoxLayout(self)
        self.icon = QLabel("✓")
        self.icon.setObjectName("resultIcon")
        text_layout = QVBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("cardTitle")
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("mutedLabel")
        text_layout.addWidget(self.title)
        text_layout.addWidget(self.message)
        self.action = QPushButton()
        self.action.setObjectName("secondaryButton")
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
        self.icon.setText("!")
        self.title.setText("Something went wrong")
        self.message.setText(message)
        self.action.setVisible(False)
        self._refresh()

    def _refresh(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        self.show()


def card(title: str, subtitle: str = "", parent: QWidget | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(parent)
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setSpacing(12)
    heading = QLabel(title)
    heading.setObjectName("cardTitle")
    layout.addWidget(heading)
    if subtitle:
        detail = QLabel(subtitle)
        detail.setObjectName("mutedLabel")
        detail.setWordWrap(True)
        layout.addWidget(detail)
    return frame, layout


class FilePill(QFrame):
    """A row representing a selected file, with a remove action."""

    remove_requested = Signal(str)

    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.setObjectName("filePill")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        name = QLabel(Path(path).name)
        name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        detail = QLabel(self._size_text())
        detail.setObjectName("mutedLabel")
        remove = QPushButton("×")
        remove.setObjectName("iconButton")
        remove.setFixedSize(28, 28)
        remove.clicked.connect(lambda: self.remove_requested.emit(self.path))
        layout.addWidget(name)
        layout.addWidget(detail)
        layout.addWidget(remove)

    def _size_text(self) -> str:
        try:
            size = Path(self.path).stat().st_size
            for unit in ("B", "KB", "MB", "GB"):
                if size < 1024 or unit == "GB":
                    return f"{size:.0f} {unit}"
                size /= 1024
        except OSError:
            return "File unavailable"
        return ""
