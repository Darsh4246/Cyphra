"""Application pages and the encrypt/decrypt/hash workflows."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSettings, Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .core_adapter import CryptoAdapter, generate_password
from .workers import OperationWorker
from .widgets import DropZone, FilePill, PasswordField, ProgressPanel, ResultBanner, card


def _button(text: str, slot: Callable[[], None], primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("primaryButton" if primary else "secondaryButton")
    button.clicked.connect(slot)
    return button


class HomePage(QWidget):
    navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(24)
        intro = QLabel("Welcome to <span style='color:#8b5cf6'>Cyphra</span>")
        intro.setObjectName("pageTitle")
        subtitle = QLabel("Private, simple file protection — right on your device.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(intro)
        layout.addWidget(subtitle)

        actions = QHBoxLayout()
        actions.setSpacing(16)
        encrypt, encrypt_layout = card("Encrypt files", "Protect files with a password before sharing or storing them.")
        encrypt_layout.addWidget(_button("Start encrypting  →", lambda: self.navigate.emit("encrypt"), True))
        decrypt, decrypt_layout = card("Decrypt files", "Restore your original files with a Cyphra password.")
        decrypt_layout.addWidget(_button("Start decrypting  →", lambda: self.navigate.emit("decrypt"), True))
        actions.addWidget(encrypt)
        actions.addWidget(decrypt)
        layout.addLayout(actions)

        recent, recent_layout = card("Quick tools", "Verify a download or inspect a file without changing it.")
        quick = QHBoxLayout()
        quick.addWidget(_button("Calculate a hash", lambda: self.navigate.emit("hash")))
        quick.addWidget(_button("Open settings", lambda: self.navigate.emit("settings")))
        quick.addStretch()
        recent_layout.addLayout(quick)
        layout.addWidget(recent)

        tips, tips_layout = card("Built for privacy")
        tip = QLabel("Your password and file contents stay local. Cyphra never uploads your files.")
        tip.setObjectName("mutedLabel")
        tips_layout.addWidget(tip)
        layout.addWidget(tips)
        layout.addStretch()


class OperationPage(QWidget):
    """Shared multi-step workflow used by Encrypt and Decrypt."""

    navigate = Signal(str)

    def __init__(self, adapter: CryptoAdapter, mode: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self.mode = mode
        self.files: list[str] = []
        self.worker: OperationWorker | None = None
        self.destination = ""
        self.stack = QStackedWidget()
        self._build_select()
        self._build_configure()
        self._build_review()
        self._build_progress()
        self._build_result()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(self.stack)
        self._show_step(0)

    @property
    def verb(self) -> str:
        return "Encrypt" if self.mode == "encrypt" else "Decrypt"

    @property
    def operation(self) -> Callable[..., object]:
        return self.adapter.encrypt_file if self.mode == "encrypt" else self.adapter.decrypt_file

    def _header(self, title: str, detail: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        subtitle = QLabel(detail)
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        return layout

    def _build_select(self) -> None:
        page = QWidget()
        layout = self._header(
            f"{self.verb} files",
            "Choose one or more files to get started. Everything stays on this device.",
        )
        zone = DropZone("Drop files here to begin")
        zone.clicked.connect(self._browse)
        zone.files_dropped.connect(self._files_selected)
        self.drop_zone = zone
        layout.addWidget(zone)
        self.file_list = QVBoxLayout()
        layout.addLayout(self.file_list)
        row = QHBoxLayout()
        row.addWidget(_button("Browse files", self._browse))
        row.addWidget(_button("Choose folder", self._browse_folder))
        row.addStretch()
        self.select_continue = _button("Continue to configuration  →", self._to_configure, True)
        self.select_continue.setEnabled(False)
        row.addWidget(self.select_continue)
        layout.addLayout(row)
        page.setLayout(layout)
        self.stack.addWidget(page)

    def _build_configure(self) -> None:
        page = QWidget()
        layout = self._header(
            "Configure protection",
            "Use a unique password. A password is never stored by Cyphra.",
        )
        content, content_layout = card("Password")
        self.password = PasswordField()
        content_layout.addWidget(self.password)
        generate = _button("Generate secure password", self._generate_password)
        content_layout.addWidget(generate, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(content)
        output, output_layout = card(
            "Output location",
            "Choose where the processed file will be written.",
        )
        out_row = QHBoxLayout()
        self.destination_input = QLineEdit()
        self.destination_input.setReadOnly(True)
        self.destination_input.setPlaceholderText("Select an output location")
        browse = _button("Choose…", self._choose_destination)
        out_row.addWidget(self.destination_input)
        out_row.addWidget(browse)
        output_layout.addLayout(out_row)
        layout.addWidget(output)
        row = QHBoxLayout()
        row.addWidget(_button("← Back", lambda: self._show_step(0)))
        row.addStretch()
        row.addWidget(_button("Review  →", self._to_review, True))
        layout.addLayout(row)
        layout.addStretch()
        page.setLayout(layout)
        self.stack.addWidget(page)

    def _build_review(self) -> None:
        page = QWidget()
        layout = self._header("Review and confirm", "Check the details before the operation begins.")
        review, review_layout = card("Ready to process")
        self.review_text = QLabel()
        self.review_text.setObjectName("reviewText")
        self.review_text.setWordWrap(True)
        review_layout.addWidget(self.review_text)
        layout.addWidget(review)
        notice = QLabel("Keep your password safe. Cyphra cannot recover a forgotten password.")
        notice.setObjectName("warningLabel")
        layout.addWidget(notice)
        row = QHBoxLayout()
        row.addWidget(_button("← Edit", lambda: self._show_step(1)))
        row.addStretch()
        row.addWidget(_button(f"Start {self.verb.lower()}  →", self._start, True))
        layout.addLayout(row)
        layout.addStretch()
        page.setLayout(layout)
        self.stack.addWidget(page)

    def _build_progress(self) -> None:
        page = QWidget()
        layout = self._header(
            f"{self.verb} in progress",
            "You can cancel at any time. Do not close the application while writing.",
        )
        self.progress_panel = ProgressPanel()
        self.progress_panel.cancel_requested.connect(self._cancel)
        layout.addWidget(self.progress_panel)
        layout.addStretch()
        page.setLayout(layout)
        self.stack.addWidget(page)

    def _build_result(self) -> None:
        page = QWidget()
        layout = self._header(f"{self.verb} complete", "Your files are ready.")
        self.result = ResultBanner()
        self.result.action_clicked.connect(self._open_destination)
        layout.addWidget(self.result)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(_button(f"{self.verb} more files", self.reset, True))
        layout.addLayout(row)
        layout.addStretch()
        page.setLayout(layout)
        self.stack.addWidget(page)

    def _show_step(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

    def _browse(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            f"Select files to {self.verb.lower()}",
            "",
            "All files (*)",
        )
        if files:
            self._files_selected(files)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose folder")
        if folder:
            self._files_selected([folder])

    def _files_selected(self, files: list[str]) -> None:
        self.files = list(dict.fromkeys(files))
        while self.file_list.count():
            item = self.file_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for path in self.files:
            pill = FilePill(path)
            pill.remove_requested.connect(self._remove_file)
            self.file_list.addWidget(pill)
        self.select_continue.setEnabled(bool(self.files))
        if self.files:
            self.drop_zone.title_label.setText(f"{len(self.files)} file(s) selected")

    def _remove_file(self, path: str) -> None:
        self._files_selected([item for item in self.files if item != path])

    def _to_configure(self) -> None:
        if not self.files:
            return
        default = self._default_destination(self.files[0])
        self.destination_input.setText(default)
        self._show_step(1)

    def _default_destination(self, source: str) -> str:
        path = Path(source)
        if self.mode == "encrypt":
            suffix = ".cyphra-vault" if path.is_dir() else ".cyphra"
            return str(path.with_name(path.name + suffix))
        if path.suffix.lower() == ".cyphra-vault":
            return str(path.with_name(path.name.removesuffix(".cyphra-vault")))
        return str(path.with_name(path.stem if path.suffix.lower() == ".cyphra" else path.name + ".decrypted"))

    def _choose_destination(self) -> None:
        start = self.destination_input.text() or str(Path(self.files[0]).parent)
        if self.mode == "decrypt" and Path(self.files[0]).suffix.lower() == ".cyphra-vault":
            destination = QFileDialog.getExistingDirectory(self, "Choose extraction folder", start)
            if destination:
                self.destination_input.setText(destination)
            return
        suffix = ".cyphra" if self.mode == "encrypt" else ""
        destination, _ = QFileDialog.getSaveFileName(
            self, "Choose output location", start, f"Cyphra files (*{suffix})" if suffix else "All files (*)"
        )
        if destination:
            self.destination_input.setText(destination)

    def _generate_password(self) -> None:
        self.password.setText(generate_password())

    def _to_review(self) -> None:
        if not self.password.text():
            self.password.input.setFocus()
            self.password.strength.setText("A password is required")
            self.password.strength.setStyleSheet("color: #fb7185;")
            return
        if not self.destination_input.text():
            self._choose_destination()
        if not self.destination_input.text():
            return
        self.destination = self.destination_input.text()
        self.review_text.setText(
            f"<b>{len(self.files)} file(s)</b><br>"
            f"Output: <b>{Path(self.destination).name}</b><br>"
            "Password: ••••••••••••"
        )
        self._show_step(2)

    def _start(self) -> None:
        password = self.password.text()
        sources = list(self.files)
        destination = self.destination

        def run(progress, cancel_event):
            total = len(sources)
            result = []
            for index, source in enumerate(sources):
                if cancel_event.is_set():
                    from .core_adapter import OperationCancelled
                    raise OperationCancelled()
                target = destination if total == 1 else str(
                    Path(destination).with_name(Path(source).name + (".cyphra" if self.mode == "encrypt" else ".decrypted"))
                )
                result.append(self.operation(source, target, password, progress, cancel_event))
                progress(int((index + 1) * 100 / total))
            return result

        self.progress_panel.set_status(f"Processing {len(sources)} file(s)…")
        self.progress_panel.set_progress(0)
        self._show_step(3)
        self.worker = OperationWorker(run, self)
        self.worker.progress.connect(self.progress_panel.set_progress)
        self.worker.succeeded.connect(self._success)
        self.worker.failed.connect(self._failure)
        self.worker.cancelled.connect(self._cancelled)
        self.worker.start()

    def _cancel(self) -> None:
        if self.worker:
            self.progress_panel.set_status("Cancelling…")
            self.progress_panel.cancel.setEnabled(False)
            self.worker.cancel()

    def _success(self, _result) -> None:
        self.progress_panel.set_progress(100)
        self.result.show_success(
            f"{self.verb} successful",
            f"{len(self.files)} file(s) processed successfully.",
            "Open output folder",
        )
        self._show_step(4)

    def _failure(self, message: str) -> None:
        if "unsupported cyphra container" in message.lower():
            message = "This is not a supported Cyphra Image or Vault container."
        self.result.show_error(message)
        self._show_step(4)

    def _cancelled(self) -> None:
        self.result.show_error("The operation was cancelled. Partial output files may need to be removed.")
        self._show_step(4)

    def _open_destination(self) -> None:
        target = Path(self.destination)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent)))

    def reset(self) -> None:
        self.files.clear()
        self.password.clear()
        self.destination_input.clear()
        self._files_selected([])
        self.progress_panel.cancel.setEnabled(True)
        self._show_step(0)


class HashPage(QWidget):
    navigate = Signal(str)

    def __init__(self, adapter: CryptoAdapter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self.worker: OperationWorker | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        heading = QLabel("Hash & verify")
        heading.setObjectName("pageTitle")
        subtitle = QLabel("Create a fingerprint for text or a file, then compare it with a known value.")
        subtitle.setObjectName("pageSubtitle")
        root.addWidget(heading)
        root.addWidget(subtitle)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._text_tab(), "Text")
        self.tabs.addTab(self._file_tab(), "File")
        root.addWidget(self.tabs)
        root.addStretch()

    def _algorithm(self) -> str:
        return self.algorithm.currentText()

    def _algorithm_combo(self) -> QComboBox:
        self.algorithm = QComboBox()
        self.algorithm.addItems(["SHA-256", "SHA-512"])
        return self.algorithm

    def _text_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        frame, frame_layout = card("Text to hash", "Paste text below. It is processed locally.")
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Enter text to calculate a hash…")
        self.text_input.setMinimumHeight(150)
        frame_layout.addWidget(self.text_input)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Algorithm"))
        controls.addWidget(self._algorithm_combo())
        controls.addStretch()
        controls.addWidget(_button("Calculate hash", self._hash_text, True))
        frame_layout.addLayout(controls)
        self.text_result = QLineEdit()
        self.text_result.setReadOnly(True)
        self.text_result.setPlaceholderText("Your hash will appear here")
        frame_layout.addWidget(self.text_result)
        copy = _button("Copy hash", lambda: self._copy(self.text_result, self.text_compare_status), False)
        copy.setObjectName("copyButton")
        frame_layout.addWidget(copy, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(frame)
        compare, compare_layout = card("Compare with a known hash")
        compare_row = QHBoxLayout()
        self.text_expected = QLineEdit()
        self.text_expected.setPlaceholderText("Paste expected hash")
        compare_row.addWidget(self.text_expected)
        compare_row.addWidget(_button("Compare", self._compare_text))
        compare_layout.addLayout(compare_row)
        self.text_compare_status = QLabel()
        self.text_compare_status.setObjectName("mutedLabel")
        compare_layout.addWidget(self.text_compare_status)
        layout.addWidget(compare)
        return page

    def _file_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        frame, frame_layout = card("File to hash", "Hashing large files runs in the background.")
        row = QHBoxLayout()
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        row.addWidget(self.file_path)
        row.addWidget(_button("Choose file…", self._choose_file))
        frame_layout.addLayout(row)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Algorithm"))
        self.file_algorithm = QComboBox()
        self.file_algorithm.addItems(["SHA-256", "SHA-512"])
        controls.addWidget(self.file_algorithm)
        controls.addStretch()
        controls.addWidget(_button("Calculate hash", self._hash_file, True))
        frame_layout.addLayout(controls)
        self.file_progress = ProgressPanel()
        self.file_progress.cancel_requested.connect(self._cancel)
        self.file_progress.hide()
        frame_layout.addWidget(self.file_progress)
        self.file_result = QLineEdit()
        self.file_result.setReadOnly(True)
        self.file_result.setPlaceholderText("Your hash will appear here")
        frame_layout.addWidget(self.file_result)
        copy = _button("Copy hash", lambda: self._copy(self.file_result, self.file_compare_status), False)
        copy.setObjectName("copyButton")
        frame_layout.addWidget(copy, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(frame)
        compare, compare_layout = card("Compare with a known hash")
        compare_row = QHBoxLayout()
        self.file_expected = QLineEdit()
        self.file_expected.setPlaceholderText("Paste expected hash")
        compare_row.addWidget(self.file_expected)
        compare_row.addWidget(_button("Compare", self._compare_file))
        compare_layout.addLayout(compare_row)
        self.file_compare_status = QLabel()
        self.file_compare_status.setObjectName("mutedLabel")
        compare_layout.addWidget(self.file_compare_status)
        layout.addWidget(compare)
        return page

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a file")
        if path:
            self.file_path.setText(path)

    def _hash_text(self) -> None:
        try:
            self.text_result.setText(self.adapter.hash_text(self.text_input.toPlainText(), self._algorithm()))
        except Exception as error:  # noqa: BLE001
            self.text_compare_status.setText(str(error))

    def _hash_file(self) -> None:
        if not self.file_path.text():
            self.file_compare_status.setText("Choose a file first.")
            return
        self.file_progress.show()
        self.file_progress.set_progress(0)
        self.worker = OperationWorker(
            lambda progress, cancel_event: self.adapter.hash_file(
                self.file_path.text(), self.file_algorithm.currentText(), progress
            ),
            self,
        )
        self.worker.progress.connect(self.file_progress.set_progress)
        self.worker.succeeded.connect(self._file_hash_success)
        self.worker.failed.connect(lambda error: self.file_compare_status.setText(error))
        self.worker.cancelled.connect(lambda: self.file_compare_status.setText("Hash cancelled."))
        self.worker.start()

    def _file_hash_success(self, value: str) -> None:
        self.file_result.setText(value)
        self.file_progress.set_progress(100)

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel()

    def _copy(self, field: QLineEdit, status: QLabel) -> None:
        value = field.text().strip()
        if not value:
            status.setText("Calculate a hash first.")
            status.setStyleSheet("color: #fbbf24;")
            return
        QApplication.clipboard().setText(value)
        status.setText("Hash copied to the clipboard.")
        status.setStyleSheet("color: #4ade80;")

    def _compare_text(self) -> None:
        self._compare(self.text_result, self.text_expected, self.text_compare_status)

    def _compare_file(self) -> None:
        self._compare(self.file_result, self.file_expected, self.file_compare_status)

    def _compare(self, actual: QLineEdit, expected: QLineEdit, status: QLabel) -> None:
        if not actual.text() or not expected.text():
            status.setText("Calculate and provide both hashes first.")
            return
        matches = self.adapter.compare_hash(actual.text(), expected.text())
        status.setText("✓ Hashes match" if matches else "✕ Hashes do not match")
        status.setStyleSheet(f"color: {'#4ade80' if matches else '#fb7185'};")


class SettingsPage(QWidget):
    navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        settings = QSettings("Cyphra", "Cyphra")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        heading = QLabel("Settings")
        heading.setObjectName("pageTitle")
        subtitle = QLabel("Tune Cyphra to your workflow. Changes are saved automatically.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        appearance, appearance_layout = card("Appearance")
        theme = QComboBox()
        theme.addItems(["Dark (recommended)", "System"])
        theme.setCurrentIndex(0 if settings.value("theme", "dark") == "dark" else 1)
        theme.currentIndexChanged.connect(lambda index: settings.setValue("theme", "dark" if index == 0 else "system"))
        form = QFormLayout()
        form.addRow("Theme", theme)
        appearance_layout.addLayout(form)
        layout.addWidget(appearance)
        behavior, behavior_layout = card("Behavior")
        remember = QCheckBox("Remember the last selected output folder")
        remember.setChecked(settings.value("remember_folder", True, type=bool))
        remember.toggled.connect(lambda value: settings.setValue("remember_folder", value))
        behavior_layout.addWidget(remember)
        layout.addWidget(behavior)
        about, about_layout = card("About Cyphra")
        about_layout.addWidget(QLabel("Version 0.1.0 · Local-first file protection"))
        about_layout.addWidget(QLabel("Your files and passwords are processed on this device."))
        layout.addWidget(about)
        layout.addStretch()
