"""Company-intel prefetch endpoint (W4 Functionality gaps).

Lets the frontend speculatively warm up company intelligence the moment a
user picks a JD — before they even click Generate. The heavy intel
gathering (7 sub-agents across web/news/reviews/culture/etc.) overlaps
with whatever the user is doing on the page (reviewing the JD, adjusting
settings). By the time the full pipeline kicks off, intel is usually
already in cache and the Recon phase resolves in milliseconds.

Endpoint
--------
POST /api/intel/prefetch
    body: {"jd_text": str, "job_title": str, "company": str,
           "company_url": str | null}
    returns: {"status": "cached" | "queued" | "skipped",
              "jd_hash": str}

- "cached"  : already in cache, no work launched.
- "queued"  : intel task is running in the background; result will be
              written to JDAnalysisCache under the same key and consumed
              by the next pipeline run for this (jd_text, job_title).
- "skipped" : feature disabled or intel chain unavailable.

Cache key
---------
We reuse :class:`ai_engine.cache.JDAnalysisCache` with a namespaced key
so intel and JD-analysis entries don't collide:
    key = "intel_" + JDAnalysisCache.hash_jd(jd_text, job_title)

Rate limit: 30/hour per IP — matches the realistic cadence of a user
browsing job postings.
"""
import asyncio
from typing import Any, Dict, Optional

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.security import limiter

logger = structlog.get_logger("hirestack.intel_prefetch")
router = APIRouter()


class PrefetchRequest(BaseModel):
    jd_text: str = Field(..., min_length=50, max_length=40_000)
    job_title: str = Field(..., min_length=1, max_length=300)
    company: str = Field(..., min_length=1, max_length=200)
    company_url: Optional[str] = Field(None, max_length=500)


def _intel_cache_key(jd_text: str, job_title: str) -> str:
    """Namespaced cache key — distinct from plain JD-analysis entries."""
    from ai_engine.cache import JDAnalysisCache  # local import: cold-start friendly
    return "intel_" + JDAnalysisCache.hash_jd(jd_text, job_title)


async def _run_and_cache(
    key: str, company: str, job_title: str, jd_text: str,
    company_url: Optional[str],
) -> None:
    """Background task: gather intel, write to JDAnalysisCache.

    Failures are swallowed (logged only) — a prefetch is best-effort; the
    pipeline will retry if the user kicks off generation before we finish.
    """
    try:
        from ai_engine.cache import get_jd_cache
        from ai_engine.chains.company_intel import CompanyIntelChain
        from ai_engine.client import AIClient

        client = AIClient()
        chain = CompanyIntelChain(client)
        result = await chain.gather_intel(
            company=company,
            job_title=job_title,
            jd_text=jd_text,
            company_url=company_url,
        )
        if isinstance(result, dict) and result:
            get_jd_cache().put(key, result)
            logger.info("intel_prefetch.done", key=key[:24], keys=len(result))
    except Exception as exc:
        logger.warning("intel_prefetch.failed", key=key[:24], error=str(exc)[:300])


@router.post("/intel/prefetch", tags=["Intel"])
@limiter.limit("30/hour")
async def prefetch_company_intel(
    request: Request,
    body: PrefetchRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Queue a speculative company-intel run; return quickly.

    Idempotent: if the exact (jd_text, job_title) is already cached we
    return 'cached' without launching any work.
    """
    key = _intel_cache_key(body.jd_text, body.job_title)

    try:
        from ai_engine.cache import get_jd_cache
        if get_jd_cache().get(key) is not None:
            return {"status": "cached", "jd_hash": key}
    except Exception as exc:
        logger.warning("intel_prefetch.cache_lookup_failed", error=str(exc)[:200])

    try:
        asyncio.create_task(
            _run_and_cache(
                key=key,
                company=body.company,
                job_title=body.job_title,
                jd_text=body.jd_text,
                company_url=body.company_url,
            ),
            name=f"intel_prefetch_{key[:12]}",
        )
    except Exception as exc:
        logger.warning("intel_prefetch.launch_failed", error=str(exc)[:200])
        return {"status": "skipped", "jd_hash": key}

    return {"status": "queued", "jd_hash": key}
