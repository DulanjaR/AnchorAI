"""Template restart summary. It only restates the student's own checkpoint text (never adds content).

This is the baseline generator: the learned Qwen model (Model 2) is compared against it.
Mirrors app/static/core.js (checked by shared test vectors).
"""
from __future__ import annotations

from typing import Any

from .difficulty import DEPTH, format_minutes

FIELD_LABELS = {
    "goal": "Goal",
    "completed": "Completed work",
    "workingPoint": "Current working point",
    "problem": "Current problem or decision",
    "nextStep": "Next step",
    "resources": "Files / resources",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def build_summary(task_title: str, checkpoint: dict, level: str, away_minutes: float) -> dict:
    cp = checkpoint or {}
    lines: list[dict] = []

    def add(label: str, text: Any) -> None:
        t = _clean(text)
        if t:
            lines.append({"label": label, "text": t})

    add("You stopped at", cp.get("workingPoint"))
    add("Next step", cp.get("nextStep"))
    if level in ("Medium", "High"):
        add("Goal", cp.get("goal"))
        add("Open problem or decision", cp.get("problem"))
    if level == "High":
        add("Already done", cp.get("completed"))
        add("Files / resources", cp.get("resources"))
        items = [str(i) for i in (cp.get("openItems") or [])][:5]
        if items:
            add("Open items found in your own files", "; ".join(items))

    title = task_title or "your task"
    intro = f'Welcome back to "{title}". You were away about {format_minutes(away_minutes)}.'
    return {"intro": intro, "lines": lines, "level": level, "depth": DEPTH[level]}


def summary_to_text(summary: dict) -> str:
    body = "\n".join(f"{line['label']}: {line['text']}" for line in summary["lines"])
    return summary["intro"] + ("\n\n" + body if body else "\n\n(No checkpoint text was written.)")
