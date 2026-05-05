"""AIM \u2014 analysis (Parser + Recon)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.services.aim.assignment_service import AIMAssignmentService

router = APIRouter()


@router.post("/assignments/{assignment_id}/analyze")
async def analyze_assignment_route(
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    svc = AIMAssignmentService()
    if not await svc.get(current_user["id"], assignment_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    try:
        analysis = await svc.analyze(current_user["id"], assignment_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "needs_clarification": analysis.needs_clarification,
        "parser_confidence": analysis.parser_confidence,
        "clarification_questions": analysis.clarification_questions,
        "parsed": analysis.parsed,
        "recon": analysis.recon,
        "flags": analysis.flags,
    }


@router.get("/assignments/{assignment_id}/analysis")
async def get_analysis(
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    svc = AIMAssignmentService()
    if not await svc.get(current_user["id"], assignment_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    row = await svc.get_analysis(assignment_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no analysis yet")
    return row


@router.get("/assignments/{assignment_id}/sections")
async def list_sections_route(
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    svc = AIMAssignmentService()
    if not await svc.get(current_user["id"], assignment_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    from app.services.aim.section_service import AIMSectionService
    return await AIMSectionService().list_sections(assignment_id)
