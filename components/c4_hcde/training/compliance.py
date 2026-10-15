"""Heuristic tier-compliance checker.

Fast, deterministic checks used in three places: filtering teacher outputs, the /assist
endpoint's guard, and the automatic part of the evaluation. It catches the common failures
(code or full answers leaking into low tiers, low tiers running long, SHARED handing nothing
back). It does not judge correctness; that is what the manual review and the LLM judge are for.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .tiers import PROBE, TIERS

CODE_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
NUMBERED_STEP = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
PLACEHOLDER = re.compile(r"TODO|___|\.\.\.|<your|# your|// your|fill in|your code here|your task", re.IGNORECASE)
INVITE = re.compile(
    r"\?|share (?:your|it)|show me|give it a (?:try|go|shot)|try it|have a go|send me|post your|let me see",
    re.IGNORECASE,
)
HANDBACK = re.compile(
    r"\?|your turn|over to you|you (?:can|could|should) (?:now )?(?:write|implement|complete|add|try|decide)",
    re.IGNORECASE,
)


@dataclass
class ComplianceResult:
    tier: str
    passed: bool
    words: int
    code_lines: int
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "passed": self.passed,
            "words": self.words,
            "code_lines": self.code_lines,
            "reasons": self.reasons,
        }


def _code_lines(text: str) -> int:
    return sum(len([ln for ln in block.strip().splitlines() if ln.strip()]) for block in CODE_BLOCK.findall(text))


def check(tier: str, text: str, task: str | None = None) -> ComplianceResult:
    """Check a reply against its tier. ``task`` (the student's request) enables the probe copy check."""
    if tier == PROBE:
        return _check_probe(text, task)
    spec = TIERS[tier]
    words = len(text.split())
    code_lines = _code_lines(text)
    steps = len(NUMBERED_STEP.findall(text))
    reasons: list[str] = []

    if not text.strip():
        reasons.append("empty reply")
    # Allow 15% slack over the target so the checker flags real overruns, not rounding.
    if words > int(spec.max_words * 1.15):
        reasons.append(f"too long: {words} words (limit {spec.max_words})")

    if tier == "HUMAN_FIRST":
        if code_lines > 0:
            reasons.append("contains code")
        if steps > 0:
            reasons.append("contains numbered steps")
        if not INVITE.search(text):
            reasons.append("does not invite the student's attempt")
    elif tier == "HINT":
        if code_lines > 1:
            reasons.append(f"contains {code_lines} lines of code")
        if steps > 1:
            reasons.append(f"contains {steps} numbered steps (one hint only)")
    elif tier == "GUIDED":
        # blanks must be IN the code; prose like "let's fill in the steps" does not count
        code = "\n".join(CODE_BLOCK.findall(text))
        if code_lines > 6 and not PLACEHOLDER.search(code):
            reasons.append(f"{code_lines} lines of code with no blanks left for the student")
    elif tier == "SHARED":
        if not HANDBACK.search(text):
            reasons.append("does not hand a part back to the student")
    elif tier == "EMERGENCY":
        if words < 30:
            reasons.append("too short to be a full solution")

    return ComplianceResult(tier=tier, passed=not reasons, words=words, code_lines=code_lines, reasons=reasons)


PROBE_PARTS = re.compile(r"^\s*\**Problem:?\**\s*\n(?P<problem>.*?)^\s*\**Answer key:?\**\s*\n(?P<key>.*)",
                         re.DOTALL | re.MULTILINE | re.IGNORECASE)


def split_probe(text: str) -> tuple[str, str] | None:
    """(problem, answer key) from a PROBE output, or None if the format is broken."""
    m = PROBE_PARTS.search(text)
    if not m:
        return None
    return m.group("problem").strip(), m.group("key").strip()


# Words that every programming task shares; ignoring them makes the copy check look at what the
# task is actually about (its data, its goal, its names).
STOPWORDS = set(
    "a an the of to and or in on for with that this these is are be as by it its from using use "
    "without write program function python java code returns return takes take given input inputs "
    "output number numbers all between loop each every your you".split()
)


def _content_words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9_]+", s.lower()) if w not in STOPWORDS}


def similarity(a: str, b: str) -> float:
    """Jaccard overlap of content words: 1.0 = same subject matter, 0 = nothing shared.
    On the trial data, copied probes scored 0.50-0.60 and real variants 0.14."""
    wa, wb = _content_words(a), _content_words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def _check_probe(text: str, task: str | None = None) -> ComplianceResult:
    words = len(text.split())
    reasons: list[str] = []
    parts = split_probe(text)
    if parts is None:
        reasons.append("missing 'Problem:' / 'Answer key:' sections")
    else:
        problem, key = parts
        if len(problem.split()) < 8:
            reasons.append("problem too short")
        if not key:
            reasons.append("empty answer key")
        if task and similarity(problem, task) > 0.4:
            reasons.append(f"probe is too close to the original task (overlap {similarity(problem, task):.2f})")
    if words > 260:
        reasons.append(f"too long: {words} words (limit 220)")
    return ComplianceResult(tier=PROBE, passed=not reasons, words=words, code_lines=_code_lines(text), reasons=reasons)
