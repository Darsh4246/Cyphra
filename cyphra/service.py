"""Small application-service facade for GUI or CLI callers."""

from __future__ import annotations

import threading

from .image import Image
from .vault import Vault


class CancellationToken:
    """Thread-safe cancellation token suitable for a Cancel button."""
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    is_set = is_cancelled


class CryptoService:
    """GUI-independent operations with progress and cancellation hooks."""
    create_image = staticmethod(Image.encrypt)
    decrypt_image = staticmethod(Image.decrypt)
    create_vault = staticmethod(Vault.create)
    extract_vault = staticmethod(Vault.extract)
    list_vault = staticmethod(Vault.list)
