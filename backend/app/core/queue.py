"""Durable job queue backed by Redis Streams.

Provides at-least-once delivery with consumer groups. Falls back to
in-process ``asyncio.create_task`` when Redis is unavailable so the
single-process deployment path still works.

Stream name : ``hirestack:generation_jobs``
Consumer group: ``gen_workers``
Each message carries ``job_id`` and ``user_id``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger("hirestack.queue")

STREAM_KEY = "hirestack:generation_jobs"
GROUP_NAME = "gen_workers"

# How long a consumer can hold a message before it can be claimed by another
CLAIM_IDLE_MS = 5 * 60 * 1000  # 5 minutes
# How many messages to read per XREADGROUP call
READ_BATCH = 5
# Block timeout for XREADGROUP (ms)
READ_BLOCK_MS = 5000


# ── Producer ──────────────────────────────────────────────────────────


def _get_redis():
    """Import get_redis lazily to avoid circular imports at module load."""
    from app.core.database import get_redis
    return get_redis()


def _ensure_group(r: Any) -> None:
    """Create the consumer group if it doesn't already exist."""
    try:
        r.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info("queue.group_created", extra={"stream": STREAM_KEY, "group": GROUP_NAME})
    except Exception as exc:
        # BUSYGROUP = group already exists → safe to ignore
        if "BUSYGROUP" in str(exc):
            pass
        else:
            raise


async def enqueue_generation_job(job_id: str, user_id: str) -> bool:
    """Add a generation job to the Redis Stream.

    Returns True if successfully enqueued, False if Redis is unavailable
    (caller should fall back to in-process execution).
    """
    r = _get_redis()
    if r is None:
        return False
    try:
        msg_id = await asyncio.to_thread(
            r.xadd,
            STREAM_KEY,
            {"job_id": job_id, "user_id": user_id, "enqueued_at": str(time.time())},
        )
        logger.info("queue.enqueued", extra={"job_id": job_id, "msg_id": msg_id})
        return True
    except Exception as exc:
        logger.warning("queue.enqueue_failed", extra={"job_id": job_id, "error": str(exc)[:200]})
        return False


def queue_depth() -> int:
    """Return approximate number of pending messages (for health checks)."""
    r = _get_redis()
    if r is None:
        return -1
    try:
        return r.xlen(STREAM_KEY)
    except Exception:
        return -1


# ── Consumer ─────────────────────────────────────────────────────────

JobHandler = Callable[[str, str], Coroutine[Any, Any, None]]


class QueueConsumer:
    """Long-running consumer that reads from the Redis Stream and dispatches
    generation jobs to a handler function.

    Usage::

        consumer = QueueConsumer(handler=my_async_handler, consumer_name="w1")
        await consumer.run()  # blocks forever
    """

    def __init__(
        self,
        handler: JobHandler,
        consumer_name: str = "worker-1",
        concurrency: int = 3,
    ) -> None:
        self.handler = handler
        self.consumer_name = consumer_name
        self._sem = asyncio.Semaphore(concurrency)
        self._running = True

    async def run(self) -> None:
        """Main consumer loop — blocks until ``stop()`` is called."""
        r = _get_redis()
        if r is None:
            logger.error("queue.consumer_no_redis — cannot start consumer without Redis")
            return

        _ensure_group(r)
        logger.info("queue.consumer_started", extra={"consumer": self.consumer_name})

        # First pass: re-claim any pending messages from crashed consumers
        await self._reclaim_pending(r)

        while self._running:
            try:
                messages = await asyncio.to_thread(
                    r.xreadgroup,
                    GROUP_NAME,
                    self.consumer_name,
                    {STREAM_KEY: ">"},
                    count=READ_BATCH,
                    block=READ_BLOCK_MS,
                )
                if not messages:
                    continue

                for _stream, entries in messages:
                    for msg_id, data in entries:
                        await self._dispatch(r, msg_id, data)

            except asyncio.CancelledError:
                logger.info("queue.consumer_cancelled")
                break
            except Exception as exc:
                logger.error("queue.consumer_error", extra={"error": str(exc)[:300]})
                await asyncio.sleep(2)  # back off on transient errors

        logger.info("queue.consumer_stopped", extra={"consumer": self.consumer_name})

    async def _reclaim_pending(self, r: Any) -> None:
        """On startup, re-claim messages that have been idle too long
        (previous consumer crashed before ACK-ing)."""
        try:
            pending = await asyncio.to_thread(
                r.xpending_range,
                STREAM_KEY,
                GROUP_NAME,
                min="-",
                max="+",
                count=50,
            )
            if not pending:
                return

            stale_ids = [
                entry["message_id"]
                for entry in pending
                if entry.get("time_since_delivered", 0) > CLAIM_IDLE_MS
            ]
            if not stale_ids:
                return

            claimed = await asyncio.to_thread(
                r.xclaim,
                STREAM_KEY,
                GROUP_NAME,
                self.consumer_name,
                min_idle_time=CLAIM_IDLE_MS,
                message_ids=stale_ids,
            )
            logger.info("queue.reclaimed_pending", extra={"count": len(claimed)})

            for msg_id, data in claimed:
                await self._dispatch(r, msg_id, data)

        except Exception as exc:
            logger.warning("queue.reclaim_error", extra={"error": str(exc)[:200]})

    async def _dispatch(self, r: Any, msg_id: str, data: Dict[str, str]) -> None:
        """Dispatch a single message to the handler, ACK on success."""
        job_id = data.get("job_id", "")
        user_id = data.get("user_id", "")
        if not job_id or not user_id:
            # Malformed message — ACK and discard
            await asyncio.to_thread(r.xack, STREAM_KEY, GROUP_NAME, msg_id)
            return

        async def _run() -> None:
            async with self._sem:
                try:
                    await self.handler(job_id, user_id)
                except Exception as exc:
                    logger.error(
                        "queue.job_handler_error",
                        extra={"job_id": job_id, "error": str(exc)[:300]},
                    )
                finally:
                    # Always ACK — the handler is responsible for marking the
                    # DB job as failed on error; we don't want infinite retries
                    # of a permanently failing job.
                    try:
                        await asyncio.to_thread(r.xack, STREAM_KEY, GROUP_NAME, msg_id)
                    except Exception:
                        pass

        asyncio.create_task(_run())

    def stop(self) -> None:
        self._running = False
