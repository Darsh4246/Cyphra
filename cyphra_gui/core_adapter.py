"""A small compatibility layer around the Cyphra cryptography core.

The core package is developed separately from the UI.  No crypto code belongs
in this module: it only discovers and normalises the public functions exposed
by a core implementation.  Supported function names are deliberately
conventional (``encrypt_file``, ``decrypt_file``, ``hash_file``,
``hash_text`` and ``compare_hash``), while the adapter also accepts a module
object in tests or from an embedding application.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import secrets
import string
from pathlib import Path
from typing import Any, Callable, Iterable


class CoreUnavailableError(RuntimeError):
    """Raised when an encryption operation is requested before the core exists."""


class OperationCancelled(RuntimeError):
    """Raised by an adapter when a worker cancellation request is observed."""


_CORE_MODULES = (
    "cyphra",
    "cyphra_core",
    "cyphra.crypto",
    "cyphra.core",
    "crypto_core",
    "core.crypto",
)


def _load_core(module: Any = None) -> Any:
    if module is not None:
        return module
    for module_name in _CORE_MODULES:
        try:
            return importlib.import_module(module_name)
        except ImportError:
            continue
    return None


def _find(core: Any, names: Iterable[str]) -> Callable[..., Any] | None:
    if core is None:
        return None
    for name in names:
        function = getattr(core, name, None)
        if callable(function):
            return function
    return None


def _call(function: Callable[..., Any], **kwargs: Any) -> Any:
    """Call a core function while accommodating small signature variations."""
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return function(**kwargs)
    accepted = {
        key: value for key, value in kwargs.items()
        if key in parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
    }
    return function(**accepted)


def _progress_callback(progress: Callable[[int], None] | None) -> Callable[..., None] | None:
    """Accept both ``progress(percent)`` and ``progress(done, total)`` cores."""
    if progress is None:
        return None

    def report(*values: Any) -> None:
        if not values:
            return
        if len(values) > 1 and values[1]:
            progress(min(100, int(values[0] * 100 / values[1])))
        else:
            value = values[0]
            progress(int(value if isinstance(value, (int, float)) else 0))

    return report


class CryptoAdapter:
    """Normalised facade used by the GUI workers.

    ``core_module`` is optional so applications can inject the real core and
    tests can supply a deterministic fake without importing implementation
    files.  File operations require a core function; hashing has a safe
    hashlib fallback to keep the Hash screen useful independently.
    """

    def __init__(self, core_module: Any = None) -> None:
        self.core = _load_core(core_module)

    @property
    def available(self) -> bool:
        return self.core is not None

    def _required(self, names: Iterable[str]) -> Callable[..., Any]:
        function = _find(self.core, names)
        if function is None:
            joined = ", ".join(names)
            raise CoreUnavailableError(
                f"Cyphra core is not available (expected one of: {joined})"
            )
        return function

    @staticmethod
    def _check_cancel(cancel_event: Any = None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled("Operation cancelled")

    def encrypt_file(
        self,
        source: str | Path,
        destination: str | Path,
        password: str,
        progress: Callable[[int], None] | None = None,
        cancel_event: Any = None,
    ) -> Any:
        self._check_cancel(cancel_event)
        source_path = Path(source)
        if source_path.is_dir():
            vault = getattr(self.core, "Vault", None)
            function = getattr(vault, "create", None)
            if function is None:
                raise CoreUnavailableError("Cyphra Vault support is not available")
            result = _call(
                function,
                source=source_path,
                destination=str(destination),
                password=password,
                progress=_progress_callback(progress),
                cancellation=cancel_event,
            )
            self._check_cancel(cancel_event)
            return result
        function = _find(self.core, ("encrypt_file", "encrypt"))
        if function is None and self.core is not None:
            image = getattr(self.core, "Image", None)
            function = getattr(image, "encrypt", None)
        if function is None:
            function = self._required(("encrypt_file", "encrypt"))
        result = _call(
            function,
            input_path=str(source),
            source=str(source),
            output_path=str(destination),
            destination=str(destination),
            password=password,
            progress_callback=_progress_callback(progress),
            progress=_progress_callback(progress),
            cancel_event=cancel_event,
            cancellation=cancel_event,
        )
        self._check_cancel(cancel_event)
        return result

    def decrypt_file(
        self,
        source: str | Path,
        destination: str | Path,
        password: str,
        progress: Callable[[int], None] | None = None,
        cancel_event: Any = None,
    ) -> Any:
        self._check_cancel(cancel_event)
        source_path = Path(source)
        if source_path.suffix.lower() == ".cyphra-vault":
            vault = getattr(self.core, "Vault", None)
            function = getattr(vault, "extract", None)
            if function is None:
                raise CoreUnavailableError("Cyphra Vault support is not available")
            result = _call(
                function,
                source=source_path,
                destination=str(destination),
                password=password,
                progress=_progress_callback(progress),
                cancellation=cancel_event,
            )
            self._check_cancel(cancel_event)
            return result
        function = _find(self.core, ("decrypt_file", "decrypt"))
        if function is None and self.core is not None:
            image = getattr(self.core, "Image", None)
            function = getattr(image, "decrypt", None)
        if function is None:
            function = self._required(("decrypt_file", "decrypt"))
        result = _call(
            function,
            input_path=str(source),
            source=str(source),
            output_path=str(destination),
            destination=str(destination),
            password=password,
            progress_callback=_progress_callback(progress),
            progress=_progress_callback(progress),
            cancel_event=cancel_event,
            cancellation=cancel_event,
        )
        self._check_cancel(cancel_event)
        return result

    def hash_text(self, text: str, algorithm: str = "SHA-256") -> str:
        function = _find(self.core, ("hash_text", "hash_string", "digest_text"))
        if function is not None:
            return str(_call(function, text=text, data=text, algorithm=algorithm))
        digest = hashlib.new(algorithm.replace("-", "").lower())
        digest.update(text.encode("utf-8"))
        return digest.hexdigest()

    def hash_file(
        self,
        source: str | Path,
        algorithm: str = "SHA-256",
        progress: Callable[[int], None] | None = None,
    ) -> str:
        function = _find(self.core, ("hash_file", "digest_file"))
        if function is not None:
            return str(_call(
                function,
                input_path=str(source),
                source=str(source),
                algorithm=algorithm,
                progress_callback=progress,
                progress=progress,
            ))
        digest = hashlib.new(algorithm.replace("-", "").lower())
        path = Path(source)
        size = max(path.stat().st_size, 1)
        read = 0
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                read += len(chunk)
                if progress:
                    progress(min(100, int(read * 100 / size)))
        return digest.hexdigest()

    def compare_hash(self, actual: str, expected: str) -> bool:
        function = _find(self.core, ("compare_hash", "verify_hash", "hash_matches"))
        if function is not None:
            return bool(_call(function, actual=actual, expected=expected, left=actual, right=expected))
        return secrets.compare_digest(actual.strip().casefold(), expected.strip().casefold())


def generate_password(length: int = 24, symbols: bool = True) -> str:
    """Generate a password using the system CSPRNG, never ``random``."""
    if length < 8:
        raise ValueError("Password length must be at least 8 characters")
    alphabet = string.ascii_letters + string.digits
    if symbols:
        alphabet += "!@#$%^&*()-_=+[]{}:,.?"
    return "".join(secrets.choice(alphabet) for _ in range(length))
