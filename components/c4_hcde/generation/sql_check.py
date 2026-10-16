"""Differential testing for SQL answers: run the student's query and the hidden reference query on the
same small test database and compare the rows. Equal rows = correct, whatever way it was written
(o.id IS NULL vs o.customer_id IS NULL, LEFT JOIN vs NOT EXISTS ...). Deterministic, no model judgement.

The test database (tables + a few rows incl. edge cases) is written once per task by the local model and
executed in an in-memory SQLite database with a time limit. If anything about the setup fails, the result
is 'inconclusive' and the caller falls back to the model grader.
"""
from __future__ import annotations

import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field

from . import ollama_client

SCHEMA_PROMPT = (
    "Write a small SQLite test database for checking answers to the task below. Use the table and column names "
    "the task and the reference query use. 4-8 rows per table, including edge cases that separate correct from "
    "almost-correct queries (for example a row with no match in the other table, duplicates, NULLs, ties). "
    "Output ONLY SQL statements (CREATE TABLE and INSERT) in one ```sql code block."
)
SQL_BLOCK = re.compile(r"```(?:sql|sqlite)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
SQL_START = re.compile(r"(?is)\b(with|select)\b.*")
TIME_LIMIT_S = 2.0


@dataclass
class SqlResult:
    status: str                      # "equal" | "different" | "error" | "inconclusive"
    evidence: str = ""               # human-readable difference, used as evidence for the grader/feedback
    student_rows: list = field(default_factory=list)
    expected_rows: list = field(default_factory=list)


def extract_sql(text: str) -> str:
    blocks = SQL_BLOCK.findall(text)
    sql = blocks[0] if blocks else text
    m = SQL_START.search(sql)
    if not m:
        return ""
    stmt = m.group(0).strip()
    return stmt.split(";")[0].strip()  # first statement only


def _run(conn: sqlite3.Connection, sql: str) -> list:
    start = time.time()
    conn.set_progress_handler(lambda: 1 if time.time() - start > TIME_LIMIT_S else 0, 10000)
    return [tuple(r) for r in conn.execute(sql).fetchall()]


def _same_rows(got: list, expected: list, ordered: bool) -> bool:
    """Same rows, allowing the student to select a subset or superset of the reference's columns
    (listing customers by name only is as correct as listing id and name)."""
    from itertools import permutations
    eq = (lambda a, b: a == b) if ordered else (lambda a, b: Counter(a) == Counter(b))
    if eq(got, expected):
        return True
    if not got or not expected or len(got) != len(expected):
        return False
    ng, ne = len(got[0]), len(expected[0])
    if max(ng, ne) > 6:
        return False
    small, big = (got, expected) if ng <= ne else (expected, got)
    k = min(ng, ne)
    for cols in permutations(range(max(ng, ne)), k):
        if eq([tuple(r) for r in small], [tuple(r[c] for c in cols) for r in big]):
            return True
    return False


def build_schema(task: str, reference_sql: str, call=None) -> str:
    call = call or ollama_client.chat
    text = call([{"role": "system", "content": SCHEMA_PROMPT},
                 {"role": "user", "content": f"Task:\n{task}\n\nReference query:\n{reference_sql}"}], temperature=0.0)
    blocks = SQL_BLOCK.findall(text)
    return (blocks[0] if blocks else text).strip()


def compare(task: str, reference_text: str, answer: str, schema: str | None, call=None) -> tuple[SqlResult, str]:
    """Returns (result, schema used). Never raises."""
    student, reference = extract_sql(answer), extract_sql(reference_text)
    if not student or not reference:
        return SqlResult("inconclusive", "no SQL query found"), schema or ""
    try:
        schema = schema or build_schema(task, reference, call)
        conn = sqlite3.connect(":memory:")
        conn.executescript(schema)
        expected = _run(conn, reference)
    except Exception as e:  # the generated test data or the reference does not run: cannot judge by execution
        return SqlResult("inconclusive", f"test setup failed: {e}"), schema or ""
    try:
        got = _run(conn, student)
    except Exception as e:
        return SqlResult("error", f"your query does not run: {e}", [], expected), schema
    ordered = bool(re.search(r"\border\s+by\b", task + " " + reference, re.I)) and "order" in task.lower()
    if _same_rows(got, expected, ordered):
        return SqlResult("equal", f"returns the same {len(got)} row(s) as a correct solution on the test data",
                         got, expected), schema
    missing = list((Counter(expected) - Counter(got)).elements())[:3]
    extra = list((Counter(got) - Counter(expected)).elements())[:3]
    ev = f"on the test data your query returned {len(got)} row(s) but a correct query returns {len(expected)}"
    if missing:
        ev += f"; missing for example {missing}"
    if extra:
        ev += f"; unexpected for example {extra}"
    if not missing and not extra:
        ev += "; the rows are right but in the wrong order"
    return SqlResult("different", ev, got, expected), schema
