"""Runs the store contract against every store implementation."""
import pytest

from components.c1_disruption.app.data.memory_store import MemoryStore
from components.c1_disruption.tests.data.store_contract import CONTRACT

# A real database store is added here once the team decides PostgreSQL vs Firestore.
STORES = {"memory": MemoryStore}


@pytest.mark.parametrize("make_store", STORES.values(), ids=STORES.keys())
@pytest.mark.parametrize("rule", CONTRACT, ids=[r.__name__ for r in CONTRACT])
def test_store_contract(rule, make_store):
    rule(make_store())


def test_list_compares_like_json_true_is_not_1():
    store = MemoryStore()
    store.create("tasks", {"delegable": True})
    store.create("tasks", {"delegable": 1})
    assert [t["delegable"] for t in store.list("tasks", {"delegable": True})] == [True]
