"""
PPT Generation API — /api/ppt.

Endpoints:
    POST /api/ppt/generate      → returns .pptx file as a streaming download.
    POST /api/ppt/outline       → returns the JSON DeckSpec (no rendering) —
                                   useful for previews and frontend editors.

Both endpoints accept:
    {
      "topic": str (required, ≤2000 chars),
      "audience": str | null,
      "slide_count": int (3..30, default 10),
      "tone": str | null,
      "theme": str (default "modern"),
      "extra_context": str | null
    }

Rate-limited to keep abuse low (PPT generation is the most expensive AI call
in the platform per request: outline LLM + composition + future image fetch).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from ai_engine.agents.ppt import PPTOrchestrator
from app.core.security import limiter

logger = structlog.get_logger("hirestack.ppt")
router = APIRouter()


_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


class PPTRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=2000)
    audience: Optional[str] = Field(None, max_length=500)
    slide_count: int = Field(10, ge=3, le=30)
    tone: Optional[str] = Field(None, max_length=200)
    theme: str = Field("modern", max_length=40)
    extra_context: Optional[str] = Field(None, max_length=10_000)

    @field_validator("topic", "audience", "tone", "extra_context")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None  # collapse blank-after-strip to None for nullable fields


def _safe_filename(topic: str) -> str:
    base = _FILENAME_SAFE_RE.sub("_", topic.strip())[:80] or "presentation"
    return f"{base}.pptx"


@router.post("/generate")
@limiter.limit("10/hour")
async def generate_ppt(request: Request, body: PPTRequest) -> Response:
    """Generate a .pptx and return it as a binary download."""
    try:
        orch = PPTOrchestrator()
        result = await orch.generate(
            topic=body.topic,
            audience=body.audience,
            slide_count=body.slide_count,
            tone=body.tone,
            theme=body.theme,
            extra_context=body.extra_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("ppt_generate_failed", topic=body.topic[:80], error=str(exc)[:300])
        raise HTTPException(status_code=500, detail="PPT generation failed") from exc

    filename = _safe_filename(body.topic if body.topic else result.deck.title)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-PPT-Slide-Count": str(result.slide_count),
        "X-PPT-Latency-Ms": str(result.latency_ms),
    }
    return Response(
        content=result.pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers=headers,
    )


@router.post("/outline")
@limiter.limit("30/hour")
async def outline_ppt(request: Request, body: PPTRequest) -> dict:
    """Return the structured DeckSpec without rendering — for previews/edits."""
    try:
        orch = PPTOrchestrator()
        deck = await orch.planner.plan(
            topic=body.topic,
            audience=body.audience,
            slide_count=body.slide_count,
            tone=body.tone,
            theme=body.theme,
            extra_context=body.extra_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("ppt_outline_failed", topic=body.topic[:80], error=str(exc)[:300])
        raise HTTPException(status_code=500, detail="PPT outline failed") from exc
    return {"deck": deck.model_dump(), "slide_count": deck.slide_count}
