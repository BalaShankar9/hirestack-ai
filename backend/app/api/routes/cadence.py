"""Cadence dashboard route."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user
from app.core.database import SupabaseDB, get_db
from app.core.security import limiter
from app.services.cadence import CadenceService

router = APIRouter()


def get_db_dep() -> SupabaseDB:
    return get_db()


@router.get("/today")
@limiter.limit("30/minute")
async def get_cadence_today(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    service = CadenceService(db=db)
    return await service.compute_dashboard(
        current_user["id"],
        user_context=current_user,
    )


__all__ = ["router", "get_db_dep"]