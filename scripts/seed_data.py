#!/usr/bin/env python3
"""Seed a local database with tenants, API keys, and events.

Usage:
    ./scripts/seed_data.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mgc.db import DEFAULT_DB_PATH, init_db
from mgc.repositories import (
    APIKeyRepository,
    DeliveryRepository,
    EndpointRepository,
    EventRepository,
    TenantRepository,
)


CREDENTIALS_PATH = Path(__file__).resolve().parent / "seed_credentials.json"
TENANT_COUNT = 10
EVENTS_PER_TENANT = 51


def clear_database(conn) -> None:
    with conn:
        for table in (
            "delivery_attempts",
            "delivery_outbox",
            "deliveries",
            "api_keys",
            "events",
            "endpoints",
            "tenants",
        ):
            conn.execute(f"DELETE FROM {table}")


def seed() -> Tuple[int, int]:
    conn = init_db(DEFAULT_DB_PATH)
    try:
        clear_database(conn)

        tenants = TenantRepository(conn)
        api_keys = APIKeyRepository(conn)
        events = EventRepository(conn)
        endpoints = EndpointRepository(conn)
        deliveries = DeliveryRepository(conn)
        total_events = 0
        total_deliveries = 0
        credentials = []

        for tenant_number in range(1, TENANT_COUNT + 1):
            tenant = tenants.create(f"Seed tenant {tenant_number}")
            _, api_key = api_keys.create(tenant.id)
            credentials.append(
                {"tenant_id": tenant.id, "name": tenant.name, "api_key": api_key}
            )
            print(f"tenant {tenant_number}: {tenant.id}  api_key={api_key}")
            endpoint = endpoints.create(
                tenant.id,
                f"https://example.com/seed/{tenant.id}",
                method="POST",
            )

            for event_number in range(1, EVENTS_PER_TENANT + 1):
                event = events.create(
                    tenant.id,
                    "seed.event",
                    {"tenant_number": tenant_number, "event_number": event_number},
                )
                deliveries.create(event.id, endpoint.id, tenant.id)
                total_events += 1
                total_deliveries += 1

        CREDENTIALS_PATH.write_text(json.dumps(credentials, indent=2) + "\n")
        os.chmod(CREDENTIALS_PATH, 0o600)
        return total_events, total_deliveries
    finally:
        conn.close()


def main() -> None:
    total_events, total_deliveries = seed()
    print(
        f"seeded {TENANT_COUNT} tenants, {total_events} events, "
        f"and {total_deliveries} deliveries in {DEFAULT_DB_PATH}"
    )


if __name__ == "__main__":
    main()
