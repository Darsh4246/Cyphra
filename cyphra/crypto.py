"""Cryptographic primitives used by the container format."""

from __future__ import annotations

import hashlib
import os
from typing import Union

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_ITERATIONS = 600_000
KEY_SIZE = 32
SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16
Password = Union[str, bytes, bytearray]


def password_bytes(password: Password) -> bytes:
    if isinstance(password, str):
        return password.encode("utf-8")
    if isinstance(password, (bytes, bytearray)):
        return bytes(password)
    raise TypeError("password must be str or bytes")


def derive_key(password: Password, salt: bytes,
               iterations: int = DEFAULT_ITERATIONS) -> bytes:
    """Derive the 256-bit container key with PBKDF2-HMAC-SHA256."""
    if len(salt) != SALT_SIZE:
        raise ValueError("salt must be exactly 16 bytes")
    if iterations < 1:
        raise ValueError("PBKDF2 iterations must be positive")
    return hashlib.pbkdf2_hmac(
        "sha256", password_bytes(password), salt, iterations, dklen=KEY_SIZE
    )


def new_salt() -> bytes:
    return os.urandom(SALT_SIZE)


def new_nonce() -> bytes:
    return os.urandom(NONCE_SIZE)


def encrypt(data: bytes, password: Password, associated_data: bytes = b"") -> bytes:
    """Small-payload convenience function; containers use the streaming API."""
    salt, nonce = new_salt(), new_nonce()
    return salt + nonce + AESGCM(derive_key(password, salt)).encrypt(
        nonce, data, associated_data
    )
