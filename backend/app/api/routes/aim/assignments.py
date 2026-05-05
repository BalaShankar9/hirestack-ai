"""AIM \u2014 assignment CRUD."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.services.aim.assignment_service import AIMAssignmentService
from app.services.aim.quota import AIMQuotaService

router = APIRouter()


class AssignmentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    course: Optional[str] = Field(None, max_length=255)
    academic_level: Optional[str] = Field(None, pattern="^(ug|pg|mba|phd|other)$")
    referencing_style: Optional[str] = Field(
        None, pattern="^(harvard|apa|mla|chicago|ieee|other)$"
    )
    deadline: Optional[str] = None  # ISO 8601
    word_count: Optional[int] = Field(None, ge=0, le=100_000)


@router.post("/assignments", status_code=201)
async def create_assignment(
    payload: AssignmentCreate,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    quota = AIMQuotaService()
    await quota.enforce_create_assignment(current_user["id"])
    svc = AIMAssignmentService()
    row = await svc.create(current_user["id"], payload.model_dump())
    await quota.record_assignment_created(current_user["id"])
    return row


@router.get("/assignments")
async def list_assignments(
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    svc = AIMAssignmentService()
    return await svc.list_for_user(current_user["id"])


@router.get("/assignments/{assignment_id}")
async def get_assignment(
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    svc = AIMAssignmentService()
    row = await svc.get(current_user["id"], assignment_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    return row


@router.delete("/assignments/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
) -> None:
    svc = AIMAssignmentService()
    ok = await svc.delete(current_user["id"], assignment_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
