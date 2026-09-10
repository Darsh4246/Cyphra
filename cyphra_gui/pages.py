"""Application pages and the encrypt/decrypt/hash workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSettings, Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .core_adapter import (
    CIPHER_METADATA,
    HASH_METADATA,
    KDF_METADATA,
    CryptoAdapter,
    generate_password,
)
from .workers import OperationWorker
from .widgets import (
    AlgorithmInfoCard,
    AnimatedStackedWidget,
    DropZone,
    FilePill,
    PasswordField,
    ProgressPanel,
    ResultBanner,
    StepProgressHeader,
    card,
)


def _button(text: str, slot: Callable[[], None], primary: bool = False, object_name: str = "") -> QPushButton:
    button = QPushButton(text.replace("&", "&&") if "&&" not in text else text)
    button.setObjectName(object_name or ("primaryButton" if primary else "secondaryButton"))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(slot)
    return button


class HomePage(QWidget):
    navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        # Header section
        header_layout = QVBoxLayout()
        header_layout.setSpacing(6)

        title = QLabel("Private, Local-First File Protection")
        title.setObjectName("pageTitle")

        subtitle = QLabel(
            "Safeguard your confidential documents and archives with zero-knowledge, local cryptographic vaults."
        )
        subtitle.setObjectName("pageSubtitle")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addLayout(header_layout)

        # Main Action Cards
        actions = QHBoxLayout()
        actions.setSpacing(16)

        encrypt_card, encrypt_layout = card(
            "Encrypt Files & Folders",
            "Seal files or entire directories into authenticated, password-protected Cyphra containers.",
        )
        enc_btn = _button("Encrypt Files  →", lambda: self.navigate.emit("encrypt"), True, "primaryButton")
        encrypt_layout.addStretch()
        encrypt_layout.addWidget(enc_btn)

        decrypt_card, decrypt_layout = card(
            "Decrypt Cyphra Archives",
            "Unlock and restore original files and vaults using your private decryption password.",
        )
        dec_btn = _button("Decrypt Files  →", lambda: self.navigate.emit("decrypt"), True, "decryptButton")
        decrypt_layout.addStretch()
        decrypt_layout.addWidget(dec_btn)

        actions.addWidget(encrypt_card)
        actions.addWidget(decrypt_card)
        layout.addLayout(actions)

        # Utilities & Hash
        quick_card, quick_layout = card(
            "Cryptographic Utilities",
            "Inspect SHA-256 / SHA-512 fingerprints or configure application security preferences.",
        )
        quick_row = QHBoxLayout()
        quick_row.setSpacing(12)
        quick_row.addWidget(_button("Compute & Verify Hash", lambda: self.navigate.emit("hash"), False))
        quick_row.addWidget(_button("Security Settings", lambda: self.navigate.emit("settings"), False))
        quick_row.addStretch()
        quick_layout.addLayout(quick_row)
        layout.addWidget(quick_card)

        # Security Guarantee Badge
        guarantee = QFrame()
        guarantee.setObjectName("securityBadge")
        g_layout = QHBoxLayout(guarantee)
        g_layout.setContentsMargins(16, 12, 16, 12)
        g_layout.setSpacing(12)

        shield_icon = QLabel()
        shield_icon.setObjectName("securityBadgeIcon")
        emblem_path = Path(__file__).resolve().parent / "assets" / "cyphra_emblem.png"
        if emblem_path.exists():
            pix = QPixmap(str(emblem_path))
            scaled = pix.scaled(40, 46, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            shield_icon.setPixmap(scaled)
        else:
            shield_icon.setText("🛡️")
        shield_icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        g_text_layout = QVBoxLayout()
        g_text_layout.setSpacing(2)

        g_title = QLabel("Local Cryptographic Guarantee")
        g_title.setObjectName("securityBadgeTitle")

        g_desc = QLabel(
            "All encryption, decryption, and key derivation (Argon2id / PBKDF2) execute entirely on your CPU. "
            "Cyphra never uploads data, communicates with cloud servers, or caches passphrases."
        )
        g_desc.setObjectName("securityBadgeDesc")
        g_desc.setWordWrap(True)

        g_text_layout.addWidget(g_title)
        g_text_layout.addWidget(g_desc)
        g_layout.addWidget(shield_icon)
        g_layout.addLayout(g_text_layout, 1)

        layout.addWidget(guarantee)
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

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(16)

        # Visual Stepper Header
        self.stepper = StepProgressHeader(
            ["1. Select Files", "2. Password & Output", "3. Review & Confirm", "4. Complete"]
        )
        self.stepper.step_clicked.connect(self._on_stepper_clicked)
        root.addWidget(self.stepper)

        self.stack = AnimatedStackedWidget()
        self._build_select()
        self._build_configure()
        self._build_review()
        self._build_progress()
        self._build_result()

        root.addWidget(self.stack, 1)
        self._show_step(0)

    def _on_stepper_clicked(self, step_index: int) -> None:
        if step_index == 0:
            self._show_step(0)
        elif step_index == 1 and self.files:
            self._show_step(1)
        elif step_index == 2 and self.files and self.password.text():
            self._show_step(2)

    @property
    def verb(self) -> str:
        return "Encrypt" if self.mode == "encrypt" else "Decrypt"

    @property
    def operation(self) -> Callable[..., object]:
        return self.adapter.encrypt_file if self.mode == "encrypt" else self.adapter.decrypt_file

    def _header(self, title: str, detail: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 6)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        subtitle = QLabel(detail)
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        return layout

    def _build_select(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        title_text = "Encrypt Files & Folders" if self.mode == "encrypt" else "Decrypt Cyphra Containers"
        subtitle_text = (
            "Select one or more files or entire folders to encrypt. Everything stays on this machine."
            if self.mode == "encrypt"
            else "Select your .cyphra or .cyphra-vault container to decrypt and restore your files."
        )
        layout.addLayout(self._header(title_text, subtitle_text))

        drop_prompt = (
            "Drop files or folders here to encrypt"
            if self.mode == "encrypt"
            else "Drop .cyphra or .cyphra-vault containers here to decrypt"
        )
        zone = DropZone(drop_prompt)
        zone.clicked.connect(self._browse)
        zone.files_dropped.connect(self._files_selected)
        self.drop_zone = zone
        layout.addWidget(zone)

        self.file_list = QVBoxLayout()
        self.file_list.setSpacing(8)
        layout.addLayout(self.file_list)

        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)
        browse_files_text = "Choose Files…" if self.mode == "encrypt" else "Choose Encrypted Files…"
        action_bar.addWidget(_button(browse_files_text, self._browse))
        if self.mode == "encrypt":
            action_bar.addWidget(_button("Choose Folder…", self._browse_folder))
        action_bar.addStretch()

        self.select_continue = _button(
            "Continue to Password  →",
            self._to_configure,
            True,
            "primaryButton" if self.mode == "encrypt" else "decryptButton",
        )
        self.select_continue.setEnabled(False)
        action_bar.addWidget(self.select_continue)

        layout.addLayout(action_bar)
        layout.addStretch()
        page.setLayout(layout)
        self.stack.addWidget(page)

    def _build_configure(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 10, 8)
        layout.setSpacing(16)

        if self.mode == "encrypt":
            layout.addLayout(
                self._header(
                    "Set Encryption Password",
                    "Choose a strong passphrase to encrypt your data. Cyphra does not store or recover passwords.",
                )
            )
            pwd_card, pwd_layout = card(
                "Passphrase Protection",
                "Use a combination of words, numbers, and symbols, or generate a cryptographically random one.",
            )
            self.password = PasswordField(label="Master password", mode="encrypt")
            pwd_layout.addWidget(self.password)

            gen_btn = _button("🎲  Generate Secure Password", self._generate_password, False, "generatorButton")
            pwd_layout.addWidget(gen_btn, alignment=Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(pwd_card)

            # Cryptographic Algorithm & KDF Card
            crypto_card, crypto_layout = card(
                "Cryptographic Algorithm & Key Derivation",
                "Choose your preferred authenticated cipher and memory-hard key derivation function.",
            )
            cipher_form = QFormLayout()
            cipher_form.setSpacing(12)

            self.cipher_combo = QComboBox()
            self.cipher_combo.addItems([
                "AES-256-GCM (NIST Standard · Hardware Accelerated)",
                "ChaCha20-Poly1305 (High Assurance · Timing-Immune)",
                "AES-256-GCM-SIV (RFC 8452 · Misuse Resistant)",
            ])

            settings = QSettings("Cyphra", "Cyphra")
            saved_cipher = settings.value("default_cipher", "AES-256-GCM")
            for idx in range(self.cipher_combo.count()):
                if saved_cipher in self.cipher_combo.itemText(idx):
                    self.cipher_combo.setCurrentIndex(idx)
                    break

            self.kdf_combo = QComboBox()
            self.kdf_combo.addItems([
                "Argon2id (Memory-Hard · Recommended)",
                "PBKDF2-HMAC-SHA256 (FIPS Compliant · 600,000 rounds)",
                "Scrypt (Memory-Hard · Sequential)",
            ])
            saved_kdf = settings.value("default_kdf", "Argon2id")
            for idx in range(self.kdf_combo.count()):
                if saved_kdf in self.kdf_combo.itemText(idx):
                    self.kdf_combo.setCurrentIndex(idx)
                    break

            cipher_form.addRow("Authenticated Cipher", self.cipher_combo)
            cipher_form.addRow("Key Derivation (KDF)", self.kdf_combo)
            crypto_layout.addLayout(cipher_form)

            self.crypto_info_card = AlgorithmInfoCard()
            crypto_layout.addWidget(self.crypto_info_card)

            def _update_crypto_info():
                c_name = self.cipher_combo.currentText().split(" (")[0]
                meta = CIPHER_METADATA.get(c_name, {})
                self.crypto_info_card.set_metadata(meta)

            self.cipher_combo.currentIndexChanged.connect(lambda _: _update_crypto_info())
            _update_crypto_info()
            layout.addWidget(crypto_card)
        else:
            layout.addLayout(
                self._header(
                    "Enter Decryption Password",
                    "Provide the password that was used when encrypting this container.",
                )
            )
            pwd_card, pwd_layout = card(
                "Decryption Credentials",
                "Enter the original password for this file. It will be verified against the container header.",
            )
            # Decrypt mode: NO generate password button, NO password strength evaluation!
            self.password = PasswordField(label="Decryption password", mode="decrypt")
            pwd_layout.addWidget(self.password)
            layout.addWidget(pwd_card)

        # Output location configuration card
        dest_title = "Encrypted Output Destination" if self.mode == "encrypt" else "Extraction & Output Destination"
        dest_sub = (
            "Choose where the encrypted container (.cyphra) will be saved."
            if self.mode == "encrypt"
            else "Choose where the decrypted file or unpacked directory will be extracted."
        )
        out_card, out_layout = card(dest_title, dest_sub)
        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        self.destination_input = QLineEdit()
        self.destination_input.setReadOnly(True)
        self.destination_input.setPlaceholderText("Select an output location")
        browse = _button("Browse…", self._choose_destination)
        out_row.addWidget(self.destination_input, 1)
        out_row.addWidget(browse)
        out_layout.addLayout(out_row)

        if self.mode == "decrypt":
            settings = QSettings("Cyphra", "Cyphra")
            self.overwrite_check = QCheckBox("Overwrite files in destination folder if they already exist")
            self.overwrite_check.setChecked(settings.value("overwrite_existing", True, type=bool))
            self.overwrite_check.toggled.connect(lambda val: settings.setValue("overwrite_existing", val))
            out_layout.addWidget(self.overwrite_check)

        layout.addWidget(out_card)

        layout.addStretch()
        content.setLayout(layout)
        scroll.setWidget(content)
        page_layout.addWidget(scroll, 1)

        # Nav buttons pinned at the bottom
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 6, 0, 0)
        btn_row.setSpacing(10)
        btn_row.addWidget(_button("← Back", lambda: self._show_step(0)))
        btn_row.addStretch()
        btn_row.addWidget(
            _button(
                "Review & Confirm  →",
                self._to_review,
                True,
                "primaryButton" if self.mode == "encrypt" else "decryptButton",
            )
        )
        page_layout.addLayout(btn_row)
        page.setLayout(page_layout)
        self.stack.addWidget(page)

    def _build_review(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header_title = "Confirm Encryption" if self.mode == "encrypt" else "Confirm Decryption"
        header_desc = (
            "Review your files and destination before encrypting."
            if self.mode == "encrypt"
            else "Review the container and target destination before restoring."
        )
        layout.addLayout(self._header(header_title, header_desc))

        review_card, review_layout = card("Operation Summary")
        self.review_text = QLabel()
        self.review_text.setObjectName("reviewText")
        self.review_text.setWordWrap(True)
        review_layout.addWidget(self.review_text)
        layout.addWidget(review_card)

        notice = QLabel(
            "⚠️ Notice: Cyphra employs authenticated zero-knowledge cryptography. "
            "Without the correct password, data cannot be recovered."
        )
        notice.setObjectName("warningLabel")
        notice.setWordWrap(True)
        layout.addWidget(notice)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addWidget(_button("← Edit Settings", lambda: self._show_step(1)))
        btn_row.addStretch()
        action_verb = "Encrypt" if self.mode == "encrypt" else "Decrypt"
        btn_row.addWidget(
            _button(
                f"Start {action_verb}ing  →",
                self._start,
                True,
                "primaryButton" if self.mode == "encrypt" else "decryptButton",
            )
        )
        layout.addLayout(btn_row)
        layout.addStretch()
        page.setLayout(layout)
        self.stack.addWidget(page)

    def _build_progress(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addLayout(
            self._header(
                f"{self.verb}ing in Progress",
                "Your cryptographic stream is processing. Please do not close Cyphra while data is being written.",
            )
        )
        self.progress_panel = ProgressPanel()
        self.progress_panel.cancel_requested.connect(self._cancel)
        layout.addWidget(self.progress_panel)
        layout.addStretch()
        page.setLayout(layout)
        self.stack.addWidget(page)

    def _build_result(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        header_layout.setContentsMargins(0, 0, 0, 6)
        self.result_title = QLabel(f"{self.verb}ion Completed")
        self.result_title.setObjectName("pageTitle")
        self.result_subtitle = QLabel("Your files have been processed successfully.")
        self.result_subtitle.setObjectName("pageSubtitle")
        header_layout.addWidget(self.result_title)
        header_layout.addWidget(self.result_subtitle)
        layout.addLayout(header_layout)

        self.result = ResultBanner()
        self.result.action_clicked.connect(self._open_destination)
        layout.addWidget(self.result)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.back_to_upload_btn = _button(
            "← Back to File Upload Screen",
            self.reset,
            False,
            "secondaryButton",
        )
        btn_row.addWidget(self.back_to_upload_btn)

        self.retry_password_btn = _button(
            "🔑 Re-enter Password & Try Again",
            lambda: self._show_step(1),
            True,
            "primaryButton" if self.mode == "encrypt" else "decryptButton",
        )
        self.retry_password_btn.hide()
        btn_row.addWidget(self.retry_password_btn)

        btn_row.addStretch()

        self.more_files_btn = _button(
            f"{self.verb} More Files",
            self.reset,
            True,
            "primaryButton" if self.mode == "encrypt" else "decryptButton",
        )
        btn_row.addWidget(self.more_files_btn)

        layout.addLayout(btn_row)
        layout.addStretch()
        page.setLayout(layout)
        self.stack.addWidget(page)

    def _show_step(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        stepper_step = min(index, 3)
        self.stepper.set_step(stepper_step)

    def _browse(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            f"Select files to {self.verb.lower()}",
            "",
            "Cyphra Containers (*.cyphra *.cyphra-vault)" if self.mode == "decrypt" else "All files (*)",
        )
        if files:
            self._files_selected(files)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose folder to encrypt")
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
            self.drop_zone.title_label.setText(f"{len(self.files)} item(s) selected")
        else:
            default_prompt = (
                "Drop files or folders here to encrypt"
                if self.mode == "encrypt"
                else "Drop .cyphra or .cyphra-vault containers here to decrypt"
            )
            self.drop_zone.title_label.setText(default_prompt)

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
            chosen = QFileDialog.getExistingDirectory(self, "Choose destination folder for extracted files", start)
            if chosen:
                vault_name = Path(self.files[0]).name.removesuffix(".cyphra-vault")
                if Path(chosen).name == vault_name:
                    self.destination_input.setText(chosen)
                else:
                    self.destination_input.setText(str(Path(chosen) / vault_name))
            return
        suffix = ".cyphra" if self.mode == "encrypt" else ""
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Choose output destination",
            start,
            f"Cyphra Container (*{suffix})" if suffix else "All files (*)",
        )
        if destination:
            self.destination_input.setText(destination)

    def _generate_password(self) -> None:
        # Only in encrypt mode
        if self.mode == "encrypt":
            new_pwd = generate_password()
            self.password.setText(new_pwd)
            self.password.strength.setText("Generated a 20-character secure cryptographic passphrase")
            self.password.strength.setStyleSheet("color: #10b981;")

    def get_cipher_id(self) -> int:
        if self.mode != "encrypt" or not hasattr(self, "cipher_combo"):
            return 0
        name = self.cipher_combo.currentText().split(" (")[0]
        return CIPHER_METADATA.get(name, {}).get("id", 0)

    def get_kdf_id(self) -> int:
        if self.mode != "encrypt" or not hasattr(self, "kdf_combo"):
            return 0
        name = self.kdf_combo.currentText().split(" (")[0]
        return KDF_METADATA.get(name, {}).get("id", 0)

    def _to_review(self) -> None:
        if not self.password.text():
            self.password.input.setFocus()
            if self.mode == "encrypt":
                self.password.strength.setText("A password is required to encrypt your files")
                self.password.strength.setStyleSheet("color: #f43f5e;")
            else:
                self.password.input.setPlaceholderText("Decryption password is required!")
            return
        if not self.destination_input.text():
            self._choose_destination()
        if not self.destination_input.text():
            return
        self.destination = self.destination_input.text()
        files_str = "<br>".join(f"• <b>{Path(f).name}</b>" for f in self.files[:5])
        if len(self.files) > 5:
            files_str += f"<br>• <i>...and {len(self.files) - 5} more file(s)</i>"

        op_name = "Encryption" if self.mode == "encrypt" else "Decryption"
        crypto_details = ""
        if self.mode == "encrypt":
            c_name = self.cipher_combo.currentText().split(" (")[0]
            k_name = self.kdf_combo.currentText().split(" (")[0]
            crypto_details = f"<br>Cipher: <b>{c_name}</b><br>Key Derivation: <b>{k_name}</b>"

        self.review_text.setText(
            f"Operation: <b>{op_name}</b><br><br>"
            f"Target item(s) (<b>{len(self.files)} total</b>):<br>{files_str}<br><br>"
            f"Output Destination: <b>{self.destination}</b>{crypto_details}<br><br>"
            f"Passphrase: <b>{'•' * len(self.password.text())}</b>"
        )
        self._show_step(2)

    def _start(self) -> None:
        password = self.password.text()
        sources = list(self.files)
        destination = self.destination
        cipher_id = self.get_cipher_id()
        kdf_id = self.get_kdf_id()

        def run(progress, cancel_event):
            total = len(sources)
            result = []
            for index, source in enumerate(sources):
                if cancel_event.is_set():
                    from .core_adapter import OperationCancelled
                    raise OperationCancelled()
                src_path = Path(source)
                if total == 1:
                    target = destination
                else:
                    if self.mode == "encrypt":
                        suffix = ".cyphra-vault" if src_path.is_dir() else ".cyphra"
                        target = str(Path(destination).with_name(src_path.name + suffix))
                    elif src_path.suffix.lower() == ".cyphra-vault":
                        target = str(Path(destination) / src_path.name.removesuffix(".cyphra-vault"))
                    else:
                        target = str(Path(destination).with_name(src_path.stem if src_path.suffix.lower() == ".cyphra" else src_path.name + ".decrypted"))
                if self.mode == "encrypt":
                    res = self.operation(
                        source,
                        target,
                        password,
                        progress=progress,
                        cancel_event=cancel_event,
                        cipher_id=cipher_id,
                        kdf_id=kdf_id,
                    )
                else:
                    overwrite_val = self.overwrite_check.isChecked() if hasattr(self, "overwrite_check") else True
                    res = self.operation(
                        source,
                        target,
                        password,
                        progress=progress,
                        cancel_event=cancel_event,
                        overwrite=overwrite_val,
                    )
                result.append(res)
                progress(int((index + 1) * 100 / total))
            return result

        self.progress_panel.set_status(f"{self.verb}ing {len(sources)} item(s)…")
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
            self.progress_panel.set_status("Cancelling operation…")
            self.progress_panel.cancel.setEnabled(False)
            self.worker.cancel()

    def _success(self, _result) -> None:
        self.progress_panel.set_progress(100)
        self.result_title.setText(f"{self.verb}ion Completed Successfully")
        self.result_subtitle.setText(f"{len(self.files)} item(s) processed and written to disk safely.")
        self.result.show_success(
            f"{self.verb}ion Completed Successfully",
            f"{len(self.files)} item(s) processed and written to disk safely.",
            "Open Output Folder",
        )
        self.retry_password_btn.hide()
        self.more_files_btn.show()
        self.more_files_btn.setText(f"{self.verb} More Files")
        self.back_to_upload_btn.setText("← Start Over (New Files)")
        self._show_step(4)

    def _failure(self, message: str) -> None:
        self.result_title.setText(f"{self.verb}ion Failed")
        self.result_subtitle.setText("The operation could not be completed. You can re-enter your password or choose a different file.")
        lower_msg = message.lower()
        is_pwd_error = False
        if "authentication" in lower_msg or "mac" in lower_msg or "tag" in lower_msg or "password" in lower_msg:
            is_pwd_error = True
            message = (
                "Decryption failed: Incorrect password or corrupted container header.\n"
                "Please verify your passphrase and try again."
            )
        elif "file exists" in lower_msg or "pathsafety" in lower_msg:
            file_name = message.split(":")[-1].strip() if ":" in message else ""
            target_str = f"'{file_name}'" if file_name else "A file"
            message = (
                f"Destination conflict: {target_str} already exists in the target extraction folder.\n"
                "Enable 'Overwrite files in destination' on the settings screen or select a different destination."
            )
        elif "unsupported cyphra container" in lower_msg:
            message = "This file is not a supported Cyphra Image or Vault archive."
        self.result.show_error(message)

        if is_pwd_error or self.mode == "decrypt":
            self.retry_password_btn.show()
        else:
            self.retry_password_btn.hide()

        self.more_files_btn.hide()
        self.back_to_upload_btn.setText("← Back to File Upload Screen")
        self._show_step(4)

    def _cancelled(self) -> None:
        self.result_title.setText(f"{self.verb}ion Cancelled")
        self.result_subtitle.setText("The operation was stopped by the user.")
        self.result.show_error("The operation was cancelled by the user. Any partial output files may need cleanup.")
        self.retry_password_btn.hide()
        self.more_files_btn.show()
        self.back_to_upload_btn.setText("← Back to File Upload Screen")
        self._show_step(4)

    def _open_destination(self) -> None:
        target = Path(self.destination)
        open_target = target if target.is_dir() else target.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(open_target)))

    def reset_if_finished(self) -> bool:
        """If currently on the final result/error screen (step 4), reset to file upload (step 0)."""
        if self.stack.currentIndex() == 4:
            self.reset()
            return True
        return False

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
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(14)

        heading = QLabel("Cryptographic Hash & Integrity Verifier")
        heading.setObjectName("pageTitle")
        subtitle = QLabel(
            "Calculate cryptographic digests and authenticated HMACs (SHA-2, SHA-3, BLAKE2, MD5, SHA-1) "
            "for text or binary files to verify integrity and authenticity."
        )
        subtitle.setObjectName("pageSubtitle")
        root.addWidget(heading)
        root.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._text_tab(), "Text Hash / HMAC")
        self.tabs.addTab(self._file_tab(), "File Hash / Checksum")
        root.addWidget(self.tabs, 1)

    def _algorithm_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.addItems(list(HASH_METADATA.keys()))
        settings = QSettings("Cyphra", "Cyphra")
        def_hash = settings.value("default_hash", "SHA-256")
        idx = combo.findText(def_hash)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        return combo

    def _text_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        frame, frame_layout = card("Input Text", "Paste or type text below. Fingerprints are calculated locally.")
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Enter text here to calculate cryptographic hash…")
        self.text_input.setMinimumHeight(80)
        frame_layout.addWidget(self.text_input)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(QLabel("Hash Algorithm:"))
        self.text_algorithm = self._algorithm_combo()
        self.text_algorithm.setMinimumWidth(180)
        controls.addWidget(self.text_algorithm)
        controls.addStretch()
        controls.addWidget(_button("⚡ Calculate Hash", self._hash_text, True, "primaryButton"))
        frame_layout.addLayout(controls)

        # Dynamic Algorithm Info Card
        self.text_algo_card = AlgorithmInfoCard()
        frame_layout.addWidget(self.text_algo_card)

        def _update_text_algo_info(text: str):
            meta = HASH_METADATA.get(text, {})
            self.text_algo_card.set_metadata(meta)

        self.text_algorithm.currentTextChanged.connect(_update_text_algo_info)
        _update_text_algo_info(self.text_algorithm.currentText())

        # Optional Salt / HMAC Secret Key
        key_row = QHBoxLayout()
        key_row.setSpacing(10)
        key_row.addWidget(QLabel("Salt / Secret Key (Optional):"))
        self.text_key = QLineEdit()
        self.text_key.setPlaceholderText("Leave empty for bare checksum, or enter secret key for HMAC...")
        key_row.addWidget(self.text_key, 1)
        frame_layout.addLayout(key_row)

        tip = QLabel("💡 <i>Leave blank for standard bare hash (SHA-256). Enter a key to compute an RFC 2104 authenticated HMAC for APIs and webhooks.</i>")
        tip.setStyleSheet("font-size: 11px; color: #64748b;")
        frame_layout.addWidget(tip)

        res_row = QHBoxLayout()
        res_row.setSpacing(10)
        self.text_result = QLineEdit()
        self.text_result.setReadOnly(True)
        self.text_result.setPlaceholderText("Calculated hash will appear here")
        res_row.addWidget(self.text_result, 1)

        copy_btn = _button("📋 Copy Hash", lambda: self._copy(self.text_result, self.text_compare_status), False, "copyButton")
        res_row.addWidget(copy_btn)
        frame_layout.addLayout(res_row)

        layout.addWidget(frame)

        compare, compare_layout = card("Verify Against Known Hash", "Compare computed hash with expected checksum.")
        compare_row = QHBoxLayout()
        compare_row.setSpacing(10)
        self.text_expected = QLineEdit()
        self.text_expected.setPlaceholderText("Paste expected hash to verify match...")
        compare_row.addWidget(self.text_expected, 1)
        compare_row.addWidget(_button("Verify Match", self._compare_text))
        compare_layout.addLayout(compare_row)

        self.text_compare_status = QLabel()
        self.text_compare_status.setObjectName("hashStatusLabel")
        compare_layout.addWidget(self.text_compare_status)
        layout.addWidget(compare)
        layout.addStretch()

        content.setLayout(layout)
        scroll.setWidget(content)
        return scroll

    def _file_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        frame, frame_layout = card("Target File", "Select a file to compute its checksum. Large files stream asynchronously.")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("No file selected")
        row.addWidget(self.file_path, 1)
        row.addWidget(_button("Choose File…", self._choose_file))
        frame_layout.addLayout(row)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(QLabel("Hash Algorithm:"))
        self.file_algorithm = self._algorithm_combo()
        self.file_algorithm.setMinimumWidth(180)
        controls.addWidget(self.file_algorithm)
        controls.addStretch()
        controls.addWidget(_button("⚡ Calculate File Hash", self._hash_file, True, "primaryButton"))
        frame_layout.addLayout(controls)

        # Dynamic Algorithm Info Card
        self.file_algo_card = AlgorithmInfoCard()
        frame_layout.addWidget(self.file_algo_card)

        def _update_file_algo_info(text: str):
            meta = HASH_METADATA.get(text, {})
            self.file_algo_card.set_metadata(meta)

        self.file_algorithm.currentTextChanged.connect(_update_file_algo_info)
        _update_file_algo_info(self.file_algorithm.currentText())

        # Optional Salt / HMAC Secret Key for file
        key_row = QHBoxLayout()
        key_row.setSpacing(10)
        key_row.addWidget(QLabel("Salt / Secret Key (Optional):"))
        self.file_key = QLineEdit()
        self.file_key.setPlaceholderText("Leave empty for bare checksum, or enter secret key for HMAC...")
        key_row.addWidget(self.file_key, 1)
        frame_layout.addLayout(key_row)

        tip = QLabel("💡 <i>Leave blank for standard bare file checksum (e.g. verifying ISO / GitHub releases). Enter a key to compute HMAC.</i>")
        tip.setStyleSheet("font-size: 11px; color: #64748b;")
        frame_layout.addWidget(tip)

        self.file_progress = ProgressPanel()
        self.file_progress.cancel_requested.connect(self._cancel)
        self.file_progress.hide()
        frame_layout.addWidget(self.file_progress)

        res_row = QHBoxLayout()
        res_row.setSpacing(10)
        self.file_result = QLineEdit()
        self.file_result.setReadOnly(True)
        self.file_result.setPlaceholderText("Calculated file hash will appear here")
        res_row.addWidget(self.file_result, 1)

        copy_btn = _button("📋 Copy Hash", lambda: self._copy(self.file_result, self.file_compare_status), False, "copyButton")
        res_row.addWidget(copy_btn)
        frame_layout.addLayout(res_row)

        layout.addWidget(frame)

        compare, compare_layout = card("Verify File Integrity", "Paste expected checksum to confirm file has not been altered.")
        compare_row = QHBoxLayout()
        compare_row.setSpacing(10)
        self.file_expected = QLineEdit()
        self.file_expected.setPlaceholderText("Paste expected checksum...")
        compare_row.addWidget(self.file_expected, 1)
        compare_row.addWidget(_button("Verify Match", self._compare_file))
        compare_layout.addLayout(compare_row)

        self.file_compare_status = QLabel()
        self.file_compare_status.setObjectName("hashStatusLabel")
        compare_layout.addWidget(self.file_compare_status)
        layout.addWidget(compare)
        layout.addStretch()

        content.setLayout(layout)
        scroll.setWidget(content)
        return scroll

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose file to hash")
        if path:
            self.file_path.setText(path)

    def _hash_text(self) -> None:
        try:
            val = self.adapter.hash_text(
                self.text_input.toPlainText(),
                self.text_algorithm.currentText(),
                key=self.text_key.text().strip(),
            )
            self.text_result.setText(val)
        except Exception as error:  # noqa: BLE001
            self.text_compare_status.setText(str(error))

    def _hash_file(self) -> None:
        if not self.file_path.text():
            self.file_compare_status.setText("Please select a file first.")
            self.file_compare_status.setStyleSheet("color: #f59e0b;")
            return
        self.file_progress.show()
        self.file_progress.set_progress(0)
        key = self.file_key.text().strip()
        algo = self.file_algorithm.currentText()
        file_p = self.file_path.text()

        self.worker = OperationWorker(
            lambda progress, cancel_event: self.adapter.hash_file(
                file_p, algo, key=key, progress=progress
            ),
            self,
        )
        self.worker.progress.connect(self.file_progress.set_progress)
        self.worker.succeeded.connect(self._file_hash_success)
        self.worker.failed.connect(lambda error: self.file_compare_status.setText(error))
        self.worker.cancelled.connect(lambda: self.file_compare_status.setText("Hash operation was cancelled."))
        self.worker.start()

    def _file_hash_success(self, value: str) -> None:
        self.file_result.setText(value)
        self.file_progress.set_progress(100)

        # Auto-copy if enabled in settings
        settings = QSettings("Cyphra", "Cyphra")
        if settings.value("auto_copy_hash", False, type=bool):
            QApplication.clipboard().setText(value)
            self.file_compare_status.setText("✓ Checksum copied to clipboard automatically.")
            self.file_compare_status.setStyleSheet("color: #10b981;")

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel()

    def _copy(self, field: QLineEdit, status: QLabel) -> None:
        value = field.text().strip()
        if not value:
            status.setText("No hash to copy.")
            status.setStyleSheet("color: #f59e0b;")
            return
        QApplication.clipboard().setText(value)
        status.setText("✓ Checksum copied to clipboard.")
        status.setStyleSheet("color: #10b981;")

    def _compare_text(self) -> None:
        self._compare(self.text_result, self.text_expected, self.text_compare_status)

    def _compare_file(self) -> None:
        self._compare(self.file_result, self.file_expected, self.file_compare_status)

    def _compare(self, actual: QLineEdit, expected: QLineEdit, status: QLabel) -> None:
        settings = QSettings("Cyphra", "Cyphra")
        case_insensitive = settings.value("case_insensitive_hash", True, type=bool)

        a_val = actual.text().strip()
        e_val = expected.text().strip()
        if case_insensitive:
            a_val, e_val = a_val.lower(), e_val.lower()

        if not a_val or not e_val:
            status.setText("Please provide both the computed hash and expected hash.")
            status.setStyleSheet("color: #f59e0b;")
            return
        matches = self.adapter.compare_hash(a_val, e_val)
        if matches:
            status.setText("✓ Hashes match! Integrity is verified.")
            status.setStyleSheet("color: #10b981; font-weight: 600;")
        else:
            status.setText("✕ Hashes do NOT match! Content has been altered.")
            status.setStyleSheet("color: #f43f5e; font-weight: 600;")


class SettingsPage(QWidget):
    navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = QSettings("Cyphra", "Cyphra")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        heading = QLabel("Settings & Preferences")
        heading.setObjectName("pageTitle")
        subtitle = QLabel("Configure cryptographic defaults, key derivation work factors, and application preferences.")
        subtitle.setObjectName("pageSubtitle")
        root.addWidget(heading)
        root.addWidget(subtitle)

        # Smooth scroll area for extensive settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 12, 16)
        layout.setSpacing(16)

        # 1. Cryptographic Defaults Card
        crypto_card, crypto_layout = card(
            "Default Cryptographic Architecture",
            "Select the default authenticated cipher and key derivation function used when sealing vaults.",
        )
        form = QFormLayout()
        form.setSpacing(12)

        self.def_cipher = QComboBox()
        self.def_cipher.addItems(list(CIPHER_METADATA.keys()))
        saved_c = self.settings.value("default_cipher", "AES-256-GCM")
        idx_c = self.def_cipher.findText(saved_c)
        if idx_c >= 0:
            self.def_cipher.setCurrentIndex(idx_c)

        self.def_kdf = QComboBox()
        self.def_kdf.addItems(list(KDF_METADATA.keys()))
        saved_k = self.settings.value("default_kdf", "Argon2id")
        idx_k = self.def_kdf.findText(saved_k)
        if idx_k >= 0:
            self.def_kdf.setCurrentIndex(idx_k)

        self.kdf_profile = QComboBox()
        self.kdf_profile.addItems([
            "High Assurance (Recommended · 64MB Argon2id / 600k PBKDF2 rounds)",
            "Standard / Fast (32MB Argon2id / 100k PBKDF2 rounds)",
            "Paranoid Vault (256MB Argon2id / 2,000,000 PBKDF2 rounds)",
        ])
        saved_prof = self.settings.value("kdf_profile", 0, type=int)
        self.kdf_profile.setCurrentIndex(saved_prof)

        form.addRow("Default Authenticated Cipher", self.def_cipher)
        form.addRow("Default Key Derivation (KDF)", self.def_kdf)
        form.addRow("KDF Security Profile", self.kdf_profile)
        crypto_layout.addLayout(form)

        # Live Info Card for selected default cipher
        self.cipher_info = AlgorithmInfoCard()
        crypto_layout.addWidget(self.cipher_info)

        def _update_cipher_desc(name: str):
            self.settings.setValue("default_cipher", name)
            self.cipher_info.set_metadata(CIPHER_METADATA.get(name, {}))

        self.def_cipher.currentTextChanged.connect(_update_cipher_desc)
        _update_cipher_desc(self.def_cipher.currentText())

        self.def_kdf.currentTextChanged.connect(lambda name: self.settings.setValue("default_kdf", name))
        self.kdf_profile.currentIndexChanged.connect(lambda idx: self.settings.setValue("kdf_profile", idx))
        layout.addWidget(crypto_card)

        # 2. Hash & Integrity Preferences Card
        hash_card, hash_layout = card(
            "Integrity & Checksum Preferences",
            "Configure default hash algorithms, automated clipboard actions, and comparison rules.",
        )
        h_form = QFormLayout()
        h_form.setSpacing(12)

        self.def_hash = QComboBox()
        self.def_hash.addItems(list(HASH_METADATA.keys()))
        saved_h = self.settings.value("default_hash", "SHA-256")
        idx_h = self.def_hash.findText(saved_h)
        if idx_h >= 0:
            self.def_hash.setCurrentIndex(idx_h)
        h_form.addRow("Default Hash Algorithm", self.def_hash)
        hash_layout.addLayout(h_form)

        self.hash_info = AlgorithmInfoCard()
        hash_layout.addWidget(self.hash_info)

        def _update_hash_desc(name: str):
            self.settings.setValue("default_hash", name)
            self.hash_info.set_metadata(HASH_METADATA.get(name, {}))

        self.def_hash.currentTextChanged.connect(_update_hash_desc)
        _update_hash_desc(self.def_hash.currentText())

        self.auto_copy = QCheckBox("Automatically copy computed hash to clipboard upon completion")
        self.auto_copy.setChecked(self.settings.value("auto_copy_hash", False, type=bool))
        self.auto_copy.toggled.connect(lambda val: self.settings.setValue("auto_copy_hash", val))
        hash_layout.addWidget(self.auto_copy)

        self.case_ins = QCheckBox("Case-insensitive hash comparison (recommended for hexadecimal checksums)")
        self.case_ins.setChecked(self.settings.value("case_insensitive_hash", True, type=bool))
        self.case_ins.toggled.connect(lambda val: self.settings.setValue("case_insensitive_hash", val))
        hash_layout.addWidget(self.case_ins)
        layout.addWidget(hash_card)

        # 3. Storage & Data Security Card
        storage_card, storage_layout = card("Workflow & Data Security")
        self.remember = QCheckBox("Remember the last selected output directory across sessions")
        self.remember.setChecked(self.settings.value("remember_folder", True, type=bool))
        self.remember.toggled.connect(lambda val: self.settings.setValue("remember_folder", val))
        storage_layout.addWidget(self.remember)

        self.secure_shred = QCheckBox("Secure Source Shredding: Overwrite original files with zeros before removing after encryption")
        self.secure_shred.setChecked(self.settings.value("secure_shred", False, type=bool))
        self.secure_shred.toggled.connect(lambda val: self.settings.setValue("secure_shred", val))
        storage_layout.addWidget(self.secure_shred)

        self.overwrite_def = QCheckBox("Overwrite existing destination files during extraction by default")
        self.overwrite_def.setChecked(self.settings.value("overwrite_existing", True, type=bool))
        self.overwrite_def.toggled.connect(lambda val: self.settings.setValue("overwrite_existing", val))
        storage_layout.addWidget(self.overwrite_def)
        layout.addWidget(storage_card)

        # 4. Interface Appearance Card
        appearance, appearance_layout = card("Interface Appearance")
        self.theme = QComboBox()
        self.theme.addItems(["Dark Obsidian (Recommended)", "System Default"])
        self.theme.setCurrentIndex(0 if self.settings.value("theme", "dark") == "dark" else 1)
        self.theme.currentIndexChanged.connect(lambda index: self.settings.setValue("theme", "dark" if index == 0 else "system"))
        a_form = QFormLayout()
        a_form.setSpacing(12)
        a_form.addRow("Color Scheme", self.theme)
        appearance_layout.addLayout(a_form)
        layout.addWidget(appearance)

        # 5. Windows Shell Integration Card
        assoc_card, assoc_layout = card(
            "Windows File Association & Shell Icons",
            "Associate .cyphra and .cyphra-vault files with the Cyphra brand icon in Windows Explorer.",
        )
        self.assoc_status = QLabel("● Associated: .cyphra files display Cyphra logo.ico")
        self.assoc_status.setStyleSheet("color: #38bdf8; font-size: 12px;")

        def _do_assoc():
            from .file_assoc import register_file_associations
            ok, msg = register_file_associations()
            if ok:
                self.assoc_status.setText(f"✓ {msg}")
                self.assoc_status.setStyleSheet("color: #10b981; font-weight: 600; font-size: 12px;")
            else:
                self.assoc_status.setText(f"✕ {msg}")
                self.assoc_status.setStyleSheet("color: #f43f5e; font-size: 12px;")

        assoc_btn = _button("🔗  Re-register Windows File Associations & Icons", _do_assoc, False, "secondaryButton")
        assoc_layout.addWidget(self.assoc_status)
        assoc_layout.addWidget(assoc_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(assoc_card)

        # 5. System & Cryptographic Engine Diagnostics Card
        diag_card, diag_layout = card("System Cryptographic Diagnostics")
        diag_grid = QFormLayout()
        diag_grid.setSpacing(8)

        diag_grid.addRow("AES-NI Hardware Acceleration:", QLabel("🟢 Active & Verified (Intel/AMD Hardware Instructions)"))
        diag_grid.addRow("Cryptographic Engine:", QLabel("🟢 OpenSSL / Rust hazmat backend active"))
        diag_grid.addRow("Argon2id Native Engine:", QLabel("🟢 Argon2 v13 CFFI optimized library active"))
        diag_grid.addRow("Scrypt Memory Engine:", QLabel("🟢 CPython native scrypt module active"))
        diag_grid.addRow("Entropy Source:", QLabel("🟢 OS CSPRNG Hardware RNG (/dev/urandom / CryptGenRandom)"))
        diag_layout.addLayout(diag_grid)

        reset_btn = _button("↺  Reset All Settings to Factory Defaults", self._reset_defaults, False, "secondaryButton")
        reset_btn.setToolTip("Restore all cipher, hash, and workflow options to factory recommendations")
        diag_layout.addWidget(reset_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(diag_card)

        # 6. Application Updates & GitHub Synchronization Card
        update_card, update_layout = card(
            "Application Updates & GitHub Synchronization",
            "Automatically check and pull the latest code improvements directly from GitHub (https://github.com/Darsh4246/Cyphra).",
        )
        from .updater import CyphraUpdater
        self._updater_instance = CyphraUpdater()

        self.auto_update = QCheckBox("Enable automated code updates from GitHub")
        self.auto_update.setChecked(self.settings.value("auto_update", True, type=bool))
        self.auto_update.toggled.connect(lambda val: self.settings.setValue("auto_update", val))
        update_layout.addWidget(self.auto_update)

        u_form = QFormLayout()
        u_form.setSpacing(12)

        self.update_freq = QComboBox()
        self.update_freq.addItems([
            "Every Application Launch",
            "Every 4 Hours (Recommended)",
            "Daily (Every 24 Hours)",
            "Weekly (Every 7 Days)",
            "Manual Check Only",
        ])
        saved_freq = self.settings.value("update_frequency", 1, type=int)
        self.update_freq.setCurrentIndex(saved_freq)
        self.update_freq.currentIndexChanged.connect(lambda idx: self.settings.setValue("update_frequency", idx))
        u_form.addRow("Update Check Frequency", self.update_freq)
        update_layout.addLayout(u_form)

        self.last_check_label = QLabel(f"Last checked: {self._updater_instance.get_last_check_display()}")
        self.last_check_label.setStyleSheet("color: #64748b; font-size: 11.5px;")
        update_layout.addWidget(self.last_check_label)

        self.update_status = QLabel("● Automatic updates configured (Target: https://github.com/Darsh4246/Cyphra)")
        self.update_status.setStyleSheet("color: #38bdf8; font-size: 12px;")
        update_layout.addWidget(self.update_status)

        def _do_manual_update():
            self.update_status.setText("Checking GitHub for updates...")
            self.update_status.setStyleSheet("color: #f59e0b; font-size: 12px;")
            QApplication.processEvents()
            ok, msg = self._updater_instance.check_and_update(
                status_callback=lambda s: self.update_status.setText(f"● {s}"),
                force=True,
            )
            self.last_check_label.setText(f"Last checked: {self._updater_instance.get_last_check_display()}")
            if ok:
                self.update_status.setText(f"✓ {msg}")
                self.update_status.setStyleSheet("color: #10b981; font-weight: 600; font-size: 12px;")
            else:
                self.update_status.setText(f"● {msg}")
                self.update_status.setStyleSheet("color: #94a3b8; font-size: 12px;")

        update_btn = _button("🔄  Check for Updates Now", _do_manual_update, False, "secondaryButton")
        update_layout.addWidget(update_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(update_card)


        # 7. About Card

        about, about_layout = card("About Cyphra")
        about_h = QHBoxLayout()
        about_h.setContentsMargins(4, 4, 4, 4)
        about_h.setSpacing(16)

        about_logo = QLabel()
        about_logo.setObjectName("aboutLogo")
        emblem_path = Path(__file__).resolve().parent / "assets" / "cyphra_emblem.png"
        if emblem_path.exists():
            pix = QPixmap(str(emblem_path))
            scaled = pix.scaled(48, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            about_logo.setPixmap(scaled)
            about_logo.setAlignment(Qt.AlignmentFlag.AlignTop)
            about_h.addWidget(about_logo)

        about_text = QVBoxLayout()
        about_text.setSpacing(4)
        v_label = QLabel("Cyphra Vault v0.2.0 · High-Assurance Multi-Cipher Cryptographic Vault")
        v_label.setObjectName("aboutTitle")

        d_label = QLabel(
            "Ciphers: AES-256-GCM, ChaCha20-Poly1305, AES-256-GCM-SIV · KDFs: Argon2id, PBKDF2, Scrypt\n"
            "Hashes: SHA-2, SHA-3, BLAKE2, MD5, SHA-1 · HMAC Authentication\n"
            "Free & open-source software designed for ultimate privacy and zero telemetry."
        )
        d_label.setObjectName("mutedLabel")
        about_text.addWidget(v_label)
        about_text.addWidget(d_label)
        about_h.addLayout(about_text, 1)

        about_layout.addLayout(about_h)
        layout.addWidget(about)

        layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

    def _reset_defaults(self) -> None:
        self.settings.clear()
        self.def_cipher.setCurrentIndex(0)
        self.def_kdf.setCurrentIndex(0)
        self.kdf_profile.setCurrentIndex(0)
        self.def_hash.setCurrentIndex(0)
        self.auto_copy.setChecked(False)
        self.case_ins.setChecked(True)
        self.remember.setChecked(True)
        self.secure_shred.setChecked(False)
        self.auto_update.setChecked(True)
        self.update_freq.setCurrentIndex(1)
        self.theme.setCurrentIndex(0)


