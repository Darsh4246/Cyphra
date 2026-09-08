"""Binary framing and streaming AES-GCM helpers for Cyphra containers."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import BinaryIO, Iterator

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .crypto import (CIPHER_AES_256_GCM, CIPHER_AES_256_GCM_SIV,
                     CIPHER_CHACHA20_POLY1305, DEFAULT_ITERATIONS,
                     KDF_ARGON2ID, KDF_PBKDF2_SHA256, KDF_SCRYPT,
                     NONCE_SIZE, SALT_SIZE, TAG_SIZE, derive_key,
                     derive_key_multi, get_aead_cipher, new_nonce, new_salt,
                     password_bytes)
from .errors import AuthenticationError, FormatError

MAGIC = b"CYPhRA\x00\x01"
VERSION = 1
KIND_IMAGE = 1
KIND_VAULT = 2
HEADER = struct.Struct(">8sBBH I 16s 12s 4s")
HEADER_SIZE = HEADER.size
MAX_METADATA = 16 * 1024 * 1024
MAX_PATH = 32767
MAX_RECORD = 64 * 1024 * 1024


@dataclass(frozen=True)
class ContainerHeader:
    kind: int
    iterations: int
    salt: bytes
    nonce: bytes
    flags: int = 0

    @property
    def cipher_id(self) -> int:
        return self.flags & 0xFF

    @property
    def kdf_id(self) -> int:
        return (self.flags >> 8) & 0xFF

    def pack(self) -> bytes:
        if self.kind not in (KIND_IMAGE, KIND_VAULT):
            raise ValueError("invalid container kind")
        return HEADER.pack(MAGIC, VERSION, self.kind, self.flags,
                           self.iterations, self.salt, self.nonce, b"\0" * 4)


def read_header(stream: BinaryIO) -> tuple[ContainerHeader, bytes]:
    raw = stream.read(HEADER_SIZE)
    if len(raw) != HEADER_SIZE:
        raise FormatError("truncated Cyphra header")
    try:
        magic, version, kind, flags, iterations, salt, nonce, reserved = HEADER.unpack(raw)
    except struct.error as exc:
        raise FormatError("invalid Cyphra header") from exc
    if magic != MAGIC or version != VERSION:
        raise FormatError("unsupported Cyphra container")
    if kind not in (KIND_IMAGE, KIND_VAULT) or reserved != b"\0" * 4:
        raise FormatError("invalid Cyphra header fields")
    if not (1 <= iterations <= 10_000_000):
        raise FormatError("invalid PBKDF2 iteration count")
    return ContainerHeader(kind, iterations, salt, nonce, flags), raw


class EncryptStream:
    """Writes an authenticated ciphertext stream and appends its authentication tag."""
    def __init__(self, stream: BinaryIO, password, kind: int,
                 iterations: int = DEFAULT_ITERATIONS,
                 cipher_id: int = CIPHER_AES_256_GCM,
                 kdf_id: int = KDF_PBKDF2_SHA256):
        salt, nonce = new_salt(), new_nonce()
        flags = ((kdf_id & 0xFF) << 8) | (cipher_id & 0xFF)
        self.header = ContainerHeader(kind, iterations, salt, nonce, flags=flags)
        self.stream = stream
        self.stream.write(self.header.pack())
        self.cipher_id = cipher_id
        self.kdf_id = kdf_id
        key = derive_key_multi(password, salt, kdf_id=kdf_id, iterations=iterations)
        self._closed = False

        if cipher_id == CIPHER_AES_256_GCM:
            self._cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
            self._cipher.authenticate_additional_data(self.header.pack())
        else:
            self._aead = get_aead_cipher(cipher_id, key)
            self._buffer = bytearray()

    def write(self, data: bytes) -> None:
        if self._closed:
            raise ValueError("stream is closed")
        if data:
            if self.cipher_id == CIPHER_AES_256_GCM:
                self.stream.write(self._cipher.update(data))
            else:
                self._buffer.extend(data)

    def close(self) -> None:
        if not self._closed:
            if self.cipher_id == CIPHER_AES_256_GCM:
                self.stream.write(self._cipher.finalize())
                self.stream.write(self._cipher.tag)
            else:
                ct = self._aead.encrypt(self.header.nonce, bytes(self._buffer), self.header.pack())
                self.stream.write(ct)
                self._buffer.clear()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def decrypt_chunks(stream: BinaryIO, password, expected_kind: int,
                   chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    """Yield authenticated plaintext chunks, verifying authentication."""
    header, raw_header = read_header(stream)
    if header.kind != expected_kind:
        raise FormatError("container type does not match the requested operation")
    key = derive_key_multi(password, header.salt, kdf_id=header.kdf_id, iterations=header.iterations)

    if header.cipher_id == CIPHER_AES_256_GCM:
        decryptor = Cipher(algorithms.AES(key), modes.GCM(header.nonce)).decryptor()
        decryptor.authenticate_additional_data(raw_header)
        trailing = b""
        try:
            while True:
                block = stream.read(chunk_size)
                if not block:
                    break
                trailing += block
                if len(trailing) > TAG_SIZE:
                    body, trailing = trailing[:-TAG_SIZE], trailing[-TAG_SIZE:]
                    plain = decryptor.update(body)
                    if plain:
                        yield plain
            if len(trailing) != TAG_SIZE:
                raise FormatError("truncated authenticated ciphertext")
            plain = decryptor.finalize_with_tag(trailing)
            if plain:
                yield plain
        except InvalidTag as exc:
            raise AuthenticationError("password is incorrect or container is corrupt") from exc
        except ValueError as exc:
            raise FormatError("invalid encrypted container") from exc
    else:
        # AEAD decrypt (ChaCha20Poly1305, AESGCMSIV)
        aead = get_aead_cipher(header.cipher_id, key)
        ciphertext = stream.read()
        try:
            plaintext = aead.decrypt(header.nonce, ciphertext, raw_header)
            for offset in range(0, len(plaintext), chunk_size):
                yield plaintext[offset:offset + chunk_size]
        except Exception as exc:
            raise AuthenticationError("password is incorrect or container is corrupt") from exc


class PlainReader:
    """Incremental length-delimited record reader over decrypted chunks."""
    def __init__(self, chunks: Iterator[bytes]):
        self._chunks = iter(chunks)
        self._buf = bytearray()
        self._done = False

    def _need(self, n: int) -> None:
        while len(self._buf) < n and not self._done:
            try:
                self._buf.extend(next(self._chunks))
            except StopIteration:
                self._done = True
        if len(self._buf) < n:
            raise FormatError("truncated container record")

    def read(self, n: int) -> bytes:
        self._need(n)
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def u8(self) -> int:
        return self.read(1)[0]

    def u32(self) -> int:
        return struct.unpack(">I", self.read(4))[0]

    def u64(self) -> int:
        return struct.unpack(">Q", self.read(8))[0]

    def exhausted(self) -> bool:
        while not self._done:
            try:
                self._buf.extend(next(self._chunks))
            except StopIteration:
                self._done = True
        return len(self._buf) == 0 and self._done

    def drain(self) -> None:
        """Consume the authenticated stream after a framing error.

        This preserves the useful distinction between a malformed format and
        a bad password: GCM authentication is only decided at end-of-stream.
        """
        while not self._done:
            try:
                next(self._chunks)
            except StopIteration:
                self._done = True
