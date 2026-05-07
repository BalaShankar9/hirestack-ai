"""Generation-status StreamConsumer (PR m6-pr18).

Listens on `events:generation.workflow_status`. The Temporal
`GenerationWorkflow` (see `backend/app/temporal/workflows/__init__.py`)
emits a single status event per step transition through the
`emit_event` activity; this consumer fans those events out to the
existing job-status pipeline so the SSE stream and `generation_jobs`
table stay accurate while we strangler-cut the legacy in-process path.

Behind `ff_event_consumer` (same flag as `billing_usage`); the
Procfile entry exits cleanly when off so it can ship before Temporal
is enabled. Real persistence is wired in PR-18b once the workflow's
`emit_event` activity is bound to a hook that pushes onto the stream.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

CONSUMER_NAME = "generation_status"
SOURCE_STREAM = "events:generation.workflow_status"


async def handle_workflow_status(event: dict[str, Any]) -> None:
    """Log + (eventually) mirror to generation_jobs / SSE stream."""
    payload = event.get("payload") or {}
    logger.info(
        "generation_status observed workflow_status",
        extra={
            "event_id": event.get("event_id"),
            "org_id": event.get("org_id"),
            "job_id": payload.get("job_id"),
            "step": payload.get("step"),
            "status": payload.get("status"),
            "workflow_id": payload.get("workflow_id"),
        },
    )


async def _amain() -> int:
    from app.core.config import settings

    if not getattr(settings, "ff_event_consumer", False):
        logger.info(
            "ff_event_consumer disabled; generation_status exiting cleanly"
        )
        return 0

    from app.core.events.consumer import ConsumerConfig, StreamConsumer, run_consumer
    from app.core.redis_client import get_redis  # type: ignore[import-not-found]
    from app.core.supabase import get_supabase_client  # type: ignore[import-not-found]

    consumer = StreamConsumer(
        redis=await get_redis(),
        supabase=get_supabase_client(),
        config=ConsumerConfig(name=CONSUMER_NAME, streams=(SOURCE_STREAM,)),
        handler=handle_workflow_status,
    )
    return await run_consumer(consumer)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    return asyncio.run(_amain())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
