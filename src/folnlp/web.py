"""Flask web UI providing a Duolingo-style block translation challenge."""

from __future__ import annotations

import random
import re
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Optional

from flask import Flask, Response, jsonify, request

from .translator import TranslationError, translate_fol_to_nl, translate_nl_to_fol

MODE_NL_TO_FOL = "nl-to-fol"
MODE_FOL_TO_NL = "fol-to-nl"
MODE_MIXED = "mixed"

MODE_LABELS = {
    MODE_NL_TO_FOL: "NL → FOL",
    MODE_FOL_TO_NL: "FOL → NL",
}

MODE_INSTRUCTIONS = {
    MODE_NL_TO_FOL: "Arrange the blocks to build the matching logical formula.",
    MODE_FOL_TO_NL: "Arrange the blocks to build the matching natural-language sentence.",
}

LOGIC_SYMBOLS = {"¬", "∧", "∨", "→", "↔", "(", ")", ",", ";"}

EXAMPLES = [
    {"nl": "Every human is mortal", "fol": "∀x(Human(x) → Mortal(x))"},
    {"nl": "Socrates is human", "fol": "Human(socrates)"},
    {"nl": "Some student is happy", "fol": "∃x(Student(x) ∧ Happy(x))"},
    {"nl": "All birds can fly", "fol": "∀x(Bird(x) → CanFly(x))"},
    {"nl": "No student is a teacher", "fol": "¬∃x(Student(x) ∧ Teacher(x))"},
    {"nl": "If socrates is human then socrates is mortal", "fol": "(Human(socrates) → Mortal(socrates))"},
    {"nl": "Alice loves Bob", "fol": "Loves(alice, bob)"},
    {"nl": "Every philosopher is wise", "fol": "∀x(Philosopher(x) → Wise(x))"},
]


def tokenize_fol_answer(formula: str) -> List[str]:
    tokens: List[str] = []
    buffer: List[str] = []
    i = 0
    while i < len(formula):
        char = formula[i]
        if char.isspace():
            if buffer:
                tokens.append("".join(buffer))
                buffer.clear()
            i += 1
            continue
        if char in {"∀", "∃"}:
            if buffer:
                tokens.append("".join(buffer))
                buffer.clear()
            j = i + 1
            token = char
            while j < len(formula) and formula[j].islower():
                token += formula[j]
                j += 1
            tokens.append(token)
            i = j
            continue
        if char in LOGIC_SYMBOLS:
            if buffer:
                tokens.append("".join(buffer))
                buffer.clear()
            tokens.append(char)
            i += 1
            continue
        buffer.append(char)
        i += 1
    if buffer:
        tokens.append("".join(buffer))
    return tokens


def tokenize_natural_language(sentence: str) -> List[str]:
    if not sentence:
        return []
    return re.findall(r"[A-Za-z']+|[0-9]+|[^\w\s]", sentence)


def tokenize_for_mode(text: str, mode: str) -> List[str]:
    if mode == MODE_NL_TO_FOL:
        return tokenize_fol_answer(text)
    return tokenize_natural_language(text)


def _assemble_fol(tokens: List[str]) -> str:
    result = ""
    for token in tokens:
        if not result:
            result = token
        elif token in {")",
            ",",
            ";",
        }:
            result = result.rstrip() + token
        elif token == "(":
            if result and result[-1] not in {"(", "¬", " "}:
                result = result.rstrip()
            result += "("
        elif token == "¬":
            if result and result[-1] not in {"(", " "}:
                result = result.rstrip() + " "
            result += "¬"
        elif token in {"∧", "∨", "→", "↔"}:
            result = result.rstrip() + f" {token} "
        else:
            if result and result[-1] not in {"(", "¬", " "}:
                result += " "
            result += token
    result = " ".join(result.split())
    result = result.replace(" (", "(")
    result = result.replace(" )", ")")
    result = result.replace(" ,", ",")
    return result.strip()


def _assemble_nl(tokens: List[str]) -> str:
    result = ""
    for token in tokens:
        if not result:
            result = token
        elif token in {".", ",", ";", ":", "?", "!", ")"}:
            result = result.rstrip() + token
        elif token in {"(", "[", "{"}:
            result += " " + token
        else:
            result += " " + token
    return result.strip()


def assemble_for_mode(tokens: List[str], mode: str) -> str:
    return _assemble_fol(tokens) if mode == MODE_NL_TO_FOL else _assemble_nl(tokens)


@dataclass
class StoredChallenge:
    mode: str
    answer_order: List[str]
    id_to_token: Dict[str, str]
    expected_text: str
    token_count: int


class ChallengeManager:
    """Tracks generated block challenges so they can be validated."""

    def __init__(self, *, max_entries: int = 64) -> None:
        self._lock = Lock()
        self._store: "OrderedDict[str, StoredChallenge]" = OrderedDict()
        self._max_entries = max_entries

    def create_challenge(self, *, forced_mode: Optional[str] = None) -> Dict[str, object]:
        example = random.choice(EXAMPLES)
        if forced_mode in {None, MODE_MIXED}:
            mode = random.choice([MODE_NL_TO_FOL, MODE_FOL_TO_NL])
        else:
            mode = forced_mode
        prompt = example["nl"] if mode == MODE_NL_TO_FOL else example["fol"]
        answer = example["fol"] if mode == MODE_NL_TO_FOL else example["nl"]
        tokens = tokenize_for_mode(answer, mode)

        answer_order: List[str] = []
        id_to_token: Dict[str, str] = {}
        token_payload: List[Dict[str, str]] = []
        for token in tokens:
            token_id = uuid.uuid4().hex
            answer_order.append(token_id)
            id_to_token[token_id] = token
            token_payload.append({"id": token_id, "text": token})

        shuffled_payload = token_payload[:]
        random.shuffle(shuffled_payload)

        challenge_id = uuid.uuid4().hex
        stored = StoredChallenge(
            mode=mode,
            answer_order=answer_order,
            id_to_token=id_to_token,
            expected_text=assemble_for_mode(tokens, mode),
            token_count=len(tokens),
        )

        with self._lock:
            self._store[challenge_id] = stored
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

        return {
            "id": challenge_id,
            "mode": mode,
            "mode_label": MODE_LABELS[mode],
            "prompt": prompt,
            "instructions": MODE_INSTRUCTIONS[mode],
            "tokens": shuffled_payload,
            "token_count": len(tokens),
        }

    def verify(self, challenge_id: str, selection: List[str]) -> Optional[Dict[str, object]]:
        with self._lock:
            stored = self._store.get(challenge_id)

        if stored is None:
            return None

        if not selection:
            return {
                "correct": False,
                "message": "Select blocks before checking your answer.",
            }

        if any(token_id not in stored.id_to_token for token_id in selection):
            return {
                "correct": False,
                "message": "One or more selected blocks are not part of this challenge.",
            }

        if len(selection) != stored.token_count:
            return {
                "correct": False,
                "message": f"You have used {len(selection)} of {stored.token_count} blocks. Keep going!",
            }

        if selection == stored.answer_order:
            with self._lock:
                self._store.pop(challenge_id, None)
            return {
                "correct": True,
                "message": "Nice work! That matches the expected translation.",
                "expected": stored.expected_text,
                "mode": stored.mode,
            }

        expected_set = set(stored.answer_order)
        if set(selection) != expected_set:
            return {
                "correct": False,
                "message": "Something is missing or extra. Double-check the blocks you used.",
            }

        return {
            "correct": False,
            "message": "Not quite right. Adjust the order of the blocks and try again.",
        }


challenge_manager = ChallengeManager()

app = Flask(__name__)

_INDEX_HTML = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Block Translation Challenge</title>
  <style>
    :root {
      color-scheme: light;
      font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      background: linear-gradient(160deg, #e0f2fe 0%, #eef2ff 40%, #ede9fe 100%);
      color: #111827;
    }
    body {
      margin: 0;
      padding: clamp(1.5rem, 4vw, 3rem) clamp(1rem, 5vw, 3rem) 4rem;
      display: flex;
      justify-content: center;
    }
    .app {
      width: min(960px, 100%);
      display: grid;
      gap: clamp(1.5rem, 3vw, 2.5rem);
    }
    .card {
      background: #ffffff;
      border-radius: 1.1rem;
      box-shadow: 0 22px 60px -32px rgba(79, 70, 229, 0.35);
      padding: clamp(1.4rem, 3vw, 2.2rem);
      display: grid;
      gap: 1.25rem;
    }
    .hero {
      display: grid;
      gap: 0.6rem;
      text-align: left;
    }
    .hero h1 {
      margin: 0;
      font-size: clamp(1.9rem, 5vw, 2.85rem);
      font-weight: 700;
      color: #312e81;
    }
    .hero p {
      margin: 0;
      color: #4338ca;
      font-weight: 500;
    }
    .muted {
      color: #6b7280;
      font-size: 0.95rem;
    }
    .muted.small {
      font-size: 0.85rem;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.35rem 0.9rem;
      border-radius: 999px;
      background: #e0e7ff;
      color: #312e81;
      font-weight: 600;
      font-size: 0.85rem;
    }
    .toggle {
      display: inline-flex;
      padding: 0.4rem;
      border-radius: 999px;
      background: #e0e7ff;
      gap: 0.35rem;
      align-items: center;
      width: fit-content;
    }
    .toggle button {
      flex: 1 1 auto;
      padding: 0.55rem 1.2rem;
      border-radius: 999px;
      border: none;
      background: transparent;
      color: #312e81;
      font-weight: 600;
      cursor: pointer;
      transition: background 140ms ease, color 140ms ease, box-shadow 140ms ease;
    }
    .toggle button.active {
      background: #312e81;
      color: #ffffff;
      box-shadow: 0 10px 20px -16px rgba(49, 46, 129, 0.6);
    }
    .prompt-card {
      background: #eef2ff;
      border: 1px solid #c7d2fe;
      border-radius: 1rem;
      padding: clamp(1rem, 2vw, 1.35rem);
      display: grid;
      gap: 0.55rem;
    }
    .prompt-label {
      text-transform: uppercase;
      font-size: 0.75rem;
      letter-spacing: 0.08em;
      color: #4338ca;
      font-weight: 700;
    }
    .prompt-card p {
      margin: 0;
      font-size: clamp(1.05rem, 2.6vw, 1.3rem);
      font-weight: 600;
      color: #1f2937;
      word-break: break-word;
    }
    .answer-area {
      min-height: 92px;
      display: flex;
      flex-wrap: wrap;
      gap: 0.6rem;
      border: 2px dashed #d1d5db;
      border-radius: 1rem;
      padding: 0.9rem;
      position: relative;
      background: #ffffff;
    }
    .answer-area[data-empty=\"true\"]::before {
      content: attr(data-placeholder);
      color: #9ca3af;
      font-size: 0.95rem;
      position: absolute;
      left: 1rem;
      top: 1rem;
      pointer-events: none;
    }
    .block-pool {
      display: flex;
      flex-wrap: wrap;
      gap: 0.6rem;
    }
    .block-button {
      padding: 0.6rem 1.15rem;
      border-radius: 999px;
      font-weight: 600;
      border: none;
      cursor: pointer;
      transition: transform 140ms ease, box-shadow 140ms ease, background 140ms ease;
    }
    .block-button.available {
      background: #e0e7ff;
      color: #312e81;
    }
    .block-button.available:hover {
      transform: translateY(-1px);
      box-shadow: 0 12px 28px -24px rgba(79, 70, 229, 0.7);
      background: #c7d2fe;
    }
    .block-button.selected {
      background: #4f46e5;
      color: #ffffff;
    }
    .actions {
      display: flex;
      gap: 0.8rem;
      flex-wrap: wrap;
    }
    button.action {
      display: inline-flex;
      justify-content: center;
      align-items: center;
      font-size: 1rem;
      font-weight: 600;
      border-radius: 999px;
      padding: 0.75rem 1.9rem;
      border: none;
      cursor: pointer;
      transition: transform 140ms ease, box-shadow 140ms ease, background 140ms ease;
    }
    button.action.primary {
      background: #34d399;
      color: #064e3b;
      box-shadow: 0 18px 36px -24px rgba(52, 211, 153, 0.6);
    }
    button.action.secondary {
      background: #e0e7ff;
      color: #312e81;
    }
    button.action.ghost {
      background: transparent;
      color: #4338ca;
      border: 1px dashed rgba(99, 102, 241, 0.45);
    }
    button.action:disabled {
      opacity: 0.55;
      cursor: not-allowed;
      transform: none;
      box-shadow: none;
    }
    button.action:not(:disabled):hover {
      transform: translateY(-1px);
      box-shadow: 0 18px 38px -30px rgba(59, 130, 246, 0.85);
    }
    .feedback {
      min-height: 2.75rem;
      border-radius: 0.95rem;
      padding: 0.9rem 1.1rem;
      font-size: 0.95rem;
      line-height: 1.45;
      display: flex;
      align-items: center;
      word-break: break-word;
    }
    .feedback.success {
      background: #ecfdf5;
      border: 1px solid #bbf7d0;
      color: #166534;
    }
    .feedback.error {
      background: #fef2f2;
      border: 1px solid #fecaca;
      color: #b91c1c;
    }
    .feedback.info {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      color: #1e3a8a;
    }
    @media (max-width: 768px) {
      body {
        padding: 1.75rem 1rem 3.5rem;
      }
      .actions {
        justify-content: stretch;
      }
      button.action {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <div class=\"app\">
    <header class=\"hero\">
      <h1>Block Translation Challenge</h1>
      <p>Choose a mode, assemble the tiles, and check your first-order logic instincts.</p>
    </header>

    <section class=\"card\">
      <span class=\"muted\">Practice mode</span>
      <div class=\"toggle\" role=\"group\" aria-label=\"Select practice mode\">
        <button id=\"mode-nl2fol\" aria-pressed=\"false\">NL → FOL</button>
        <button id=\"mode-fol2nl\" aria-pressed=\"false\">FOL → NL</button>
        <button id=\"mode-mixed\" class=\"active\" aria-pressed=\"true\">Mixed</button>
      </div>
      <p class=\"muted small\">Mixed mode alternates randomly between natural-language prompts and logical formulas.</p>
    </section>

    <section class=\"card\" id=\"challenge-card\">
      <div style=\"display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;\">
        <span id=\"challenge-mode\" class=\"badge\">NL → FOL</span>
        <span id=\"challenge-instructions\" class=\"muted\"></span>
      </div>
      <div class=\"prompt-card\">
        <span class=\"prompt-label\">Prompt</span>
        <p id=\"challenge-prompt\"></p>
      </div>
      <div id=\"challenge-answer\" class=\"answer-area\" data-empty=\"true\" data-placeholder=\"Tap blocks to start building your answer.\"></div>
      <div id=\"challenge-pool\" class=\"block-pool\"></div>
      <div class=\"actions\">
        <button id=\"challenge-check\" class=\"action primary\">Check answer</button>
        <button id=\"challenge-clear\" class=\"action secondary\">Clear</button>
        <button id=\"challenge-new\" class=\"action ghost\">New challenge</button>
      </div>
      <div id=\"challenge-feedback\" class=\"feedback\"></div>
      <div id=\"challenge-expected\" class=\"feedback info\" hidden></div>
    </section>
  </div>

  <script>
    const MODE = {
      NL2FOL: 'nl-to-fol',
      FOL2NL: 'fol-to-nl',
      MIXED: 'mixed'
    };

    const modeButtons = {
      [MODE.NL2FOL]: document.querySelector('#mode-nl2fol'),
      [MODE.FOL2NL]: document.querySelector('#mode-fol2nl'),
      [MODE.MIXED]: document.querySelector('#mode-mixed')
    };

    const state = {
      selectedMode: MODE.MIXED,
      challengeId: null,
      challengeMode: MODE.NL2FOL,
      tokens: [],
      selected: [],
      placeholder: 'Tap blocks to start building your answer.'
    };

    const challengeMode = document.querySelector('#challenge-mode');
    const challengeInstructions = document.querySelector('#challenge-instructions');
    const challengePrompt = document.querySelector('#challenge-prompt');
    const challengeAnswer = document.querySelector('#challenge-answer');
    const challengePool = document.querySelector('#challenge-pool');
    const challengeFeedback = document.querySelector('#challenge-feedback');
    const challengeExpected = document.querySelector('#challenge-expected');
    const checkButton = document.querySelector('#challenge-check');
    const clearButton = document.querySelector('#challenge-clear');
    const newButton = document.querySelector('#challenge-new');

    function resetFeedback() {
      challengeFeedback.textContent = '';
      challengeFeedback.className = 'feedback';
      challengeExpected.textContent = '';
      challengeExpected.hidden = true;
      challengeExpected.className = 'feedback info';
    }

    function placeholderForMode(mode) {
      return mode === MODE.NL2FOL
        ? 'Tap blocks to assemble the logical formula.'
        : 'Tap blocks to assemble the sentence.';
    }

    function renderBlocks() {
      challengeAnswer.innerHTML = '';
      challengePool.innerHTML = '';
      challengeAnswer.dataset.placeholder = state.placeholder;

      if (state.selected.length === 0) {
        challengeAnswer.dataset.empty = 'true';
      } else {
        challengeAnswer.dataset.empty = 'false';
        state.selected.forEach((token, index) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'block-button selected';
          button.textContent = token.text;
          button.addEventListener('click', () => {
            state.selected.splice(index, 1);
            const original = state.tokens.find((item) => item.id === token.id);
            if (original) {
              original.used = false;
            }
            renderBlocks();
            resetFeedback();
          });
          challengeAnswer.appendChild(button);
        });
      }

      const available = state.tokens.filter((token) => !token.used);
      if (available.length === 0) {
        const info = document.createElement('p');
        info.className = 'muted small';
        info.textContent = state.tokens.length ? 'All blocks are in use.' : 'Loading blocks…';
        challengePool.appendChild(info);
      } else {
        available.forEach((token) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'block-button available';
          button.textContent = token.text;
          button.addEventListener('click', () => {
            token.used = true;
            state.selected.push(token);
            renderBlocks();
            resetFeedback();
          });
          challengePool.appendChild(button);
        });
      }
    }

    function selectMode(mode) {
      state.selectedMode = mode;
      Object.entries(modeButtons).forEach(([key, button]) => {
        const active = key === mode;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', String(active));
      });
      loadChallenge();
    }

    async function loadChallenge() {
      checkButton.disabled = true;
      newButton.disabled = true;
      resetFeedback();

      state.challengeId = null;
      state.tokens = [];
      state.selected = [];
      challengeAnswer.dataset.empty = 'true';
      challengeAnswer.innerHTML = '';
      challengePool.innerHTML = '';
      const loading = document.createElement('p');
      loading.className = 'muted small';
      loading.textContent = 'Loading blocks…';
      challengePool.appendChild(loading);

      try {
        const response = await fetch(`/api/practice?mode=${encodeURIComponent(state.selectedMode)}`);
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.error || 'Unable to load a challenge.');
        }
        const challenge = data.challenge;
        state.challengeId = challenge.id;
        state.challengeMode = challenge.mode;
        state.tokens = challenge.tokens.map((token) => ({ ...token, used: false }));
        state.selected = [];
        state.placeholder = placeholderForMode(challenge.mode);
        challengeMode.textContent = challenge.mode_label;
        challengeInstructions.textContent = challenge.instructions;
        challengePrompt.textContent = challenge.prompt;
        renderBlocks();
        checkButton.disabled = false;
      } catch (error) {
        challengeFeedback.textContent = error.message;
        challengeFeedback.className = 'feedback error';
      } finally {
        newButton.disabled = false;
      }
    }

    async function checkAnswer() {
      if (!state.challengeId) {
        return;
      }
      checkButton.disabled = true;
      resetFeedback();
      try {
        const response = await fetch('/api/practice/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            challenge_id: state.challengeId,
            tokens: state.selected.map((token) => token.id)
          })
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.error || 'Unable to check the answer.');
        }
        challengeFeedback.textContent = data.message;
        challengeFeedback.className = data.correct ? 'feedback success' : 'feedback error';
        if (data.correct && data.expected) {
          challengeExpected.textContent = data.expected;
          challengeExpected.hidden = false;
        }
        if (!data.correct) {
          checkButton.disabled = false;
        }
      } catch (error) {
        challengeFeedback.textContent = error.message;
        challengeFeedback.className = 'feedback error';
        checkButton.disabled = false;
      }
    }

    function clearSelection() {
      state.selected.forEach((token) => {
        const original = state.tokens.find((item) => item.id === token.id);
        if (original) {
          original.used = false;
        }
      });
      state.selected = [];
      renderBlocks();
      resetFeedback();
    }

    modeButtons[MODE.NL2FOL].addEventListener('click', () => selectMode(MODE.NL2FOL));
    modeButtons[MODE.FOL2NL].addEventListener('click', () => selectMode(MODE.FOL2NL));
    modeButtons[MODE.MIXED].addEventListener('click', () => selectMode(MODE.MIXED));

    checkButton.addEventListener('click', checkAnswer);
    clearButton.addEventListener('click', clearSelection);
    newButton.addEventListener('click', () => {
      clearSelection();
      loadChallenge();
    });

    // initial render
    renderBlocks();
    loadChallenge();
  </script>
</body>
</html>
"""


def _translate(func, payload: Optional[str]):
    if payload is None:
        raise TranslationError("request body must be JSON with a 'text' key")
    return func(payload)


@app.get("/")
def index() -> Response:
    return Response(_INDEX_HTML, mimetype="text/html")


@app.get("/api/practice")
def practice_challenge():
    mode = request.args.get("mode", MODE_MIXED)
    if mode not in {MODE_MIXED, MODE_NL_TO_FOL, MODE_FOL_TO_NL}:
        return jsonify({"ok": False, "error": "Unknown practice mode."}), 400
    challenge = challenge_manager.create_challenge(forced_mode=mode)
    return jsonify({"ok": True, "challenge": challenge})


@app.post("/api/practice/verify")
def practice_verify():
    payload = request.get_json(silent=True) or {}
    challenge_id = payload.get("challenge_id")
    tokens = payload.get("tokens")

    if not isinstance(challenge_id, str) or not isinstance(tokens, list):
        return jsonify({"ok": False, "error": "Invalid request payload."}), 400

    selection: List[str] = []
    for token_id in tokens:
        if not isinstance(token_id, str):
            return jsonify({"ok": False, "error": "Token identifiers must be strings."}), 400
        selection.append(token_id)

    result = challenge_manager.verify(challenge_id, selection)
    if result is None:
        return jsonify({"ok": False, "error": "Challenge expired or unknown."}), 404

    return jsonify({"ok": True, **result})


# Retain simple translator API for potential reuse
@app.post("/api/nl-to-fol")
def nl_to_fol_endpoint():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    try:
        result = _translate(translate_nl_to_fol, text)
    except TranslationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "result": result})


@app.post("/api/fol-to-nl")
def fol_to_nl_endpoint():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    try:
        result = _translate(translate_fol_to_nl, text)
    except TranslationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "result": result})


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the Flask development server."""

    app.run(host=host, port=port, debug=False)


__all__ = [
    "app",
    "run",
]
