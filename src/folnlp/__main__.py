"""Entry point for ``python -m folnlp``."""

from .cli import main

if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
