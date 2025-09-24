"""Tokenizer for the natural-language to FOL translator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from .vocabulary import AUXILIARIES, CONNECTIVES, CONSTANTS, PREDICATES, QUANTIFIERS


class TokenType(str, Enum):
    EVERY = "EVERY"
    SOME = "SOME"
    EXISTS = "EXISTS"
    ALL = "ALL"
    NO = "NO"
    NOT = "NOT"
    AND = "AND"
    OR = "OR"
    IF = "IF"
    THEN = "THEN"
    IFF = "IFF"
    IS = "IS"
    NOUN = "NOUN"
    VERB = "VERB"
    ADJECTIVE = "ADJECTIVE"
    VARIABLE = "VARIABLE"
    CONSTANT = "CONSTANT"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    COMMA = "COMMA"
    DOT = "DOT"
    EOF = "EOF"


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str


class Tokenizer:
    """Converts a natural-language sentence into a stream of tokens."""

    def __init__(self, text: str):
        self._text = text.lower().strip()
        self._position = 0
        self._tokens: List[Token] = []
        self._multiword_entries: List[Tuple[str, TokenType, str]] = self._build_multiword_entries()

    def tokenize(self) -> List[Token]:
        while self._position < len(self._text):
            self._skip_whitespace()
            if self._position >= len(self._text):
                break

            if self._match_multiword_phrase():
                continue

            word = self._consume_word()
            if word:
                token = self._classify_word(word)
                if token is not None:
                    self._tokens.append(token)
                continue

            char = self._text[self._position]
            if char == "(":
                self._tokens.append(Token(TokenType.LPAREN, char))
            elif char == ")":
                self._tokens.append(Token(TokenType.RPAREN, char))
            elif char == ",":
                self._tokens.append(Token(TokenType.COMMA, char))
            elif char == ".":
                self._tokens.append(Token(TokenType.DOT, char))
            self._position += 1

        self._tokens.append(Token(TokenType.EOF, ""))
        return list(self._tokens)

    def _build_multiword_entries(self) -> List[Tuple[str, TokenType, str]]:
        entries: List[Tuple[str, TokenType, str]] = []
        for phrase, type_name in QUANTIFIERS.items():
            if " " in phrase:
                entries.append((phrase, TokenType(type_name), phrase))
        for phrase, type_name in CONNECTIVES.items():
            if " " in phrase:
                entries.append((phrase, TokenType(type_name), phrase))
        for phrase, predicate in PREDICATES.items():
            if " " in phrase:
                entries.append((phrase, TokenType.NOUN, predicate))
        entries.sort(key=lambda item: len(item[0]), reverse=True)
        return entries

    def _match_multiword_phrase(self) -> bool:
        for phrase, token_type, value in self._multiword_entries:
            if not self._text.startswith(phrase, self._position):
                continue
            end = self._position + len(phrase)
            if end < len(self._text) and self._text[end].isalpha():
                continue
            self._tokens.append(Token(token_type, value))
            self._position = end
            return True
        return False

    def _consume_word(self) -> str:
        start = self._position
        while self._position < len(self._text) and self._text[self._position].isalpha():
            self._position += 1
        return self._text[start:self._position]

    def _classify_word(self, word: str) -> Optional[Token]:
        if not word:
            return None

        if word in QUANTIFIERS:
            return Token(TokenType(QUANTIFIERS[word]), word)

        if word in CONNECTIVES:
            return Token(TokenType(CONNECTIVES[word]), word)

        if word in PREDICATES:
            return Token(TokenType.NOUN, PREDICATES[word])

        if word in CONSTANTS:
            return Token(TokenType.CONSTANT, CONSTANTS[word])

        if word in AUXILIARIES:
            if word in {"is", "are"}:
                return Token(TokenType.IS, word)
            return None

        if len(word) == 1 and word in {"x", "y", "z"}:
            return Token(TokenType.VARIABLE, word)

        return Token(TokenType.NOUN, word.capitalize())

    def _skip_whitespace(self) -> None:
        while self._position < len(self._text) and self._text[self._position].isspace():
            self._position += 1


def tokenize(text: str) -> List[Token]:
    """Convenience wrapper returning the token list for *text*."""
    return Tokenizer(text).tokenize()


__all__ = ["Token", "TokenType", "Tokenizer", "tokenize"]
