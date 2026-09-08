"""Errors raised by Cyphra containers."""

class ContainerError(Exception):
    """Base class for all expected container failures."""

class FormatError(ContainerError):
    """The input is not a supported, valid Cyphra container."""

class AuthenticationError(ContainerError):
    """The password or authenticated container contents are incorrect."""

class InvalidPasswordError(AuthenticationError):
    """The password did not authenticate the container."""

class PathSafetyError(ContainerError):
    """An archive path would escape the extraction directory."""

class OperationCancelled(ContainerError):
    """An operation was cancelled by its caller."""
