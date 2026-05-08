"""AIM source library routes."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.services.aim.source_service import AIMSourceService

router = APIRouter()

SourceType = Literal[
    "assignment_brief",
    "rubric",
    "lecture_notes",
    "journal_article",
    "book",
    "book_chapter",
    "textbook",
    "official_statistics",
    "standard",
    "government_report",
    "ngo_report",
    "institution_report",
    "industry_report",
    "company_report",
    "trade_publication",
    "news",
    "dataset",
    "web_page",
    "blog",
    "image_figure",
    "user_notes",
    "other",
]

ReliabilityTier = Literal["tier_1", "tier_2", "tier_3", "tier_4", "blocked"]
VerificationStatus = Literal["needs_metadata", "unverified", "verified", "blocked"]


class SourceCreate(BaseModel):
    source_type: SourceType = "other"
    title: Optional[str] = Field(None, max_length=500)
    authors: list[str] = Field(default_factory=list, max_length=50)
    year: Optional[int] = Field(None, ge=0, le=9999)
    publisher: Optional[str] = Field(None, max_length=500)
    journal: Optional[str] = Field(None, max_length=500)
    doi: Optional[str] = Field(None, max_length=255)
    url: Optional[str] = Field(None, max_length=2048)
    access_date: Optional[str] = Field(None, max_length=30)
    reliability_tier: Optional[ReliabilityTier] = None
    verification_status: Optional[VerificationStatus] = None
    raw_text: Optional[str] = Field(None, max_length=250_000)
    extracted_summary: Optional[str] = Field(None, max_length=20_000)
    relevant_quotes: list[Any] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/assignments/{assignment_id}/sources", status_code=201)
async def create_source(
    assignment_id: str,
    payload: SourceCreate,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    svc = AIMSourceService()
    try:
        return await svc.create_source(
            current_user["id"],
            assignment_id,
            payload.model_dump(),
        )
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")


@router.get("/assignments/{assignment_id}/sources")
async def list_sources(
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    svc = AIMSourceService()
    try:
        return await svc.list_sources(current_user["id"], assignment_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")


@router.get("/sources/{source_id}")
async def get_source(
    source_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    svc = AIMSourceService()
    row = await svc.get_source(current_user["id"], source_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="source not found")
    return row


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: str,
    current_user: dict = Depends(get_current_user),
) -> None:
    svc = AIMSourceService()
    ok = await svc.delete_source(current_user["id"], source_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="source not found")