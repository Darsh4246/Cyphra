"""The streamed .cyphra-vault encrypted directory container."""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import struct
import time
from dataclasses import dataclass

from .callbacks import check_cancel, report
from .errors import FormatError, PathSafetyError
from .format import (KIND_VAULT, MAX_METADATA, MAX_PATH, MAX_RECORD,
                     EncryptStream, PlainReader, decrypt_chunks)
from .paths import destination_path, ensure_no_symlink_parents, safe_relative_path

RECORD_METADATA = 1
RECORD_DIRECTORY = 2
RECORD_FILE = 3
RECORD_DATA = 4
RECORD_END_FILE = 5
RECORD_END = 6
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class VaultEntry:
    path: str
    is_dir: bool
    size: int = 0
    mtime_ns: int = 0


def _metadata_bytes(metadata) -> bytes:
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary")
    try:
        value = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"),
                           sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypeError("metadata must be JSON-serializable") from exc
    if len(value) > MAX_METADATA:
        raise ValueError("metadata is too large")
    return value


def _entries(root: str):
    root = os.path.abspath(os.fspath(root))
    if not os.path.isdir(root) or os.path.islink(root):
        raise ValueError("vault source must be a real directory")
    result = []
    total = 0
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        dirs.sort()
        files.sort()
        # os.walk places symlinked directories in dirs; never follow or encode them.
        for name in list(dirs):
            full = os.path.join(current, name)
            if os.path.islink(full):
                raise PathSafetyError("symbolic links are not supported in vaults")
        rel_dir = os.path.relpath(current, root)
        if rel_dir != ".":
            path = safe_relative_path(rel_dir.replace(os.sep, "/"))
            mtime = os.stat(current, follow_symlinks=False).st_mtime_ns
            result.append(VaultEntry(path, True, 0, mtime))
        for name in files:
            full = os.path.join(current, name)
            if os.path.islink(full):
                raise PathSafetyError("symbolic links are not supported in vaults")
            st = os.stat(full, follow_symlinks=False)
            if not stat.S_ISREG(st.st_mode):
                raise ValueError("vault source contains a non-regular file")
            path = safe_relative_path(os.path.relpath(full, root).replace(os.sep, "/"))
            result.append(VaultEntry(path, False, st.st_size, st.st_mtime_ns))
            total += st.st_size
    # Directories precede files and ordering is stable across platforms.
    result.sort(key=lambda e: (e.path, not e.is_dir))
    return root, result, total


def _path_record(kind: int, entry: VaultEntry) -> bytes:
    path = entry.path.encode("utf-8")
    if len(path) > MAX_PATH:
        raise ValueError("vault path is too long")
    return bytes([kind]) + struct.pack(">IQQ", len(path), entry.size, entry.mtime_ns) + path


class Vault:
    @classmethod
    def create(cls, source, destination=None, password=None, metadata=None,
               progress=None, cancellation=None, cipher_id: int = 0, kdf_id: int = 0):
        if password is None:
            raise TypeError("password is required")
        root, entries, total = _entries(os.fspath(source))
        if destination is None:
            out = io.BytesIO()
            close_out = False
        elif hasattr(destination, "write"):
            out, close_out = destination, False
        else:
            out, close_out = open(os.fspath(destination), "wb"), True
        completed = 0
        try:
            with EncryptStream(out, password, KIND_VAULT, cipher_id=cipher_id, kdf_id=kdf_id) as encrypted:
                meta = _metadata_bytes(metadata)
                encrypted.write(bytes([RECORD_METADATA]) + struct.pack(">I", len(meta)) + meta)
                for entry in entries:
                    check_cancel(cancellation)
                    if entry.is_dir:
                        encrypted.write(_path_record(RECORD_DIRECTORY, entry))
                        continue
                    encrypted.write(_path_record(RECORD_FILE, entry))
                    with open(os.path.join(root, *entry.path.split("/")), "rb") as inp:
                        while True:
                            check_cancel(cancellation)
                            chunk = inp.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            encrypted.write(bytes([RECORD_DATA]) + struct.pack(">I", len(chunk)) + chunk)
                            completed += len(chunk)
                            report(progress, completed, total)
                    encrypted.write(bytes([RECORD_END_FILE]))
                encrypted.write(bytes([RECORD_END]))
            if destination is None:
                return out.getvalue()
            return completed
        finally:
            if close_out:
                out.close()

    encrypt = create
    pack = create

    @classmethod
    def _read_entries(cls, source, password, on_directory=None, on_file=None,
                      progress=None, cancellation=None):
        if hasattr(source, "read"):
            inp, close_in = source, False
        elif isinstance(source, (bytes, bytearray, memoryview)):
            inp, close_in = io.BytesIO(bytes(source)), True
        else:
            inp, close_in = open(os.fspath(source), "rb"), True
        try:
            reader = PlainReader(decrypt_chunks(inp, password, KIND_VAULT))
            if reader.u8() != RECORD_METADATA:
                reader.drain()
                raise FormatError("vault metadata record is missing")
            n = reader.u32()
            if n > MAX_METADATA:
                reader.drain()
                raise FormatError("vault metadata is too large")
            try:
                metadata = json.loads(reader.read(n).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                reader.drain()
                raise FormatError("invalid vault metadata") from exc
            if not isinstance(metadata, dict):
                reader.drain()
                raise FormatError("vault metadata must be an object")
            entries = []
            completed = 0
            while True:
                check_cancel(cancellation)
                kind = reader.u8()
                if kind == RECORD_END:
                    break
                if kind not in (RECORD_DIRECTORY, RECORD_FILE):
                    reader.drain()
                    raise FormatError("invalid vault entry record")
                n, size, mtime_ns = reader.u32(), reader.u64(), reader.u64()
                if n == 0 or n > MAX_PATH:
                    reader.drain()
                    raise FormatError("invalid vault path length")
                try:
                    path = safe_relative_path(reader.read(n).decode("utf-8"))
                except (UnicodeDecodeError, PathSafetyError) as exc:
                    reader.drain()
                    raise FormatError("invalid vault path") from exc
                entry = VaultEntry(path, kind == RECORD_DIRECTORY, size, mtime_ns)
                entries.append(entry)
                if entry.is_dir:
                    if size != 0:
                        raise FormatError("directory has a non-zero size")
                    if on_directory:
                        on_directory(entry)
                    continue
                if on_file:
                    on_file(entry, reader)
                else:
                    while True:
                        part = reader.u8()
                        if part == RECORD_END_FILE:
                            break
                        if part != RECORD_DATA:
                            raise FormatError("invalid vault file data record")
                        ndata = reader.u32()
                        if ndata > MAX_RECORD:
                            raise FormatError("vault data record is too large")
                        reader.read(ndata)
                completed += entry.size
                report(progress, completed, 0)
            if not reader.exhausted():
                raise FormatError("trailing vault records")
            return metadata, entries
        finally:
            if close_in:
                inp.close()

    @classmethod
    def extract(cls, source, destination, password=None, progress=None,
                cancellation=None, overwrite=False):
        if password is None:
            raise TypeError("password is required")
        root = os.path.abspath(os.fspath(destination))
        os.makedirs(root, exist_ok=True)
        created = []
        current_output = [None]

        def make_dir(entry):
            path = destination_path(root, entry.path)
            ensure_no_symlink_parents(root, os.path.dirname(path))
            if os.path.exists(path) and not os.path.isdir(path):
                raise PathSafetyError("archive directory conflicts with a file")
            if os.path.islink(path):
                raise PathSafetyError("refusing to use a symbolic link")
            if not os.path.exists(path):
                os.makedirs(path)
                created.append(path)
            try:
                os.utime(path, ns=(entry.mtime_ns, entry.mtime_ns), follow_symlinks=False)
            except (OSError, ValueError, NotImplementedError):
                pass

        def make_file(entry, reader):
            path = destination_path(root, entry.path)
            parent = os.path.dirname(path)
            os.makedirs(parent, exist_ok=True)
            ensure_no_symlink_parents(root, parent)
            if os.path.lexists(path) and (not overwrite or os.path.islink(path)):
                raise PathSafetyError("file exists or is a symbolic link: %s" % entry.path)
            current_output[0] = path
            with open(path, "wb") as out:
                if path not in created:
                    created.append(path)
                written = 0
                while True:
                    check_cancel(cancellation)
                    part = reader.u8()
                    if part == RECORD_END_FILE:
                        break
                    if part != RECORD_DATA:
                        raise FormatError("invalid vault file data record")
                    ndata = reader.u32()
                    if ndata > MAX_RECORD or written + ndata > entry.size:
                        raise FormatError("vault file size does not match its records")
                    out.write(reader.read(ndata))
                    written += ndata
                if written != entry.size:
                    raise FormatError("vault file is truncated")
            current_output[0] = None
            try:
                os.utime(path, ns=(entry.mtime_ns, entry.mtime_ns))
            except (OSError, ValueError, NotImplementedError):
                pass

        try:
            metadata, entries = cls._read_entries(
                source, password, make_dir, make_file, progress, cancellation)
            return metadata, entries
        except Exception:
            # Do not leave attacker-controlled partial files behind on auth failure.
            for path in reversed(created):
                try:
                    if os.path.isdir(path) and not os.path.islink(path):
                        os.rmdir(path)
                    else:
                        os.remove(path)
                except OSError:
                    pass
            raise

    decrypt = extract
    unpack = extract

    @classmethod
    def list(cls, source, password=None, cancellation=None):
        metadata, entries = cls._read_entries(source, password, cancellation=cancellation)
        return metadata, entries

    inspect = list
