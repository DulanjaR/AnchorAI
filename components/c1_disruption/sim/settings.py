"""Simulation settings (all SYNTHETIC). PROPOSED values, fixed before any run."""
from typing import Final

DATASET: Final = "SYNTHETIC"
SEEDS: Final[tuple[int, ...]] = (11, 22, 33, 44, 55)
START_DATE: Final = "2026-09-07"  # day 1, a Monday

# Layer C: on each day a disruption happens with this probability; its type is drawn
# from DISRUPTION_MIX (connectivity_failure left out while its EF values are None).
DISRUPTION_RATE: Final = 0.3
DISRUPTION_MIX: Final[dict[str, float]] = {
    "power_outage": 0.35, "transport_delay": 0.25, "urgent_work": 0.2, "family_obligation": 0.1, "health_issue": 0.1,
}
DISRUPTION_MINUTES: Final[tuple[int, int]] = (30, 240)  # time lost, 15-minute steps

# Misspecified generator: a hidden daily factor (log-normal, this sd) multiplies every
# task's drift that day. The model never sees it.
HIDDEN_DAILY_SD: Final = 0.25

# Layer D: simulated decisions. A student accepts when the shown strategy is their
# preferred one with this probability, otherwise edits/rejects (see events.py).
ACCEPT_IF_PREFERRED: Final = 0.85
ACCEPT_OTHERWISE: Final = 0.3
EDIT_SHARE_OF_NOT_ACCEPTED: Final = 0.5

# Model 1 evaluation inside the simulation (fewer trees than production to keep runs short).
SIM_N_ESTIMATORS: Final = 100
ROLLING_STEP_DAYS: Final = 7
