"""All tunable numbers for ML Model 1 (CLAUDE.md rule 9). Fixed before any run;
nothing here is tuned on test data."""
from typing import Final

# Range reported with every prediction (log drift quantiles): q10–q90 = nominal 80%.
QUANTILES: Final[tuple[float, float]] = (0.1, 0.9)

# Shrinkage w = n / (n + k): k is chosen from this grid by cross-validation inside
# the training data. k = 0 trusts a student's own mean fully; large k ≈ pooled only.
K_GRID: Final[tuple[float, ...]] = (0, 1, 2, 5, 10, 20, 50, 100)

# Random forest (quantile regression forest). Fixed settings, no tuning on test data.
N_ESTIMATORS: Final = 200
MIN_SAMPLES_LEAF: Final = 5
RANDOM_STATE: Final = 2026

# Folds for the out-of-fold pooled predictions used to compute student residuals.
RESIDUAL_FOLDS: Final = 5

# Exclusion rule (CLAUDE.md §3.6, 9 Oct 2026): a record whose task time overlaps a
# confirmed disruption has the overlap subtracted; it is dropped when the overlap is
# more than this share of the recorded span, or less than MIN_CLEAN_MINUTES remain.
# PROPOSED values (from the earlier Task 4 plan).
MAX_OVERLAP_SHARE: Final = 0.5
MIN_CLEAN_MINUTES: Final = 10
