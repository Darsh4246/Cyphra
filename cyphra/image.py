"""The streamed .cyphra single-payload container."""

from __future__ import annotations

import io
import json
import os
import struct
from dataclasses import dataclass
from typing import BinaryIO, Optional, Union

from .callbacks import check_cancel, report
from .errors import FormatError
from .format import (KIND_IMAGE, MAX_METADATA, MAX_RECORD, EncryptStream,
                     PlainReader, decrypt_chunks)

RECORD_METADATA = 1
RECORD_DATA = 2
RECORD_END = 3
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ImageInfo:
    size: int
    metadata: dict


def _metadata_bytes(metadata) -> bytes:
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary")
    try:
        result = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"),
                            sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypeError("metadata must be JSON-serializable") from exc
    if len(result) > MAX_METADATA:
        raise ValueError("metadata is too large")
    return result


def _open_input(source):
    if isinstance(source, (bytes, bytearray, memoryview)):
        value = bytes(source)
        return io.BytesIO(value), True, len(value)
    if hasattr(source, "read"):
        return source, False, None
    path = os.fspath(source)
    return open(path, "rb"), True, os.path.getsize(path)


def _open_output(destination):
    if destination is None:
        return io.BytesIO(), True
    if hasattr(destination, "write"):
        return destination, False
    return open(os.fspath(destination), "wb"), True


class Image:
    """A single encrypted file or byte payload.

    ``encrypt`` and ``decrypt`` accept paths or binary streams.  The format is
    authenticated from the first byte through the final GCM tag; metadata is
    inside the encrypted stream and is never written in cleartext.
    """

    @classmethod
    def encrypt(cls, source, destination=None, password=None, metadata=None,
                progress=None, cancellation=None):
        if password is None:
            raise TypeError("password is required")
        inp, close_in, total = _open_input(source)
        if isinstance(source, (bytes, bytearray, memoryview)):
            inp = io.BytesIO(bytes(source))
            close_in, total = True, len(source)
        out, close_out = _open_output(destination)
        completed = 0
        try:
            with EncryptStream(out, password, KIND_IMAGE) as encrypted:
                meta = _metadata_bytes(metadata)
                encrypted.write(bytes([RECORD_METADATA]) + struct.pack(">I", len(meta)) + meta)
                while True:
                    check_cancel(cancellation)
                    chunk = inp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    encrypted.write(bytes([RECORD_DATA]) + struct.pack(">I", len(chunk)) + chunk)
                    completed += len(chunk)
                    report(progress, completed, total or 0)
                encrypted.write(bytes([RECORD_END]))
            if destination is None:
                return out.getvalue()
            return ImageInfo(completed, metadata or {})
        finally:
            if close_in:
                inp.close()
            if close_out:
                out.close()

    create = encrypt
    pack = encrypt

    @classmethod
    def decrypt(cls, source, destination=None, password=None, progress=None,
                cancellation=None) -> Union[ImageInfo, bytes]:
        if password is None:
            raise TypeError("password is required")
        inp, close_in, total = _open_input(source)
        if isinstance(source, (bytes, bytearray, memoryview)):
            inp = io.BytesIO(bytes(source))
            close_in, total = True, len(source)
        out, close_out = _open_output(destination)
        info = None
        completed = 0
        try:
            reader = PlainReader(decrypt_chunks(inp, password, KIND_IMAGE))
            if reader.u8() != RECORD_METADATA:
                reader.drain()
                raise FormatError("image metadata record is missing")
            n = reader.u32()
            if n > MAX_METADATA:
                reader.drain()
                raise FormatError("image metadata is too large")
            try:
                metadata = json.loads(reader.read(n).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                reader.drain()
                raise FormatError("invalid image metadata") from exc
            if not isinstance(metadata, dict):
                raise FormatError("image metadata must be an object")
            while True:
                check_cancel(cancellation)
                kind = reader.u8()
                if kind == RECORD_DATA:
                    n = reader.u32()
                    if n > MAX_RECORD:
                        reader.drain()
                        raise FormatError("image data record is too large")
                    data = reader.read(n)
                    out.write(data)
                    completed += n
                    report(progress, completed, 0)
                elif kind == RECORD_END:
                    break
                else:
                    reader.drain()
                    raise FormatError("invalid image record")
            if not reader.exhausted():
                raise FormatError("trailing image records")
            info = ImageInfo(completed, metadata)
            if destination is None:
                return out.getvalue()
            return info
        finally:
            if close_in:
                inp.close()
            if close_out:
                out.close()

    extract = decrypt
    unpack = decrypt

    @classmethod
    def inspect(cls, source, password=None) -> ImageInfo:
        """Authenticate and inspect an image without retaining its payload."""
        value = cls.decrypt(source, destination=io.BytesIO(), password=password)
        return value if isinstance(value, ImageInfo) else ImageInfo(len(value), {})
