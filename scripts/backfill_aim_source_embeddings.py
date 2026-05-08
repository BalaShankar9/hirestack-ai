"""Backfill pgvector embeddings for `aim_sources` (PR m6-pr19c).

One-shot async script. Paginates `aim_sources WHERE embedding IS NULL`
in batches, computes embeddings via OpenAI, and updates rows in place.
Idempotent: re-runs skip rows that already have an embedding.

Usage
-----
    python scripts/backfill_aim_source_embeddings.py --dry-run
    python scripts/backfill_aim_source_embeddings.py --batch-size 50
    python scripts/backfill_aim_source_embeddings.py --org-id <uuid>
    python scripts/backfill_aim_source_embeddings.py --limit 100

Exit code 0 on success, 1 on any embedding/update failure.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Optional

logger = logging.getLogger("aim_source_backfill")


# ── Pagination helper (extracted for testability) ──────────────────────


async def fetch_pending_batch(
    *,
    supabase: Any,
    batch_size: int,
    after_id: Optional[str] = None,
    org_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return the next batch of rows that need embedding.

    Sorted by `id` so we can paginate with a `> after_id` cursor and
    avoid OFFSET on a moving target.
    """
    query = (
        supabase.table("aim_sources")
        .select("id, title, extracted_summary, organization_id")
        .is_("embedding", None)
        .order("id")
        .limit(batch_size)
    )
    if after_id is not None:
        query = query.gt("id", after_id)
    if org_id is not None:
        query = query.eq("organization_id", org_id)
    resp = query.execute()
    return list(getattr(resp, "data", []) or [])


# ── Backfill loop ──────────────────────────────────────────────────────


async def run_backfill(
    *,
    service: Any,
    supabase: Any,
    batch_size: int,
    limit: Optional[int],
    org_id: Optional[str],
    dry_run: bool,
) -> dict[str, int]:
    """Drive the pagination + embedding loop.

    Returns counts: {scanned, embedded, skipped, failed}.
    """
    scanned = embedded = skipped = failed = 0
    cursor: Optional[str] = None

    while True:
        if limit is not None and scanned >= limit:
            break
        remaining = (limit - scanned) if limit is not None else batch_size
        page_size = min(batch_size, remaining)
        rows = await fetch_pending_batch(
            supabase=supabase, batch_size=page_size,
            after_id=cursor, org_id=org_id,
        )
        if not rows:
            break

        for row in rows:
            scanned += 1
            cursor = row["id"]
            if dry_run:
                logger.info(
                    "backfill.dry_run", extra={"source_id": row["id"]}
                )
                skipped += 1
                continue
            try:
                result = await service.embed_source(
                    source_id=row["id"],
                    title=row.get("title"),
                    extracted_summary=row.get("extracted_summary"),
                )
                if result is None:
                    skipped += 1
                else:
                    embedded += 1
            except Exception as exc:
                failed += 1
                logger.error(
                    "backfill.failed",
                    extra={"source_id": row["id"], "error": str(exc)},
                )

    return {
        "scanned": scanned,
        "embedded": embedded,
        "skipped": skipped,
        "failed": failed,
    }


# ── CLI entry point ────────────────────────────────────────────────────


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--batch-size", type=int, default=50)
    p.add_argument("--limit", type=int, default=None,
                   help="Stop after scanning this many rows (across batches).")
    p.add_argument("--org-id", type=str, default=None,
                   help="Restrict to a single organization (for staged rollouts).")
    p.add_argument("--dry-run", action="store_true",
                   help="List candidate rows without calling the embedder.")
    return p.parse_args(argv)


async def _main_async(args: argparse.Namespace) -> int:
    # Imports kept lazy so the test suite can exercise run_backfill /
    # fetch_pending_batch without the OpenAI/supabase deps at import time.
    from app.core.config import get_settings
    from app.core.supabase_admin import get_supabase_admin
    from app.services.aim.source_embeddings import (
        DEFAULT_MODEL,
        SourceEmbeddingsService,
    )
    from openai import AsyncOpenAI

    settings = get_settings()
    if not args.dry_run and not getattr(settings, "openai_api_key", None) \
            and not os.environ.get("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY missing; aborting.")
        return 1

    supabase = get_supabase_admin()
    client = AsyncOpenAI()

    async def embedder(text: str) -> list[float]:
        resp = await client.embeddings.create(
            model=DEFAULT_MODEL, input=text,
        )
        return resp.data[0].embedding

    service = SourceEmbeddingsService(supabase=supabase, embedder=embedder)
    counts = await run_backfill(
        service=service, supabase=supabase,
        batch_size=args.batch_size, limit=args.limit,
        org_id=args.org_id, dry_run=args.dry_run,
    )
    logger.info(
        "backfill.complete scanned=%d embedded=%d skipped=%d failed=%d",
        counts["scanned"], counts["embedded"],
        counts["skipped"], counts["failed"],
    )
    return 0 if counts["failed"] == 0 else 1


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _parse_args(argv)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
