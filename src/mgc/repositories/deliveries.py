from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from mgc.db import utcnow_iso
from mgc.models import Delivery, DeliveryWorkItem, Endpoint, Event
from mgc.repositories.outbox import DeliveryOutboxRepository


class DeliveryRepository:
    """Data access for the ``deliveries`` table.

    A delivery moves through a simple lifecycle: ``pending`` -> ``claimed``
    (by a worker, via :meth:`claim`) -> a terminal or retryable status set
    by :meth:`mark_status` (e.g. ``succeeded``, ``failed``, ``dead``).
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(
        self,
        event_id: str,
        endpoint_id: str,
        tenant_id: str,
        next_attempt_at: Optional[str] = None,
    ) -> Delivery:
        now = utcnow_iso()
        delivery = Delivery(
            id=str(uuid.uuid4()),
            event_id=event_id,
            endpoint_id=endpoint_id,
            tenant_id=tenant_id,
            status="pending",
            attempt_count=0,
            next_attempt_at=next_attempt_at or now,
            claimed_by=None,
            claim_token=None,
            claim_expires_at=None,
            created_at=now,
            updated_at=now,
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO deliveries (
                    id, event_id, endpoint_id, tenant_id, status, attempt_count,
                    next_attempt_at, claimed_by, claim_token, claim_expires_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery.id,
                    delivery.event_id,
                    delivery.endpoint_id,
                    delivery.tenant_id,
                    delivery.status,
                    delivery.attempt_count,
                    delivery.next_attempt_at,
                    delivery.claimed_by,
                    delivery.claim_token,
                    delivery.claim_expires_at,
                    delivery.created_at,
                    delivery.updated_at,
                ),
            )
            DeliveryOutboxRepository(self._conn).create_uncommitted(delivery.id)
        return delivery

    def create_uncommitted(
        self,
        event_id: str,
        endpoint_id: str,
        tenant_id: str,
        next_attempt_at: Optional[str] = None,
    ) -> Delivery:
        now = utcnow_iso()
        delivery = Delivery(
            id=str(uuid.uuid4()),
            event_id=event_id,
            endpoint_id=endpoint_id,
            tenant_id=tenant_id,
            status="pending",
            attempt_count=0,
            next_attempt_at=next_attempt_at or now,
            claimed_by=None,
            claim_token=None,
            claim_expires_at=None,
            created_at=now,
            updated_at=now,
        )
        self._conn.execute(
            """
            INSERT INTO deliveries (
                id, event_id, endpoint_id, tenant_id, status, attempt_count,
                next_attempt_at, claimed_by, claim_token, claim_expires_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                delivery.id, delivery.event_id, delivery.endpoint_id,
                delivery.tenant_id, delivery.status, delivery.attempt_count,
                delivery.next_attempt_at, delivery.claimed_by, delivery.claim_token,
                delivery.claim_expires_at, delivery.created_at, delivery.updated_at,
            ),
        )
        DeliveryOutboxRepository(self._conn).create_uncommitted(delivery.id)
        return delivery

    def get(self, delivery_id: str) -> Optional[Delivery]:
        row = self._conn.execute(
            "SELECT * FROM deliveries WHERE id = ?", (delivery_id,)
        ).fetchone()
        return Delivery.from_row(row) if row else None

    def get_by_tenant(self, delivery_id: str, tenant_id: str) -> Optional[Delivery]:
        row = self._conn.execute(
            "SELECT * FROM deliveries WHERE id = ? AND tenant_id = ?",
            (delivery_id, tenant_id),
        ).fetchone()
        return Delivery.from_row(row) if row else None

    def list_by_event(self, event_id: str) -> list[Delivery]:
        rows = self._conn.execute(
            "SELECT * FROM deliveries WHERE event_id = ?", (event_id,)
        ).fetchall()
        return [Delivery.from_row(row) for row in rows]

    def get_work(self, delivery_id: str) -> Optional[DeliveryWorkItem]:
        row = self._conn.execute(
            """
            SELECT d.*,
                   e.id AS event_row_id,
                   e.tenant_id AS event_tenant_id,
                   e.event_type AS event_type,
                   e.payload AS event_payload,
                   e.created_at AS event_created_at,
                   e.body_hash AS event_body_hash,
                   p.id AS endpoint_row_id,
                   p.tenant_id AS endpoint_tenant_id,
                   p.url AS endpoint_url,
                   p.method AS endpoint_method,
                   p.enabled AS endpoint_enabled
            FROM deliveries AS d
            JOIN events AS e ON e.id = d.event_id
            JOIN endpoints AS p ON p.id = d.endpoint_id
            WHERE d.id = ?
            """,
            (delivery_id,),
        ).fetchone()
        if row is None:
            return None
        return DeliveryWorkItem(
            delivery=Delivery.from_row(row),
            event=Event(
                id=row["event_row_id"],
                tenant_id=row["event_tenant_id"],
                event_type=row["event_type"],
                payload=row["event_payload"],
                created_at=row["event_created_at"],
                body_hash=row["event_body_hash"],
            ),
            endpoint=Endpoint(
                id=row["endpoint_row_id"],
                tenant_id=row["endpoint_tenant_id"],
                url=row["endpoint_url"],
                method=row["endpoint_method"],
                enabled=bool(row["endpoint_enabled"]),
            ),
        )

    def claim(self, delivery_id, worker_id: str, lease_seconds: int = 60) -> Optional[Delivery]:
        """Atomically claim a pending/expired delivery for a worker.

        Returns the updated ``Delivery`` on success, or ``None`` if it was
        not available to claim (already claimed by an unexpired worker, or
        does not exist).
        """
        claim_token = str(uuid.uuid4())
        delivery_object = delivery_id if isinstance(delivery_id, Delivery) else None
        delivery_id_value = delivery_object.id if delivery_object else delivery_id
        now = datetime.now(timezone.utc)
        claim_expires_at = (now + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds")
        now_iso = now.isoformat(timespec="seconds")

        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE deliveries
                SET status = 'claimed',
                    claimed_by = ?,
                    claim_token = ?,
                    claim_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND (
                        status = 'pending'
                        OR (status = 'claimed' AND claim_expires_at <= ?)
                      )
                """,
                (worker_id, claim_token, claim_expires_at, now_iso, delivery_id_value, now_iso),
            )
            if cursor.rowcount == 0:
                return None
        if delivery_object is not None:
            return Delivery(
                id=delivery_object.id,
                event_id=delivery_object.event_id,
                endpoint_id=delivery_object.endpoint_id,
                tenant_id=delivery_object.tenant_id,
                status="claimed",
                attempt_count=delivery_object.attempt_count,
                next_attempt_at=delivery_object.next_attempt_at,
                claimed_by=worker_id,
                claim_token=claim_token,
                claim_expires_at=claim_expires_at,
                created_at=delivery_object.created_at,
                updated_at=now_iso,
            )
        return self.get(delivery_id_value)

    def mark_status(
        self,
        delivery_id: str,
        status: str,
        next_attempt_at: Optional[str] = None,
        increment_attempt: bool = False,
        claim_token: Optional[str] = None,
    ) -> None:
        """Update status (and optionally next_attempt_at / attempt_count).

        Also clears the claim fields, since a status transition means the
        worker is done with its lease.
        """
        increment_sql = "+ 1" if increment_attempt else ""
        token_sql = " AND claim_token = ?" if claim_token is not None else ""
        parameters = [status, next_attempt_at, utcnow_iso(), delivery_id]
        if claim_token is not None:
            parameters.append(claim_token)
        with self._conn:
            self._conn.execute(
                f"""
                UPDATE deliveries
                SET status = ?,
                    next_attempt_at = ?,
                    attempt_count = attempt_count {increment_sql},
                    claimed_by = NULL,
                    claim_token = NULL,
                    claim_expires_at = NULL,
                    updated_at = ?
                WHERE id = ?{token_sql}
                """,
                parameters,
            )

    def delete(self, delivery_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM deliveries WHERE id = ?", (delivery_id,))
