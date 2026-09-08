"""Progress and cancellation adapters."""

from .errors import OperationCancelled


def cancelled(token) -> bool:
    if token is None:
        return False
    if callable(token):
        return bool(token())
    if hasattr(token, "is_cancelled"):
        return bool(token.is_cancelled())
    if hasattr(token, "is_set"):
        return bool(token.is_set())
    return bool(token)


def check_cancel(token) -> None:
    if cancelled(token):
        raise OperationCancelled("operation cancelled")


def report(callback, completed: int, total: int) -> None:
    if callback is None:
        return
    if callable(callback):
        callback(completed, total)
    elif hasattr(callback, "update"):
        callback.update(completed, total)
