"""Input checks for the C1 API, as Pydantic types with Node-style messages.

Each field type below is the Python form of one Node validate.js check, with the
same rule and the same message, so docs/API.md and the frozen API cases
(tests/golden/api_cases.json) still hold:
  - missing / null required field → "'name' is required (expected)"
  - wrong value                   → "'name' must be expected"
  - unknown field                 → "Unknown field(s): a, b"  (checked first)
Allowed task types, priorities and disruption types come from the engine config,
so there is one source of truth for them.
"""
import math
from typing import Annotated, Any, Callable, ClassVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationInfo, model_validator
from pydantic_core import PydanticCustomError

from components.c1_disruption.app.api.errors import bad_request
from components.c1_disruption.engine import config
from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.time import is_time, parse_date, to_minutes

DISRUPTION_TYPES = tuple(config.DISRUPTION_KINDS)
TASK_TYPES = config.TASK_TYPES
PRIORITIES = tuple(config.PRIORITY_SCORE)
TAGS = ("Keep", "Reduce", "Move", "Delegate")
TASK_CATEGORIES = config.TASK_CATEGORIES

# --- plain checks (also used for query and path parameters) ------------------

# is_time (a real 'HH:MM' time of day) lives in engine/time.py; imported above.


def is_date(value: Any) -> bool:
    """'YYYY-MM-DD' that exists in the calendar (stricter than Node, DECISIONS.md 2026-10-13)."""
    try:
        parse_date(value)
    except EngineError:
        return False
    return isinstance(value, str)


def is_date_time(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split("T")
    return is_date(parts[0]) and len(parts) > 1 and is_time(parts[1])


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def is_positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _whole_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, float) and value.is_integer())


def one_of(options: tuple[Any, ...]) -> Callable[[Any], bool]:
    def test(value: Any) -> bool:
        # No bools: in Python True == 1, in JSON they are different values.
        return not isinstance(value, bool) and value in options

    return test


def require_date(value: Any, name: str) -> str:
    """For query/path parameters, which are not part of a body model."""
    if value is None:
        raise bad_request(f"'{name}' is required (a date YYYY-MM-DD)")
    if not is_date(value):
        raise bad_request(f"'{name}' must be a date YYYY-MM-DD")
    return value


# --- Pydantic field types ------------------------------------------------------

def _rule(expected: str, test: Callable[[Any], bool], convert: Callable[[Any], Any] | None = None) -> BeforeValidator:
    def check(value: Any, info: ValidationInfo) -> Any:
        if value is None:
            return None  # absent; the model decides whether that is allowed
        if not test(value):
            raise PydanticCustomError("c1_invalid", "'{name}' must be {expected}", {"name": info.field_name, "expected": expected})
        return convert(value) if convert else value

    return BeforeValidator(check)


def _field(expected: str) -> Any:
    return Field(default=None, description=expected)


Text = Annotated[str | None, _rule("a non-empty string", is_non_empty_string), _field("a non-empty string")]
Time = Annotated[str | None, _rule("a time HH:MM", is_time), _field("a time HH:MM")]
Date = Annotated[str | None, _rule("a date YYYY-MM-DD", is_date), _field("a date YYYY-MM-DD")]
DateTime = Annotated[
    str | None, _rule("a date-time YYYY-MM-DDTHH:MM", is_date_time), _field("a date-time YYYY-MM-DDTHH:MM")
]
Flag = Annotated[bool | None, _rule("true or false", lambda x: isinstance(x, bool)), _field("true or false")]
PositiveNumber = Annotated[int | float | None, _rule("a positive number", is_positive_number), _field("a positive number")]


def whole_number(lo: int, hi: int) -> Any:
    expected = f"a whole number from {lo} to {hi}"
    return Annotated[
        int | None, _rule(expected, lambda x: _whole_number(x) and lo <= x <= hi, int), _field(expected)
    ]


def choice(options: tuple[Any, ...]) -> Any:
    expected = f"one of: {', '.join(str(o) for o in options)}"
    return Annotated[Any, _rule(expected, one_of(options)), _field(expected)]


def non_empty_list(item: Any) -> Any:
    return Annotated[
        list[item] | None,
        _rule("a non-empty list", lambda x: isinstance(x, list) and len(x) > 0),
        _field("a non-empty list"),
    ]


def any_list(item: Any) -> Any:
    return Annotated[list[item] | None, _rule("a list", lambda x: isinstance(x, list)), _field("a list")]


class Body(BaseModel):
    """Base for request bodies: unknown fields refused, required fields named.

    Subclasses list their required fields in REQUIRED. Every field defaults to
    None, so "absent" and "null" are treated alike, as in the Node API.
    """

    model_config = ConfigDict(extra="forbid")
    REQUIRED: ClassVar[tuple[str, ...]] = ()
    # Message when the value is not an object (Node wording per body).
    NOT_OBJECT: ClassVar[str] = "Request body must be a JSON object"

    @classmethod
    def pre_check(cls, data: dict[str, Any]) -> None:
        """Hook for a check that must run after the unknown-field check and
        before the field checks (e.g. confirmed: true on a disruption)."""

    @model_validator(mode="before")
    @classmethod
    def _node_style_checks(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise PydanticCustomError("c1_invalid", cls.NOT_OBJECT)
        # Unknown fields first, so a typo like "prority" is reported, not ignored.
        unknown = [key for key in data if key not in cls.model_fields]
        if unknown:
            raise PydanticCustomError("c1_invalid", "Unknown field(s): {fields}", {"fields": ", ".join(unknown)})
        cls.pre_check(data)
        for name in cls.REQUIRED:
            if data.get(name) is None:
                expected = cls.model_fields[name].description
                raise PydanticCustomError(
                    "c1_invalid", "'{name}' is required ({expected})", {"name": name, "expected": expected}
                )
        return data
