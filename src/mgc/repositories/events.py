from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Optional

from mgc.db import utcnow_iso
from mgc.models import Event


class EventRepository:
    """Data access for the ``events`` table."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(
        self, tenant_id: str, event_type: str, payload: dict[str, Any], body_hash: str = ""
    ) -> Event:
        event = Event(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            event_type=event_type,
            payload=json.dumps(payload),
            created_at=utcnow_iso(),
            body_hash=body_hash,
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO events (id, tenant_id, event_type, payload, created_at, body_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event.id, event.tenant_id, event.event_type, event.payload, event.created_at, event.body_hash),
            )
        return event

    def create_uncommitted(
        self, tenant_id: str, event_type: str, payload: dict[str, Any], body_hash: str = ""
    ) -> Event:
        event = Event(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            event_type=event_type,
            payload=json.dumps(payload),
            created_at=utcnow_iso(),
            body_hash=body_hash,
        )
        self._conn.execute(
            """
            INSERT INTO events (id, tenant_id, event_type, payload, created_at, body_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event.id, event.tenant_id, event.event_type, event.payload, event.created_at, event.body_hash),
        )
        return event

    def get(self, event_id: str) -> Optional[Event]:
        row = self._conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        return Event.from_row(row) if row else None

    def list_by_tenant(self, tenant_id: str, limit: int = 100) -> list[Event]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit),
        ).fetchall()
        return [Event.from_row(row) for row in rows]

    def delete(self, event_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
