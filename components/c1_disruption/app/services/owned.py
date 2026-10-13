"""Loads a record and checks it belongs to the caller.

Another user's record is reported as "not found" (404), so the API never reveals
that it exists.
"""
from components.c1_disruption.app.api.errors import not_found
from components.c1_disruption.app.data.repository import Record, Repository


def load_owned(store: Repository, collection: str, id: str, user_id: str, what: str) -> Record:
    record = store.get(collection, id)
    if record is None or record.get("userId") != user_id:
        raise not_found(what)
    return record
