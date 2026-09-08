"""The Cyphra encrypted container core.

The package deliberately contains no GUI dependencies.  :class:`Image` is a
single encrypted payload and :class:`Vault` is a streamed encrypted directory.
"""

from .errors import (
    AuthenticationError,
    ContainerError,
    FormatError,
    InvalidPasswordError,
    OperationCancelled,
    PathSafetyError,
)
from .crypto import DEFAULT_ITERATIONS, KEY_SIZE, SALT_SIZE, derive_key
from .image import Image, ImageInfo
from .vault import Vault, VaultEntry
from .service import CryptoService, CancellationToken

__all__ = [
    "AuthenticationError", "ContainerError", "FormatError",
    "InvalidPasswordError", "OperationCancelled", "PathSafetyError",
    "DEFAULT_ITERATIONS", "KEY_SIZE", "SALT_SIZE", "derive_key",
    "Image", "ImageInfo", "Vault", "VaultEntry", "CryptoService",
    "CancellationToken",
]
