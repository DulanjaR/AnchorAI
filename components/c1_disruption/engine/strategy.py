"""Strategy config for one MVD run (methodology update, 14 Oct 2026).

A strategy is one concrete way of building the MVD; ML Model 2 chooses between
strategies. Every setting defaults to the approved behaviour, so an input without
a strategy gives exactly the golden output.

  compressRatio   how much a placed task may be shortened at most (default
                  config.MAX_COMPRESSION = 0.5, "up to 50%")
  deferOrder      "fi" (default: the approved order) | "deadline" (within each group,
                  earliest deadline first, then Fi): decides which tasks are reduced or
                  moved first when time runs out
  recoveryTiming  "earliest" (default) | "latest": outside window-first, fill the
                  latest free gaps first (a task goes to the end of the latest gap that
                  holds it; equal largest gaps for compression → the latest)
(planning chat, 14 Oct 2026). The candidate groups and window-first (Q6) stay as approved.
"""
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Mapping

from components.c1_disruption.engine import config as default_config
from components.c1_disruption.engine.errors import EngineError

KNOWN_KEYS = ("compressRatio", "deferOrder", "recoveryTiming")
DEFER_ORDERS = ("fi", "deadline")
RECOVERY_TIMINGS = ("earliest", "latest")


@dataclass(frozen=True)
class Strategy:
    compress_ratio: float
    defer_order: str = "fi"
    recovery_timing: str = "earliest"


def read_strategy(raw: Mapping[str, Any] | None, config: ModuleType = default_config) -> Strategy:
    """The engine input's optional 'strategy' → Strategy, with defaults filled in.

    Unknown keys are an error, so a typo never silently falls back to the default.
    """
    raw = raw or {}
    if not isinstance(raw, Mapping):
        raise EngineError("'strategy' must be an object")
    unknown = [key for key in raw if key not in KNOWN_KEYS]
    if unknown:
        raise EngineError(f"Unknown strategy setting(s): {', '.join(unknown)}")
    ratio = raw.get("compressRatio", config.MAX_COMPRESSION)
    # 0 = never shorten; must stay below 1 (a task cannot be shortened to nothing).
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 <= ratio < 1:
        raise EngineError(f"'compressRatio' must be a number from 0 up to (not including) 1, got {ratio!r}")
    defer = raw.get("deferOrder", "fi")
    if defer not in DEFER_ORDERS:
        raise EngineError(f"'deferOrder' must be one of: {', '.join(DEFER_ORDERS)}, got {defer!r}")
    timing = raw.get("recoveryTiming", "earliest")
    if timing not in RECOVERY_TIMINGS:
        raise EngineError(f"'recoveryTiming' must be one of: {', '.join(RECOVERY_TIMINGS)}, got {timing!r}")
    return Strategy(compress_ratio=ratio, defer_order=defer, recovery_timing=timing)
