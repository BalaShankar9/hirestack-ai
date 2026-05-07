"""AIM source-embedding StreamConsumer (PR m6-pr19). Behind ff_aim_rag.

Listens on events:aim.source.{created,updated}; loads the row and
computes/persists an embedding via SourceEmbeddingsService.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

CONSUMER_NAME = "aim_source_embed"
SOURCE_STREAMS = (
    "events:aim.source.created",
    "events:aim.source.updated",
)


async def handle_source_event(event: dict[str, Any]) -> None:
    payload = event.get("payload") or {}
    source_id = payload.get("source_id") or payload.get("id")
    if not source_id:
        logger.warning(
            "aim_source_embed.missing_source_id",
            extra={"event_id": event.get("event_id")},
        )
        return

    from app.core.supabase import get_supabase_client  # type: ignore[import-not-found]
    from app.services.aim.source_embeddings import SourceEmbeddingsService

    sb = get_supabase_client()
    row_resp = sb.table("aim_sources").select(
        "id,title,extracted_summary"
    ).eq("id", source_id).maybe_single().execute()
    row = getattr(row_resp, "data", None)
    if not row:
        logger.info(
            "aim_source_embed.row_missing",
            extra={"source_id": source_id},
        )
        return

    embedder = await _build_embedder()
    service = SourceEmbeddingsService(supabase=sb, embedder=embedder)
    await service.embed_source(
        source_id=row["id"],
        title=row.get("title"),
        extracted_summary=row.get("extracted_summary"),
    )


async def _build_embedder():  # pragma: no cover - thin provider seam
    from openai import AsyncOpenAI  # type: ignore[import-not-found]

    client = AsyncOpenAI()

    async def _embed(text: str) -> list[float]:
        resp = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return list(resp.data[0].embedding)

    return _embed


async def _amain() -> int:
    from app.core.config import settings

    if not getattr(settings, "ff_aim_rag", False):
        logger.info("ff_aim_rag disabled; aim_source_embed exiting cleanly")
        return 0
    if not getattr(settings, "ff_event_consumer", False):
        logger.info(
            "ff_event_consumer disabled; aim_source_embed exiting cleanly"
        )
        return 0

    from app.core.events.consumer import ConsumerConfig, StreamConsumer, run_consumer
    from app.core.redis_client import get_redis  # type: ignore[import-not-found]
    from app.core.supabase import get_supabase_client  # type: ignore[import-not-found]

    consumer = StreamConsumer(
        redis=await get_redis(),
        supabase=get_supabase_client(),
        config=ConsumerConfig(name=CONSUMER_NAME, streams=SOURCE_STREAMS),
        handler=handle_source_event,
    )
    return await run_consumer(consumer)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    return asyncio.run(_amain())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
