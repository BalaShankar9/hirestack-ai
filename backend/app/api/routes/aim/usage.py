"""AIM \u2014 usage / quota visibility."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.services.aim.quota import AIMQuotaService, FREE_ASSIGNMENT_LIMIT

router = APIRouter()


@router.get("/usage")
async def get_usage(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    usage = await AIMQuotaService().get_or_create_period(current_user["id"])
    return {
        **usage,
        "free_assignment_limit": FREE_ASSIGNMENT_LIMIT,
        "remaining": (
            None if usage.get("plan") != "free"
            else max(0, FREE_ASSIGNMENT_LIMIT - int(usage.get("assignments_created", 0)))
        ),
    }
