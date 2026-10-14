"""Evaluation settings. Fixed BEFORE any analysis (D-EVAL, DECISIONS.md 2026-10-14);
changing one after results are seen is not allowed."""
from typing import Final

# Slack ratio below this = a "tight-slack" event; results are split on it.
# PROPOSED value, owner to confirm before the pilot analysis.
TIGHT_SLACK_THRESHOLD: Final = 0.10
