from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from mgc.models import Delivery, Endpoint
from mgc.repositories import (
    DeliveryAttemptRepository,
    DeliveryRepository,
    DeliveryOutboxRepository,
)
from mgc.webhook_visitor import WebhookVisitResult, WebhookVisitor

MAX_ATTEMPTS = 5
CONCURRENCY = 20
logger = logging.getLogger(__name__)


class DeliveryWorker:
    def __init__(
        self,
        conn,
        visitor: Optional[WebhookVisitor] = None,
        lease_seconds: int = 60,
        semaphore: Optional[asyncio.Semaphore] = None,
    ):
        self._conn = conn
        self._worker_id = f"worker-{uuid.uuid4()}"
        self._visitor = visitor or WebhookVisitor()
        self._lease_seconds = lease_seconds
        self._semaphore = semaphore

    async def _visit_delivery(
        self, endpoint: Endpoint, event_payload: str
    ) -> WebhookVisitResult:
        async with self._semaphore:
            result = await self._visitor.visit(endpoint, event_payload)
        if isinstance(result, tuple):
            status_code, error = result
            return WebhookVisitResult(
                status_code,
                error,
                retryable=status_code is None or status_code == 429 or status_code >= 500,
            )
        return result

    def _complete_delivery(
        self,
        delivery: Delivery,
        attempt_number: int,
        result: WebhookVisitResult,
        attempt_id: str,
    ) -> None:
        succeeded = result.status_code is not None and 200 <= result.status_code < 300
        outcome = "success" if succeeded else "failure"
        error = result.error
        if not succeeded and error is None:
            error = "webhook returned a non-success status"

        DeliveryAttemptRepository(self._conn).finish(
            attempt_id, outcome, http_status=result.status_code, error=error
        )
        deliveries = DeliveryRepository(self._conn)
        outbox = DeliveryOutboxRepository(self._conn)
        if succeeded:
            logger.info("delivery %s succeeded on attempt %s", delivery.id, attempt_number)
            deliveries.mark_status(
                delivery.id, "succeeded", increment_attempt=True, claim_token=delivery.claim_token
            )
        elif not result.retryable or attempt_number >= MAX_ATTEMPTS:
            logger.error(
                "delivery %s marked dead on attempt %s: %s",
                delivery.id,
                attempt_number,
                error,
            )
            deliveries.mark_status(
                delivery.id, "dead", increment_attempt=True, claim_token=delivery.claim_token
            )
        else:
            delay_seconds = 2 ** (attempt_number - 1)
            next_attempt = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            logger.warning(
                "delivery %s will retry after attempt %s at %s: %s",
                delivery.id,
                attempt_number,
                next_attempt.isoformat(),
                error,
            )
            deliveries.mark_status(
                delivery.id,
                "pending",
                next_attempt_at=next_attempt.isoformat(),
                increment_attempt=True,
                claim_token=delivery.claim_token,
            )
            outbox.requeue(delivery.id, next_attempt.isoformat())

    async def process_queued(self, delivery_id: str) -> Optional[Delivery]:
        """Process one delivery ID received from the queue."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(CONCURRENCY)
        work = DeliveryRepository(self._conn).get_work(delivery_id)
        if work is None:
            logger.warning("queued delivery %s no longer exists", delivery_id)
            return None

        delivery = DeliveryRepository(self._conn).claim(
            work.delivery, self._worker_id, lease_seconds=self._lease_seconds
        )
        if delivery is None:
            logger.debug("queued delivery %s was already claimed", delivery_id)
            return None

        attempt = DeliveryAttemptRepository(self._conn).start(
            delivery.id,
            delivery.attempt_count + 1,
            self._worker_id,
            delivery.claim_token,
        )
        try:
            result = await self._visit_delivery(work.endpoint, work.event.payload)
        except Exception as exc:
            logger.exception("error processing queued delivery %s", delivery.id)
            result = WebhookVisitResult(None, str(exc), retryable=True)
        self._complete_delivery(delivery, delivery.attempt_count + 1, result, attempt.id)
        return delivery

    async def run_queue(self, queue, stop_event: Optional[asyncio.Event] = None) -> None:
        """Consume delivery IDs from an async queue with 20 workers."""
        stop_event = stop_event or asyncio.Event()
        logger.info("delivery worker started with %s queue consumers", CONCURRENCY)
        async def consume() -> None:
            while not stop_event.is_set():
                try:
                    delivery_id = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                try:
                    await self.process_queued(delivery_id)
                finally:
                    queue.task_done()

        await asyncio.gather(*(consume() for _ in range(CONCURRENCY)))
        logger.info("delivery worker stopped")

