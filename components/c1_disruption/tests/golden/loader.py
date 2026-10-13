"""Loads the frozen golden spec (README.md in this folder describes the format)."""
import json
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).parent
SCENARIO_DIR = GOLDEN_DIR / "scenarios"

APPROVED_TASK_FIELDS = ("fi", "efUsed", "tag", "start", "end", "compressionPct", "reason", "deadlineRisk")
# Compared exactly, in addition to the approved fields (fi is compared after rounding).
CAPTURED_TASK_FIELDS = ("group", "explanation")


def load_scenarios() -> list[dict[str, Any]]:
    files = sorted(SCENARIO_DIR.glob("S*.json"))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def scenario(scenario_id: str) -> dict[str, Any]:
    return next(s for s in load_scenarios() if s["id"] == scenario_id)


def load_api_cases() -> dict[str, Any]:
    return json.loads((GOLDEN_DIR / "api_cases.json").read_text(encoding="utf-8"))
