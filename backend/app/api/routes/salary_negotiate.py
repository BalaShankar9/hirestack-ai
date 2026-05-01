"""Salary Negotiation Generator API — POST /api/salary/negotiate."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ai_engine.agents.salary import OfferDetails
from ai_engine.agents.salary.integration import generate_negotiation
from app.core.security import limiter

logger = structlog.get_logger("hirestack.salary.negotiate")
router = APIRouter()


class NegotiateRequest(BaseModel):
    offer: OfferDetails
    tone: str = Field("collaborative", max_length=50)


@router.post("/negotiate")
@limiter.limit("10/hour")
async def negotiate(request: Request, body: NegotiateRequest) -> dict:
    try:
        report = await generate_negotiation(body.offer, tone=body.tone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("salary_negotiate_failed", error=str(exc)[:300])
        raise HTTPException(status_code=500, detail="negotiation generation failed") from exc
    return report.model_dump()
