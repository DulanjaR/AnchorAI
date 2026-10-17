"""A Repository (repository.py) in a SQL database: Supabase/PostgreSQL, or a local SQLite file.

    SqlStore("postgresql://user:password@host:5432/postgres")   # Supabase (the team database)
    SqlStore("sqlite:///C:/Users/me/anchor_c1.sqlite3")           # a local file, no setup

One table, `c1_records` (collection, id, seq, data as JSON), so C1 needs no migrations
of its own and never touches other components' tables. `seq` keeps the creation order
(a replaced record keeps its place, as in MemoryStore). Filters are applied in Python
with MemoryStore's rule (JSON equality: True is not 1), so every store behaves the same
(tests/data/store_contract.py). Fine for a pilot's data volume.
"""
import copy
import json
import sqlite3
import threading
import uuid
from typing import Any

from components.c1_disruption.app.data.memory_store import _MISSING, _same
from components.c1_disruption.app.data.repository import Record

TABLE = "c1_records"


def _plain_postgres_url(url: str) -> str:
    """SQLAlchemy style (postgresql+psycopg://) → what psycopg accepts (postgresql://)."""
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def safe_url(url: str) -> str:
    """The URL without its password, for logs and the demo banner."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url


class SqlStore:
    def __init__(self, url: str) -> None:
        self.url = url
        self._lock = threading.Lock()
        if url.startswith("sqlite:///"):
            self.kind = "sqlite"
            self._conn = sqlite3.connect(url[len("sqlite:///"):], check_same_thread=False, isolation_level=None)
            self._conn.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} (collection TEXT NOT NULL, id TEXT NOT NULL, "
                               "seq INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, UNIQUE (collection, id))")
            self.mark = "?"
        elif url.startswith(("postgresql", "postgres://")):
            import psycopg  # the team's driver (root requirements.txt)

            self.kind = "postgres"
            self._dsn = _plain_postgres_url(url)
            self._conn = psycopg.connect(self._dsn, autocommit=True)
            self._conn.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} (collection TEXT NOT NULL, id TEXT NOT NULL, "
                               "seq BIGSERIAL, data JSONB NOT NULL, PRIMARY KEY (collection, id))")
            # Supabase exposes tables in `public` through its REST API; with row-level security on and
            # no policies, that API cannot read them. This direct connection (the table owner) still can.
            self._conn.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
            self.mark = "%s"
        else:
            raise ValueError("Database URL must start with sqlite:/// or postgresql://")

    # --- low level ---------------------------------------------------------------------------
    def _run(self, sql: str, params: tuple = (), fetch: bool = False) -> list[tuple]:
        sql = sql.replace("?", self.mark)
        with self._lock:
            try:
                cur = self._conn.execute(sql, params)
            except Exception:
                if self.kind != "postgres":
                    raise
                import psycopg  # a dropped connection (e.g. the pooler timed out): reconnect once

                self._conn = psycopg.connect(self._dsn, autocommit=True)
                cur = self._conn.execute(sql, params)
            return list(cur.fetchall()) if fetch else []

    def _dump(self, record: Record) -> str:
        return json.dumps(record, ensure_ascii=False)

    @staticmethod
    def _load(value: Any) -> Record:
        return copy.deepcopy(value) if isinstance(value, dict) else json.loads(value)

    def _upsert(self, collection: str, record: Record) -> None:
        cast = "?::jsonb" if self.kind == "postgres" else "?"
        self._run(f"INSERT INTO {TABLE} (collection, id, data) VALUES (?, ?, {cast}) "
                  "ON CONFLICT (collection, id) DO UPDATE SET data = excluded.data",
                  (collection, record["id"], self._dump(record)))

    # --- Repository -----------------------------------------------------------------------------
    def create(self, collection: str, data: Record) -> Record:
        record = {**copy.deepcopy(data), "id": str(uuid.uuid4())}
        self._upsert(collection, record)
        return copy.deepcopy(record)

    def set(self, collection: str, id: str, data: Record) -> Record:
        record = {**copy.deepcopy(data), "id": id}
        self._upsert(collection, record)  # an existing row keeps its seq = its place in the order
        return copy.deepcopy(record)

    def get(self, collection: str, id: str) -> Record | None:
        rows = self._run(f"SELECT data FROM {TABLE} WHERE collection = ? AND id = ?", (collection, id), fetch=True)
        return self._load(rows[0][0]) if rows else None

    def update(self, collection: str, id: str, patch: Record) -> Record | None:
        current = self.get(collection, id)
        if current is None:
            return None
        record = {**current, **copy.deepcopy(patch), "id": id}
        self._upsert(collection, record)
        return copy.deepcopy(record)

    def remove(self, collection: str, id: str) -> bool:
        existed = self.get(collection, id) is not None
        self._run(f"DELETE FROM {TABLE} WHERE collection = ? AND id = ?", (collection, id))
        return existed

    def list(self, collection: str, where: Record | None = None) -> list[Record]:
        rows = self._run(f"SELECT data FROM {TABLE} WHERE collection = ? ORDER BY seq", (collection,), fetch=True)
        conditions = list((where or {}).items())
        out = []
        for (value,) in rows:
            record = self._load(value)
            if all(_same(record.get(key, _MISSING), v) for key, v in conditions):
                out.append(record)
        return out


def make_store(url: str | None):
    """The store for a database URL; None or "" → the in-memory store (data lost on restart)."""
    from components.c1_disruption.app.data.memory_store import MemoryStore

    return SqlStore(url) if url else MemoryStore()
