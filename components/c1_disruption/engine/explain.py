"""Plain-language explanations (CLAUDE.md §3.3 step 10). Pure functions only.

Every task gets exactly one explanation, built from its reason code. The text is
short and concrete so a student can see WHY the planner made each choice. The
texts are frozen in the golden spec (tests/golden/), character for character.
"""
from typing import Any, Callable, Mapping, NotRequired, TypedDict

from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.jsnum import number_text, to_fixed_number


class ExplainContext(TypedDict):
    disruptionType: str
    windowStart: str  # as reported, not clipped (e.g. 20:00–02:00)
    windowEnd: str
    freeMinutesLeft: NotRequired[int]
    maxCompression: NotRequired[float]  # from the strategy; default 0.5


# A task result as produced by mvd.py (camelCase keys, see schema.MvdTask).
Task = Mapping[str, Any]


def format_fi(fi: float) -> str:
    """Fi to 3 decimals, without trailing zeros: 0.2083 → '0.208', 12.5 → '12.5'."""
    return number_text(to_fixed_number(fi, 3))


def due_text(days_until_deadline: int) -> str:
    if days_until_deadline < 0:
        return "overdue"
    if days_until_deadline == 0:
        return "due today"
    if days_until_deadline == 1:
        return "due tomorrow"
    return f"due in {days_until_deadline} days"


def disruption_text(context: ExplainContext) -> str:
    name = context["disruptionType"].replace("_", " ")
    return f"{name} ({context['windowStart']}–{context['windowEnd']})"


FREE_TIME_NOTE = "You have free time today, so you can start it early if you like."


def shortening_text(context: ExplainContext) -> str:
    """End of a "not enough time" sentence, true for the strategy's compress ratio.

    0.5 (the approved default) gives the golden text ", even at half length.".
    Other ratios: PROPOSED wording (methodology update, 14 Oct 2026), not yet
    approved by the owner.
    """
    ratio = context.get("maxCompression", 0.5)
    if ratio == 0.5:
        return ", even at half length."
    if ratio == 0:
        return "."
    return f", even shortened by {number_text(to_fixed_number(ratio * 100, 1))}%."


def _low_urgency(t: Task, c: ExplainContext) -> str:
    # Group D tasks are never placed, even when time is left over. In that case we
    # say so: starting early is the student's choice, not an auto-action.
    text = (
        f"Moved to tomorrow: it is {due_text(t['daysUntilDeadline'])} and flexible (Fi {format_fi(t['fi'])}), "
        "so today's time goes to more urgent tasks."
    )
    if c.get("freeMinutesLeft", 0) > 0:
        text += f" {FREE_TIME_NOTE}"
    return text


TEMPLATES: dict[str, Callable[[Task, ExplainContext], str]] = {
    "KEEP_URGENT": lambda t, c: (
        f"Kept: {due_text(t['daysUntilDeadline'])} and {t['priority']} priority, so it is one of the most urgent tasks "
        f"(Fi {format_fi(t['fi'])}). Scheduled {t['start']}–{t['end']}."
    ),
    "FITS_FULLY": lambda t, c: (
        f"Kept in full: there was enough free time, so no shortening was needed (Fi {format_fi(t['fi'])}). "
        f"Scheduled {t['start']}–{t['end']}."
    ),
    "OUTSIDE_DISRUPTION_WINDOW": lambda t, c: (
        f"Kept: it cannot be done during the {disruption_text(c)}, so it is scheduled outside it, "
        f"{t['start']}–{t['end']} (Fi {format_fi(t['fi'])})."
    ),
    "REDUCE_BUDGET": lambda t, c: (
        f"Shortened by {number_text(t['compressionPct'])}% to fit the free time left today ({t['start']}–{t['end']}). "
        f"Do the most important part first (Fi {format_fi(t['fi'])})."
    ),
    "BLOCKED_BY_DISRUPTION": lambda t, c: (
        f"Moved to tomorrow: it cannot be done during the {disruption_text(c)}, and there is not enough "
        f"free time outside it{shortening_text(c)}"
    ),
    "LOW_URGENCY": _low_urgency,
    "TIME_TAKEN_BY_DISRUPTION": lambda t, c: (
        f"Moved to tomorrow: this time is taken by {disruption_text(c)}, and there is not enough "
        f"free time left today{shortening_text(c)}"
    ),
    "BUDGET_EXCEEDED": lambda t, c: f"Moved to tomorrow: there is not enough free time left today{shortening_text(c)}",
    "DELEGABLE": lambda t, c: (
        "Not enough time for you today, but you marked it as delegable: ask someone else or use AI help."
    ),
}


def explain_task(task: Task, context: ExplainContext) -> str:
    template = TEMPLATES.get(task["reason"])
    if template is None:
        raise EngineError(f"No explanation template for reason code '{task['reason']}'")
    text = template(task, context)
    if task["deadlineRisk"]:
        text += f" Warning: this task is {due_text(task['daysUntilDeadline'])}, so its deadline is at risk."
    return text


def explain_protected(block: Mapping[str, str]) -> str:
    name = block.get("label") or block["id"]
    return f"Protected time ({name}, {block['start']}–{block['end']}): the planner never moves or shortens it."
