import asyncio
import json
from datetime import datetime, timedelta, timezone

from mgc.repositories import DeliveryRepository, EndpointRepository, EventRepository
from mgc.worker import DeliveryWorker, MAX_ATTEMPTS


class FakeVisitor:
    def __init__(self, statuses):
        self.statuses = iter(statuses)
        self.calls = []

    async def visit(self, endpoint, payload):
        self.calls.append((endpoint.method, endpoint.url, json.loads(payload)))
        return next(self.statuses), None

def create_pending_delivery(conn, method="POST"):
    event = EventRepository(conn).create("t1", "video_uploaded", {"id": 1})
    endpoint = EndpointRepository(conn).create("t1", "https://example.com/hook", method)
    return DeliveryRepository(conn).create(event.id, endpoint.id, "t1")


def test_worker_completes_delivery(conn):
    delivery = create_pending_delivery(conn)
    visitor = FakeVisitor([204])

    processed = asyncio.run(DeliveryWorker(conn, visitor).process_queued(delivery.id))

    assert processed.id == delivery.id
    final = DeliveryRepository(conn).get(delivery.id)
    assert final.status == "succeeded"
    assert final.attempt_count == 1
    assert final.claim_token is None
    assert final.claim_expires_at is None
    assert visitor.calls == [("POST", "https://example.com/hook", {"id": 1})]


def test_worker_retries_with_backoff(conn):
    delivery = create_pending_delivery(conn)
    visitor = FakeVisitor([500])

    before = datetime.now(timezone.utc)
    asyncio.run(DeliveryWorker(conn, visitor).process_queued(delivery.id))

    retry = DeliveryRepository(conn).get(delivery.id)
    retry_at = datetime.fromisoformat(retry.next_attempt_at)
    assert retry.status == "pending"
    assert retry.attempt_count == 1
    assert retry_at >= before + timedelta(seconds=1)
    assert retry_at <= before + timedelta(seconds=5)


def test_worker_reclaims_expired_delivery(conn):
    delivery = create_pending_delivery(conn)
    repo = DeliveryRepository(conn)
    # immediate expiration to simulate a crashed worker
    repo.claim(delivery.id, worker_id="crashed-worker", lease_seconds=-1)
    visitor = FakeVisitor([204])
    # the claim that runs in process_queued should succeed in claiming because the previous claim has expired
    processed = asyncio.run(DeliveryWorker(conn, visitor).process_queued(delivery.id))

    assert processed.id == delivery.id
    final = repo.get(delivery.id)
    assert final.status == "succeeded"
    assert final.attempt_count == 1
    assert visitor.calls == [("POST", "https://example.com/hook", {"id": 1})]


def test_worker_stops_after_five_attempts(conn):
    delivery = create_pending_delivery(conn)
    visitor = FakeVisitor([500] * MAX_ATTEMPTS)
    worker = DeliveryWorker(conn, visitor)

    statuses = []
    for _ in range(MAX_ATTEMPTS):
        asyncio.run(worker.process_queued(delivery.id))
        runningStatus = DeliveryRepository(conn).get(delivery.id)
        statuses.append(runningStatus.status)

    assert statuses == ["pending"] * (MAX_ATTEMPTS - 1) + ["dead"]
    final = DeliveryRepository(conn).get(delivery.id)
    assert final.attempt_count == MAX_ATTEMPTS


def test_worker_ignores_missing_queued_delivery(conn):
    processed = asyncio.run(DeliveryWorker(conn).process_queued("missing-delivery-id"))

    assert processed is None




