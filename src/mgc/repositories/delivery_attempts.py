from __future__ import annotations

import sqlite3
import uuid
from typing import Optional

from mgc.db import utcnow_iso
from mgc.models import DeliveryAttempt


class DeliveryAttemptRepository:
    """Data access for the ``delivery_attempts`` table."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def start(
        self,
        delivery_id: str,
        attempt_number: int,
        worker_id: str,
        claim_token: str,
    ) -> DeliveryAttempt:
        attempt = DeliveryAttempt(
            id=str(uuid.uuid4()),
            delivery_id=delivery_id,
            attempt_number=attempt_number,
            worker_id=worker_id,
            claim_token=claim_token,
            started_at=utcnow_iso(),
            finished_at=None,
            outcome=None,
            http_status=None,
            error=None,
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO delivery_attempts (
                    id, delivery_id, attempt_number, worker_id, claim_token,
                    started_at, finished_at, outcome, http_status, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.id,
                    attempt.delivery_id,
                    attempt.attempt_number,
                    attempt.worker_id,
                    attempt.claim_token,
                    attempt.started_at,
                    attempt.finished_at,
                    attempt.outcome,
                    attempt.http_status,
                    attempt.error,
                ),
            )
        return attempt

    def finish(
        self,
        attempt_id: str,
        outcome: str,
        http_status: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                UPDATE delivery_attempts
                SET finished_at = ?, outcome = ?, http_status = ?, error = ?
                WHERE id = ?
                """,
                (utcnow_iso(), outcome, http_status, error, attempt_id),
            )

    def get(self, attempt_id: str) -> Optional[DeliveryAttempt]:
        row = self._conn.execute(
            "SELECT * FROM delivery_attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        return DeliveryAttempt.from_row(row) if row else None

    def list_by_delivery(self, delivery_id: str) -> list[DeliveryAttempt]:
        rows = self._conn.execute(
            "SELECT * FROM delivery_attempts WHERE delivery_id = ? ORDER BY attempt_number ASC",
            (delivery_id,),
        ).fetchall()
        return [DeliveryAttempt.from_row(row) for row in rows]
