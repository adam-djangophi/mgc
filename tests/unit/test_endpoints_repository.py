from mgc.repositories import EndpointRepository


def test_endpoint_can_be_created_and_read(conn):
    repo = EndpointRepository(conn)
    endpoint = repo.create(tenant_id="t1", url="https://example.com/hook")

    fetched = repo.get(endpoint.id)

    assert fetched == endpoint
    assert fetched.enabled is True


def test_endpoint_can_start_disabled(conn):
    repo = EndpointRepository(conn)
    endpoint = repo.create(tenant_id="t1", url="https://example.com/hook", enabled=False)

    assert repo.get(endpoint.id).enabled is False


def test_endpoint_list_is_tenant_scoped(conn):
    repo = EndpointRepository(conn)
    repo.create(tenant_id="t1", url="https://a", enabled=True)
    repo.create(tenant_id="t1", url="https://b", enabled=False)
    repo.create(tenant_id="t2", url="https://c", enabled=True)

    results = repo.list_by_tenant("t1", enabled_only=True)

    assert len(results) == 1
    assert results[0].url == "https://a"


def test_endpoint_can_be_toggled(conn):
    repo = EndpointRepository(conn)
    endpoint = repo.create(tenant_id="t1", url="https://a", enabled=True)

    repo.set_enabled(endpoint.id, False)

    assert repo.get(endpoint.id).enabled is False
