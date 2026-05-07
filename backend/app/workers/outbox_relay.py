"""Outbox relay worker (PR m3-pr9).

Drains `events_outbox` and republishes each event onto a per-type
Redis Stream (`events:{event_type}`). Idempotent w.r.t. the outbox via
`outbox_claim_batch` (FOR UPDATE SKIP LOCKED), so multiple replicas can
run in parallel without double-publishing.

Failure modes:
  * XADD raises  → record_failure(error). publish_attempts already
    bumped by the claim. After `max_attempts` total attempts the row
    is marked dead_lettered_at and skipped on future claims.
  * RPC raises   → log + sleep, retry whole batch.
  * Empty batch  → sleep `idle_sleep_s`.

Behind `ff_outbox_relay`. When the flag is False (default), `main()`
exits 0 immediately so the Procfile entry is safe to enable in a release
where the flag is still off in the environment.
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_ATTEMPTS = 10
DEFAULT_IDLE_SLEEP_S = 1.0
DEFAULT_ERROR_SLEEP_S = 5.0
STREAM_PREFIX = "events:"


class _RedisLike(Protocol):
    async def xadd(self, name: str, fields: dict[str, str], *args: Any, **kwargs: Any) -> Any: ...


class _SupabaseLike(Protocol):
    def rpc(self, fn: str, params: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class RelayConfig:
    batch_size: int = DEFAULT_BATCH_SIZE
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    idle_sleep_s: float = DEFAULT_IDLE_SLEEP_S
    error_sleep_s: float = DEFAULT_ERROR_SLEEP_S


class OutboxRelay:
    """Pull-mode relay from Postgres outbox to Redis Streams."""

    def __init__(
        self,
        supabase: _SupabaseLike,
        redis: _RedisLike,
        *,
        config: RelayConfig | None = None,
    ) -> None:
        self._supabase = supabase
        self._redis = redis
        self._config = config or RelayConfig()
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        """Loop until `request_stop()` is called or the process is signalled."""
        logger.info("outbox_relay starting", extra={"config": self._config.__dict__})
        while not self._stop.is_set():
            try:
                published = await self.drain_once()
            except Exception:  # noqa: BLE001 — relay must survive
                logger.exception("outbox_relay drain failed")
                await self._sleep(self._config.error_sleep_s)
                continue
            if published == 0:
                await self._sleep(self._config.idle_sleep_s)
        logger.info("outbox_relay stopped")

    async def drain_once(self) -> int:
        """Claim and publish one batch. Returns number of rows published."""
        rows = self._claim_batch()
        if not rows:
            return 0

        published = 0
        for row in rows:
            try:
                await self._publish(row)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "outbox_relay publish failed",
                    extra={
                        "event_id": row.get("event_id"),
                        "event_type": row.get("event_type"),
                        "attempts": row.get("publish_attempts"),
                        "error": str(exc),
                    },
                )
                self._record_failure(row, str(exc))
                continue
            self._mark_published(row)
            published += 1
        return published

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _claim_batch(self) -> list[dict[str, Any]]:
        response = self._supabase.rpc(
            "outbox_claim_batch",
            {"p_batch_size": self._config.batch_size},
        ).execute()
        data = getattr(response, "data", None) or []
        return list(data)

    async def _publish(self, row: dict[str, Any]) -> None:
        event_type = row["event_type"]
        stream = f"{STREAM_PREFIX}{event_type}"
        payload = {
            "event_id": str(row["event_id"]),
            "event_type": event_type,
            "event_version": str(row["event_version"]),
            "org_id": str(row["org_id"]),
            "occurred_at": str(row["occurred_at"]),
            "payload": json.dumps(row.get("payload") or {}, default=str),
        }
        await self._redis.xadd(stream, payload)

    def _mark_published(self, row: dict[str, Any]) -> None:
        self._supabase.rpc(
            "outbox_mark_published",
            {
                "p_event_id": str(row["event_id"]),
                "p_occurred_at": str(row["occurred_at"]),
            },
        ).execute()

    def _record_failure(self, row: dict[str, Any], error: str) -> None:
        self._supabase.rpc(
            "outbox_record_failure",
            {
                "p_event_id": str(row["event_id"]),
                "p_occurred_at": str(row["occurred_at"]),
                "p_error": error[:1000],
                "p_max_attempts": self._config.max_attempts,
            },
        ).execute()

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return


# ---------------------------------------------------------------------------
# Entry point — `python -m app.workers.outbox_relay`
# ---------------------------------------------------------------------------


async def _amain() -> int:
    from app.core.config import settings

    if not getattr(settings, "ff_outbox_relay", False):
        logger.info("ff_outbox_relay disabled; outbox_relay exiting cleanly")
        return 0

    from app.core.supabase import get_supabase_client  # type: ignore[import-not-found]
    from app.core.redis_client import get_redis  # type: ignore[import-not-found]

    relay = OutboxRelay(supabase=get_supabase_client(), redis=await get_redis())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, relay.request_stop)
        except NotImplementedError:  # pragma: no cover — Windows
            pass

    await relay.run()
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    return asyncio.run(_amain())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
