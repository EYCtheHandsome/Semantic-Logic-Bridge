"""Utilities for converting FOL formulas back into natural language."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, Iterator, List, Tuple


class ConversionError(ValueError):
    """Raised when a FOL formula cannot be rendered in natural language."""


PREDICATE_MAP = {
    "Human": "is human",
    "Mortal": "is mortal",
    "Student": "is a student",
    "Teacher": "is a teacher",
    "Philosopher": "is a philosopher",
    "Wise": "is wise",
    "Happy": "is happy",
    "Bird": "is a bird",
    "CanFly": "can fly",
    "Loves": "loves",
    "Teaches": "teaches",
    "Knows": "knows",
    "Likes": "likes",
    "ParentOf": "is the parent of",
    "FriendOf": "is a friend of",
    "GreaterThan": "is greater than",
    "Equals": "is equal to",
}


class FOLToNLConverter:
    def __init__(self, formula: str):
        self._formula = formula.strip()
        self._position = 0
        self._bindings: Dict[str, Tuple[str, str, bool]] = {}
        self._binding_stack: List[str] = []

    def convert(self) -> str:
        if not self._formula:
            raise ConversionError("empty formula")
        result = self._parse_formula()
        self._skip_whitespace()
        if self._position != len(self._formula):
            raise ConversionError("unexpected trailing characters")
        return self._finalize_sentence(result)

    def _parse_formula(self) -> str:
        self._skip_whitespace()
        if self._position >= len(self._formula):
            raise ConversionError("unexpected end of formula")

        char = self._formula[self._position]
        if char == "∀":
            return self._parse_universal()
        if char == "∃":
            return self._parse_existential()
        if char == "¬":
            self._position += 1
            return "it is not the case that " + self._parse_formula()
        if char == "(":
            self._position += 1
            result = self._parse_compound_formula()
            self._expect(")")
            return result
        return self._parse_atomic()

    def _parse_universal(self) -> str:
        self._position += 1  # skip ∀
        variable = self._consume_variable()
        self._skip_whitespace()
        with self._bind_variable(variable, kind="universal") as intro:
            body = None
            if self._position < len(self._formula) and self._formula[self._position] == "(":
                self._position += 1
                body = self._parse_compound_formula()
                self._expect(")")
            elif self._position < len(self._formula):
                body = self._parse_formula()
            return f"{intro}, {body}" if body else intro

    def _parse_existential(self) -> str:
        self._position += 1  # skip ∃
        variable = self._consume_variable()
        self._skip_whitespace()
        with self._bind_variable(variable, kind="existential") as intro:
            body = None
            if self._position < len(self._formula) and self._formula[self._position] == "(":
                self._position += 1
                body = self._parse_compound_formula()
                self._expect(")")
            elif self._position < len(self._formula):
                body = self._parse_formula()
            suffix = f" such that {body}" if body else ""
            return intro + suffix

    def _parse_compound_formula(self) -> str:
        left = self._parse_subformula()
        self._skip_whitespace()

        if self._position >= len(self._formula):
            return left

        char = self._formula[self._position]
        if char == "∧":
            self._position += 1
            right = self._parse_subformula()
            return f"{left} and {right}"
        if char == "∨":
            self._position += 1
            right = self._parse_subformula()
            return f"{left} or {right}"
        if char == "→":
            self._position += 1
            right = self._parse_subformula()
            return f"if {left}, then {right}"
        if char == "↔":
            self._position += 1
            right = self._parse_subformula()
            return f"{left} if and only if {right}"

        return left

    def _parse_subformula(self) -> str:
        self._skip_whitespace()
        if self._position >= len(self._formula):
            raise ConversionError("unexpected end of subformula")

        if self._formula[self._position] == "(":
            self._position += 1
            result = self._parse_compound_formula()
            self._expect(")")
            return result

        return self._parse_atomic()

    def _parse_atomic(self) -> str:
        predicate = self._consume_identifier()
        natural_predicate = PREDICATE_MAP.get(predicate, predicate.lower())

        self._skip_whitespace()
        if self._position >= len(self._formula) or self._formula[self._position] != "(":
            return natural_predicate

        self._position += 1
        args = self._consume_arguments()
        if len(args) == 1:
            subject, plural = self._format_term(args[0], role="subject")
            return self._render_unary(subject, natural_predicate, plural)
        if len(args) == 2:
            subject, plural = self._format_term(args[0], role="subject")
            obj, _ = self._format_term(args[1], role="object")
            return f"{subject} {self._render_binary_verb(natural_predicate, plural)} {obj}"
        formatted_args = [self._format_term(arg)[0] for arg in args]
        return f"{natural_predicate} {', '.join(formatted_args)}"

    def _consume_arguments(self) -> List[str]:
        args: List[str] = []
        current = []
        while self._position < len(self._formula):
            char = self._formula[self._position]
            if char == ")":
                if current:
                    args.append("".join(current).strip())
                    current.clear()
                self._position += 1
                break
            if char == ",":
                args.append("".join(current).strip())
                current = []
                self._position += 1
                self._skip_whitespace()
                continue
            current.append(char)
            self._position += 1
        else:
            raise ConversionError("arguments list not terminated")
        return args

    def _consume_identifier(self) -> str:
        start = self._position
        while self._position < len(self._formula) and self._formula[self._position].isalpha():
            self._position += 1
        if start == self._position:
            raise ConversionError("expected identifier")
        return self._formula[start:self._position]

    def _consume_variable(self) -> str:
        if self._position >= len(self._formula) or not self._formula[self._position].isalpha():
            raise ConversionError("expected variable")
        variable = self._formula[self._position]
        self._position += 1
        return variable

    def _expect(self, char: str) -> None:
        self._skip_whitespace()
        if self._position >= len(self._formula) or self._formula[self._position] != char:
            raise ConversionError(f"expected '{char}'")
        self._position += 1

    def _skip_whitespace(self) -> None:
        while self._position < len(self._formula) and self._formula[self._position].isspace():
            self._position += 1

    def _format_term(self, term: str, role: str = "subject") -> Tuple[str, bool]:
        term = term.strip()
        if not term:
            return term, False
        if len(term) == 1 and term.islower():
            binding = self._bindings.get(term)
            if binding:
                subject, obj, plural = binding
                return (subject if role == "subject" else obj, plural)
            return term, False
        return self._format_constant(term), False

    def _format_constant(self, term: str) -> str:
        if not term:
            return term
        if term.islower():
            return term.capitalize()
        return term

    def _render_unary(self, subject: str, predicate: str, plural: bool) -> str:
        if predicate.startswith("is "):
            copula = "are" if plural else "is"
            return f"{subject} {copula}{predicate[2:]}"
        return f"{subject} {predicate}"

    def _render_binary_verb(self, predicate: str, plural: bool) -> str:
        if predicate.startswith("is "):
            copula = "are" if plural else "is"
            return f"{copula}{predicate[2:]}"
        if plural:
            return self._pluralize_verb(predicate)
        return predicate

    def _pluralize_verb(self, verb: str) -> str:
        if verb.endswith("ies"):
            return verb[:-3] + "y"
        if verb.endswith("ses") or verb.endswith("xes") or verb.endswith("zes"):
            return verb[:-2]
        if verb.endswith("ches") or verb.endswith("shes"):
            return verb[:-2]
        if verb.endswith("es"):
            return verb[:-1]
        if verb.endswith("s") and not verb.endswith("ss"):
            return verb[:-1]
        return verb

    @contextmanager
    def _bind_variable(self, variable: str, *, kind: str) -> Iterator[str]:
        if kind == "universal":
            intro = "For every individual"
            binding = ("they", "them", True)
        else:
            intro = "there exists someone"
            binding = ("they", "them", True)
        self._bindings[variable] = binding
        self._binding_stack.append(variable)
        try:
            yield intro
        finally:
            self._binding_stack.pop()
            self._bindings.pop(variable, None)

    def _finalize_sentence(self, text: str) -> str:
        text = text.strip()
        if not text:
            return text
        if not text[0].isupper():
            text = text[0].upper() + text[1:]
        if not text.endswith("."):
            text += "."
        return text


def convert_fol_to_natural_language(formula: str) -> str:
    """High-level helper for translating a FOL formula to natural language."""
    return FOLToNLConverter(formula).convert()


__all__ = ["ConversionError", "FOLToNLConverter", "convert_fol_to_natural_language"]
