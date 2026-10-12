# shared

Code every component depends on. Agree changes as a team before merging.

- `config.py` - settings loaded from `.env`
- `db.py` - SQLAlchemy engine, session, `Base`
- `auth.py` - API-key check used by every router
- `schemas.py` - common types: user id, the five assistance tiers, capacity level from C2
