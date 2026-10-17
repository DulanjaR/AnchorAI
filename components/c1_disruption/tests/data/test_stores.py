"""Runs the store contract against every store implementation."""
import pytest

import os
import tempfile
from pathlib import Path

from components.c1_disruption.app.data.memory_store import MemoryStore
from components.c1_disruption.app.data.sql_store import SqlStore, make_store, safe_url
from components.c1_disruption.tests.data.store_contract import CONTRACT


def sqlite_store():
    path = Path(tempfile.mkdtemp()) / "c1.sqlite3"
    return SqlStore(f"sqlite:///{path}")


# The team database is Supabase (PostgreSQL, 17 Oct 2026). Its test runs only when a test
# database is given (never the real data): C1_TEST_DATABASE_URL=postgresql://...
STORES = {"memory": MemoryStore, "sqlite": sqlite_store}
if os.environ.get("C1_TEST_DATABASE_URL"):
    STORES["postgres"] = lambda: _fresh_postgres(os.environ["C1_TEST_DATABASE_URL"])


def _fresh_postgres(url):
    store = SqlStore(url)
    store._run("DELETE FROM c1_records")
    return store


@pytest.mark.parametrize("make_store", STORES.values(), ids=STORES.keys())
@pytest.mark.parametrize("rule", CONTRACT, ids=[r.__name__ for r in CONTRACT])
def test_store_contract(rule, make_store):
    rule(make_store())


def test_list_compares_like_json_true_is_not_1():
    store = MemoryStore()
    store.create("tasks", {"delegable": True})
    store.create("tasks", {"delegable": 1})
    assert [t["delegable"] for t in store.list("tasks", {"delegable": True})] == [True]


def test_sqlite_store_keeps_data_after_a_restart():
    path = Path(tempfile.mkdtemp()) / "c1.sqlite3"
    first = SqlStore(f"sqlite:///{path}")
    task = first.create("tasks", {"title": "Essay", "done": False})
    first.set("users", "u1", {"workStart": "09:00"})
    again = SqlStore(f"sqlite:///{path}")  # a new process opening the same file
    assert again.get("tasks", task["id"]) == task
    assert again.list("users") == [{"workStart": "09:00", "id": "u1"}]


def test_make_store_and_safe_url():
    assert isinstance(make_store(None), MemoryStore) and isinstance(make_store(""), MemoryStore)
    assert safe_url("postgresql://postgres.abc:secret@aws-0.pooler.supabase.com:5432/postgres") ==         "postgresql://postgres.abc:***@aws-0.pooler.supabase.com:5432/postgres"
