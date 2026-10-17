"""Progress lines for long steps in the notebooks (planning chat, 17 Oct 2026).

    progress = Progress()
    progress("training fold 3/5…")   →   [   12.4s] training fold 3/5…

Every long-running function takes an optional `progress` callable; None (the default)
prints nothing, so tests and the API are unchanged.
"""
import time
from typing import Callable, Optional

ProgressFn = Optional[Callable[[str], None]]


class Progress:
    def __init__(self, out: Callable[[str], None] = print) -> None:
        self.start = time.perf_counter()
        self.out = out

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.start

    def __call__(self, message: str) -> None:
        self.out(f"[{self.elapsed:7.1f}s] {message}")


def say(progress: ProgressFn, message: str) -> None:
    if progress is not None:
        progress(message)
