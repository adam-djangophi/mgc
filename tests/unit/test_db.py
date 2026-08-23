import sqlite3

import pytest

from mgc.db import connect, require_db, run_migrations


def test_database_requires_a_file(tmp_path):
    missing = tmp_path / "does-not-exist.db"

    with pytest.raises(FileNotFoundError, match="scripts/init_db.py"):
        require_db(str(missing))


def test_database_requires_migrations(tmp_path):
    db_path = tmp_path / "unmigrated.db"
    sqlite3.connect(str(db_path)).close()  # create an empty, un-migrated file

    with pytest.raises(RuntimeError, match="scripts/init_db.py"):
        require_db(str(db_path))


def test_database_works_after_migrations(tmp_path):
    db_path = tmp_path / "app.db"
    bootstrap = connect(str(db_path))
    run_migrations(bootstrap)
    bootstrap.close()

    conn = require_db(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"events", "endpoints", "deliveries", "delivery_attempts"} <= tables
    finally:
        conn.close()
