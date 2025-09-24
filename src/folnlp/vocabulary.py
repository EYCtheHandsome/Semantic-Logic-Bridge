"""Vocabulary definitions for the FOL/NL translator."""

QUANTIFIERS = {
    "every": "EVERY",
    "all": "ALL",
    "some": "SOME",
    "exists": "EXISTS",
    "there exists": "EXISTS",
    "no": "NO",
    "for all": "ALL",
    "for every": "EVERY",
}

CONNECTIVES = {
    "and": "AND",
    "or": "OR",
    "not": "NOT",
    "if": "IF",
    "then": "THEN",
    "implies": "THEN",
    "iff": "IFF",
    "if and only if": "IFF",
}

PREDICATES = {
    # Unary predicates
    "human": "Human",
    "mortal": "Mortal",
    "student": "Student",
    "teacher": "Teacher",
    "philosopher": "Philosopher",
    "wise": "Wise",
    "happy": "Happy",
    "bird": "Bird",
    "can fly": "CanFly",
    "flies": "CanFly",
    # Binary predicates
    "loves": "Loves",
    "teaches": "Teaches",
    "knows": "Knows",
    "likes": "Likes",
    "parent of": "ParentOf",
    "friend of": "FriendOf",
    "greater than": "GreaterThan",
    "equals": "Equals",
}

CONSTANTS = {
    "socrates": "socrates",
    "plato": "plato",
    "aristotle": "aristotle",
    "alice": "alice",
    "bob": "bob",
    "john": "john",
    "mary": "mary",
}

AUXILIARIES = {"is", "are", "has", "have", "that", "who", "which", "a", "an", "the"}

__all__ = [
    "QUANTIFIERS",
    "CONNECTIVES",
    "PREDICATES",
    "CONSTANTS",
    "AUXILIARIES",
]
