import asyncio
import json

import httpx

from mgc.repositories import (
    DeliveryAttemptRepository,
    DeliveryRepository,
    EndpointRepository,
    EventRepository,
    TenantRepository,
)
from mgc.outbox_publisher import OutboxPublisher
from mgc.worker import CONCURRENCY, DeliveryWorker, WebhookVisitor


def _seed_deliveries(conn, tenants=10, events_per_tenant=51):
    tenant_repo = TenantRepository(conn)
    endpoint_repo = EndpointRepository(conn)
    event_repo = EventRepository(conn)
    delivery_repo = DeliveryRepository(conn)
    deliveries = []

    for tenant_number in range(tenants):
        tenant = tenant_repo.create(f"Fixture tenant {tenant_number}")
        endpoint = endpoint_repo.create(
            tenant.id,
            f"https://example.com/{tenant.id}",
            method="POST",
        )
        for event_number in range(events_per_tenant):
            event = event_repo.create(
                tenant.id,
                "fixture.created",
                {"tenant_number": tenant_number, "event_number": event_number},
            )
            deliveries.append(
                delivery_repo.create(event.id, endpoint.id, tenant.id)
            )

    return deliveries


class FixtureQueue:
    def __init__(self):
        self.items = []

    async def put(self, value):
        self.items.append(value)


async def _process_all(worker, publisher, queue, expected_count):
    processed_count = 0
    while processed_count < expected_count:
        await publisher.publish_once(limit=CONCURRENCY)
        delivery_ids = queue.items[:CONCURRENCY]
        del queue.items[:CONCURRENCY]
        processed = await asyncio.gather(
            *(worker.process_queued(delivery_id) for delivery_id in delivery_ids)
        )
        batch_count = sum(item is not None for item in processed)
        assert batch_count > 0
        processed_count += batch_count
    return processed_count


def test_worker_processes_fixture_batch(conn):
    deliveries = _seed_deliveries(conn)
    requests = []

    async def handler(request):
        requests.append(
            (request.method, str(request.url), json.loads(request.content))
        )
        return httpx.Response(204)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        worker = DeliveryWorker(conn, WebhookVisitor(client))
        queue = FixtureQueue()
        publisher = OutboxPublisher(conn, queue)
        processed_count = asyncio.run(
            _process_all(worker, publisher, queue, len(deliveries))
        )
    finally:
        asyncio.run(client.aclose())

    assert processed_count == 510
    assert len(requests) == 510
    assert all(method == "POST" for method, _, _ in requests)
    assert all(
        delivery.status == "succeeded"
        for delivery in DeliveryRepository(conn).list_by_event(
            deliveries[0].event_id
        )
    )
    succeeded = conn.execute(
        "SELECT COUNT(*) FROM deliveries WHERE status = 'succeeded'"
    ).fetchone()[0]
    attempts = conn.execute("SELECT COUNT(*) FROM delivery_attempts").fetchone()[0]
    assert succeeded == 510
    assert attempts == 510


def test_worker_succeeds_after_2_transient_failures(conn):
    async def run_test():
        deliveries = _seed_deliveries(conn, tenants=1, events_per_tenant=1)
        fakeResponses = iter([
            httpx.Response(503),
            httpx.Response(429),
            httpx.Response(204),
        ])

        async def handler(request):
            return next(fakeResponses)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            worker = DeliveryWorker(conn, WebhookVisitor(client))
            delivery_id = deliveries[0].id

            for _ in range(3):
                    await worker.process_queued(delivery_id)
        finally:
            await client.aclose()

        return delivery_id

    delivery_id = asyncio.run(run_test())
    delivery = DeliveryRepository(conn).get(delivery_id)
    attempts = DeliveryAttemptRepository(conn).list_by_delivery(delivery_id)
    assert delivery.status == "succeeded"
    assert delivery.attempt_count == 3
    assert [attempt.http_status for attempt in attempts] == [503, 429, 204]
