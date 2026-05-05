"""
AIM \u2014 Quota & Plan Gate.

Free plan: 2 assignments per calendar month (full pipeline depth, throttled).
Paid plan: unlimited.

* `get_or_create_period(user_id)`  \u2192 current month aim_usage row
* `enforce_create_assignment(user_id)` raises HTTPException(429) on free cap
* `record_assignment_created(user_id)` increments counter
* `record_section_generated(user_id)` increments counter
* `record_evaluation_run(user_id)` increments counter
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from app.core.database import SupabaseDB, TABLES, get_db


FREE_ASSIGNMENT_LIMIT = 2


def _period_for(d: date | None = None) -> str:
    d = d or datetime.now(timezone.utc).date()
    return d.replace(day=1).isoformat()


class AIMQuotaService:
    def __init__(self, db: Optional[SupabaseDB] = None) -> None:
        self.db = db or get_db()

    async def get_or_create_period(self, user_id: str) -> dict[str, Any]:
        period = _period_for()
        rows = await self.db.query(
            TABLES["aim_usage"],
            filters=[("user_id", "==", user_id), ("period_month", "==", period)],
            limit=1,
        )
        if rows:
            return rows[0]
        new = {
            "user_id": user_id,
            "period_month": period,
            "assignments_created": 0,
            "sections_generated": 0,
            "evaluations_run": 0,
            "plan": "free",
        }
        new_id = await self.db.create(TABLES["aim_usage"], new)
        new["id"] = new_id
        return new

    async def enforce_create_assignment(self, user_id: str) -> None:
        usage = await self.get_or_create_period(user_id)
        if usage.get("plan", "free") != "free":
            return
        if int(usage.get("assignments_created", 0)) >= FREE_ASSIGNMENT_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "aim_free_limit_reached",
                    "message": (
                        f"Free plan allows {FREE_ASSIGNMENT_LIMIT} assignments per month. "
                        "Upgrade for unlimited assignments."
                    ),
                    "limit": FREE_ASSIGNMENT_LIMIT,
                    "used": usage.get("assignments_created", 0),
                },
            )

    async def _bump(self, user_id: str, field: str) -> None:
        usage = await self.get_or_create_period(user_id)
        new_val = int(usage.get(field, 0)) + 1
        await self.db.update(
            TABLES["aim_usage"],
            usage["id"],
            {field: new_val, "updated_at": datetime.now(timezone.utc).isoformat()},
        )

    async def record_assignment_created(self, user_id: str) -> None:
        await self._bump(user_id, "assignments_created")

    async def record_section_generated(self, user_id: str) -> None:
        await self._bump(user_id, "sections_generated")

    async def record_evaluation_run(self, user_id: str) -> None:
        await self._bump(user_id, "evaluations_run")
