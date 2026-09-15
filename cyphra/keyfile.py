"""Keyfile generation and management for Cyphra containers.

A keyfile is a 64-byte cryptographically random blob stored on disk.
It can be used as the sole authentication secret (instead of a password),
or combined with a password so that *both* are required to decrypt.
"""

from __future__ import annotations

import hashlib
import os

KEYFILE_SIZE = 64


# ---------------------------------------------------------------------------
# Generation & loading
# ---------------------------------------------------------------------------

def generate_keyfile(path) -> str:
    """Write *KEYFILE_SIZE* random bytes to *path* and return the path string.

    The file is created with binary mode; any existing file is overwritten.
    """
    data = os.urandom(KEYFILE_SIZE)
    with open(os.fspath(path), "wb") as fh:
        fh.write(data)
    return str(path)


def load_keyfile(path) -> bytes:
    """Read a keyfile from *path* and return its raw bytes.

    Raises :exc:`ValueError` if the file is smaller than 16 bytes.
    Any size >= 16 bytes is accepted so users may supply custom key material.
    """
    with open(os.fspath(path), "rb") as fh:
        data = fh.read()
    if len(data) < 16:
        raise ValueError(
            f"Keyfile is too small ({len(data)} bytes). "
            "A valid Cyphra keyfile must be at least 16 bytes."
        )
    return data


# ---------------------------------------------------------------------------
# Secret derivation helpers
# ---------------------------------------------------------------------------

def keyfile_to_password(keyfile_bytes: bytes) -> str:
    """Return a hex string representation of *keyfile_bytes*.

    This can be passed directly as the ``password`` argument to any
    Cyphra container function.
    """
    return keyfile_bytes.hex()


def combine_password_keyfile(password, keyfile_bytes: bytes) -> str:
    """Derive a single secret from *password* **and** *keyfile_bytes*.

    Both inputs are required to reproduce the same secret, so the container
    can only be opened when the user supplies both credentials.

    The derivation is:
        SHA-256(password_bytes || 0x00 || b":cyphra-kf:" || 0x00 || keyfile_bytes).hexdigest()
    """
    if isinstance(password, str):
        pw_bytes = password.encode("utf-8")
    elif isinstance(password, (bytes, bytearray)):
        pw_bytes = bytes(password)
    else:
        raise TypeError("password must be str or bytes")
    domain = b"\x00:cyphra-kf:\x00"
    return hashlib.sha256(pw_bytes + domain + keyfile_bytes).hexdigest()


def resolve_key(password: str | None, keyfile_path: str | None) -> str:
    """Return the effective password string from any combination of inputs.

    Exactly one of the following must be true:
    - *password* is non-empty (password-only mode)
    - *keyfile_path* is non-empty (keyfile-only mode)
    - Both are non-empty (combined mode — both required to decrypt)

    Raises :exc:`ValueError` when neither is provided.
    """
    has_pw = bool(password)
    has_kf = bool(keyfile_path)

    if not has_pw and not has_kf:
        raise ValueError(
            "Either a password or a keyfile (or both) must be provided."
        )

    if has_pw and has_kf:
        kf_bytes = load_keyfile(keyfile_path)
        return combine_password_keyfile(password, kf_bytes)

    if has_kf:
        kf_bytes = load_keyfile(keyfile_path)
        return keyfile_to_password(kf_bytes)

    # Password-only
    return password  # type: ignore[return-value]
