"""Tier-calibrated generation with a verified guardrail.

The fine-tuned model receives only the short tier tag it was trained on. Every reply is then checked
against its tier's rules (the same checker used to clean the training data) plus extra runtime guards;
a reply that breaks them is regenerated with the exact reasons, up to MAX_ATTEMPTS times. The student
never sees a rule-breaking reply unless every attempt failed (then the least-bad one is returned and
flagged). "A trained policy plus a verified guardrail."
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ..training.compliance import PLACEHOLDER, check, split_probe
from ..training.tiers import control_system_prompt
from . import ollama_client

MAX_ATTEMPTS = 3
# lower randomness for the strict tiers, so the model stays close to what it learned
TEMPERATURE = {"HUMAN_FIRST": 0.2, "HINT": 0.2, "GUIDED": 0.2, "PROBE": 0.3, "SHARED": 0.3, "EMERGENCY": 0.3}
CODE_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


@dataclass
class GenResult:
    text: str
    tier: str
    attempts: int
    passed: bool
    reasons: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)  # every attempt and why it was rejected

    def to_dict(self) -> dict:
        return asdict(self)


def runtime_guards(tier: str, text: str) -> list[str]:
    """Extra checks the training checker does not do."""
    reasons = []
    if tier == "SHARED":
        for block in CODE_BLOCK.findall(text):
            lines = [l for l in block.splitlines() if l.strip() and not l.strip().startswith(("#", "//", "--"))]
            if len(lines) >= 8 and not PLACEHOLDER.search(block):
                reasons.append("contains a complete code solution; leave the student's part as ___ or a named step")
                break
    if tier == "PROBE":
        parts = split_probe(text)
        if parts and len(parts[1].split()) > 180:
            reasons.append("answer key is too long; keep it to the answer and 2-4 checkpoints")
    return reasons


def repair(tier: str, reasons: list[str]) -> str:
    return (f"That reply breaks the {tier.replace('_', ' ').title()} rules: {'; '.join(reasons)}. "
            f"Rewrite it so it follows the rules exactly. Reply with the rewritten answer only.")


def generate(task: str, tier: str, student_attempt: str | None = None, call=None) -> GenResult:
    """call: optional chat function (tests); defaults to the local Ollama model."""
    call = call or ollama_client.chat
    user = task if not student_attempt else f"{task}\n\nMy attempt so far:\n{student_attempt}"
    messages = [{"role": "system", "content": control_system_prompt(tier)}, {"role": "user", "content": user}]
    best, history = None, []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        text = call(messages, temperature=TEMPERATURE[tier] + 0.15 * (attempt - 1))
        c = check(tier, text, task)
        reasons = list(c.reasons) + runtime_guards(tier, text)
        history.append({"attempt": attempt, "passed": not reasons, "reasons": reasons})
        cand = GenResult(text, tier, attempt, not reasons, reasons, history)
        if not reasons:
            return cand
        if best is None or len(reasons) < len(best.reasons):
            best = cand
        messages = messages + [{"role": "assistant", "content": text}, {"role": "user", "content": repair(tier, reasons)}]
    best.attempts, best.history = MAX_ATTEMPTS, history
    return best


GRADER = ("You are grading a student's answer to a short practice problem. Compare it with the answer key. "
          "Reply with JSON only: {\"pass\": true or false, \"feedback\": \"one or two sentences for the student\"}. "
          "Pass only if the answer meets the key's required points; small wording differences are fine.")


def grade_probe(problem: str, answer_key: str, answer: str, call=None) -> dict:
    import json
    call = call or ollama_client.chat
    msg = f"Problem:\n{problem}\n\nAnswer key:\n{answer_key}\n\nStudent answer:\n{answer}"
    text = call([{"role": "system", "content": GRADER}, {"role": "user", "content": msg}], temperature=0.0)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        data = json.loads(m.group(0)) if m else {}
        return {"pass": bool(data.get("pass")), "feedback": str(data.get("feedback", "")).strip()}
    except Exception:
        passed = bool(re.search(r"\bpass\b[\"']?\s*:\s*true", text, re.I))
        return {"pass": passed, "feedback": text.strip()[:300]}
