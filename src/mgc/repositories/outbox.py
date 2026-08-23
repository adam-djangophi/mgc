from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from mgc.db import utcnow_iso
from mgc.models import DeliveryOutbox


class DeliveryOutboxRepository:
    """Stores delivery messages until they have been published to a queue."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create_uncommitted(self, delivery_id: str) -> DeliveryOutbox:
        now = utcnow_iso()
        message = DeliveryOutbox(
            id=str(uuid.uuid4()),
            delivery_id=delivery_id,
            created_at=now,
            published_at=None,
            attempt_count=0,
            next_attempt_at=now,
            last_error=None,
        )
        self._conn.execute(
            """
            INSERT INTO delivery_outbox
                (id, delivery_id, created_at, published_at, attempt_count,
                 next_attempt_at, last_error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (message.id, message.delivery_id, message.created_at,
             message.published_at, message.attempt_count,
             message.next_attempt_at, message.last_error),
        )
        return message

    def list_due(self, limit: int = 50) -> list[DeliveryOutbox]:
        rows = self._conn.execute(
            """
            SELECT * FROM delivery_outbox
            WHERE published_at IS NULL AND next_attempt_at <= ?
            ORDER BY next_attempt_at ASC
            LIMIT ?
            """,
            (utcnow_iso(), limit),
        ).fetchall()
        return [DeliveryOutbox.from_row(row) for row in rows]

    def mark_published(self, message_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE delivery_outbox SET published_at = ?, last_error = NULL WHERE id = ?",
                (utcnow_iso(), message_id),
            )

    def mark_failed(self, message_id: str, attempt_count: int, error: str) -> None:
        delay = 2 ** max(attempt_count - 1, 0)
        next_attempt = datetime.now(timezone.utc) + timedelta(seconds=delay)
        with self._conn:
            self._conn.execute(
                """
                UPDATE delivery_outbox
                SET attempt_count = ?, next_attempt_at = ?, last_error = ?
                WHERE id = ? AND published_at IS NULL
                """,
                (attempt_count, next_attempt.isoformat(timespec="seconds"), error, message_id),
            )

    def requeue(self, delivery_id: str, next_attempt_at: str) -> None:
        """Make a published delivery available to the publisher again."""
        with self._conn:
            self._conn.execute(
                """
                UPDATE delivery_outbox
                SET published_at = NULL, next_attempt_at = ?
                WHERE delivery_id = ?
                """,
                (next_attempt_at, delivery_id),
            )

    def reset_unfinished(self) -> None:
        """Republish nonterminal work after an in-process queue restart."""
        with self._conn:
            self._conn.execute(
                """
                UPDATE delivery_outbox
                SET published_at = NULL
                WHERE delivery_id IN (
                    SELECT id FROM deliveries WHERE status IN ('pending', 'claimed')
                )
                """
            )
