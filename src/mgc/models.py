"""Dataclasses representing rows of each table.

These are plain data holders. All DB access lives in ``mgc.repositories``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Tenant":
        return cls(id=row["id"], name=row["name"], created_at=row["created_at"])


@dataclass(frozen=True)
class APIKey:
    id: str
    tenant_id: str
    key_hash: str
    created_at: str
    revoked_at: Optional[str]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "APIKey":
        return cls(
            id=row["id"],
            tenant_id=row["tenant_id"],
            key_hash=row["key_hash"],
            created_at=row["created_at"],
            revoked_at=row["revoked_at"],
        )


@dataclass(frozen=True)
class Event:
    id: str
    tenant_id: str
    event_type: str
    payload: str
    created_at: str
    body_hash: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Event":
        return cls(
            id=row["id"],
            tenant_id=row["tenant_id"],
            event_type=row["event_type"],
            payload=row["payload"],
            created_at=row["created_at"],
            body_hash=row["body_hash"],
        )


@dataclass(frozen=True)
class Endpoint:
    id: str
    tenant_id: str
    url: str
    method: str
    enabled: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Endpoint":
        return cls(
            id=row["id"],
            tenant_id=row["tenant_id"],
            url=row["url"],
            method=row["method"],
            enabled=bool(row["enabled"]),
        )


@dataclass(frozen=True)
class Delivery:
    id: str
    event_id: str
    endpoint_id: str
    tenant_id: str
    status: str
    attempt_count: int
    next_attempt_at: Optional[str]
    claimed_by: Optional[str]
    claim_token: Optional[str]
    claim_expires_at: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Delivery":
        return cls(
            id=row["id"],
            event_id=row["event_id"],
            endpoint_id=row["endpoint_id"],
            tenant_id=row["tenant_id"],
            status=row["status"],
            attempt_count=row["attempt_count"],
            next_attempt_at=row["next_attempt_at"],
            claimed_by=row["claimed_by"],
            claim_token=row["claim_token"],
            claim_expires_at=row["claim_expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass(frozen=True)
class DeliveryWorkItem:
    """A due delivery with the event and endpoint needed to send it."""

    delivery: Delivery
    event: Event
    endpoint: Endpoint


@dataclass(frozen=True)
class DeliveryOutbox:
    id: str
    delivery_id: str
    created_at: str
    published_at: Optional[str]
    attempt_count: int
    next_attempt_at: str
    last_error: Optional[str]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DeliveryOutbox":
        return cls(
            id=row["id"],
            delivery_id=row["delivery_id"],
            created_at=row["created_at"],
            published_at=row["published_at"],
            attempt_count=row["attempt_count"],
            next_attempt_at=row["next_attempt_at"],
            last_error=row["last_error"],
        )


@dataclass(frozen=True)
class DeliveryAttempt:
    id: str
    delivery_id: str
    attempt_number: int
    worker_id: Optional[str]
    claim_token: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    outcome: Optional[str]
    http_status: Optional[int]
    error: Optional[str]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DeliveryAttempt":
        return cls(
            id=row["id"],
            delivery_id=row["delivery_id"],
            attempt_number=row["attempt_number"],
            worker_id=row["worker_id"],
            claim_token=row["claim_token"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            outcome=row["outcome"],
            http_status=row["http_status"],
            error=row["error"],
        )
