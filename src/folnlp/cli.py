"""Command line interface for the FOL/NL translator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .translator import TranslationError, translate_fol_to_nl, translate_nl_to_fol


def _read_input(text: Optional[str], file: Optional[Path]) -> str:
    if text is not None:
        return text
    if file is not None:
        return file.read_text(encoding="utf-8")
    return sys.stdin.read()


def _handle_translation(func, payload: str) -> int:
    try:
        result = func(payload.strip())
    except TranslationError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    sys.stdout.write(result + "\n")
    return 0


def _import_web_run():
    from .web import run

    return run


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="folnlp",
        description="Translate between natural language and first-order logic.",
    )
    subparsers = parser.add_subparsers(dest="command")

    nl_parser = subparsers.add_parser(
        "nl2fol",
        help="Translate a natural language statement into FOL.",
    )
    nl_parser.add_argument("text", nargs="?", help="Statement to translate.")
    nl_parser.add_argument(
        "-f",
        "--file",
        type=Path,
        help="Read natural-language input from a file instead of the command line.",
    )

    fol_parser = subparsers.add_parser(
        "fol2nl",
        help="Translate a FOL formula into natural language.",
    )
    fol_parser.add_argument("formula", nargs="?", help="Formula to translate.")
    fol_parser.add_argument(
        "-f",
        "--file",
        type=Path,
        help="Read the FOL formula from a file instead of the command line.",
    )

    web_parser = subparsers.add_parser(
        "web",
        help="Launch the web interface (requires Flask).",
    )
    web_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind (default: 127.0.0.1).",
    )
    web_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind (default: 8000).",
    )

    args = parser.parse_args(argv)

    if args.command == "nl2fol":
        payload = _read_input(args.text, args.file)
        return _handle_translation(translate_nl_to_fol, payload)
    if args.command == "fol2nl":
        payload = _read_input(args.formula, args.file)
        return _handle_translation(translate_fol_to_nl, payload)
    if args.command == "web":
        try:
            run = _import_web_run()
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on env
            if getattr(exc, "name", None) == "flask":
                sys.stderr.write(
                    "error: Flask is required for the web interface. Install it with `pip install flask`.\n"
                )
                return 1
            raise

        run(host=args.host, port=args.port)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    sys.exit(main())
