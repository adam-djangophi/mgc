import asyncio

from fastapi.testclient import TestClient

from mgc.app import create_app
from mgc.db import init_db
from mgc.repositories import (
    APIKeyRepository,
    DeliveryRepository,
    EndpointRepository,
    TenantRepository,
)
from mgc.worker import DeliveryWorker


class SuccessfulVisitor:
    async def visit(self, endpoint, payload):
        return 204, None


def _tenant_credentials(db_path, name):
    conn = init_db(db_path)
    try:
        tenant = TenantRepository(conn).create(name)
        _, api_key = APIKeyRepository(conn).create(tenant.id)
        return tenant, api_key
    finally:
        conn.close()


def test_event_creates_endpoint_and_delivery(tmp_path):
    db_path = str(tmp_path / "mgc.db")
    tenant, api_key = _tenant_credentials(db_path, "Tenant 123")
    client = TestClient(create_app(db_path))
    headers = {"Authorization": f"Bearer {api_key}"}
    event_request = {
        "event_type": "invoice.paid",
        "payload": {"invoice_id": "inv_123"},
        "endpoint": {"url": "https://example.com/webhooks", "method": "POST"},
    }

    response = client.post("/events", json=event_request, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert len(body["delivery_ids"]) == 1
    conn = init_db(db_path)
    try:
        endpoint = EndpointRepository(conn).get_by_tenant_url(
            tenant.id, event_request["endpoint"]["url"]
        )
        delivery = DeliveryRepository(conn).get(body["delivery_ids"][0])
    finally:
        conn.close()
    assert endpoint is not None
    assert delivery.event_id == body["event_id"]
    assert delivery.endpoint_id == endpoint.id
    assert delivery.tenant_id == tenant.id

    second = client.post("/events", json=event_request, headers=headers)
    assert second.status_code == 409


def test_event_creation_validation(tmp_path):
    db_path = str(tmp_path / "mgc.db")
    _, api_key = _tenant_credentials(db_path, "Tenant 123")
    client = TestClient(create_app(db_path))
    headers = {"Authorization": f"Bearer {api_key}"}

    missing_event_type = client.post(
        "/events",
        json={"endpoint": {"url": "https://example.com", "method": "POST"}},
        headers=headers,
    )
    invalid_url = client.post(
        "/events",
        json={
            "event_type": "invoice.paid",
            "endpoint": {"url": "not-a-url", "method": "POST"},
        },
        headers=headers,
    )
    invalid_method = client.post(
        "/events",
        json={
            "event_type": "invoice.paid",
            "endpoint": {"url": "https://example.com", "method": "TRACE"},
        },
        headers=headers,
    )

    assert missing_event_type.status_code == 422
    assert missing_event_type.json()["detail"][0]["msg"] == "Field required"

    assert invalid_url.status_code == 422
    assert invalid_url.json()["detail"][0]["msg"] == (
        "Input should be a valid URL, relative URL without a base"
    )
    assert invalid_method.status_code == 422
    assert invalid_method.json()["detail"][0]["msg"] == (
        "Input should be 'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD' or 'OPTIONS'"
    )


def test_good_delivery_shows_attempts(tmp_path):
    db_path = str(tmp_path / "mgc.db")
    _, api_key = _tenant_credentials(db_path, "Tenant 123")
    client = TestClient(create_app(db_path))
    headers = {"Authorization": f"Bearer {api_key}"}
    event = client.post(
        "/events",
        json={
            "event_type": "invoice.paid",
            "payload": {},
            "endpoint": {"url": "https://example.com", "method": "POST"},
        },
        headers=headers,
    ).json()
    delivery_id = event["delivery_ids"][0]
    conn = init_db(db_path)
    try:
        asyncio.run(DeliveryWorker(conn, SuccessfulVisitor()).process_queued(delivery_id))
    finally:
        conn.close()

    response = client.get(f"/deliveries/{delivery_id}", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["attempts"]) == 1


def test_can_only_access_own_deliveries(tmp_path):
    db_path = str(tmp_path / "mgc.db")
    _, api_key = _tenant_credentials(db_path, "Tenant 123")
    _, other_key = _tenant_credentials(db_path, "Other tenant")
    client = TestClient(create_app(db_path))
    headers = {"Authorization": f"Bearer {api_key}"}
    other_headers = {"Authorization": f"Bearer {other_key}"}
    event = client.post(
        "/events",
        json={
            "event_type": "invoice.paid",
            "payload": {},
            "endpoint": {"url": "https://example.com", "method": "POST"},
        },
        headers=headers,
    ).json()
    delivery_id = event["delivery_ids"][0]

    assert client.get(f"/deliveries/{delivery_id}", headers=other_headers).status_code == 404
    assert client.get("/deliveries/missing_id", headers=headers).status_code == 404


def test_authentication_rejects_bad_keys(tmp_path):
    db_path = str(tmp_path / "mgc.db")
    _tenant_credentials(db_path, "Tenant 123")
    client = TestClient(create_app(db_path))

    assert client.get("/endpoints").status_code == 401
    assert client.get(
        "/endpoints", headers={"Authorization": "Bearer invalid"}
    ).status_code == 401


def test_authentication_rejects_revoked_keys(tmp_path):
    db_path = str(tmp_path / "mgc.db")
    _, api_key = _tenant_credentials(db_path, "Tenant 123")
    client = TestClient(create_app(db_path))

    conn = init_db(db_path)
    try:
        key = APIKeyRepository(conn).get_active_by_key(api_key)
        APIKeyRepository(conn).revoke(key.id)
    finally:
        conn.close()

    assert client.get(
        "/endpoints", headers={"Authorization": f"Bearer {api_key}"}
    ).status_code == 401


def test_tenant_registration_returns_api_key(tmp_path):
    db_path = str(tmp_path / "mgc.db")
    client = TestClient(create_app(db_path))

    response = client.post("/tenants", json={"name": "Tenant 123"})

    assert response.status_code == 201
    body = response.json()
    assert client.get(
        "/endpoints", headers={"Authorization": f"Bearer {body['api_key']}"}
    ).status_code == 200
