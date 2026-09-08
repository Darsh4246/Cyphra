"""Behavioural tests for the GUI-independent Cyphra container APIs."""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path

import pytest

from cyphra import (
    AuthenticationError,
    FormatError,
    Image,
    ImageInfo,
    PathSafetyError,
    Vault,
    VaultEntry,
)
from cyphra.crypto import derive_key, encrypt as encrypt_payload
from cyphra.format import (
    KIND_VAULT,
    EncryptStream,
)
from cyphra.paths import safe_relative_path
from cyphra.vault import (
    RECORD_DATA,
    RECORD_END,
    RECORD_END_FILE,
    RECORD_FILE,
    RECORD_METADATA,
)


PASSWORD = "correct horse battery staple"


def _malicious_vault(path: str, payload: bytes = b"secret") -> bytes:
    """Build a valid, authenticated vault containing one attacker path."""
    output = io.BytesIO()
    encoded_path = path.encode("utf-8")
    with EncryptStream(output, PASSWORD, KIND_VAULT, iterations=1) as stream:
        metadata = json.dumps({}).encode("utf-8")
        stream.write(bytes([RECORD_METADATA]) + struct.pack(">I", len(metadata)))
        stream.write(metadata)
        stream.write(
            bytes([RECORD_FILE])
            + struct.pack(">IQQ", len(encoded_path), len(payload), 0)
            + encoded_path
        )
        stream.write(bytes([RECORD_DATA]) + struct.pack(">I", len(payload)))
        stream.write(payload)
        stream.write(bytes([RECORD_END_FILE, RECORD_END]))
    return output.getvalue()


def test_key_derivation_is_deterministic_and_password_sensitive() -> None:
    salt = bytes(range(16))
    first = derive_key(PASSWORD, salt, iterations=1)
    assert first == derive_key(PASSWORD, salt, iterations=1)
    assert first != derive_key("a different password", salt, iterations=1)
    assert len(first) == 32


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        bytes(range(256)) * 4,
        "данные с emoji 🔐 and accents café".encode("utf-8"),
    ],
)
def test_image_bytes_round_trip(payload: bytes) -> None:
    metadata = {"original_name": "данные.bin", "empty": not payload}
    container = Image.encrypt(payload, password=PASSWORD, metadata=metadata)

    assert container != payload
    assert Image.decrypt(container, password=PASSWORD) == payload
    assert Image.inspect(container, password=PASSWORD) == ImageInfo(
        len(payload), metadata
    )


def test_image_file_round_trip_reports_progress(tmp_path: Path) -> None:
    source = tmp_path / "photo.bin"
    encrypted = tmp_path / "photo.cyphra"
    restored = tmp_path / "restored.bin"
    source.write_bytes(bytes(range(251)) * 100)
    progress: list[tuple[int, int]] = []

    result = Image.encrypt(
        source,
        encrypted,
        password=PASSWORD,
        metadata={"original_name": source.name},
        progress=lambda completed, total: progress.append((completed, total)),
    )
    assert isinstance(result, ImageInfo)
    assert result.size == source.stat().st_size
    assert progress and progress[-1] == (source.stat().st_size, source.stat().st_size)

    restored_info = Image.decrypt(encrypted, restored, password=PASSWORD)
    assert isinstance(restored_info, ImageInfo)
    assert restored_info.metadata == {"original_name": source.name}
    assert restored.read_bytes() == source.read_bytes()


def test_image_wrong_password_is_rejected() -> None:
    container = Image.encrypt(b"private", password=PASSWORD)

    with pytest.raises(AuthenticationError):
        Image.decrypt(container, password="wrong password")


def test_image_ciphertext_tampering_is_rejected() -> None:
    container = bytearray(Image.encrypt(b"private", password=PASSWORD))
    container[len(container) // 2] ^= 0x80

    with pytest.raises(AuthenticationError):
        Image.decrypt(bytes(container), password=PASSWORD)


@pytest.mark.parametrize(
    ("mutator", "error"),
    [
        (lambda value: b"BAD!" + value[4:], FormatError),
        (lambda value: value[:8] + b"\x02" + value[9:], FormatError),
        (lambda value: value[:20] + b"\xff" + value[21:], AuthenticationError),
    ],
)
def test_image_corrupt_headers_are_rejected(mutator, error) -> None:
    container = Image.encrypt(b"payload", password=PASSWORD)

    with pytest.raises(error):
        Image.decrypt(mutator(container), password=PASSWORD)


def test_image_truncated_tag_is_rejected() -> None:
    container = Image.encrypt(b"payload", password=PASSWORD)

    with pytest.raises(AuthenticationError):
        Image.decrypt(container[:-1], password=PASSWORD)


def test_vault_round_trip_preserves_nested_unicode_and_empty_directories(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    (source / "nested" / "空のフォルダ").mkdir(parents=True)
    (source / "nested" / "папка").mkdir()
    (source / "nested" / "папка" / "файл.txt").write_text(
        "Привет, vault 🔐\n", encoding="utf-8"
    )
    (source / "empty.bin").write_bytes(b"")
    container = Vault.create(
        source,
        password=PASSWORD,
        metadata={"purpose": "round-trip", "unicode": "✓"},
    )

    metadata, entries = Vault.list(container, password=PASSWORD)
    assert metadata == {"purpose": "round-trip", "unicode": "✓"}
    assert all(isinstance(entry, VaultEntry) for entry in entries)
    paths = {entry.path for entry in entries}
    assert "nested" in paths
    assert "nested/空のフォルダ" in paths
    assert "nested/папка/файл.txt" in paths
    assert "empty.bin" in paths
    assert any(entry.is_dir and entry.path == "nested/空のフォルダ" for entry in entries)

    destination = tmp_path / "restored"
    extracted_metadata, extracted_entries = Vault.extract(
        container, destination, password=PASSWORD
    )
    assert extracted_metadata == metadata
    assert len(extracted_entries) == len(entries)
    assert (destination / "nested" / "папка" / "файл.txt").read_text(
        encoding="utf-8"
    ) == "Привет, vault 🔐\n"
    assert (destination / "nested" / "空のフォルダ").is_dir()
    assert (destination / "empty.bin").read_bytes() == b""


def test_vault_file_round_trip_and_progress(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    payload = bytes(range(256)) * 500
    (source / "data.bin").write_bytes(payload)
    destination = tmp_path / "archive.cyphra-vault"
    progress: list[tuple[int, int]] = []

    completed = Vault.create(
        source,
        destination,
        password=PASSWORD,
        progress=lambda done, total: progress.append((done, total)),
    )
    assert completed == len(payload)
    assert progress and progress[-1] == (len(payload), len(payload))
    assert Vault.extract(destination, tmp_path / "out", password=PASSWORD)


def test_vault_wrong_password_removes_partial_outputs(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "secret.txt").write_text("do not leave this behind", encoding="utf-8")
    container = Vault.create(source, password=PASSWORD)
    destination = tmp_path / "restored"

    with pytest.raises(AuthenticationError):
        Vault.extract(container, destination, password="wrong password")

    assert list(destination.rglob("*")) == []


def test_vault_tampering_and_corrupt_header_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload.bin").write_bytes(b"payload")
    container = bytearray(Vault.create(source, password=PASSWORD))
    container[-1] ^= 1
    with pytest.raises(AuthenticationError):
        Vault.list(bytes(container), password=PASSWORD)

    corrupted = b"BAD!" + bytes(container[4:])
    with pytest.raises(FormatError):
        Vault.list(corrupted, password=PASSWORD)


@pytest.mark.parametrize("path", ["../escape.txt", "/absolute.txt", r"..\escape.txt", "C:/absolute.txt"])
def test_vault_path_traversal_is_rejected(tmp_path: Path, path: str) -> None:
    destination = tmp_path / "restored"

    with pytest.raises(FormatError):
        Vault.extract(_malicious_vault(path), destination, password=PASSWORD)

    assert not (tmp_path / "escape.txt").exists()
    assert not (tmp_path / "absolute.txt").exists()


@pytest.mark.parametrize("path", ["../escape", "/absolute", r"..\escape", "C:/absolute"])
def test_safe_relative_path_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(PathSafetyError):
        safe_relative_path(path)


def test_payload_helper_uses_authenticated_ciphertext() -> None:
    encrypted = encrypt_payload(b"payload", PASSWORD, associated_data=b"context")
    assert encrypted[:16] != b"payload"
    assert len(encrypted) > len(b"payload")
