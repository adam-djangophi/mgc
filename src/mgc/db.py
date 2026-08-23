"""SQLite connection handling and migration runner.

Migrations are plain ``.sql`` files under ``mgc/migrations`` named with a
numeric prefix (``0001_create_events.sql``, ``0002_...``). They are applied
in filename order, once each, tracked in a ``schema_migrations`` table.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

DEFAULT_DB_PATH = "mgc.db"

_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
)
"""


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string (second precision)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection configured for app use.

    Foreign keys and row-as-dict access are enabled. Callers are
    responsible for closing the returned connection.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migration_files() -> list[Path]:
    migrations_dir = resources.files("mgc").joinpath("migrations")
    return sorted(
        (Path(str(p)) for p in migrations_dir.iterdir() if p.name.endswith(".sql")),
        key=lambda p: p.name,
    )


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply any pending migrations, in order. Returns versions applied."""
    conn.execute(_MIGRATIONS_TABLE)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

    newly_applied = []
    for path in _migration_files():
        version = path.name
        if version in applied:
            continue
        sql = path.read_text()
        with conn:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, utcnow_iso()),
            )
        newly_applied.append(version)
    return newly_applied


def init_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a database and apply any pending migrations."""
    conn = connect(db_path)
    run_migrations(conn)
    return conn


def require_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a connection to an already-migrated database, or fail loudly.

    Application entry points (``mgc.main``) should use this. It assumes
    the database has already been created and migrated by
    ``scripts/init_db.py`` — the only thing that should call
    :func:`connect` + :func:`run_migrations` to bootstrap one — and
    raises rather than silently creating or migrating one on the fly.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(
            f"no database at '{db_path}'. Run "
            f"'python scripts/init_db.py {db_path}' to create it."
        )

    conn = connect(db_path)
    has_migrations_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if not has_migrations_table:
        conn.close()
        raise RuntimeError(
            f"'{db_path}' exists but has not been migrated. Run "
            f"'python scripts/init_db.py {db_path}' to migrate it."
        )
    return conn
