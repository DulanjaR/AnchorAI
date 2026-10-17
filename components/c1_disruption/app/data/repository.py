"""Data-access interface (CLAUDE.md rule 4). Routes and services only ever call
these methods; nothing else talks to storage.

The team database is Supabase (PostgreSQL), decided 17 Oct 2026. Every store —
MemoryStore (tests) and SqlStore (Supabase/PostgreSQL or a local SQLite file) —
implements this Protocol and passes the same contract tests (tests/data/store_contract.py).

Records are plain JSON-like dicts. A store returns COPIES, so changing a returned
dict never changes stored data (this is also how a real database behaves).

Collections (CLAUDE.md §5): users, tasks, protectedBlocks, disruptions, mvds,
feedback, completions, signals.
"""
from typing import Any, Protocol

Record = dict[str, Any]


class Repository(Protocol):
    def create(self, collection: str, data: Record) -> Record:
        """Stores a new record; the store assigns 'id'. Returns the new record."""

    def set(self, collection: str, id: str, data: Record) -> Record:
        """Creates or replaces a record with a known id (e.g. users/<userId>)."""

    def get(self, collection: str, id: str) -> Record | None:
        """The record, or None if there is none."""

    def update(self, collection: str, id: str, patch: Record) -> Record | None:
        """Shallow merge of `patch`; returns the updated record, or None if missing."""

    def remove(self, collection: str, id: str) -> bool:
        """Deletes the record; True if it existed."""

    def list(self, collection: str, where: Record | None = None) -> list[Record]:
        """Records whose fields equal every value in `where`, in creation order."""
