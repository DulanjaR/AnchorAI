"""In-memory store implementing the Repository interface (repository.py).

Used until the team chooses the database. Data lives only as long as the
process; every test gets a fresh store. FastAPI runs sync routes in a thread
pool, so a lock keeps each operation atomic.
"""
import copy
import threading
import uuid
from typing import Any

from components.c1_disruption.app.data.repository import Record


class MemoryStore:
    def __init__(self) -> None:
        # name → {id → record}; dicts keep insertion order = creation order.
        self._collections: dict[str, dict[str, Record]] = {}
        self._lock = threading.Lock()

    def _table(self, name: str) -> dict[str, Record]:
        return self._collections.setdefault(name, {})

    def create(self, collection: str, data: Record) -> Record:
        with self._lock:
            record = {**copy.deepcopy(data), "id": str(uuid.uuid4())}
            self._table(collection)[record["id"]] = record
            return copy.deepcopy(record)

    def set(self, collection: str, id: str, data: Record) -> Record:
        with self._lock:
            record = {**copy.deepcopy(data), "id": id}
            self._table(collection)[id] = record  # a replaced record keeps its place in the order
            return copy.deepcopy(record)

    def get(self, collection: str, id: str) -> Record | None:
        with self._lock:
            record = self._table(collection).get(id)
            return copy.deepcopy(record) if record is not None else None

    def update(self, collection: str, id: str, patch: Record) -> Record | None:
        with self._lock:
            table = self._table(collection)
            if id not in table:
                return None
            record = {**table[id], **copy.deepcopy(patch), "id": id}
            table[id] = record
            return copy.deepcopy(record)

    def remove(self, collection: str, id: str) -> bool:
        with self._lock:
            return self._table(collection).pop(id, None) is not None

    def list(self, collection: str, where: Record | None = None) -> list[Record]:
        conditions = list((where or {}).items())
        with self._lock:
            return [
                copy.deepcopy(record)
                for record in self._table(collection).values()
                if all(_same(record.get(key, _MISSING), value) for key, value in conditions)
            ]


_MISSING: Any = object()


def _same(a: Any, b: Any) -> bool:
    """Equality as in JSON: True is not 1."""
    return type(a) is type(b) and a == b if isinstance(a, bool) or isinstance(b, bool) else a == b
