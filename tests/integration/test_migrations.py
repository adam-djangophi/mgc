import sqlite3

from mgc.db import run_migrations


def test_migrations_create_tables():
    connection = sqlite3.connect(":memory:")
    try:
        run_migrations(connection)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "events",
            "endpoints",
            "deliveries",
            "delivery_attempts",
            "tenants",
            "api_keys",
            "delivery_outbox",
        } <= tables
    finally:
        connection.close()


def test_migrations_are_idempotent():
    connection = sqlite3.connect(":memory:")
    try:
        first = run_migrations(connection)
        second = run_migrations(connection)
        assert len(first) == 9
        assert second == []
    finally:
        connection.close()
