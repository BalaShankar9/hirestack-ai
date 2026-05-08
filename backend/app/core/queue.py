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
import os
import time
from typing import Any, Callable, Coroutine, Dict

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
        _ensure_group(r)

        # Safety guard: if Redis is up but no worker is actively consuming,
        # don't enqueue and let caller fall back to in-process execution.
        from app.core.config import settings as _settings
        require_active_consumer = bool(_settings.queue_require_active_consumer)
        if require_active_consumer:
            consumers = await asyncio.to_thread(r.xinfo_consumers, STREAM_KEY, GROUP_NAME)
            active_consumers = [
                c for c in (consumers or [])
                if int(c.get("idle", CLAIM_IDLE_MS + 1)) < CLAIM_IDLE_MS
            ]
            if not active_consumers:
                logger.warning(
                    "queue.no_active_consumers_fallback",
                    extra={"job_id": job_id, "stream": STREAM_KEY, "group": GROUP_NAME},
                )
                return False

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
        """Dispatch a single message to the handler.

        Two paths, gated by ``ff_queue_ack_on_success`` (ADR-0040):

        - Flag OFF (legacy): always ACK in ``finally``. Handler is the
          sole arbiter of failure visibility (via DB row updates).
        - Flag ON: ACK only on handler success. Failures stay pending
          and are retried via ``_reclaim_pending``. After
          ``queue_max_deliveries`` total deliveries the message is
          XADDed to ``events:dlq`` and ACKed off the source. A
          ``processed_queue_events`` row guards against re-execution
          on at-least-once redelivery.
        """
        job_id = data.get("job_id", "")
        user_id = data.get("user_id", "")
        if not job_id or not user_id:
            # Malformed message — ACK and discard
            await asyncio.to_thread(r.xack, STREAM_KEY, GROUP_NAME, msg_id)
            return

        from app.core.config import settings as _settings
        ack_on_success = bool(getattr(_settings, "ff_queue_ack_on_success", False))

        if not ack_on_success:
            # ── Legacy path — bit-for-bit identical to pre-ADR-0040 ──
            async def _run_legacy() -> None:
                async with self._sem:
                    try:
                        await self.handler(job_id, user_id)
                    except Exception as exc:
                        logger.error(
                            "queue.job_handler_error",
                            extra={"job_id": job_id, "error": str(exc)[:300]},
                        )
                    finally:
                        try:
                            await asyncio.to_thread(r.xack, STREAM_KEY, GROUP_NAME, msg_id)
                        except Exception:
                            pass

            asyncio.create_task(_run_legacy())
            return

        # ── ACK-on-success path (ADR-0040) ──
        max_deliveries = max(1, int(getattr(_settings, "queue_max_deliveries", 5)))
        delivery_count = await self._delivery_count(r, msg_id)

        if delivery_count > max_deliveries:
            await self._dead_letter(
                r, msg_id, job_id, user_id,
                reason=f"max_deliveries_exceeded ({delivery_count}>{max_deliveries})",
            )
            return

        async def _run_ack_on_success() -> None:
            async with self._sem:
                try:
                    await self.handler(job_id, user_id)
                except Exception as exc:
                    # Do NOT ACK — message stays in PEL, reclaim will retry.
                    logger.warning(
                        "queue.job_handler_error",
                        extra={
                            "job_id": job_id,
                            "msg_id": msg_id,
                            "delivery": delivery_count,
                            "error": str(exc)[:300],
                        },
                    )
                    if delivery_count >= max_deliveries:
                        # This was the last allowed attempt — DLQ now
                        # rather than waiting for the next reclaim pass
                        # to notice and DLQ then.
                        try:
                            await self._dead_letter(
                                r, msg_id, job_id, user_id, reason=str(exc)[:500]
                            )
                        except Exception:
                            logger.exception("queue.dlq_failed_on_handler_error")
                    return

                # Success → record dedup row, then ACK. Duplicate row
                # means a previous delivery already processed this
                # msg_id (handler ran but ACK round-trip failed) —
                # treat as success.
                try:
                    inserted = await asyncio.to_thread(
                        self._record_processed, msg_id
                    )
                    if not inserted:
                        logger.info(
                            "queue.duplicate_delivery_skipped",
                            extra={"job_id": job_id, "msg_id": msg_id},
                        )
                except Exception:
                    # Dedup table down → still ACK (handler succeeded).
                    # Worst case: a redelivery re-runs the handler and the
                    # job's own state guards prevent duplicate side-effects.
                    logger.exception("queue.dedup_record_failed")

                try:
                    await asyncio.to_thread(r.xack, STREAM_KEY, GROUP_NAME, msg_id)
                except Exception:
                    logger.exception("queue.ack_failed_after_success")

        asyncio.create_task(_run_ack_on_success())

    async def _delivery_count(self, r: Any, msg_id: str) -> int:
        """Return the delivery count for this msg_id from XPENDING.

        Returns 1 if XPENDING reports nothing (first delivery, message
        not yet in the PEL view) — safe default that lets the handler
        proceed.
        """
        try:
            entries = await asyncio.to_thread(
                r.xpending_range,
                STREAM_KEY,
                GROUP_NAME,
                min=msg_id,
                max=msg_id,
                count=1,
            )
        except Exception:
            logger.warning("queue.xpending_range_failed", extra={"msg_id": msg_id})
            return 1

        if not entries:
            return 1
        entry = entries[0]
        # redis-py returns either {"times_delivered": N, ...} or a tuple
        # depending on version. Be defensive.
        if isinstance(entry, dict):
            return int(entry.get("times_delivered", 1))
        try:
            return int(entry[3])
        except Exception:
            return 1

    def _record_processed(self, msg_id: str) -> bool:
        """Insert (consumer, msg_id) into ``processed_queue_events``.

        Returns True if a new row was inserted, False if the row already
        existed (duplicate delivery). Synchronous — call via
        ``asyncio.to_thread``.
        """
        try:
            from app.core.database import get_db
            db = get_db()
        except Exception:
            logger.exception("queue.record_processed_no_db")
            return True  # fail-open: don't block the ACK

        try:
            db.client.table("processed_queue_events").insert(
                {"consumer": GROUP_NAME, "msg_id": msg_id}
            ).execute()
            return True
        except Exception as exc:
            err = str(exc).lower()
            if "duplicate key" in err or ("unique" in err and "violat" in err):
                return False
            raise

    async def _dead_letter(
        self,
        r: Any,
        msg_id: str,
        job_id: str,
        user_id: str,
        *,
        reason: str,
    ) -> None:
        """Push the message to the shared DLQ stream and ACK off source."""
        logger.error(
            "queue.dead_lettering",
            extra={
                "consumer": GROUP_NAME,
                "msg_id": msg_id,
                "job_id": job_id,
                "reason": reason,
            },
        )
        try:
            await asyncio.to_thread(
                r.xadd,
                "events:dlq",
                {
                    "consumer": GROUP_NAME,
                    "source_stream": STREAM_KEY,
                    "source_msg_id": msg_id,
                    "job_id": job_id,
                    "user_id": user_id,
                    "reason": reason,
                },
            )
        except Exception:
            logger.exception("queue.dlq_xadd_failed")
        try:
            await asyncio.to_thread(r.xack, STREAM_KEY, GROUP_NAME, msg_id)
        except Exception:
            logger.exception("queue.dlq_ack_failed")

    def stop(self) -> None:
        self._running = False
