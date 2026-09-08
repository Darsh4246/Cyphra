"""Compatibility launcher for ``python main.py``."""

from cyphra_gui.main import main


if __name__ == "__main__":
    raise SystemExit(main())
