"""Cryptographic primitives used by the container format."""

from __future__ import annotations

import hashlib
import os
from typing import Union

from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305, AESGCMSIV

DEFAULT_ITERATIONS = 600_000
KEY_SIZE = 32
SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16
Password = Union[str, bytes, bytearray]

# Cipher Identifiers
CIPHER_AES_256_GCM = 0x00
CIPHER_CHACHA20_POLY1305 = 0x01
CIPHER_AES_256_GCM_SIV = 0x02

# Key Derivation Identifiers
KDF_PBKDF2_SHA256 = 0x00
KDF_ARGON2ID = 0x01
KDF_SCRYPT = 0x02


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


def derive_key_multi(
    password: Password,
    salt: bytes,
    kdf_id: int = KDF_PBKDF2_SHA256,
    iterations: int = DEFAULT_ITERATIONS,
    memory_cost: int = 65536,
    time_cost: int = 3,
    parallelism: int = 4,
) -> bytes:
    """Derive container key using the requested KDF (PBKDF2, Argon2id, or Scrypt)."""
    if len(salt) != SALT_SIZE:
        raise ValueError("salt must be exactly 16 bytes")
    pw = password_bytes(password)

    if kdf_id == KDF_ARGON2ID:
        try:
            import argon2.low_level
            return argon2.low_level.hash_secret_raw(
                secret=pw,
                salt=salt,
                time_cost=time_cost,
                memory_cost=memory_cost,
                parallelism=parallelism,
                hash_len=KEY_SIZE,
                type=argon2.low_level.Type.ID,
            )
        except ImportError:
            pass

    elif kdf_id == KDF_SCRYPT:
        # Scrypt memory-hard KDF (N=32768, r=8, p=1 ~32MB)
        return hashlib.scrypt(pw, salt=salt, n=32768, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=KEY_SIZE)

    # Standard fallback / default: PBKDF2-HMAC-SHA256
    if iterations < 1:
        raise ValueError("PBKDF2 iterations must be positive")
    return hashlib.pbkdf2_hmac("sha256", pw, salt, iterations, dklen=KEY_SIZE)


def get_aead_cipher(cipher_id: int, key: bytes):
    """Instantiate the corresponding AEAD cipher."""
    if cipher_id == CIPHER_CHACHA20_POLY1305:
        return ChaCha20Poly1305(key)
    if cipher_id == CIPHER_AES_256_GCM_SIV:
        return AESGCMSIV(key)
    return AESGCM(key)


def new_salt() -> bytes:
    return os.urandom(SALT_SIZE)


def new_nonce() -> bytes:
    return os.urandom(NONCE_SIZE)


def encrypt(data: bytes, password: Password, associated_data: bytes = b"",
            cipher_id: int = CIPHER_AES_256_GCM, kdf_id: int = KDF_PBKDF2_SHA256) -> bytes:
    """Convenience payload encryption function supporting multi-cipher."""
    salt, nonce = new_salt(), new_nonce()
    key = derive_key_multi(password, salt, kdf_id=kdf_id)
    cipher = get_aead_cipher(cipher_id, key)
    return salt + nonce + cipher.encrypt(nonce, data, associated_data)
