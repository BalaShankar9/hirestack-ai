"""Standalone worker process for consuming generation jobs from Redis Streams.

Run via::

    cd /app/backend && PYTHONPATH=/app python -m app.worker

Or in Railway via the ``worker`` process in Procfile.
"""
import asyncio
import logging
import os
import signal
import sys

# Ensure the backend package root is on sys.path when invoked with -m
_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import structlog  # noqa: E402

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = logging.getLogger("hirestack.worker")


async def _handler(job_id: str, user_id: str) -> None:
    """Execute a generation job — delegates to the same runner the web process uses."""
    from app.api.routes.generate.jobs import _run_generation_job_via_runtime

    logger.info("worker.processing", extra={"job_id": job_id, "user_id": user_id})
    await _run_generation_job_via_runtime(job_id, user_id)
    logger.info("worker.completed", extra={"job_id": job_id})


async def main() -> None:
    from app.core.queue import QueueConsumer

    from app.core.config import settings
    consumer_name = settings.worker_name
    concurrency = settings.worker_concurrency

    consumer = QueueConsumer(
        handler=_handler,
        consumer_name=consumer_name,
        concurrency=concurrency,
    )

    # Graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.get_running_loop()

    def _shutdown(*_: object) -> None:
        logger.info("worker.shutdown_signal")
        consumer.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except (NotImplementedError, RuntimeError):
            pass  # Windows

    logger.info("worker.starting", extra={"consumer": consumer_name, "concurrency": concurrency})
    await consumer.run()
    logger.info("worker.exited")


if __name__ == "__main__":
    asyncio.run(main())
