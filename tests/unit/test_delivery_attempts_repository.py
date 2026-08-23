from mgc.repositories import (
    DeliveryAttemptRepository,
    DeliveryRepository,
    EndpointRepository,
    EventRepository,
)


def _create_delivery(conn, tenant_id="t1"):
    event = EventRepository(conn).create(tenant_id=tenant_id, event_type="e", payload={})
    endpoint = EndpointRepository(conn).create(tenant_id=tenant_id, url="https://example.com")
    return DeliveryRepository(conn).create(event_id=event.id, endpoint_id=endpoint.id, tenant_id=tenant_id)


def test_attempt_can_be_started_and_read(conn):
    delivery = _create_delivery(conn)
    repo = DeliveryAttemptRepository(conn)

    attempt = repo.start(
        delivery_id=delivery.id, attempt_number=1, worker_id="worker-1", claim_token="tok-1"
    )

    fetched = repo.get(attempt.id)
    assert fetched == attempt
    assert fetched.finished_at is None
    assert fetched.outcome is None


def test_finished_attempt_has_outcome_and_time(conn):
    delivery = _create_delivery(conn)
    repo = DeliveryAttemptRepository(conn)
    attempt = repo.start(
        delivery_id=delivery.id, attempt_number=1, worker_id="worker-1", claim_token="tok-1"
    )

    repo.finish(attempt.id, outcome="success", http_status=200)

    fetched = repo.get(attempt.id)
    assert fetched.outcome == "success"
    assert fetched.http_status == 200
    assert fetched.finished_at is not None


def test_failed_attempt_keeps_error(conn):
    delivery = _create_delivery(conn)
    repo = DeliveryAttemptRepository(conn)
    attempt = repo.start(
        delivery_id=delivery.id, attempt_number=1, worker_id="worker-1", claim_token="tok-1"
    )

    repo.finish(attempt.id, outcome="failure", http_status=500, error="connection reset")

    fetched = repo.get(attempt.id)
    assert fetched.outcome == "failure"
    assert fetched.error == "connection reset"


def test_attempts_are_ordered(conn):
    delivery = _create_delivery(conn)
    repo = DeliveryAttemptRepository(conn)
    repo.start(delivery_id=delivery.id, attempt_number=2, worker_id="w", claim_token="t2")
    repo.start(delivery_id=delivery.id, attempt_number=1, worker_id="w", claim_token="t1")

    results = repo.list_by_delivery(delivery.id)

    assert [a.attempt_number for a in results] == [1, 2]
