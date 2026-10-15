"""Settings for the external (real-data) evaluation of ML Model 1 (CLAUDE.md rule 9).
Fixed before any run; nothing here is tuned on test data."""
from typing import Final

# Fewer trees than production (settings.N_ESTIMATORS = 200): CESAW has ~60,000 tasks and
# every fold fits six forests. Same value for every fold and every method.
N_ESTIMATORS: Final = 50

# Cold start: developers are split into this many groups (seeded); each group is held out
# in turn, so every developer is predicted without any of their own tasks in training.
# (One fold per developer = 247 fits did not finish; owner approved 15 Oct 2026.)
COLD_FOLDS: Final = 10
COLD_SEED: Final = 2026

# Parallel workers. Each one holds a full forest (the quantile forest keeps its training
# samples), so more workers run out of memory; with 7 a worker crashed.
N_JOBS: Final = 3

# Warm (rolling-origin) evaluation: a seeded sample of developers, because one fit on
# 60,000 tasks takes about a minute. Developers need enough history to be evaluated warm.
WARM_DEVELOPERS: Final = 40
WARM_MIN_DAYS: Final = 20   # distinct working days a sampled developer needs
WARM_STEP_DAYS: Final = 30  # one origin per 30 of the developer's own days
WARM_SEED: Final = 2026

# CESAW has no priority and no task type: every task is the same type and priority.
TASK_TYPE: Final = "Digital"
PRIORITY: Final = "Medium"

LABEL: Final = "REAL (CESAW, professional developers)"
TASK_FILE: Final = "CESAW_task_fact.csv"
