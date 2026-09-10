"""Cyphra's PySide6 desktop interface.

The GUI intentionally talks to the encryption project through
``cyphra_gui.core_adapter``.  This keeps the UI usable while the core package is
being developed independently and gives the core a small, documented seam to
integrate with.
"""

__all__ = ["MainWindow"]
__version__ = "0.2.0"


def __getattr__(name):
    # Keep the adapter importable in headless environments where the optional
    # desktop dependency has not been installed yet.
    if name == "MainWindow":
        from .main_window import MainWindow
        return MainWindow
    raise AttributeError(name)
