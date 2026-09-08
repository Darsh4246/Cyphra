"""Cancellable QThread workers for operations that may touch large files."""

from __future__ import annotations

import threading
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from .core_adapter import OperationCancelled


class OperationWorker(QThread):
    """Run one adapter operation off the UI thread.

    The callable receives ``progress`` and ``cancel_event`` keyword arguments.
    A callable that does not accept either is also supported by a small
    compatibility fallback, which is useful for simple core adapters.
    """

    progress = Signal(int)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, operation: Callable[..., Any], parent: Any = None) -> None:
        super().__init__(parent)
        self.operation = operation
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            try:
                import inspect
                sig = inspect.signature(self.operation)
                params = sig.parameters
                has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
                kwargs: dict[str, Any] = {}
                if "progress" in params or has_var_kw:
                    kwargs["progress"] = self.progress.emit
                if "cancel_event" in params or has_var_kw:
                    kwargs["cancel_event"] = self.cancel_event
                result = self.operation(**kwargs)
            except (ValueError, TypeError):
                # Fallback for callables without inspectable signature
                result = self.operation(
                    progress=self.progress.emit,
                    cancel_event=self.cancel_event,
                )
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.succeeded.emit(result)
        except OperationCancelled:
            self.cancelled.emit()
        except Exception as error:  # noqa: BLE001 - surface worker errors in UI
            # Keep compatibility with the core's own OperationCancelled class
            # without importing implementation files into the GUI.
            if error.__class__.__name__ == "OperationCancelled":
                self.cancelled.emit()
                return
            message = str(error).strip() or error.__class__.__name__
            self.failed.emit(message)
