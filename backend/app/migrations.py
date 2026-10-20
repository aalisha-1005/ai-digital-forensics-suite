"""Minimal versioned migration runner (Alembic-free so it works fully offline).
Add new migrations by appending (version, description, function) to MIGRATIONS."""
from sqlalchemy import text

from . import models  # noqa: F401  (registers tables)
from .database import Base, engine


def _m0001(conn):
    Base.metadata.create_all(bind=conn)


MIGRATIONS = [("0001", "initial schema", _m0001)]


def run():
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, description TEXT, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)"))
        done = {r[0] for r in conn.execute(text("SELECT version FROM schema_migrations"))}
        for version, desc, fn in MIGRATIONS:
            if version not in done:
                fn(conn)
                conn.execute(text("INSERT INTO schema_migrations(version, description) VALUES (:v, :d)"), {"v": version, "d": desc})
                print(f"applied migration {version}: {desc}")
