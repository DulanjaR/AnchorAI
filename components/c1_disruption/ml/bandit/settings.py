"""All tunable numbers for ML Model 2 (CLAUDE.md rule 9)."""
from typing import Final

# fixed_order (pilot week 1, default) | bandit | randomised
POLICY_MODE: Final = "fixed_order"

# LinUCB: exploration width and ridge penalties. The per-student part has a larger
# penalty, so a student's own deviation grows only with their own evidence.
ALPHA: Final = 0.5
LAMBDA_SHARED: Final = 1.0
LAMBDA_STUDENT: Final = 5.0

# randomised mode: probability of showing the bandit ranking (else the fixed one).
RANDOMISED_BANDIT_SHARE: Final = 0.5

# Time-of-day buckets for the context (start of the replan, hour < bound).
MORNING_BEFORE: Final = 12
AFTERNOON_BEFORE: Final = 17

# Student history: prior acceptance rate before any decision (neutral).
PRIOR_ACCEPTANCE: Final = 0.5
