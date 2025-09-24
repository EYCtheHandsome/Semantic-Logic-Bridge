"""High-level translation helpers for the FOL/NL toolkit."""

from __future__ import annotations

from .fol_to_nl import ConversionError, convert_fol_to_natural_language
from .nl_parser import NLToFOLParser, ParseError, parse_natural_language


class TranslationError(ValueError):
    """Generic wrapper for parse or conversion errors."""


def translate_nl_to_fol(text: str) -> str:
    if not text or not text.strip():
        raise TranslationError("natural language statement is empty")
    try:
        return parse_natural_language(text)
    except ParseError as exc:
        raise TranslationError(str(exc)) from exc


def translate_fol_to_nl(formula: str) -> str:
    if not formula or not formula.strip():
        raise TranslationError("FOL formula is empty")
    try:
        return convert_fol_to_natural_language(formula)
    except ConversionError as exc:
        raise TranslationError(str(exc)) from exc


__all__ = [
    "TranslationError",
    "translate_fol_to_nl",
    "translate_nl_to_fol",
]
