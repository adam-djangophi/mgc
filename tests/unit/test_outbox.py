import asyncio
import json

from mgc.worker import DeliveryWorker, WebhookVisitResult
from mgc.outbox_publisher import OutboxPublisher
from mgc.repositories import DeliveryOutboxRepository, DeliveryRepository
from mgc.repositories.endpoints import EndpointRepository
from mgc.repositories.events import EventRepository


def _create_delivery(conn):
    event = EventRepository(conn).create("tenant-1", "test.event", {})
    endpoint = EndpointRepository(conn).create("tenant-1", "https://example.com/hook")
    return DeliveryRepository(conn).create(event.id, endpoint.id, "tenant-1")


def test_delivery_creation_adds_an_unpublished_outbox_message(conn):
    delivery = _create_delivery(conn)

    messages = DeliveryOutboxRepository(conn).list_due()

    assert [message.delivery_id for message in messages] == [delivery.id]


def test_is_published_after_queueing(conn):
    delivery = _create_delivery(conn)
    class Queue:
        def __init__(self):
            self.items = []

        async def put(self, value):
            self.items.append(value)

    queue = Queue()
    publisher = OutboxPublisher(conn, queue)

    assert asyncio.run(publisher.publish_once()) == 1
    assert queue.items == [delivery.id]
    assert DeliveryOutboxRepository(conn).list_due() == []


def test_broken_publish_reason_is_recorded(conn):
    _create_delivery(conn)

    class BrokenQueue:
        async def put(self, value):
            raise RuntimeError("queue unavailable")

    publisher = OutboxPublisher(conn, BrokenQueue())

    assert asyncio.run(publisher.publish_once()) == 0
    message = conn.execute("SELECT * FROM delivery_outbox").fetchone()
    assert message["published_at"] is None
    assert message["attempt_count"] == 1
    assert message["last_error"] == "queue unavailable"


def test_worker_processes_published_outbox_item(conn):
    delivery = _create_delivery(conn)

    class Queue:
        def __init__(self):
            self.items = []

        async def put(self, value):
            self.items.append(value)

    class Visitor:
        async def visit(self, endpoint, payload):
            assert endpoint.url == "https://example.com/hook"
            assert json.loads(payload) == {}
            return WebhookVisitResult(204)

    queue = Queue()
    publisher = OutboxPublisher(conn, queue)
    worker = DeliveryWorker(conn, Visitor())

    assert asyncio.run(publisher.publish_once()) == 1
    assert asyncio.run(worker.process_queued(queue.items.pop())) is not None

    outbox_message = conn.execute("SELECT * FROM delivery_outbox").fetchone()
    assert outbox_message["published_at"] is not None
    assert DeliveryRepository(conn).get(delivery.id).status == "succeeded"


def test_restart_resets_published_messages(conn):
    delivery = _create_delivery(conn)

    class Queue:
        async def put(self, value):
            pass

    queue = Queue()
    publisher = OutboxPublisher(conn, queue)
    asyncio.run(publisher.publish_once())

    outbox_message = conn.execute("SELECT * FROM delivery_outbox").fetchone()
    assert outbox_message["delivery_id"] == delivery.id
    assert outbox_message["published_at"] is not None
    assert DeliveryOutboxRepository(conn).list_due() == []

    DeliveryOutboxRepository(conn).reset_unfinished()

    # The message should be back in the outbox for retry
    assert [message.delivery_id for message in DeliveryOutboxRepository(conn).list_due()] == [
        delivery.id
    ]
    