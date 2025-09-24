"""Parser that converts natural language to a FOL string."""

from __future__ import annotations

from typing import Iterable, List

from .tokenizer import Token, TokenType, Tokenizer


class ParseError(ValueError):
    """Raised when the natural-language statement cannot be parsed."""


class NLToFOLParser:
    def __init__(self, tokens: Iterable[Token]):
        self._tokens: List[Token] = list(tokens)
        if not self._tokens:
            self._tokens = [Token(TokenType.EOF, "")]
        self._position = 0
        self._current: Token = self._tokens[0]

    @classmethod
    def from_text(cls, text: str) -> "NLToFOLParser":
        return cls(Tokenizer(text).tokenize())

    def parse(self) -> str:
        result = self._parse_statement()
        while self._current.type is TokenType.DOT:
            self._advance()
        if self._current.type is not TokenType.EOF:
            raise ParseError("unexpected tokens at end of input")
        return result

    def _parse_statement(self) -> str:
        if self._is_quantifier(self._current.type):
            return self._parse_quantified()
        if self._current.type is TokenType.IF:
            return self._parse_conditional()
        if self._current.type is TokenType.NOT:
            self._consume(TokenType.NOT)
            return f"¬({self._parse_statement()})"
        return self._parse_compound()

    def _parse_quantified(self) -> str:
        quantifier_token = self._current
        self._advance()

        variable = "x"
        if self._current.type is TokenType.VARIABLE:
            variable = self._current.value
            self._advance()

        if self._current.type is TokenType.IS:
            self._advance()

        if self._current.type is not TokenType.NOUN:
            raise ParseError("expected predicate after quantifier")
        predicate = self._current.value
        self._advance()

        if quantifier_token.type in {TokenType.EVERY, TokenType.ALL}:
            quantifier = f"∀{variable}"
        elif quantifier_token.type in {TokenType.SOME, TokenType.EXISTS}:
            quantifier = f"∃{variable}"
        elif quantifier_token.type is TokenType.NO:
            quantifier = f"¬∃{variable}"
        else:
            raise ParseError("unsupported quantifier")

        if self._current.type in {TokenType.IS, TokenType.THEN}:
            if self._current.type is TokenType.IS:
                self._advance()
            if self._current.type is TokenType.NOUN:
                consequent = self._current.value
                self._advance()
                if quantifier_token.type in {TokenType.EVERY, TokenType.ALL}:
                    return f"{quantifier}({predicate}({variable}) → {consequent}({variable}))"
                return f"{quantifier}({predicate}({variable}) ∧ {consequent}({variable}))"
            return f"{quantifier}({predicate}({variable}))"

        return f"{quantifier}({predicate}({variable}))"

    def _parse_conditional(self) -> str:
        self._consume(TokenType.IF)
        antecedent = self._parse_compound()
        if self._current.type is TokenType.THEN:
            self._consume(TokenType.THEN)
        consequent = self._parse_compound()
        return f"({antecedent} → {consequent})"

    def _parse_compound(self) -> str:
        left = self._parse_atomic()
        while self._current.type in {TokenType.AND, TokenType.OR}:
            operator = self._current.type
            self._advance()
            right = self._parse_atomic()
            connective = "∧" if operator is TokenType.AND else "∨"
            left = f"({left} {connective} {right})"
        return left

    def _parse_atomic(self) -> str:
        if self._current.type is TokenType.CONSTANT:
            constant = self._current.value
            self._advance()

            if self._current.type is TokenType.IS:
                self._advance()

            if self._current.type is TokenType.NOUN:
                predicate = self._current.value
                self._advance()
                if self._current.type is TokenType.CONSTANT:
                    obj = self._current.value
                    self._advance()
                    return f"{predicate}({constant}, {obj})"
                return f"{predicate}({constant})"

            return constant

        if self._current.type is TokenType.NOUN:
            predicate = self._current.value
            self._advance()

            if self._current.type is TokenType.LPAREN:
                self._advance()
                args: List[str] = []
                while self._current.type is not TokenType.RPAREN:
                    if self._current.type in {TokenType.CONSTANT, TokenType.VARIABLE}:
                        args.append(self._current.value)
                        self._advance()
                    if self._current.type is TokenType.COMMA:
                        self._advance()
                self._consume(TokenType.RPAREN)
                return f"{predicate}({', '.join(args)})"

            return predicate

        raise ParseError(f"unexpected token: {self._current.type}")

    def _is_quantifier(self, token_type: TokenType) -> bool:
        return token_type in {TokenType.EVERY, TokenType.ALL, TokenType.SOME, TokenType.EXISTS, TokenType.NO}

    def _consume(self, expected: TokenType) -> None:
        if self._current.type is not expected:
            raise ParseError(f"expected {expected} but found {self._current.type}")
        self._advance()

    def _advance(self) -> None:
        if self._position < len(self._tokens) - 1:
            self._position += 1
            self._current = self._tokens[self._position]
        else:
            self._current = Token(TokenType.EOF, "")


def parse_natural_language(text: str) -> str:
    """High-level convenience API for parsing natural language into FOL."""
    return NLToFOLParser.from_text(text).parse()


__all__ = ["NLToFOLParser", "ParseError", "parse_natural_language"]
