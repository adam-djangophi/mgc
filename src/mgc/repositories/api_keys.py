from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from typing import Optional, Tuple

from mgc.db import utcnow_iso
from mgc.models import APIKey


class APIKeyRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, tenant_id: str) -> Tuple[APIKey, str]:
        # Generate a new API key for the given tenant. Returns a tuple of (APIKey, raw_key).
        raw_key = secrets.token_urlsafe(32)
        api_key = APIKey(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            key_hash=hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
            created_at=utcnow_iso(),
            revoked_at=None,
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO api_keys (id, tenant_id, key_hash, created_at, revoked_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    api_key.id,
                    api_key.tenant_id,
                    api_key.key_hash,
                    api_key.created_at,
                    api_key.revoked_at,
                ),
            )
        return api_key, raw_key

    def get_active_by_key(self, raw_key: str) -> Optional[APIKey]:
        # given a raw API key, hash it and look up the corresponding active APIKey record
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        row = self._conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL",
            (key_hash,),
        ).fetchone()
        return APIKey.from_row(row) if row else None

    def revoke(self, api_key_id: str) -> None:
        # Revokes an API key
        with self._conn:
            self._conn.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE id = ?",
                (utcnow_iso(), api_key_id),
            )