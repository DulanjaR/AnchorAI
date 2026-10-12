from enum import IntEnum
from typing import NewType

UserId = NewType("UserId", str)  # pseudonymous id, never a real name or email


class AssistanceTier(IntEnum):
    HUMAN_FIRST = 0
    HINT = 1
    GUIDED = 2
    SHARED = 3
    EMERGENCY = 4


class CapacityLevel(IntEnum):
    """Signal produced by Component 2 (Human Capacity Manager)."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
