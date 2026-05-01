"""Culture-Fit Interview Coach API — /api/culture-fit/*."""
from __future__ import annotations

from typing import List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ai_engine.agents.culture_fit import coach_culture_fit
from app.core.security import limiter

logger = structlog.get_logger("hirestack.culture_fit")
router = APIRouter()


class CoachRequest(BaseModel):
    company: str = Field("", max_length=200)
    company_text: str = Field(..., min_length=20, max_length=20000)
    candidate_values: Optional[List[str]] = None
    questions_per_dimension: int = Field(1, ge=1, le=3)
    top_n: int = Field(4, ge=1, le=8)


@router.post("/coach")
@limiter.limit("10/hour")
async def coach(request: Request, body: CoachRequest) -> dict:
    try:
        report = await coach_culture_fit(
            company=body.company,
            company_text=body.company_text,
            candidate_values=body.candidate_values,
            questions_per_dimension=body.questions_per_dimension,
            top_n=body.top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "culture_fit_coach",
        company=body.company,
        signals=len(report.value_map.signals),
        questions=len(report.questions),
    )
    return report.model_dump()
