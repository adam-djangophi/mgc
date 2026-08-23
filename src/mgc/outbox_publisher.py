from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from mgc.repositories import DeliveryOutboxRepository

logger = logging.getLogger(__name__)


class OutboxPublisher:
    """Publishes durable outbox messages to an async queue."""

    def __init__(self, conn, queue: Any):
        self._conn = conn
        self._queue = queue
        self._outbox = DeliveryOutboxRepository(conn)

    async def publish_once(self, limit: int = 20) -> int:
        published = 0
        for message in self._outbox.list_due(limit):
            try:
                await self._queue.put(message.delivery_id)
            except Exception as exc:
                logger.exception("could not publish outbox message %s", message.id)
                self._outbox.mark_failed(
                    message.id, message.attempt_count + 1, str(exc)
                )
                continue

            self._outbox.mark_published(message.id)
            published += 1
            logger.info(
                "published delivery %s from outbox message %s",
                message.delivery_id,
                message.id,
            )
        return published

    async def run(
        self, poll_interval: float = 1.0, stop_event: Optional[asyncio.Event] = None
    ) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            if await self.publish_once() == 0:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
                except asyncio.TimeoutError:
                    pass
