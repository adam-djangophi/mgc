from mgc.repositories import DeliveryRepository, EndpointRepository, EventRepository


def _create_event_and_endpoint(conn, tenant_id="t1"):
    event = EventRepository(conn).create(tenant_id=tenant_id, event_type="e", payload={})
    endpoint = EndpointRepository(conn).create(tenant_id=tenant_id, url="https://example.com")
    return event, endpoint


def test_new_delivery_is_pending(conn):
    event, endpoint = _create_event_and_endpoint(conn)
    repo = DeliveryRepository(conn)

    delivery = repo.create(event_id=event.id, endpoint_id=endpoint.id, tenant_id="t1")

    assert delivery.status == "pending"
    assert delivery.attempt_count == 0
    assert delivery.claimed_by is None


def test_get_work(conn):
    event, endpoint = _create_event_and_endpoint(conn)
    repo = DeliveryRepository(conn)
    delivery = repo.create(event_id=event.id, endpoint_id=endpoint.id, tenant_id="t1")
    results = repo.get_work(delivery.id)

    assert results.delivery.id == delivery.id
    assert results.event.id == event.id
    assert results.endpoint.id == endpoint.id


def test_pending_delivery_can_be_claimed(conn):
    event, endpoint = _create_event_and_endpoint(conn)
    repo = DeliveryRepository(conn)
    delivery = repo.create(event_id=event.id, endpoint_id=endpoint.id, tenant_id="t1")

    assert delivery.status == "pending"
    assert delivery.claimed_by is None
    assert delivery.claim_token is None

    claimed = repo.claim(delivery.id, worker_id="worker-1", lease_seconds=60)

    assert claimed is not None
    assert claimed.status == "claimed"
    assert claimed.claimed_by == "worker-1"
    assert claimed.claim_token is not None


def test_active_claim_blocks_another_worker(conn):
    event, endpoint = _create_event_and_endpoint(conn)
    repo = DeliveryRepository(conn)
    delivery = repo.create(event_id=event.id, endpoint_id=endpoint.id, tenant_id="t1")
    repo.claim(delivery.id, worker_id="worker-1", lease_seconds=60)

    second_claim = repo.claim(delivery.id, worker_id="worker-2", lease_seconds=60)

    assert second_claim is None


def test_expired_claim_can_be_reclaimed(conn):
    event, endpoint = _create_event_and_endpoint(conn)
    repo = DeliveryRepository(conn)
    delivery = repo.create(event_id=event.id, endpoint_id=endpoint.id, tenant_id="t1")
    repo.claim(delivery.id, worker_id="worker-1", lease_seconds=-1)  # already expired

    second_claim = repo.claim(delivery.id, worker_id="worker-2", lease_seconds=60)

    assert second_claim is not None
    assert second_claim.claimed_by == "worker-2"


def test_finishing_delivery_clears_claim(conn):
    event, endpoint = _create_event_and_endpoint(conn)
    repo = DeliveryRepository(conn)
    delivery = repo.create(event_id=event.id, endpoint_id=endpoint.id, tenant_id="t1")
    repo.claim(delivery.id, worker_id="worker-1", lease_seconds=60)

    repo.mark_status(delivery.id, status="succeeded", increment_attempt=True)

    updated = repo.get(delivery.id)
    assert updated.status == "succeeded"
    assert updated.attempt_count == 1
    assert updated.claimed_by is None
    assert updated.claim_token is None


def test_stale_claim_token_cannot_change_delivery(conn):
    event, endpoint = _create_event_and_endpoint(conn)
    repo = DeliveryRepository(conn)
    delivery = repo.create(event_id=event.id, endpoint_id=endpoint.id, tenant_id="t1")
    claimed = repo.claim(delivery.id, worker_id="worker-1", lease_seconds=60)

    repo.mark_status(
        delivery.id,
        status="succeeded",
        increment_attempt=True,
        claim_token="stale-token",
    )

    current = repo.get(delivery.id)
    assert current.status == "claimed"
    assert current.claim_token == claimed.claim_token
    assert current.attempt_count == 0
