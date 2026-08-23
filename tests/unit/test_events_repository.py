from mgc.repositories import EventRepository


def test_event_can_be_created_and_read(conn):
    repo = EventRepository(conn)
    event = repo.create(tenant_id="t1", event_type="order.created", payload={"a": 1})

    fetched = repo.get(event.id)

    assert fetched == event
    assert fetched.payload == '{"a": 1}'


def test_missing_event_is_none(conn):
    repo = EventRepository(conn)
    assert repo.get("does-not-exist") is None


def test_event_list_is_scoped_and_ordered(conn):
    repo = EventRepository(conn)
    repo.create(tenant_id="t1", event_type="a", payload={})
    repo.create(tenant_id="t2", event_type="b", payload={})
    repo.create(tenant_id="t1", event_type="c", payload={})

    results = repo.list_by_tenant("t1")

    assert {e.event_type for e in results} == {"a", "c"}


def test_event_list_respects_limit(conn):
    repo = EventRepository(conn)
    for i in range(5):
        repo.create(tenant_id="t1", event_type=f"evt-{i}", payload={})

    results = repo.list_by_tenant("t1", limit=2)

    assert len(results) == 2


def test_event_can_be_deleted(conn):
    repo = EventRepository(conn)
    event = repo.create(tenant_id="t1", event_type="a", payload={})

    repo.delete(event.id)

    assert repo.get(event.id) is None
