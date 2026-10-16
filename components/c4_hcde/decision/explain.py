"""Human-readable explanation of a decision from its top contributing factors."""
from __future__ import annotations

from .context import label as ctx_label

LABEL = {"HUMAN_FIRST": "Human First", "HINT": "Hint", "GUIDED": "Guided", "SHARED": "Shared", "EMERGENCY": "Emergency"}


def _mastery_phrase(m: float, n_obs: int, prior_note: str | None = None) -> str:
    if n_obs == 0:
        return prior_note or "this is your first task on this skill"
    if m >= 0.75:
        return "you have shown you can do this kind of task on your own"
    if m >= 0.5:
        return "you are getting there with this kind of task"
    return "this skill is still new for you"


def explain(tier: str, skill: str, mastery: float, n_obs: int, difficulty: int, urgency: float,
            minutes_left: float | None, contributions: dict[str, float], emergency_rule: bool,
            fading_reason: str | None, memory_note: str | None = None, context: str = "general",
            prior_note: str | None = None) -> str:
    parts = [_mastery_phrase(mastery, n_obs, prior_note)]
    top = sorted(contributions.items(), key=lambda kv: -kv[1])
    for k, v in top[:2]:
        if v < 0.05:
            continue
        if k == "difficulty" and difficulty >= 4:
            parts.append("the task is on the harder side")
        elif k == "difficulty" and difficulty <= 2:
            parts.append("the task is fairly short")
        elif k == "urgency" and urgency >= 0.5 and tier in ("GUIDED", "SHARED", "EMERGENCY"):
            parts.append(f"your deadline is close ({int(minutes_left)} min left)" if minutes_left is not None
                         else "your deadline is close")
        elif k == "recent_struggle":
            parts.append("the last attempt on this skill was difficult")
        elif k == "novelty" and context != "general":
            parts.append(f"{ctx_label(context)} is new for you" if v >= 0.1 else f"this is new for you in {ctx_label(context)}")
    if emergency_rule:
        parts = [f"you have little time ({int(minutes_left)} min) and this skill is not yet secure"
                 if minutes_left is not None else "time is short and this skill is not yet secure"]
    if fading_reason:
        parts.append(fading_reason)
    if memory_note:
        parts.append(memory_note)
    reason = "; ".join(dict.fromkeys(parts))
    what = "this task" if skill == "general" else skill.replace("-", " ")
    if context != "general" and skill != "general":
        what += f" in {ctx_label(context)}"
    return f"Recommended: {LABEL[tier]} for {what}, because {reason}. You can choose a different level."
