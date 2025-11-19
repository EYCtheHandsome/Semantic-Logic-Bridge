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
      font-family: 'Nunito', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background-color: #d9f9c6;
      color: #0f172a;
    }
    *, *::before, *::after {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      min-height: 100vh;
      background: radial-gradient(circle at top left, #fafff0 0%, #d8fadb 40%, #c7e8ff 100%);
      display: flex;
      justify-content: center;
      padding: clamp(1.5rem, 4vw, 3.5rem) clamp(0.8rem, 3vw, 2.5rem);
    }
    body::before,
    body::after {
      content: '';
      position: fixed;
      width: 420px;
      height: 420px;
      background: radial-gradient(circle, rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 0));
      z-index: 0;
      pointer-events: none;
    }
    body::before {
      top: -140px;
      left: -120px;
    }
    body::after {
      bottom: -180px;
      right: -100px;
    }
    .app-shell {
      width: min(1080px, 100%);
      display: flex;
      flex-direction: column;
      gap: clamp(1.2rem, 3vw, 2.5rem);
      position: relative;
      z-index: 1;
    }
    .hero-card {
      background: linear-gradient(140deg, #ffffff 0%, #edffe1 80%);
      border-radius: 28px;
      border: 2px solid rgba(88, 204, 2, 0.2);
      box-shadow: 0 30px 85px -45px rgba(21, 94, 7, 0.4);
      padding: clamp(1.2rem, 4vw, 2.6rem);
      display: flex;
      align-items: center;
      gap: clamp(1rem, 3vw, 2.5rem);
      flex-wrap: wrap;
    }
    .hero-avatar {
      width: 120px;
      height: 120px;
      border-radius: 32px;
      background: #58cc02;
      color: #ffffff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: clamp(3.5rem, 6vw, 4.5rem);
      box-shadow: 0 25px 50px -25px rgba(88, 204, 2, 0.7);
    }
    .hero-copy {
      flex: 1 1 260px;
      min-width: 240px;
    }
    .hero-copy h1 {
      margin: 0 0 0.45rem;
      font-size: clamp(1.9rem, 4vw, 2.8rem);
      color: #0b4213;
    }
    .hero-copy p {
      margin: 0;
      color: #1e3a34;
      font-weight: 600;
    }
    .eyebrow {
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 0.75rem;
      color: #3fb10c;
      margin-bottom: 0.25rem;
      font-weight: 700;
    }
    .progress-track {
      margin-top: 1.1rem;
      height: 12px;
      border-radius: 999px;
      background: rgba(15, 23, 42, 0.1);
      overflow: hidden;
      position: relative;
    }
    .progress-fill {
      position: absolute;
      inset: 0;
      background: linear-gradient(90deg, #ffd929, #ff9d0a);
      border-radius: inherit;
    }
    .progress-caption {
      display: block;
      margin-top: 0.35rem;
      font-size: 0.9rem;
      color: #475467;
      font-weight: 600;
    }
    .hero-stats {
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex: 1 0 220px;
      gap: 0.85rem;
      justify-content: space-between;
      flex-wrap: wrap;
    }
    .hero-stats li {
      background: rgba(255, 255, 255, 0.85);
      border-radius: 18px;
      padding: 0.9rem 1.1rem;
      min-width: 140px;
      flex: 1 1 140px;
      border: 1px solid rgba(10, 92, 24, 0.08);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
    }
    .hero-stats .stat-label {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #64748b;
      font-weight: 700;
    }
    .hero-stats .stat-value {
      display: block;
      font-size: 1.35rem;
      font-weight: 700;
      color: #076014;
      margin: 0.2rem 0;
    }
    .hero-stats small {
      color: #64748b;
      font-weight: 600;
    }
    .panel {
      background: rgba(255, 255, 255, 0.92);
      border-radius: 26px;
      padding: clamp(1.2rem, 3vw, 2rem);
      box-shadow: 0 20px 65px -50px rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(15, 23, 42, 0.05);
    }
    .practice-panel {
      display: grid;
      gap: 0.9rem;
    }
    .practice-panel h2 {
      margin: 0;
      font-size: clamp(1.3rem, 3vw, 1.8rem);
    }
    .helper-text {
      margin: 0;
      color: #4b5563;
      font-weight: 600;
      font-size: 0.95rem;
    }
    .mode-toggle {
      display: inline-flex;
      gap: 0.35rem;
      padding: 0.35rem;
      background: rgba(245, 255, 232, 0.7);
      border-radius: 999px;
      border: 1px solid rgba(63, 177, 12, 0.2);
      width: fit-content;
    }
    .mode-toggle button {
      border: none;
      border-radius: 999px;
      padding: 0.65rem 1.55rem;
      background: transparent;
      color: #106b1e;
      font-weight: 700;
      font-size: 0.95rem;
      cursor: pointer;
      transition: background 140ms ease, color 140ms ease, box-shadow 140ms ease;
    }
    .mode-toggle button.active {
      background: linear-gradient(120deg, #58cc02, #4cba00);
      color: #ffffff;
      box-shadow: 0 12px 25px -18px rgba(26, 86, 18, 0.7);
    }
    .mode-toggle button:focus-visible {
      outline: 2px solid #ffd929;
      outline-offset: 2px;
    }
    .challenge-panel {
      display: grid;
      gap: 1rem;
    }
    .challenge-header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 0.75rem;
    }
    .mode-pill {
      padding: 0.55rem 1.45rem;
      border-radius: 999px;
      background: rgba(15, 118, 110, 0.08);
      color: #0f766e;
      font-weight: 700;
      font-size: 0.95rem;
    }
    .challenge-meta {
      display: flex;
      gap: 0.9rem;
      align-items: center;
      flex-wrap: wrap;
    }
    .ghost-link {
      border: none;
      background: transparent;
      font-weight: 700;
      color: #0ea5e9;
      cursor: pointer;
      padding: 0.35rem 0.6rem;
      border-radius: 999px;
      transition: background 140ms ease;
    }
    .ghost-link:hover {
      background: rgba(14, 165, 233, 0.12);
    }
    .ghost-link:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .prompt-card {
      background: linear-gradient(120deg, rgba(14, 165, 233, 0.08), rgba(72, 187, 120, 0.1));
      border-radius: 1.5rem;
      padding: 1rem 1.2rem;
      border: 1px solid rgba(14, 165, 233, 0.15);
    }
    .prompt-label {
      display: block;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #0f766e;
      font-weight: 700;
      margin-bottom: 0.4rem;
    }
    .prompt-card p {
      margin: 0;
      font-size: clamp(1.1rem, 2.6vw, 1.45rem);
      font-weight: 700;
      color: #0f172a;
    }
    .answer-stack {
      display: grid;
      gap: 0.6rem;
    }
    .answer-area {
      min-height: 100px;
      border-radius: 1.3rem;
      border: 2px dashed rgba(15, 23, 42, 0.15);
      padding: 0.9rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      background: rgba(255, 255, 255, 0.9);
      position: relative;
    }
    .answer-area[data-empty="true"]::before {
      content: attr(data-placeholder);
      position: absolute;
      left: 1rem;
      top: 1rem;
      color: #9ca3af;
      font-size: 0.95rem;
      pointer-events: none;
    }
    .block-pool {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      min-height: 70px;
    }
    .block-button {
      border: none;
      border-radius: 30px;
      padding: 0.55rem 1.3rem;
      font-weight: 700;
      font-size: 1rem;
      cursor: pointer;
      transition: transform 140ms ease, box-shadow 140ms ease;
    }
    .block-button.available {
      background: #fff4d6;
      color: #a45c00;
      box-shadow: 0 10px 20px -12px rgba(244, 158, 43, 0.7);
    }
    .block-button.available:hover {
      transform: translateY(-1px);
    }
    .block-button.selected {
      background: #58cc02;
      color: #ffffff;
      box-shadow: 0 10px 25px -15px rgba(88, 204, 2, 0.8);
    }
    .muted {
      color: #4b5563;
    }
    .small {
      font-size: 0.85rem;
    }
    .muted.small {
      color: #6b7280;
    }
    .actions {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
    }
    button.action {
      border: none;
      border-radius: 999px;
      padding: 0.85rem 2rem;
      font-size: 1.05rem;
      font-weight: 700;
      cursor: pointer;
      transition: transform 120ms ease, box-shadow 120ms ease, opacity 120ms ease;
    }
    button.action.primary {
      background: linear-gradient(120deg, #58cc02, #4cb000);
      color: #08330d;
      box-shadow: 0 20px 35px -25px rgba(88, 204, 2, 0.9);
    }
    button.action.secondary {
      background: linear-gradient(120deg, #ffd929, #ffb500);
      color: #723b00;
      box-shadow: 0 18px 30px -24px rgba(255, 160, 0, 0.7);
    }
    button.action:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none;
      box-shadow: none;
    }
    button.action:not(:disabled):hover {
      transform: translateY(-1px);
    }
    .feedback-stack {
      display: grid;
      gap: 0.6rem;
    }
    .feedback {
      min-height: 2.5rem;
      border-radius: 1rem;
      padding: 0.85rem 1rem;
      font-size: 0.95rem;
      font-weight: 600;
      color: #0f172a;
      background: rgba(15, 23, 42, 0.04);
      border: 1px solid transparent;
    }
    .feedback.success {
      background: #ecfdf5;
      border-color: #a7f3d0;
      color: #065f46;
    }
    .feedback.error {
      background: #fef2f2;
      border-color: #fecaca;
      color: #b91c1c;
    }
    .feedback.info {
      background: #eff6ff;
      border-color: #bfdbfe;
      color: #1e3a8a;
    }
    @media (max-width: 720px) {
      body {
        padding: 1.2rem 0.85rem 2rem;
      }
      .hero-card {
        padding: 1.5rem;
      }
      .hero-stats {
        flex-direction: column;
      }
      .actions button {
        flex: 1 1 100%;
      }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <header class="hero-card">
      <div class="hero-avatar" aria-hidden="true">🤖</div>
      <div class="hero-copy">
        <p class="eyebrow">Logic League</p>
        <h1>Semantic Logic Quest</h1>
        <p>Stack the translation tiles to earn XP and keep your streak alive.</p>
        <div class="progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="50" aria-valuenow="34">
          <span class="progress-fill" style="width: 68%;"></span>
        </div>
        <span class="progress-caption">Daily goal · 34 / 50 XP</span>
      </div>
      <ul class="hero-stats">
        <li>
          <span class="stat-label">Hearts</span>
          <span class="stat-value">❤️ ❤️ ❤️ ❤️</span>
          <small>Don't lose them!</small>
        </li>
        <li>
          <span class="stat-label">Streak</span>
          <span class="stat-value">🔥 8</span>
          <small>Days in a row</small>
        </li>
        <li>
          <span class="stat-label">XP Boost</span>
          <span class="stat-value">2×</span>
          <small>Active 13 min</small>
        </li>
      </ul>
    </header>

    <section class="panel practice-panel">
      <div>
        <p class="eyebrow muted">Practice mode</p>
        <h2>Pick your course</h2>
        <p class="muted">Switch between natural-language drills, logic formulas, or mix things up for surprise rounds.</p>
      </div>
      <div class="mode-toggle" role="group" aria-label="Select practice mode">
        <button id="mode-nl2fol" type="button" aria-pressed="false">NL → FOL</button>
        <button id="mode-fol2nl" type="button" aria-pressed="false">FOL → NL</button>
        <button id="mode-mixed" type="button" class="active" aria-pressed="true">Mixed</button>
      </div>
      <p class="helper-text">Mixed keeps you guessing—perfect for streak-safe review.</p>
    </section>

    <section class="panel challenge-panel" id="challenge-card">
      <div class="challenge-header">
        <div id="challenge-mode" class="mode-pill">NL → FOL</div>
        <div class="challenge-meta">
          <span id="challenge-instructions" class="muted"></span>
          <button id="challenge-new" type="button" class="ghost-link">New challenge</button>
        </div>
      </div>
      <div class="prompt-card">
        <span class="prompt-label">Prompt</span>
        <p id="challenge-prompt"></p>
      </div>
      <div class="answer-stack">
        <div id="challenge-answer" class="answer-area" data-empty="true" data-placeholder="Tap blocks to start building your answer."></div>
        <div id="challenge-pool" class="block-pool"></div>
      </div>
      <div class="actions">
        <button id="challenge-check" type="button" class="action primary">Check answer</button>
        <button id="challenge-clear" type="button" class="action secondary">Clear</button>
      </div>
      <div class="feedback-stack">
        <div id="challenge-feedback" class="feedback info"></div>
        <div id="challenge-expected" class="feedback success" hidden></div>
      </div>
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
