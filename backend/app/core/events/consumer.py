"""Generic Redis Streams consumer scaffold (PR m3-pr10).

XREADGROUP + dedup via `consumed_events` table for effectively-once
delivery. Handler exceptions leave messages unacked; XAUTOCLAIM brings
them back. After `max_deliveries` the message is XADDed to
`events:dlq` and ACKed on the source stream.
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

logger = logging.getLogger(__name__)

DLQ_STREAM = "events:dlq"
DEFAULT_BLOCK_MS = 5000
DEFAULT_BATCH_SIZE = 16
DEFAULT_MAX_DELIVERIES = 5
DEFAULT_RECLAIM_IDLE_MS = 30_000

HandlerFn = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class ConsumerConfig:
    name: str
    streams: tuple[str, ...]
    group: str = ""
    block_ms: int = DEFAULT_BLOCK_MS
    batch_size: int = DEFAULT_BATCH_SIZE
    max_deliveries: int = DEFAULT_MAX_DELIVERIES
    reclaim_idle_ms: int = DEFAULT_RECLAIM_IDLE_MS

    @property
    def group_name(self) -> str:
        return self.group or self.name


class _DuplicateConsumed(Exception):
    pass


def _is_unique_violation(err: BaseException) -> bool:
    if getattr(err, "code", None) == "23505":
        return True
    msg = str(err).lower()
    return "duplicate key" in msg or ("unique" in msg and "violat" in msg)


class StreamConsumer:
    def __init__(self, redis: Any, supabase: Any, config: ConsumerConfig, handler: HandlerFn) -> None:
        self._redis = redis
        self._supabase = supabase
        self._config = config
        self._handler = handler
        self._stop = asyncio.Event()
        self._consumer_id = f"{config.name}-{uuid.uuid4().hex[:8]}"
        self._groups_ensured = False

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        logger.info("stream_consumer starting", extra={"consumer": self._config.name})
        await self._ensure_groups()
        while not self._stop.is_set():
            try:
                processed = await self._reclaim_pending()
                processed += await self._read_new()
            except Exception:
                logger.exception("stream_consumer loop iteration failed")
                await self._sleep(1.0)
                continue
            if processed == 0:
                await self._sleep(0.01)
        logger.info("stream_consumer stopped", extra={"consumer": self._config.name})

    async def _ensure_groups(self) -> None:
        if self._groups_ensured:
            return
        for stream in self._config.streams:
            try:
                await self._redis.xgroup_create(
                    name=stream, groupname=self._config.group_name, id="$", mkstream=True
                )
            except Exception as exc:
                if "BUSYGROUP" not in str(exc).upper():
                    raise
        self._groups_ensured = True

    async def _read_new(self) -> int:
        result = await self._redis.xreadgroup(
            groupname=self._config.group_name,
            consumername=self._consumer_id,
            streams={s: ">" for s in self._config.streams},
            count=self._config.batch_size,
            block=self._config.block_ms,
        )
        if not result:
            return 0
        total = 0
        for stream, messages in result:
            total += await self._process_messages(stream, messages, delivery_attempt=1)
        return total

    async def _reclaim_pending(self) -> int:
        total = 0
        for stream in self._config.streams:
            res = await self._redis.xautoclaim(
                name=stream,
                groupname=self._config.group_name,
                consumername=self._consumer_id,
                min_idle_time=self._config.reclaim_idle_ms,
                start_id="0-0",
                count=self._config.batch_size,
            )
            messages = (
                res[1]
                if isinstance(res, (list, tuple)) and len(res) >= 2 and isinstance(res[1], list)
                else (res or [])
            )
            if messages:
                total += await self._process_messages(stream, messages, delivery_attempt=2)
        return total

    async def _process_messages(self, stream: str, messages: Any, *, delivery_attempt: int) -> int:
        count = 0
        for msg_id, fields in messages:
            await self._handle_one(stream, msg_id, fields, delivery_attempt=delivery_attempt)
            count += 1
        return count

    async def _handle_one(
        self, stream: str, msg_id: str, fields: Mapping[str, Any], *, delivery_attempt: int
    ) -> None:
        event = self._decode(fields)
        event_id = event.get("event_id")
        if not event_id:
            logger.warning(
                "stream_consumer skipping event without event_id",
                extra={"consumer": self._config.name, "msg_id": msg_id},
            )
            await self._redis.xack(stream, self._config.group_name, msg_id)
            from app.core import queue_metrics as _qm
            _qm.inc_queue_ack(self._config.name)
            return

        if delivery_attempt > self._config.max_deliveries:
            await self._dead_letter(stream, msg_id, event, reason="max_deliveries_exceeded")
            return

        try:
            await self._handler(event)
        except Exception as exc:
            logger.warning(
                "stream_consumer handler raised",
                extra={
                    "consumer": self._config.name,
                    "event_id": event_id,
                    "attempt": delivery_attempt,
                    "error": str(exc),
                },
            )
            if delivery_attempt >= self._config.max_deliveries:
                await self._dead_letter(stream, msg_id, event, reason=str(exc)[:500])
            return

        try:
            self._record_consumed(event_id)
        except _DuplicateConsumed:
            pass

        await self._redis.xack(stream, self._config.group_name, msg_id)
        from app.core import queue_metrics as _qm
        _qm.inc_queue_ack(self._config.name)

    async def _dead_letter(
        self, stream: str, msg_id: str, event: dict[str, Any], *, reason: str
    ) -> None:
        logger.error(
            "stream_consumer dead-lettering event",
            extra={
                "consumer": self._config.name,
                "event_id": event.get("event_id"),
                "stream": stream,
                "reason": reason,
            },
        )
        await self._redis.xadd(
            DLQ_STREAM,
            {
                "consumer": self._config.name,
                "source_stream": stream,
                "source_msg_id": msg_id,
                "reason": reason,
                "event": json.dumps(event, default=str),
            },
        )
        from app.core import queue_metrics as _qm
        _qm.inc_queue_dlq(self._config.name, reason)
        await self._redis.xack(stream, self._config.group_name, msg_id)
        _qm.inc_queue_ack(self._config.name)

    def _record_consumed(self, event_id: str) -> None:
        try:
            self._supabase.table("consumed_events").insert(
                {"consumer": self._config.name, "event_id": event_id}
            ).execute()
        except Exception as exc:
            if _is_unique_violation(exc):
                raise _DuplicateConsumed(event_id) from exc
            raise

    @staticmethod
    def _decode(fields: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in fields.items():
            key = k.decode() if isinstance(k, bytes) else str(k)
            val = v.decode() if isinstance(v, bytes) else v
            out[key] = val
        payload_raw = out.get("payload")
        if isinstance(payload_raw, str):
            try:
                out["payload"] = json.loads(payload_raw)
            except (TypeError, ValueError):
                pass
        return out

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return


async def run_consumer(consumer: StreamConsumer) -> int:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, consumer.request_stop)
        except NotImplementedError:  # pragma: no cover
            pass
    await consumer.run()
    return 0
