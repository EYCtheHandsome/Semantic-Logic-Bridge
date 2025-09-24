# Semantic Logic Bridge

Translate between natural-language statements about individuals and their corresponding first-order logic (FOL) formulas. Semantic Logic Bridge bundles a reusable Python library, a batteries-included CLI, and a Duolingo-style practice UI so students and researchers can experiment with symbolic reasoning workflows end-to-end.

## Table of Contents
- [Key Features](#key-features)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Command Line](#command-line)
  - [Python API](#python-api)
  - [Web Playground](#web-playground)
- [How It Works](#how-it-works)
- [Project Layout](#project-layout)
- [Development](#development)
- [Future Ideas](#future-ideas)

## Key Features
- Bidirectional translation between English-like sentences and FOL formulas with clear error reporting.
- Deterministic tokeniser, grammar, and vocabulary layers designed for easy extension.
- Ready-to-run CLI for file-based pipelines or quick shell experiments.
- Flask-powered practice interface that shuffles logic blocks for self-guided drills.
- Pure-Python core—no heavyweight ML dependencies—keeping deployment lightweight.

## Quick Start
Create an isolated environment and install the package in editable mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify the installation:

```bash
python -m folnlp --help
```

Prefer not to install? Prepend `PYTHONPATH=src` and invoke the repo wrapper:

```bash
chmod +x folnlp  # once
./folnlp --help
```

## Usage
### Command Line
Translate natural language to FOL:

```bash
folnlp nl2fol "Every human is mortal"
# → ∀x(Human(x) → Mortal(x))
```

Translate FOL back to natural language:

```bash
folnlp fol2nl "∀x(Human(x) → Mortal(x))"
# → for every x, if x is human then x is mortal
```

Both subcommands accept stdin or files for batch processing:

```bash
folnlp nl2fol -f examples.txt
printf "∀x(Bird(x) → CanFly(x))" | folnlp fol2nl
```

### Python API
```python
from folnlp import translate_nl_to_fol, translate_fol_to_nl

print(translate_nl_to_fol("Some student is happy"))
# ∃x(Student(x) ∧ Happy(x))

print(translate_fol_to_nl("Loves(alice, bob)"))
# alice loves bob
```

Both helpers raise `folnlp.TranslationError` so callers can distinguish invalid user input from other failures.

### Web Playground
Launch the Duolingo-style challenge interface (Flask required):

```bash
folnlp web --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` to practice NL→FOL, FOL→NL, or mixed challenges. Each round shuffles the correct translation into blocks; arrange them, hit **Check answer**, and iterate. The launcher also works via `python -m folnlp web`.

## How It Works
1. The natural-language parser tokenises input, applies a hand-crafted grammar, and emits predicate logic structures.
2. The FOL formatter normalises quantifiers, predicates, and connectives using a controlled vocabulary (`src/folnlp/vocabulary.py`).
3. Conversion helpers (`translator.py`) wrap both directions, surfacing consistent error messages for the CLI, API, and web UI.

This deterministic approach keeps behaviour predictable and testable without requiring statistical models.

## Project Layout
```
folnlp             # Convenience wrapper for running the CLI without installation
src/folnlp/        # Core library package and Flask app
tests/             # CLI and translator unit tests
pyproject.toml     # Build metadata and dependencies
```

## Development
- Python 3.9+ is recommended.
- `pip install -e .[dev]` if you add an extra for linting/testing, or just `pip install -e .` for the core stack.
- Run tests with `pytest` from the repository root.
- Extend the vocabulary in `src/folnlp/vocabulary.py` to support new predicates, constants, or connectives.
- The web UI depends on Flask; the rest of the library runs on the Python standard library.

## Future Ideas
- Add more classroom-ready example corpora and export formats.
- Provide syntax highlighting or visual tree displays in the web UI.
- Ship optional integrations for Jupyter and popular proof assistants.
