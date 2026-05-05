"""AIM \u2014 grade prediction & evaluation history."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.core.database import TABLES, get_db
from app.services.aim.assignment_service import AIMAssignmentService
from app.services.aim.quota import AIMQuotaService
from app.services.aim.section_service import AIMSectionService

router = APIRouter()


@router.post("/assignments/{assignment_id}/predict-grade")
async def predict_grade_route(
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    if not await AIMAssignmentService().get(current_user["id"], assignment_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    try:
        prediction = await AIMSectionService().predict_grade_for_assignment(
            current_user["id"], assignment_id
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    await AIMQuotaService().record_evaluation_run(current_user["id"])
    return prediction


@router.get("/assignments/{assignment_id}/evaluations")
async def list_evaluations(
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if not await AIMAssignmentService().get(current_user["id"], assignment_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    db = get_db()
    return await db.query(
        TABLES["aim_evaluations"],
        filters=[("assignment_id", "==", assignment_id)],
        order_by="created_at",
        order_direction="DESCENDING",
    )
