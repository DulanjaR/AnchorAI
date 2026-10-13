"""Runs every case in tests/golden/api_cases.json (frozen from the Node API tests)
against the FastAPI app. The case format is described in tests/golden/README.md;
this runner is the Python twin of the one in tests/golden/tools/golden_from_node.js.
"""
import json
import re
from typing import Any

import pytest

from components.c1_disruption.tests.api.client import setup
from components.c1_disruption.tests.golden.loader import load_api_cases

SPEC = load_api_cases()
ANY_STRING = "<any-string>"
_VAR = re.compile(r"\$\{([\w.]+)\}")


def _get_path(obj: Any, path: str) -> Any:
    if path == "":
        return obj
    for key in path.split("."):
        if obj is None:
            return None
        obj = obj[int(key)] if isinstance(obj, list) else obj.get(key)
    return obj


def _substitute(value: Any, saved: dict[str, Any]) -> Any:
    if isinstance(value, str):
        whole = _VAR.fullmatch(value)
        if whole:
            return _get_path(saved, whole[1])
        return _VAR.sub(lambda m: str(_get_path(saved, m[1])), value)
    if isinstance(value, list):
        return [_substitute(v, saved) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, saved) for k, v in value.items()}
    return value


def _same_scalar(got: Any, want: Any) -> bool:
    # JSON semantics: true is not 1, 2 equals 2.0.
    if isinstance(got, bool) or isinstance(want, bool):
        return type(got) is type(want) and got == want
    return got == want


def matches(got: Any, want: Any) -> bool:
    """Partial match: objects need only the listed keys, arrays must match element by element."""
    if want == ANY_STRING:
        return isinstance(got, str)
    if isinstance(want, list):
        return isinstance(got, list) and len(got) == len(want) and all(matches(g, w) for g, w in zip(got, want))
    if isinstance(want, dict):
        return isinstance(got, dict) and all(k in got and matches(got[k], w) for k, w in want.items())
    return _same_scalar(got, want)


def equals_exact(got: Any, want: Any) -> bool:
    if want == ANY_STRING:
        return isinstance(got, str)
    if isinstance(want, list):
        return isinstance(got, list) and len(got) == len(want) and all(equals_exact(g, w) for g, w in zip(got, want))
    if isinstance(want, dict):
        return isinstance(got, dict) and got.keys() == want.keys() and all(equals_exact(got[k], want[k]) for k in want)
    return _same_scalar(got, want)


def check(where: str, body: Any, status: int | None, expect: dict[str, Any]) -> list[str]:
    problems = []
    shown = json.dumps(body)[:400]
    if "status" in expect and status != expect["status"]:
        problems.append(f"{where}: status {status}, want {expect['status']} ({shown})")
    if "equals" in expect and not equals_exact(body, expect["equals"]):
        problems.append(f"{where}: body {shown} != {expect['equals']}")
    if "match" in expect and not matches(body, expect["match"]):
        problems.append(f"{where}: body {shown} does not match {expect['match']}")
    if "length" in expect and not (isinstance(body, list) and len(body) == expect["length"]):
        problems.append(f"{where}: length is not {expect['length']} ({shown})")
    error = body.get("error") if isinstance(body, dict) else None
    if "errorCode" in expect and not (error and error.get("code") == expect["errorCode"]):
        problems.append(f"{where}: error {error}, want code {expect['errorCode']}")
    if "messageRegex" in expect and not (error and re.search(expect["messageRegex"], error.get("message", ""))):
        problems.append(f"{where}: message {error} does not match /{expect['messageRegex']}/")
    for at in expect.get("at", []):
        value = _get_path(body, at["path"])
        if "find" in at:
            value = next((v for v in value or [] if matches(v, at["find"])), None)
        if "pluck" in at:
            value = [v.get(at["pluck"]) for v in value] if isinstance(value, list) else None
        if "equals" in at and not equals_exact(value, at["equals"]):
            problems.append(f"{where}: {at['path']} = {value} != {at['equals']}")
        if "match" in at and not matches(value, at["match"]):
            problems.append(f"{where}: {at['path']} = {value} does not match {at['match']}")
    return problems


def _expand_body(body: Any) -> Any:
    if not isinstance(body, dict):
        return body
    for name, template in SPEC["templates"].items():
        if f"${name}" in body:
            merged = {**template, **body[f"${name}"]}
            for key in body.get("$omit", []):
                merged.pop(key, None)
            return merged
    return body


def run_case(case: dict[str, Any]) -> list[str]:
    ctx = setup(case.get("now", SPEC["defaultNow"]))
    saved: dict[str, Any] = {}
    steps = [*SPEC["fixtures"].get(case.get("fixture"), []), *case["steps"]] if case.get("fixture") else case["steps"]
    problems: list[str] = []
    for i, raw in enumerate(steps, start=1):
        where = f"{case['id']} step {i}"
        step = _substitute(raw, saved)
        if "setNow" in step:
            ctx.clock.set(step["setNow"])
            continue
        if "store" in step:
            rows = ctx.store.list(step["store"]["collection"], step["store"].get("where"))
            problems += check(where, rows, None, step.get("expect", {}))
            continue
        res = ctx.call(
            step["method"],
            step["path"],
            user=step.get("as"),
            body=_expand_body(step.get("body")),
            raw=step.get("rawBody"),
            headers=step.get("headers"),
        )
        body = res.json() if res.content else None
        problems += check(where, body, res.status_code, step.get("expect", {}))
        if "save" in step:
            saved[step["save"]] = body
    return problems


def test_all_57_cases_are_present():
    assert len(SPEC["cases"]) == 57
    assert len({c["id"] for c in SPEC["cases"]}) == 57


@pytest.mark.parametrize("case", SPEC["cases"], ids=[c["id"] for c in SPEC["cases"]])
def test_api_case(case):
    assert run_case(case) == []
