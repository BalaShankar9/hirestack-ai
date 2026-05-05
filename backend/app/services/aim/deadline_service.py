"""AIM Deadline Mode \u2014 derive a backed-off task plan from the assignment deadline.

Generates a deterministic checklist (no LLM calls) so the user always sees a
plan even if Gemini is rate-limited. Plan structure:

  T-7d : Parse brief + lock the directive
  T-6d : Recon \u2014 confirm structure & rubric weighting
  T-5d..T-2d : One drafting block per section (writer\u2194reviewer loop)
  T-1d : Grade-prediction sweep + Fix-My-Section pass
  T-0  : Final read-through + submission

If the deadline is < 7 days away, blocks compress proportionally and the
earliest tasks become 'today'. Tasks are persisted to aim_tasks; subsequent
runs delete prior auto-generated rows and re-plan.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from app.core.database import SupabaseDB, get_db


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _build_plan(deadline: date, sections: list[dict]) -> list[dict]:
    """Return ordered list of task dicts (without ids/user_id)."""
    today = _today()
    days_left = max(1, (deadline - today).days)

    # Allocate: 1 day parser+recon (combined if tight), N days drafting, 1 day polish, deadline day = submit.
    n_sections = max(1, len(sections))
    polish_days = 1 if days_left >= 4 else 0
    submit_day = 1
    drafting_budget = max(1, days_left - 1 - polish_days - submit_day)
    days_per_section = max(1, drafting_budget // n_sections)

    tasks: list[dict] = []
    cursor = today

    tasks.append({
        "task_name": "Parse brief & lock directive",
        "description": "Run AIM parser; confirm directive, word count, rubric criteria.",
        "due_date": cursor.isoformat(),
        "effort_minutes": 20,
        "order_index": len(tasks),
    })
    if days_left >= 5:
        cursor += timedelta(days=1)

    tasks.append({
        "task_name": "Recon \u2014 confirm structure & rubric weighting",
        "description": "Validate section plan and per-criterion strategy.",
        "due_date": cursor.isoformat(),
        "effort_minutes": 30,
        "order_index": len(tasks),
    })

    for i, section in enumerate(sections):
        cursor = min(deadline - timedelta(days=polish_days + submit_day),
                     cursor + timedelta(days=days_per_section if i > 0 else 1))
        tasks.append({
            "task_name": f"Draft + review: {section.get('title', f'Section {i + 1}')}",
            "description": (
                f"Run writer\u2194reviewer loop until quality \u2265 85. "
                f"Target {section.get('word_limit') or '?'} words."
            ),
            "section_id": section.get("id"),
            "due_date": cursor.isoformat(),
            "effort_minutes": 90,
            "order_index": len(tasks),
        })

    if polish_days:
        cursor = deadline - timedelta(days=submit_day)
        tasks.append({
            "task_name": "Predict grade + Fix-My-Section pass",
            "description": "Run grade predictor; address the top 3 ranked issues per section.",
            "due_date": cursor.isoformat(),
            "effort_minutes": 60,
            "order_index": len(tasks),
        })

    tasks.append({
        "task_name": "Final read-through & submit",
        "description": "Citation check, formatting pass, submit.",
        "due_date": deadline.isoformat(),
        "effort_minutes": 45,
        "order_index": len(tasks),
    })
    return tasks


class AIMDeadlineService:
    def __init__(self, db: Optional[SupabaseDB] = None) -> None:
        self.db = db or get_db()

    async def list_tasks(self, user_id: str, assignment_id: str) -> list[dict[str, Any]]:
        return await self.db.query(
            "aim_tasks",
            filters=[("user_id", "==", user_id), ("assignment_id", "==", assignment_id)],
            order_by="order_index",
            order_direction="ASCENDING",
        )

    async def replan(self, user_id: str, assignment_id: str, deadline_iso: str) -> list[dict[str, Any]]:
        """Delete existing plan and regenerate from sections + deadline."""
        try:
            deadline = date.fromisoformat(deadline_iso)
        except ValueError as exc:
            raise ValueError(f"deadline must be YYYY-MM-DD, got {deadline_iso!r}") from exc
        if deadline < _today():
            raise ValueError("deadline is in the past")

        # Ownership check: assignment must belong to caller. Mirrors RLS policy.
        assignment = await self.db.get("aim_assignments", assignment_id)
        if not assignment or assignment.get("user_id") != user_id:
            raise PermissionError("assignment not found")

        existing = await self.list_tasks(user_id, assignment_id)
        for row in existing:
            await self.db.delete("aim_tasks", row["id"])

        sections = await self.db.query(
            "aim_sections",
            filters=[("user_id", "==", user_id), ("assignment_id", "==", assignment_id)],
            order_by="order_index",
            order_direction="ASCENDING",
        )
        plan = _build_plan(deadline, sections or [])
        created: list[dict[str, Any]] = []
        for task in plan:
            row = {**task, "user_id": user_id, "assignment_id": assignment_id, "status": "pending"}
            new_id = await self.db.create("aim_tasks", row)
            created.append({**row, "id": new_id})
        return created

    async def update_status(
        self, user_id: str, task_id: str, status: str
    ) -> dict[str, Any]:
        if status not in {"pending", "in_progress", "done", "skipped"}:
            raise ValueError(f"invalid status: {status}")
        existing = await self.db.get("aim_tasks", task_id)
        if not existing or existing.get("user_id") != user_id:
            raise PermissionError("task not found")
        patch: dict[str, Any] = {"status": status}
        if status == "done":
            patch["completed_at"] = datetime.now(timezone.utc).isoformat()
        await self.db.update("aim_tasks", task_id, patch)
        return {**existing, **patch}
