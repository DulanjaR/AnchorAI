"""Contract tests for the Repository interface (app/data/repository.py).

Any store must pass these. Today: MemoryStore. Later: the real database store
(PostgreSQL or Firestore, team decision), by adding its factory to STORES in
test_stores.py. Port of the Node tests/data/store.contract.js.
"""
from typing import Callable

from components.c1_disruption.app.data.repository import Repository

StoreFactory = Callable[[], Repository]


def create_assigns_an_id_and_get_returns_the_record(store: Repository) -> None:
    created = store.create("tasks", {"title": "A", "userId": "u1"})
    assert isinstance(created["id"], str) and created["id"]
    assert store.get("tasks", created["id"]) == created


def get_returns_none_for_a_missing_id(store: Repository) -> None:
    assert store.get("tasks", "nope") is None


def set_creates_or_replaces_with_a_known_id(store: Repository) -> None:
    store.set("users", "u1", {"workStart": "09:00"})
    store.set("users", "u1", {"workStart": "08:00"})
    assert store.get("users", "u1") == {"id": "u1", "workStart": "08:00"}


def update_merges_a_patch_missing_id_gives_none(store: Repository) -> None:
    created = store.create("tasks", {"title": "A", "status": "planned"})
    assert store.update("tasks", created["id"], {"status": "done"}) == {"id": created["id"], "title": "A", "status": "done"}
    assert store.update("tasks", "nope", {"status": "done"}) is None


def remove_deletes_and_reports_whether_it_existed(store: Repository) -> None:
    created = store.create("tasks", {"title": "A"})
    assert store.remove("tasks", created["id"]) is True
    assert store.remove("tasks", created["id"]) is False
    assert store.get("tasks", created["id"]) is None


def list_filters_by_equality_in_creation_order(store: Repository) -> None:
    store.create("tasks", {"title": "A", "userId": "u1", "plannedDate": "2026-10-07"})
    store.create("tasks", {"title": "B", "userId": "u2", "plannedDate": "2026-10-07"})
    store.create("tasks", {"title": "C", "userId": "u1", "plannedDate": "2026-10-08"})
    store.create("tasks", {"title": "D", "userId": "u1", "plannedDate": "2026-10-07"})
    titles = [t["title"] for t in store.list("tasks", {"userId": "u1", "plannedDate": "2026-10-07"})]
    assert titles == ["A", "D"]
    assert len(store.list("tasks")) == 4
    assert store.list("empty_collection") == []


def returned_records_are_copies(store: Repository) -> None:
    created = store.create("tasks", {"title": "A", "tags": ["x"]})
    created["title"] = "changed"
    created["tags"].append("y")
    from_list = store.list("tasks")[0]
    from_list["title"] = "changed again"
    assert store.get("tasks", created["id"]) == {"id": created["id"], "title": "A", "tags": ["x"]}


CONTRACT = [
    create_assigns_an_id_and_get_returns_the_record,
    get_returns_none_for_a_missing_id,
    set_creates_or_replaces_with_a_known_id,
    update_merges_a_patch_missing_id_gives_none,
    remove_deletes_and_reports_whether_it_existed,
    list_filters_by_equality_in_creation_order,
    returned_records_are_copies,
]
