from __future__ import annotations

import sqlite3
import uuid

from mgc.db import utcnow_iso
from mgc.models import Tenant


class TenantRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, name: str) -> Tenant:
        tenant = Tenant(id=str(uuid.uuid4()), name=name, created_at=utcnow_iso())
        with self._conn:
            self._conn.execute(
                "INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)",
                (tenant.id, tenant.name, tenant.created_at),
            )
        return tenant

    def get(self, tenant_id: str) -> Tenant | None:
        row = self._conn.execute(
            "SELECT * FROM tenants WHERE id = ?", (tenant_id,)
        ).fetchone()
        return Tenant.from_row(row) if row else None