import asyncio
import json

import httpx

from mgc.models import Endpoint
from mgc.webhook_visitor import REQUEST_TIMEOUT_SECONDS, USER_AGENT, WebhookVisitor


def _endpoint(method="POST"):
    return Endpoint(
        id="endpoint-1",
        tenant_id="tenant-1",
        url="https://example.com/webhook",
        method=method,
        enabled=True,
    )


def test_visitor_sends_payload_and_headers():
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(204)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = asyncio.run(WebhookVisitor(client).visit(_endpoint(), '{"message":"hello"}'))
    finally:
        asyncio.run(client.aclose())

    assert result.status_code == 204
    assert result.retryable is False
    assert requests[0].method == "POST"
    assert requests[0].headers["User-Agent"] == USER_AGENT
    assert requests[0].headers["Accept"] == "application/json, text/plain, */*"
    assert json.loads(requests[0].content) == {"message": "hello"}


def test_visitor_retries_server_errors():
    async def handler(request):
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = asyncio.run(WebhookVisitor(client).visit(_endpoint(), "{}"))
    finally:
        asyncio.run(client.aclose())

    assert result.status_code == 503
    assert result.retryable is True


def test_visitor_rejects_client_errors():
    async def handler(request):
        return httpx.Response(400)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = asyncio.run(WebhookVisitor(client).visit(_endpoint(), "{}"))
    finally:
        asyncio.run(client.aclose())

    assert result.status_code == 400
    assert result.retryable is False


def test_visitor_retries_timeouts():
    async def handler(request):
        raise httpx.ReadTimeout("temporary timeout")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = asyncio.run(WebhookVisitor(client).visit(_endpoint(), "{}"))
    finally:
        asyncio.run(client.aclose())

    assert result.status_code is None
    assert result.retryable is True
    assert result.error == "temporary timeout"


def test_visitor_retries_network_errors():
    async def handler(request):
        raise httpx.ConnectError("connection failed")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = asyncio.run(WebhookVisitor(client).visit(_endpoint(), "{}"))
    finally:
        asyncio.run(client.aclose())

    assert result.status_code is None
    assert result.retryable is True
    assert result.error == "connection failed"


def test_visitor_uses_a_bounded_request_timeout():
    captured = []

    async def handler(request):
        captured.append(request.extensions["timeout"])
        return httpx.Response(204)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = asyncio.run(WebhookVisitor(client).visit(_endpoint(), "{}"))
    finally:
        asyncio.run(client.aclose())

    assert result.status_code == 204
    assert captured