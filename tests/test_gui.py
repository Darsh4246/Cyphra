"""Automated tests for Cyphra GUI workflows and components."""

from __future__ import annotations

from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from cyphra_gui.core_adapter import CryptoAdapter
from cyphra_gui.main_window import MainWindow
from cyphra_gui.pages import OperationPage
from cyphra_gui.widgets import FilePill, PasswordField, StepProgressHeader


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_decrypt_mode_has_no_generator_button(qapp):
    adapter = CryptoAdapter()
    page = OperationPage(adapter, mode="decrypt")
    
    # Verify password field is in decrypt mode
    assert page.password.mode == "decrypt"
    assert page.password.strength.isHidden()
    
    # Verify that in decrypt mode, no generator button exists in the configure page
    buttons = page.stack.widget(1).findChildren(QPushButton)
    generator_buttons = [b for b in buttons if "generate" in b.text().lower() or b.objectName() == "generatorButton"]
    assert len(generator_buttons) == 0, "Decrypt mode must not offer password generation"


def test_encrypt_mode_has_generator_button(qapp):
    adapter = CryptoAdapter()
    page = OperationPage(adapter, mode="encrypt")
    
    # Verify password field is in encrypt mode
    assert page.password.mode == "encrypt"
    assert not page.password.strength.isHidden()
    
    # Verify generator button exists in encrypt mode
    buttons = page.stack.widget(1).findChildren(QPushButton)
    generator_buttons = [b for b in buttons if "generate" in b.text().lower() or b.objectName() == "generatorButton"]
    assert len(generator_buttons) == 1, "Encrypt mode should provide a password generator button"
    
    # Test generating password
    assert page.password.text() == ""
    page._generate_password()
    assert len(page.password.text()) >= 16


def test_operation_stepper_progression(qapp):
    adapter = CryptoAdapter()
    page = OperationPage(adapter, mode="decrypt")
    
    assert page.stepper._current_step == 0
    page._show_step(1)
    assert page.stepper._current_step == 1
    page._show_step(2)
    assert page.stepper._current_step == 2
    page._show_step(3)
    assert page.stepper._current_step == 3
    page._show_step(4)
    assert page.stepper._current_step == 3  # Clamped to step 4 indicator


def test_default_destination_naming(qapp):
    adapter = CryptoAdapter()
    dec_page = OperationPage(adapter, mode="decrypt")
    enc_page = OperationPage(adapter, mode="encrypt")
    
    # Encrypt regular file
    assert enc_page._default_destination("doc.txt").endswith("doc.txt.cyphra")
    
    # Decrypt cyphra file
    assert dec_page._default_destination("doc.txt.cyphra").endswith("doc.txt")
    
    # Decrypt vault container
    assert dec_page._default_destination("photos.cyphra-vault").endswith("photos")


def test_file_pill_badges(qapp):
    pill1 = FilePill("test.cyphra")
    assert pill1._badge_type(Path("test.cyphra")) == "CYPHRA"
    
    pill2 = FilePill("archive.cyphra-vault")
    assert pill2._badge_type(Path("archive.cyphra-vault")) == "VAULT"
    
    pill3 = FilePill("document.pdf")
    assert pill3._badge_type(Path("document.pdf")) == "PDF"


def test_main_window_pages_switch(qapp):
    window = MainWindow()
    assert "home" in window.page_map
    assert "encrypt" in window.page_map
    assert "decrypt" in window.page_map
    assert "hash" in window.page_map
    assert "settings" in window.page_map
    
    for key in ("home", "encrypt", "decrypt", "hash", "settings"):
        window.show_page(key)
        assert window.pages.currentWidget() == window.page_map[key]


def test_operation_page_result_navigation(qapp):
    adapter = CryptoAdapter()
    page = OperationPage(adapter, mode="decrypt")
    page._files_selected(["test.cyphra"])
    page._to_configure()
    assert page.stack.currentIndex() == 1

    # Simulate authentication/password failure
    page._failure("Decryption failed: password is incorrect or container is corrupt")
    assert page.stack.currentIndex() == 4
    assert page.result_title.text() == "Decryption Failed"
    assert not page.retry_password_btn.isHidden()

    # 1. Clicking retry password returns to step 1 with files preserved
    page.retry_password_btn.click()
    assert page.stack.currentIndex() == 1
    assert page.files == ["test.cyphra"]

    # Go back to failure state
    page._failure("Decryption failed: password is incorrect or container is corrupt")
    assert page.stack.currentIndex() == 4

    # 2. Clicking 'back to upload' returns to step 0
    page.back_to_upload_btn.click()
    assert page.stack.currentIndex() == 0
    assert len(page.files) == 0

    # 3. Clicking stepper 0 from any step returns to step 0
    page._files_selected(["test.cyphra"])
    page._show_step(2)
    assert page.stack.currentIndex() == 2
    page._on_stepper_clicked(0)
    assert page.stack.currentIndex() == 0


def test_main_window_auto_resets_finished_operation(qapp):
    window = MainWindow()
    dec_page = window.page_map["decrypt"]
    dec_page._files_selected(["test.cyphra"])
    dec_page._show_step(4)
    assert dec_page.stack.currentIndex() == 4

    # Re-navigating to decrypt automatically resets to step 0
    window.show_page("decrypt")
    assert dec_page.stack.currentIndex() == 0
    assert len(dec_page.files) == 0


def test_hash_page_multi_algorithms_and_hmac(qapp):
    from cyphra_gui.pages import HashPage
    import hmac, hashlib

    adapter = CryptoAdapter()
    page = HashPage(adapter)

    # 1. Check algorithms list
    items = [page.text_algorithm.itemText(i) for i in range(page.text_algorithm.count())]
    assert "SHA-256" in items
    assert "SHA-512" in items
    assert "SHA3-256" in items
    assert "BLAKE2b" in items
    assert "MD5" in items

    # 2. Test bare text hash calculation
    page.text_input.setPlainText("Hello Cyphra")
    page.text_algorithm.setCurrentText("SHA-256")
    page.text_key.setText("")
    page._hash_text()
    expected_sha256 = hashlib.sha256(b"Hello Cyphra").hexdigest()
    assert page.text_result.text() == expected_sha256

    # 3. Test HMAC text calculation with key
    secret_key = "MySecretKey"
    page.text_key.setText(secret_key)
    page._hash_text()
    expected_hmac = hmac.new(b"MySecretKey", b"Hello Cyphra", "sha256").hexdigest()
    assert page.text_result.text() == expected_hmac

    # 4. Test BLAKE2b hash
    page.text_key.setText("")
    page.text_algorithm.setCurrentText("BLAKE2b")
    page._hash_text()
    expected_blake = hashlib.blake2b(b"Hello Cyphra").hexdigest()
    assert page.text_result.text() == expected_blake


def test_encrypt_page_cipher_and_kdf_selection(qapp):
    adapter = CryptoAdapter()
    page = OperationPage(adapter, mode="encrypt")
    assert hasattr(page, "cipher_combo")
    assert hasattr(page, "kdf_combo")
    assert hasattr(page, "crypto_info_card")

    # Check available ciphers and KDFs
    cipher_items = [page.cipher_combo.itemText(i) for i in range(page.cipher_combo.count())]
    assert any("AES-256-GCM" in c for c in cipher_items)
    assert any("ChaCha20-Poly1305" in c for c in cipher_items)
    assert any("AES-256-GCM-SIV" in c for c in cipher_items)

    kdf_items = [page.kdf_combo.itemText(i) for i in range(page.kdf_combo.count())]
    assert any("Argon2id" in k for k in kdf_items)
    assert any("PBKDF2" in k for k in kdf_items)
    assert any("Scrypt" in k for k in kdf_items)

    # Test selection IDs
    page.cipher_combo.setCurrentIndex(1)
    assert page.get_cipher_id() == 1  # ChaCha20-Poly1305
    page.kdf_combo.setCurrentIndex(0)
    assert page.get_kdf_id() == 1  # Argon2id


def test_settings_page_controls_and_defaults(qapp):
    from cyphra_gui.pages import SettingsPage

    page = SettingsPage()
    assert hasattr(page, "def_cipher")
    assert hasattr(page, "def_kdf")
    assert hasattr(page, "def_hash")
    assert hasattr(page, "auto_copy")
    assert hasattr(page, "secure_shred")

    # Test reset defaults
    page.auto_copy.setChecked(True)
    page._reset_defaults()
    assert not page.auto_copy.isChecked()
    assert page.def_cipher.currentIndex() == 0


def test_decrypt_start_arguments_and_worker(qapp, monkeypatch, tmp_path):
    """Ensure decrypt mode starts without argument mismatch or unexpected keyword argument error."""
    adapter = CryptoAdapter()
    page = OperationPage(adapter, mode="decrypt")
    
    # Fake file
    fake_enc = tmp_path / "secret.txt.cyphra"
    fake_enc.write_bytes(b"dummy")
    
    called_args = {}
    def mock_decrypt(source, target, password, progress=None, cancel_event=None, **kwargs):
        called_args["source"] = source
        called_args["target"] = target
        called_args["password"] = password
        called_args["progress"] = progress
        called_args["cancel_event"] = cancel_event
        called_args["kwargs"] = kwargs
        return target

    monkeypatch.setattr(adapter, "decrypt_file", mock_decrypt)
    
    page._files_selected([str(fake_enc)])
    page.password.setText("SecretPassphrase123")
    page.destination = str(tmp_path / "secret.txt")
    
    # Run _start - worker should run without throwing argument errors
    page._start()
    page.worker.wait(5000)
    
    assert called_args["source"] == str(fake_enc)
    assert called_args["password"] == "SecretPassphrase123"
    assert "cipher_id" not in called_args["kwargs"]


def test_file_assoc_and_ico(qapp):
    """Ensure preferred icon path finds logo.ico and FilePill supports it."""
    from cyphra_gui.file_assoc import get_preferred_icon_path
    
    icon_path = get_preferred_icon_path()
    assert icon_path.exists()
    assert icon_path.suffix.lower() == ".ico"
    
    pill = FilePill("archive.cyphra")
    assert pill._badge_type(Path("archive.cyphra")) == "CYPHRA"


def test_vault_decrypt_creates_dedicated_folder(qapp, tmp_path):
    """Ensure decrypting a vault into a parent directory creates a dedicated folder for its files."""
    adapter = CryptoAdapter()
    
    # Create sample folder with files
    sample_dir = tmp_path / "my_documents"
    sample_dir.mkdir()
    (sample_dir / "notes.txt").write_text("Hello Cyphra", encoding="utf-8")
    (sample_dir / "report.pdf").write_bytes(b"%PDF-test")
    
    # Encrypt to vault
    vault_path = tmp_path / "my_documents.cyphra-vault"
    adapter.encrypt_file(sample_dir, vault_path, "VaultPass#123")
    assert vault_path.exists()
    
    # Decrypt targeting a clean extract parent folder
    extract_parent = tmp_path / "destination_directory"
    extract_parent.mkdir()
    
    # Extract into extract_parent
    result_dir = adapter.decrypt_file(vault_path, extract_parent, "VaultPass#123")
    
    # Must have created dedicated subfolder my_documents inside extract_parent!
    expected_subfolder = extract_parent / "my_documents"
    assert Path(result_dir) == expected_subfolder
    assert expected_subfolder.is_dir()
    assert (expected_subfolder / "notes.txt").exists()
    assert (expected_subfolder / "report.pdf").exists()
    
    # Ensure files are NOT loose inside extract_parent
    assert not (extract_parent / "notes.txt").exists()
    assert not (extract_parent / "report.pdf").exists()




