"""All tunable numbers for ML Model 1 (CLAUDE.md rule 9). Fixed before any run;
nothing here is tuned on test data."""
from typing import Final

# Range reported with every prediction (log drift quantiles): q10–q90 = nominal 80%.
QUANTILES: Final[tuple[float, float]] = (0.1, 0.9)

# Point estimate of the forest: the median (q50) of the log drift, so outlier days pull it
# less (planning chat, 16 Oct 2026; before: the mean). Used for the shrinkage residuals too.
POINT_QUANTILE: Final = 0.5

# Earned-trust gate (planning chat, 16 Oct 2026): the model corrects a student's estimates only
# if, on that student's own most recent records, it beat B0 (drift 1.0) by the margin; otherwise
# the student gets drift 1.0. Evidence per record: out-of-fold forest point + shrinkage from the
# student's records of EARLIER days only. PROPOSED values, fixed before any run.
GATE_ENABLED: Final = True
GATE_LOOKBACK: Final = 20     # the student's most recent records used as evidence
GATE_MIN_RECORDS: Final = 5   # fewer → not proven → drift 1.0 (a new student always starts at 1.0)
GATE_MARGIN: Final = 0.05     # open only if model MAE (minutes) < (1 − margin) × B0 MAE

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
