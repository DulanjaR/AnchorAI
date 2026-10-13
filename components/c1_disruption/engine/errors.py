"""The one error type the engine raises.

The API turns it into 422 (the engine cannot plan, e.g. a None EF value), so a
planning problem is never confused with a programming bug.
"""


class EngineError(ValueError):
    """Input the engine cannot plan with; the message says what and why."""
