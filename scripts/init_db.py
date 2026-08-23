#!/usr/bin/env python3
"""Bootstrap: create (if needed) and migrate the mgc SQLite database.

Initialises the DB and runs migrations,  it's safe to re-run, since already-applied
migrations are skipped.

Interview context: The application entry point (`mgc` / `python -m mgc.main`) deliberately
does *not* do this itself: it expects an already-migrated database and
fails fast if one isn't there.

Usage:
    python scripts/init_db.py [db_path]
"""

from __future__ import annotations

import sys

from mgc.db import DEFAULT_DB_PATH, connect, run_migrations


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH

    conn = connect(db_path)
    try:
        applied = run_migrations(conn)
    finally:
        conn.close()

    if applied:
        print(f"applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        print("already up to date, nothing to apply")
    print(f"database ready at {db_path}")


if __name__ == "__main__":
    main()
