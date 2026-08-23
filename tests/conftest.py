import sqlite3

import pytest

from mgc.db import run_migrations

@pytest.fixture
def conn():
    """An isolated, fully-migrated in-memory database for a single test."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    run_migrations(connection)
    yield connection
    connection.close()
