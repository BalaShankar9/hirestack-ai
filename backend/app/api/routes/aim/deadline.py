"""AIM Deadline Mode routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.services.aim.assignment_service import AIMAssignmentService
from app.services.aim.deadline_service import AIMDeadlineService

router = APIRouter()


class ReplanRequest(BaseModel):
    deadline: str = Field(..., description="YYYY-MM-DD")


class StatusUpdate(BaseModel):
    status: str = Field(..., description="pending|in_progress|done|skipped")


@router.get("/assignments/{assignment_id}/tasks")
async def list_tasks(
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if not await AIMAssignmentService().get(current_user["id"], assignment_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    return await AIMDeadlineService().list_tasks(current_user["id"], assignment_id)


@router.post("/assignments/{assignment_id}/tasks/replan")
async def replan_tasks(
    assignment_id: str,
    payload: ReplanRequest,
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if not await AIMAssignmentService().get(current_user["id"], assignment_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    try:
        return await AIMDeadlineService().replan(
            current_user["id"], assignment_id, payload.deadline
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    payload: StatusUpdate,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await AIMDeadlineService().update_status(
            current_user["id"], task_id, payload.status
        )
    except PermissionError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
