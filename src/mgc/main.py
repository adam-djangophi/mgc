"""Run the asynchronous webhook delivery worker."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from mgc.db import DEFAULT_DB_PATH, require_db
from mgc.outbox_publisher import OutboxPublisher
from mgc.repositories import DeliveryOutboxRepository
from mgc.worker import DeliveryWorker


async def run_worker(poll_interval: float) -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop_event.set)

    conn = require_db(DEFAULT_DB_PATH)
    queue = asyncio.Queue()
    try:
        DeliveryOutboxRepository(conn).reset_unfinished()
        await asyncio.gather(
            OutboxPublisher(conn, queue).run(poll_interval, stop_event),
            DeliveryWorker(conn).run_queue(queue, stop_event),
        )
    finally:
        conn.close()


def main() -> None:
    log_format = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    log_path = Path(__file__).resolve().parents[2] / "worker.log"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(),
        ],
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Seconds to wait when no deliveries are ready (default: 1.0)",
    )
    args = parser.parse_args()

    asyncio.run(run_worker(args.poll_interval))


if __name__ == "__main__":
    main()
