"""All tunable numbers for the MVD engine live here (CLAUDE.md rule 9).

These are initial heuristics; thresholds are tuned during the pilot. Values are
identical to the Node project's config.js (golden spec, tests/golden/).
"""
from typing import Final, Literal

# Priority encoding: High = 1 so that high-priority tasks get a LOW Fi (= urgent, keep).
PRIORITY_SCORE: Final[dict[str, int]] = {"High": 1, "Medium": 2, "Low": 3}

# Feasibility gate (revised 6 Oct 2026): EF below this = cannot be placed inside the
# disruption window; may still be placed outside it (before or after). It becomes
# Move only if it does not fit there.
FEASIBILITY_GATE: Final = 0.3

# EF outside the disruption window = normal conditions (EF definition, 6 Oct 2026).
OUTSIDE_WINDOW_EF: Final = 1.0

# Deadline proximity is measured in days; "due today" is floored at 0.5
# so Fi never becomes 0.
DEADLINE_MIN_DAYS: Final = 0.5

# A moved task due within this many days (0 = today, 1 = tomorrow) gets a
# deadline risk warning (revised 6 Oct 2026).
DEADLINE_RISK_DAYS: Final = 1

KEEP_THRESHOLD: Final = 0.5
REDUCE_RANGE: Final[tuple[float, float]] = (0.5, 2.0)
MAX_COMPRESSION: Final = 0.5  # Reduce compresses by UP TO 50%

TASK_TYPES: Final[tuple[str, ...]] = ("Digital", "Analog", "Meeting", "Fixed")

# Optional task category (planning chat, 16 Oct 2026): a feature for ML Model 1 only, so it can
# tell task kinds apart within a type. The MVD engine never reads it.
TASK_CATEGORIES: Final[tuple[str, ...]] = ("coding", "writing", "reading", "revision")

DisruptionKind = Literal["environment", "unavailable"]

# Disruption kinds (Task 2a, 12 Oct 2026):
#   environment: conditions change; EF decides which task types can run in the window.
#   unavailable: the student's time is taken; the window is removed from free time
#                like a protected block, so no EF value is needed.
DISRUPTION_KINDS: Final[dict[str, DisruptionKind]] = {
    "power_outage": "environment",
    "transport_delay": "environment",
    "connectivity_failure": "environment",
    "urgent_work": "unavailable",
    "family_obligation": "unavailable",
    "health_issue": "unavailable",
}

# Environmental Feasibility (EF) per ENVIRONMENT disruption type and task type.
# None = open research decision for the owner. Do not invent values;
# the engine must raise a clear error if it hits a None.
ENV_FEASIBILITY: Final[dict[str, dict[str, float | None]]] = {
    "power_outage":         {"Digital": 0.1,  "Analog": 1.2,  "Meeting": None, "Fixed": None},
    "transport_delay":      {"Digital": 0.7,  "Analog": 1.2,  "Meeting": None, "Fixed": None},
    "connectivity_failure": {"Digital": None, "Analog": None, "Meeting": None, "Fixed": None},
}
