"""Path validation shared by vault creation and extraction."""

from __future__ import annotations

import os
import ntpath
from pathlib import PurePosixPath

from .errors import PathSafetyError


def safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise PathSafetyError("archive path is empty or contains NUL")
    # Archive paths are always POSIX encoded, even on Windows.
    value = value.replace("\\", "/")
    if value.startswith("/") or ntpath.splitdrive(value)[0]:
        raise PathSafetyError("absolute archive paths are not allowed")
    parts = value.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise PathSafetyError("unsafe archive path: %r" % value)
    normalized = str(PurePosixPath(*parts))
    if normalized != value or normalized in ("", "."):
        raise PathSafetyError("unsafe archive path: %r" % value)
    return normalized


def destination_path(root: str, archive_path: str) -> str:
    rel = safe_relative_path(archive_path)
    root_abs = os.path.realpath(os.path.abspath(root))
    result = os.path.realpath(os.path.join(root_abs, *rel.split("/")))
    try:
        inside = os.path.commonpath((root_abs, result)) == root_abs
    except ValueError:
        inside = False
    if not inside:
        raise PathSafetyError("archive path escapes extraction directory")
    return result


def ensure_no_symlink_parents(root: str, path: str) -> None:
    root_abs = os.path.abspath(root)
    current = root_abs
    relative = os.path.relpath(path, root_abs)
    for part in relative.split(os.sep):
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise PathSafetyError("refusing to traverse symbolic link: %s" % current)
