"""Evaluation metrics for restart summaries.

The central question is not "does it match a reference" but "does it stay inside the C3 boundary":
  * grounding  - every content word comes from the checkpoint (or from the fixed summary wording),
  * advice     - no advice, suggestions, code or answers,
  * depth      - Low / Medium / High use the right fields,
  * voice      - first person ("I need to") is rewritten as second person ("you need to"),
  * question   - a student's question is repeated, not answered,
  * length     - close to the reference length for the same checkpoint.
ROUGE-L against the synthetic reference is reported only as a sanity check.
"""
from __future__ import annotations

import re

from .textutils import to_you, tokens

ADVICE_PATTERNS = [
    r"\byou (should|could|might want to|may want to|can try|can use|need to consider)\b",
    r"\b(i recommend|i suggest|i would|consider|try to|try using|make sure|best practice|a good idea)\b",
    r"\b(here is|here's|for example|e\.g\.|for instance)\b",
    r"\bthe (answer|solution) is\b",
    r"```",
    r"\b(def |class |select .* from |import |console\.log|function\()",
]
_ADVICE = [re.compile(p, re.IGNORECASE) for p in ADVICE_PATTERNS]


def _norm(text: str) -> str:
    return " ".join(tokens(text))


def grounding(output: str, input_text: str, frame_vocab: set[str]) -> dict:
    known = set(tokens(input_text)) | frame_vocab
    toks = tokens(output)
    ungrounded = [t for t in toks if t not in known]
    return {"n_tokens": len(toks), "ungrounded": ungrounded, "rate": (len(ungrounded) / len(toks)) if toks else 0.0}


def advice_hits(output: str, input_text: str = "") -> list[str]:
    """Patterns found in the output but not in the student's own text (what the student wrote is never 'advice')."""
    return [p.pattern for p in _ADVICE if p.search(output) and not p.search(input_text)]


def contains_text(output: str, field_text: str | None) -> bool:
    """True if the field appears in the output, as written or with first person rewritten as second person."""
    if not field_text:
        return False
    out = _norm(output)
    return _norm(to_you(field_text)) in out or _norm(field_text) in out


FIRST_PERSON = {"i", "my", "me", "mine", "myself", "i'm", "i've", "i'll", "i'd"}


def first_person_words(output: str) -> list[str]:
    """First-person words left in the output (the summary should be written to the student as 'you')."""
    return [t for t in tokens(output) if t in FIRST_PERSON]


def depth_policy(output: str, fields: dict, level: str) -> dict:
    """Low: only working point + next step. Medium: adds goal and problem. High: adds completed, resources, open items."""
    allowed = {"Low": {"working_point", "next_step"},
               "Medium": {"working_point", "next_step", "goal", "problem"},
               "High": {"working_point", "next_step", "goal", "problem", "completed", "resources", "open_items"}}[level]
    expected = {k for k in allowed if fields.get(k)}
    present, leaked = set(), set()
    for key in ("goal", "completed", "working_point", "problem", "next_step", "resources"):
        if contains_text(output, fields.get(key)):
            present.add(key)
    items = fields.get("open_items") or []
    # A short item such as "conclusion" can occur inside another sentence, so the list is recognised by its heading.
    heading = "still open in your files" in _norm(output) or "open items found in your own files" in _norm(output)
    if heading and (not items or all(contains_text(output, i) for i in items)):
        present.add("open_items")
    for key in ("goal", "completed", "working_point", "problem", "next_step", "resources", "open_items"):
        if key in present and key not in allowed:
            leaked.add(key)
    missing = expected - present
    return {"missing": sorted(missing), "leaked": sorted(leaked), "ok": not missing and not leaked}


def question_handling(output: str, fields: dict, level: str, input_text: str = "") -> dict | None:
    """Only defined when a question was written and the level should mention it."""
    q = fields.get("problem")
    if not q or not q.strip().endswith("?") or level == "Low":
        return None
    restated = contains_text(output, q)
    answered = bool(advice_hits(output, input_text))
    return {"restated": restated, "answered": answered, "ok": restated and not answered}


def length_ok(output: str, reference: str, lo: float = 0.5, hi: float = 1.6) -> bool:
    n, r = len(output.split()), len(reference.split())
    return r > 0 and lo * r <= n <= hi * r


def rouge_l(candidate: str, reference: str) -> float:
    a, b = tokens(candidate), tokens(reference)
    if not a or not b:
        return 0.0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, start=1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
        prev = cur
    lcs = prev[-1]
    if lcs == 0:
        return 0.0
    p, r = lcs / len(a), lcs / len(b)
    return 2 * p * r / (p + r)


def score_example(output: str, row: dict, frame_vocab: set[str]) -> dict:
    g = grounding(output, row["input"], frame_vocab)
    pol = depth_policy(output, row["fields"], row["level"])
    q = question_handling(output, row["fields"], row["level"], row["input"])
    hits = advice_hits(output, row["input"])
    return {
        "ungrounded_rate": g["rate"],
        "grounded_ok": g["rate"] <= 0.02,
        "advice": hits,
        "no_advice": not hits,
        "policy_ok": pol["ok"],
        "second_person_ok": not first_person_words(output),
        "question_ok": None if q is None else q["ok"],
        "length_ok": length_ok(output, row["output"]),
        "rouge_l": rouge_l(output, row["output"]),
    }
