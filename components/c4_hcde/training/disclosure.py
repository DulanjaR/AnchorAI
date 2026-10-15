"""Solution Disclosure Score (SDS): how much of the solution a reply gives away, from 0 to 1.

Two judge steps, both with temperature 0:

1. From a task's full reference solution (its EMERGENCY reply), extract the 3-8 key solution
   elements: the pieces of reasoning or code a student would otherwise have to produce.
2. For any reply, mark each element as not revealed (0), partly revealed (0.5) or fully
   revealed (1). SDS = the mean.

SDS turns "how much help" into a number: each tier has a target band (tiers.DISCLOSURE_BANDS),
and the evaluation checks that SDS rises with the tier. Asking a guiding question about an
element does not count as revealing it; stating it does.
"""
from __future__ import annotations

import json
import os
import re

from .tiers import DISCLOSURE_BANDS

ELEMENTS_PROMPT = """Below is a student's task and a complete reference solution.
List the key solution elements: the 3 to 6 distinct things a student would have to work out
themselves to solve the task (the key idea, the essential steps, the final answer).
Rules:
- Describe WHAT must be achieved, not one particular implementation. If the task can be solved
  in several valid ways, phrase each element so that any valid method satisfies it
  (write "select only the even numbers", not "use range with a step of 2").
- No duplicates, no trivial elements (such as naming a parameter), no restating the task.
- Each element is one short sentence, specific to this task.

Task:
{task}

Reference solution:
{reference}

Answer with a JSON array of strings only."""

SCORE_PROMPT = """A study assistant replied to a student's task. Decide how much of each key
solution element the reply REVEALS to the student.

- 0 = not revealed (absent, or only asked about as a question, or only named as a general topic)
- 0.5 = partly revealed (the direction is given but the student still has to work it out)
- 1 = fully revealed (stated, shown in code, or given as the answer)
If the reply uses a different valid method, judge whether it reveals the EQUIVALENT step.

Task:
{task}

Key solution elements:
{elements}

Assistant reply:
{reply}

Answer with JSON only: {{"scores": [one number per element, in order]}}"""


def _judge_config() -> tuple[str, str, str]:
    base_url = os.environ.get("TEACHER_BASE_URL", "")
    key = os.environ.get("TEACHER_API_KEY", "")
    model = os.environ.get("JUDGE_MODEL") or os.environ.get("TEACHER_MODEL", "")
    return base_url, key, model


def _json(text: str):
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON in judge output: {text[:200]!r}")
    return json.loads(m.group(1))


def extract_elements(task: str, reference: str, ask=None) -> list[str]:
    from .build_dataset import chat

    ask = ask or (lambda prompt: chat(*_judge_config(), [{"role": "user", "content": prompt}], 0.0, 600))
    data = _json(ask(ELEMENTS_PROMPT.format(task=task, reference=reference)))
    if isinstance(data, dict):  # some models wrap the array
        data = next(iter(data.values()))
    elements = [str(e).strip() for e in data if str(e).strip()]
    if not 1 <= len(elements) <= 12:
        raise ValueError(f"judge returned {len(elements)} elements")
    return elements


def score_reply(task: str, elements: list[str], reply: str, ask=None) -> list[float]:
    from .build_dataset import chat

    ask = ask or (lambda prompt: chat(*_judge_config(), [{"role": "user", "content": prompt}], 0.0, 300))
    numbered = "\n".join(f"{i}. {e}" for i, e in enumerate(elements, 1))
    data = _json(ask(SCORE_PROMPT.format(task=task, elements=numbered, reply=reply)))
    scores = data["scores"] if isinstance(data, dict) else data
    if len(scores) != len(elements):
        raise ValueError(f"judge scored {len(scores)} of {len(elements)} elements")
    return [min(1.0, max(0.0, float(s))) for s in scores]


def summarise_disclosure(tier: str, scores: list[float]) -> dict:
    sds = round(sum(scores) / len(scores), 3)
    lo, hi = DISCLOSURE_BANDS[tier]
    return {"score": sds, "band": [lo, hi], "in_band": lo <= sds <= hi, "element_scores": scores}
