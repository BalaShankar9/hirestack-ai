"""Billing-usage StreamConsumer (PR m3-pr10).

Listens on `events:generation.completed`. Real billing storage lands
in PR-11+; for now this proves end-to-end delivery. Behind
`ff_event_consumer`; the Procfile entry exits cleanly when off so it
can ship before the flag flip.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

CONSUMER_NAME = "billing_usage"
SOURCE_STREAM = "events:generation.completed"


async def handle_generation_completed(event: dict[str, Any]) -> None:
    payload = event.get("payload") or {}
    logger.info(
        "billing_usage observed generation.completed",
        extra={
            "event_id": event.get("event_id"),
            "org_id": event.get("org_id"),
            "model": payload.get("model"),
            "tokens": payload.get("tokens"),
            "cost_usd": payload.get("cost_usd"),
        },
    )


async def _amain() -> int:
    from app.core.config import settings

    if not getattr(settings, "ff_event_consumer", False):
        logger.info("ff_event_consumer disabled; billing_usage exiting cleanly")
        return 0

    from app.core.events.consumer import ConsumerConfig, StreamConsumer, run_consumer
    from app.core.redis_client import get_redis  # type: ignore[import-not-found]
    from app.core.supabase import get_supabase_client  # type: ignore[import-not-found]

    consumer = StreamConsumer(
        redis=await get_redis(),
        supabase=get_supabase_client(),
        config=ConsumerConfig(name=CONSUMER_NAME, streams=(SOURCE_STREAM,)),
        handler=handle_generation_completed,
    )
    return await run_consumer(consumer)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    return asyncio.run(_amain())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
