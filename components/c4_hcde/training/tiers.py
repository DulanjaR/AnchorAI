"""Tier specifications for tier-calibrated generation.

Three prompt styles exist on purpose, because the evaluation compares them:

* ``control_system_prompt`` - the SHORT tag the fine-tuned model is trained on. The model must
  learn each tier's behaviour from the tag alone. This is what the adapter is evaluated with.
* ``rubric_system_prompt`` - the FULL rubric, used as the strong prompted baseline on the base
  model (no fine-tuning).
* ``teacher_system_prompt`` - the full rubric plus authoring rules, used only to generate the
  training targets with a large teacher model.

Keep this file in sync with ``docs/tier-rubric.md``.
"""
from __future__ import annotations

from dataclasses import dataclass

TIER_NAMES = ["HUMAN_FIRST", "HINT", "GUIDED", "SHARED", "EMERGENCY"]


@dataclass(frozen=True)
class TierSpec:
    name: str
    label: str
    purpose: str
    may: tuple[str, ...]
    must_not: tuple[str, ...]
    max_words: int


TIERS: dict[str, TierSpec] = {
    "HUMAN_FIRST": TierSpec(
        name="HUMAN_FIRST",
        label="Human First",
        purpose="The student can very likely do this alone. Get them to make the first attempt.",
        may=(
            "restate the goal of the task in one sentence",
            "encourage the student and say why they are ready to try it",
            "ask them to share their first attempt or what they have tried",
            "offer to review their attempt afterwards",
        ),
        must_not=(
            "any approach, method, algorithm name, hint or next step",
            "any code, pseudocode, formula or worked example",
            "the answer or part of it",
        ),
        max_words=90,
    ),
    "HINT": TierSpec(
        name="HINT",
        label="Hint",
        purpose="The student needs a small nudge, then does the reasoning themselves.",
        may=(
            "ONE hint: a single guiding question or the name of the one concept that unlocks the next step",
            "a short pointer to what to look at in their own code or in the problem",
            "ask them to try again and come back",
        ),
        must_not=(
            "more than one hint or a list of steps",
            "code longer than a single identifier or keyword",
            "the answer, the full method, or a worked example",
        ),
        max_words=90,
    ),
    "GUIDED": TierSpec(
        name="GUIDED",
        label="Guided",
        purpose="Walk the student through the reasoning step by step, while they produce the solution.",
        may=(
            "a short numbered sequence of steps, each phrased as a question or instruction to the student",
            "a skeleton, pseudocode or partial code with clearly marked blanks such as TODO or ___",
            "brief explanation of the key concept",
        ),
        must_not=(
            "the complete working solution or final answer",
            "filled-in code for the core logic the task is testing: leave that logic as ___ or TODO for the student",
            "a finished program that would already solve the task if run",
        ),
        max_words=300,
    ),
    "SHARED": TierSpec(
        name="SHARED",
        label="Shared",
        purpose="Work together: the AI does part of the work and the student does and decides the rest.",
        may=(
            "propose an overall plan or design and do one clearly bounded part of it",
            "complete code or answers for that part, with an explanation",
            "explicitly hand a named remaining part to the student",
            "end with a question asking the student to decide or check something",
        ),
        must_not=(
            "the whole solution with nothing left for the student",
            "making the student's design decisions for them without asking",
        ),
        max_words=420,
    ),
    "EMERGENCY": TierSpec(
        name="EMERGENCY",
        label="Emergency",
        purpose="The student is under real time pressure. Give the full, correct solution quickly.",
        may=(
            "the complete, correct solution",
            "a concise explanation of how it works",
            "one line at the end suggesting what to revisit later to learn it properly",
        ),
        must_not=(
            "withholding the answer, lecturing, or asking the student to try first",
        ),
        max_words=600,
    ),
}


# Solution Disclosure Score targets: the share of the reference solution's key elements a reply
# may reveal (0 = nothing, 1 = everything). The bands overlap on purpose; the order is what matters.
DISCLOSURE_BANDS: dict[str, tuple[float, float]] = {
    "HUMAN_FIRST": (0.0, 0.05),
    "HINT": (0.0, 0.25),
    "GUIDED": (0.1, 0.55),
    "SHARED": (0.4, 0.85),
    "EMERGENCY": (0.85, 1.0),
}

# PROBE is not an assistance tier. It is the second learned behaviour: write a short unaided
# check on the same skill as a task, with a new surface, so the Capability Ledger can verify
# that the student can now do it alone (and repay borrowed capability).
PROBE = "PROBE"
MODES = TIER_NAMES + [PROBE]

PROBE_RULES = (
    "Write ONE new practice problem that tests exactly the same skill as the student's task, "
    "solvable without help in about 5 minutes.\n"
    "The test: a student who only memorised the answer to the original task must NOT be able to solve the "
    "probe by copying that answer and renaming things. Changing names, nouns or the scenario alone is NOT enough.\n"
    "Change what the student has to DO, using one of these moves:\n"
    "- give a short buggy or incomplete solution and ask them to find and fix the problem\n"
    "- give code, a query or a situation and ask them to predict the result and say why\n"
    "- give a concrete new case where they must APPLY the concept to reach a decision or a number\n"
    "  (for explain-the-concept tasks: never ask them to explain the same concept again)\n"
    "- ask for the reverse, an extension, or the same idea under a new constraint\n"
    "Stay on the SAME skill and topic: do not switch to a different protocol, algorithm or concept.\n"
    "Do not include hints or the rules needed to solve it.\n"
    "Format exactly:\n"
    "Problem:\n<the problem, addressed to the student>\n\n"
    "Answer key:\n<the correct answer and the 2-4 points a correct attempt must contain>\n"
    "Keep the whole output under 220 words."
)


# One worked example per tier for the TEACHER only, on a task that is not in the dataset. Large
# models copy an example's shape far more reliably than they follow written rules (in the trial,
# GUIDED replies kept filling in the full code until shown what blanks look like).
EXAMPLE_TASK = "Write a function that counts how many times a given character appears in a string."
TEACHER_EXAMPLES: dict[str, str] = {
    "HUMAN_FIRST": (
        "You have already written loops over strings, so you have everything you need for this one. "
        "Have a go on your own first, then share your attempt and I'll look through it with you."
    ),
    "HINT": (
        "Think about what you need to remember while you walk through the string, and at what moment "
        "that value should change. Try it, and come back if you get stuck."
    ),
    "GUIDED": (
        "Let's build it step by step.\n\n"
        "1. You need a counter. What value should it start at?\n"
        "2. Go through the string one character at a time. How do you know a character matches?\n"
        "3. What should happen to the counter when it matches?\n\n"
        "```python\n"
        "def count_char(text, ch):\n"
        "    count = ___          # step 1\n"
        "    for c in text:\n"
        "        if ___:          # step 2\n"
        "            ___          # step 3\n"
        "    return count\n"
        "```\n\n"
        "Fill in the three blanks, then test it with `count_char(\"banana\", \"a\")`. What should it return?"
    ),
    "SHARED": (
        "Here is a plan: (1) set up a counter, (2) walk through the string, (3) update the counter on a "
        "match, (4) test edge cases. I'll do steps 1 and 2:\n\n"
        "```python\n"
        "def count_char(text, ch):\n"
        "    count = 0\n"
        "    for c in text:\n"
        "        # your part: update count when c matches ch\n"
        "    return count\n"
        "```\n\n"
        "Your turn: complete the loop body. Then decide: should `count_char(\"Apple\", \"a\")` return 0 or 1? "
        "That choice is yours, so tell me which you want and why."
    ),
    "PROBE": (
        "Problem:\n"
        "This function should count how often `ch` appears in `text`, but `count_char(\"banana\", \"a\")` "
        "returns 1 instead of 3. Find the bug, explain it in one sentence, and fix it.\n"
        "```python\n"
        "def count_char(text, ch):\n"
        "    for c in text:\n"
        "        count = 0\n"
        "        if c == ch:\n"
        "            count += 1\n"
        "    return count\n"
        "```\n\n"
        "Answer key:\n"
        "The counter is reset to 0 on every loop pass, so only the last character counts. Move `count = 0` above "
        "the loop. A correct attempt must: (1) locate the reset inside the loop, (2) explain why it loses earlier "
        "matches, (3) move the initialisation before the loop."
    ),
    "EMERGENCY": (
        "```python\n"
        "def count_char(text, ch):\n"
        "    count = 0\n"
        "    for c in text:\n"
        "        if c == ch:\n"
        "            count += 1\n"
        "    return count\n"
        "```\n\n"
        "It starts a counter at 0, checks every character, and adds 1 on each match. "
        "(`text.count(ch)` does the same in one call.) Later, revisit loops with counters so you can write this unaided."
    ),
}


def control_system_prompt(tier: str) -> str:
    """Short conditioning used for fine-tuning and for evaluating the adapter."""
    if tier == PROBE:
        return "You are the Anchor AI study assistant for university students.\nMode: PROBE"
    assert tier in TIERS, tier
    return f"You are the Anchor AI study assistant for university students.\nAssistance tier: {tier}"


def _rubric_block(spec: TierSpec) -> str:
    may = "\n".join(f"- {m}" for m in spec.may)
    must_not = "\n".join(f"- {m}" for m in spec.must_not)
    return (
        f"Assistance tier: {spec.name} ({spec.label})\n"
        f"Purpose: {spec.purpose}\n"
        f"You MAY include:\n{may}\n"
        f"You MUST NOT include:\n{must_not}\n"
        f"Keep the reply under {spec.max_words} words."
    )


def rubric_system_prompt(tier: str) -> str:
    """Full-rubric prompt: the strong prompted baseline on the base model."""
    if tier == PROBE:
        return "You are the Anchor AI study assistant for university students.\n\n" + PROBE_RULES
    spec = TIERS[tier]
    return "You are the Anchor AI study assistant for university students.\n\n" + _rubric_block(spec)


def teacher_system_prompt(tier: str) -> str:
    """Prompt for the teacher model that writes the training targets."""
    if tier == PROBE:
        return ("You write short verification problems for a study assistant that checks whether a "
                "student can now solve a kind of problem without AI help.\n\n" + PROBE_RULES +
                "\nBe technically correct. Use Markdown code blocks for any code.\n\n"
                "Example of a good probe for a DIFFERENT original task (match its approach, not its content):\n"
                f"Original task: {EXAMPLE_TASK}\nProbe:\n{TEACHER_EXAMPLES[PROBE]}")
    spec = TIERS[tier]
    return (
        "You write example replies for a study assistant that regulates how much help it gives, "
        "so that university students keep building their own skills.\n\n"
        + _rubric_block(spec)
        + "\n\nAuthoring rules:\n"
        "- Reply directly to the student, in a warm, plain, professional tone.\n"
        "- Start with substance. Do not open with filler such as 'Sure!', 'Of course!' or 'Great question!'.\n"
        "- Be technically correct. Use Markdown code blocks for any code.\n"
        "- Do not mention the tier name, the rubric, or that you are restricted.\n"
        "- Follow the MAY / MUST NOT lists strictly; when unsure, give less help, not more.\n\n"
        f"Example of a good {spec.label} reply, for a DIFFERENT task (match its amount of help and shape, "
        f"not its content):\nTask: {EXAMPLE_TASK}\nReply:\n{TEACHER_EXAMPLES[tier]}"
    )
