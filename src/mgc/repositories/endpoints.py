from __future__ import annotations

import sqlite3
import uuid
from typing import Optional

from mgc.models import Endpoint


class EndpointRepository:
    """Data access for the ``endpoints`` table."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(
        self, tenant_id: str, url: str, method: str = "POST", enabled: bool = True
    ) -> Endpoint:
        with self._conn:
            return self.create_uncommitted(tenant_id, url, method, enabled)

    def create_uncommitted(
        self, tenant_id: str, url: str, method: str = "POST", enabled: bool = True
    ) -> Endpoint:
        endpoint = Endpoint(
            id=str(uuid.uuid4()), tenant_id=tenant_id, url=url, method=method, enabled=enabled
        )
        self._insert(endpoint)
        return endpoint

    def _insert(self, endpoint: Endpoint) -> None:
        self._conn.execute(
            "INSERT INTO endpoints (id, tenant_id, url, method, enabled) VALUES (?, ?, ?, ?, ?)",
            (endpoint.id, endpoint.tenant_id, endpoint.url, endpoint.method, int(endpoint.enabled)),
        )

    def get_by_tenant_url(
        self, tenant_id: str, url: str, method: str = "POST"
    ) -> Optional[Endpoint]:
        row = self._conn.execute(
            "SELECT * FROM endpoints WHERE tenant_id = ? AND url = ? AND method = ?",
            (tenant_id, url, method),
        ).fetchone()
        return Endpoint.from_row(row) if row else None

    def get(self, endpoint_id: str) -> Optional[Endpoint]:
        row = self._conn.execute(
            "SELECT * FROM endpoints WHERE id = ?", (endpoint_id,)
        ).fetchone()
        return Endpoint.from_row(row) if row else None

    def list_by_tenant(self, tenant_id: str, enabled_only: bool = False) -> list[Endpoint]:
        if enabled_only:
            rows = self._conn.execute(
                "SELECT * FROM endpoints WHERE tenant_id = ? AND enabled = 1",
                (tenant_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM endpoints WHERE tenant_id = ?", (tenant_id,)
            ).fetchall()
        return [Endpoint.from_row(row) for row in rows]

    def set_enabled(self, endpoint_id: str, enabled: bool) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE endpoints SET enabled = ? WHERE id = ?",
                (int(enabled), endpoint_id),
            )

    def delete(self, endpoint_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM endpoints WHERE id = ?", (endpoint_id,))
