"""Scheduler entry point.

Run via::

    cd /app/backend && PYTHONPATH=/app python -m app.scheduler.main

The process acquires a Redis leader lock and only then spins up the
periodic jobs.  Followers sit idle and re-poll every ``LOCK_RETRY_S``
seconds so they can take over on leader death.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

# Ensure backend root is on sys.path when invoked with -m.
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
logger = logging.getLogger("hirestack.scheduler")


LOCK_KEY = "hirestack:scheduler:leader"
LOCK_TTL_S = 30
LOCK_RETRY_S = 10


async def _run_jobs(stop: asyncio.Event) -> None:
    """Launch every periodic job; cancel them when ``stop`` is set."""
    from app.scheduler.jobs import (
        periodic_stale_job_cleanup,
        periodic_career_monitor_tick,
    )
    from app.core.config import settings as _cfg

    tasks: list[asyncio.Task] = [
        asyncio.create_task(
            periodic_stale_job_cleanup(), name="stale-job-cleanup"
        ),
    ]
    if _cfg.career_monitor_background_enabled:
        tasks.append(
            asyncio.create_task(
                periodic_career_monitor_tick(), name="career-monitor-tick"
            )
        )

    # JobWatchdog has its own start/stop lifecycle — bring it up too.
    watchdog = None
    try:
        from app.services.job_watchdog import JobWatchdog
        from app.core.database import get_supabase, TABLES

        watchdog = JobWatchdog(get_supabase(), TABLES)
        watchdog.start()
    except Exception as wd_err:
        logger.warning("scheduler.watchdog_start_failed: %s", str(wd_err)[:200])

    await stop.wait()

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    if watchdog is not None:
        try:
            await watchdog.stop()
        except Exception:
            pass


async def run() -> None:
    """Acquire leadership and run jobs.  Re-attempt on lease loss."""
    from app.scheduler.leader_lock import LeaderLock
    import redis.asyncio as aioredis
    from app.core.config import settings as _cfg

    stop = asyncio.Event()

    def _shutdown(*_: object) -> None:
        logger.info("scheduler.shutdown_signal")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except (NotImplementedError, RuntimeError):
            pass

    if not _cfg.redis_url:
        logger.error("scheduler.no_redis_url — cannot acquire leader lock; exiting")
        return
    redis = aioredis.from_url(
        _cfg.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    lock = LeaderLock(redis, LOCK_KEY, ttl_seconds=LOCK_TTL_S)

    while not stop.is_set():
        if await lock.acquire():
            logger.info("scheduler.leader_running")
            try:
                await _run_jobs(stop)
            finally:
                await lock.release()
            break
        else:
            logger.info(
                "scheduler.waiting_for_leadership retry_in=%ss", LOCK_RETRY_S
            )
            try:
                await asyncio.wait_for(stop.wait(), timeout=LOCK_RETRY_S)
            except asyncio.TimeoutError:
                continue

    logger.info("scheduler.exited")


if __name__ == "__main__":
    asyncio.run(run())
