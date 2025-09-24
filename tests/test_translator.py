"""Regression tests for the high level translation helpers."""

from __future__ import annotations

import os
import sys
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from folnlp import translate_fol_to_nl, translate_nl_to_fol  # noqa: E402


class TranslateNLToFOLTests(unittest.TestCase):
    def test_sentence_with_trailing_period(self) -> None:
        self.assertEqual(translate_nl_to_fol("Socrates is human."), "Human(socrates)")

    def test_no_quantifier_sentence(self) -> None:
        expected = "¬∃x(Student(x) ∧ Teacher(x))"
        self.assertEqual(translate_nl_to_fol("No student is a teacher."), expected)


class TranslateFOLToNLTests(unittest.TestCase):
    def test_universal_quantifier_roundtrip(self) -> None:
        sentence = translate_fol_to_nl("∀x(Human(x) → Mortal(x))")
        self.assertTrue(sentence.startswith("For every individual"))
        self.assertIn("if they are human", sentence)
        self.assertIn("then they are mortal", sentence)


if __name__ == "__main__":
    unittest.main()
