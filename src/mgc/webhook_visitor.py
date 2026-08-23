from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from mgc.models import Endpoint

USER_AGENT = "mgc-webhook-worker/0.1"
REQUEST_TIMEOUT_SECONDS = 10.0
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookVisitResult:
    status_code: Optional[int]
    error: Optional[str] = None
    retryable: bool = False


class WebhookVisitor:
    """Send one event payload to its configured webhook endpoint."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._client = client

    async def visit(self, endpoint: Endpoint, payload: str) -> WebhookVisitResult:
        request_payload = json.loads(payload)
        logger.info("visiting webhook %s %s", endpoint.method, endpoint.url)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        }
        try:
            if self._client is not None:
                response = await self._client.request(
                    endpoint.method, endpoint.url, json=request_payload, headers=headers
                )
            else:
                async with httpx.AsyncClient(
                    timeout=REQUEST_TIMEOUT_SECONDS
                ) as client:
                    response = await client.request(
                        endpoint.method, endpoint.url, json=request_payload, headers=headers
                    )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning(
                "webhook visit failed for %s %s: %s",
                endpoint.method,
                endpoint.url,
                exc,
            )
            return WebhookVisitResult(None, str(exc), retryable=True)

        retryable = response.status_code == 429 or response.status_code >= 500
        error = None if 200 <= response.status_code < 300 else (
            f"webhook returned HTTP {response.status_code}"
        )
        if error is not None:
            logger.warning(
                "webhook returned HTTP %s for %s %s",
                response.status_code,
                endpoint.method,
                endpoint.url,
            )
        else:
            logger.info(
                "webhook returned HTTP %s for %s %s",
                response.status_code,
                endpoint.method,
                endpoint.url,
            )
        return WebhookVisitResult(response.status_code, error, retryable)
