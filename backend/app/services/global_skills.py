"""
Global Skills Service — manages user's profile-wide skills, gaps, and learning goals.
"""
import uuid as _uuid
from typing import Any, Dict, List, Optional

import structlog

from app.core.database import get_supabase

logger = structlog.get_logger()


class GlobalSkillsService:
    """Service layer for global (sidebar-level) skills, gaps, and learning goals."""

    def __init__(self):
        self.sb = get_supabase()

    # ── User Skills ──────────────────────────────────────────────────────

    async def list_skills(self, user_id: str) -> List[Dict[str, Any]]:
        """List all skills for a user."""
        import asyncio

        def _query():
            return (
                self.sb.table("user_skills")
                .select("*")
                .eq("user_id", user_id)
                .order("category")
                .order("skill_name")
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return result.data or []

    async def upsert_skill(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a user skill."""
        import asyncio

        row = {
            "user_id": user_id,
            "skill_name": data["skill_name"],
            "category": data.get("category", "other"),
            "proficiency": data.get("proficiency", "beginner"),
            "years_experience": data.get("years_experience"),
            "source": data.get("source", "manual"),
            "updated_at": "now()",
        }

        def _query():
            return (
                self.sb.table("user_skills")
                .upsert(row, on_conflict="user_id,skill_name")
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return (result.data or [{}])[0]

    async def delete_skill(self, user_id: str, skill_id: str) -> None:
        """Delete a user skill."""
        import asyncio

        def _query():
            return (
                self.sb.table("user_skills")
                .delete()
                .eq("id", skill_id)
                .eq("user_id", user_id)
                .execute()
            )

        await asyncio.get_event_loop().run_in_executor(None, _query)

    # ── Global Skill Gaps ────────────────────────────────────────────────

    async def list_gaps(self, user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all global skill gaps for a user."""
        import asyncio

        def _query():
            q = (
                self.sb.table("user_skill_gaps")
                .select("*")
                .eq("user_id", user_id)
            )
            if status:
                q = q.eq("status", status)
            return q.order("priority_score", desc=True).execute()

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return result.data or []

    async def sync_gaps_from_applications(self, user_id: str) -> List[Dict[str, Any]]:
        """Aggregate skill gaps across all user applications into global gaps.

        This reads each application's gap analysis and merges them into the
        global user_skill_gaps table, computing frequency and priority.
        """
        import asyncio

        # 1. Fetch all user applications with gap data
        def _get_apps():
            return (
                self.sb.table("applications")
                .select("id, gaps, title")
                .eq("user_id", user_id)
                .neq("status", "archived")
                .execute()
            )

        apps_result = await asyncio.get_event_loop().run_in_executor(None, _get_apps)
        apps = apps_result.data or []

        # 2. Aggregate gaps across applications
        gap_map: Dict[str, Dict[str, Any]] = {}
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "major": 3, "moderate": 2, "minor": 1}

        for app in apps:
            gaps_data = app.get("gaps") or {}
            structured = gaps_data.get("skill_gaps") or gaps_data.get("skillGaps") or []
            if not isinstance(structured, list):
                # Fallback: use missingKeywords if no structured gaps
                missing = gaps_data.get("missingKeywords") or gaps_data.get("missing_keywords") or []
                for kw in missing:
                    if isinstance(kw, str):
                        structured.append({"skill": kw, "gap_severity": "medium"})

            for gap in structured:
                skill = (gap.get("skill") or gap.get("skill_name") or "").strip()
                if not skill:
                    continue
                skill_key = skill.lower()

                if skill_key not in gap_map:
                    gap_map[skill_key] = {
                        "skill_name": skill,
                        "gap_severity": gap.get("gap_severity", "medium"),
                        "current_level": gap.get("current_level"),
                        "target_level": gap.get("required_level") or gap.get("target_level"),
                        "frequency": 0,
                        "application_ids": [],
                    }

                entry = gap_map[skill_key]
                entry["frequency"] += 1
                entry["application_ids"].append(app["id"])

                # Keep the highest severity
                existing_sev = severity_order.get(entry["gap_severity"], 1)
                new_sev = severity_order.get(gap.get("gap_severity", "medium"), 1)
                if new_sev > existing_sev:
                    entry["gap_severity"] = gap.get("gap_severity", "medium")

        # 3. Compute priority scores and upsert
        rows = []
        for skill_key, entry in gap_map.items():
            sev_weight = severity_order.get(entry["gap_severity"], 1)
            priority = round(sev_weight * entry["frequency"] * 10, 2)
            rows.append({
                "user_id": user_id,
                "skill_name": entry["skill_name"],
                "gap_severity": entry["gap_severity"],
                "current_level": entry.get("current_level"),
                "target_level": entry.get("target_level"),
                "frequency": entry["frequency"],
                "application_ids": entry["application_ids"],
                "priority_score": priority,
                "status": "open",
                "updated_at": "now()",
            })

        if rows:
            def _upsert():
                return (
                    self.sb.table("user_skill_gaps")
                    .upsert(rows, on_conflict="user_id,skill_name")
                    .execute()
                )

            await asyncio.get_event_loop().run_in_executor(None, _upsert)

        return await self.list_gaps(user_id)

    async def update_gap_status(self, user_id: str, gap_id: str, status: str) -> Dict[str, Any]:
        """Update a skill gap's status."""
        import asyncio

        def _query():
            return (
                self.sb.table("user_skill_gaps")
                .update({"status": status, "updated_at": "now()"})
                .eq("id", gap_id)
                .eq("user_id", user_id)
                .select()
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return (result.data or [{}])[0]

    # ── Learning Goals ───────────────────────────────────────────────────

    async def list_goals(self, user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all learning goals for a user."""
        import asyncio

        def _query():
            q = (
                self.sb.table("user_learning_goals")
                .select("*")
                .eq("user_id", user_id)
            )
            if status:
                q = q.eq("status", status)
            return q.order("created_at", desc=True).execute()

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return result.data or []

    async def create_goal(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new learning goal."""
        import asyncio

        row = {
            "id": str(_uuid.uuid4()),
            "user_id": user_id,
            "title": data["title"],
            "description": data.get("description"),
            "target_skills": data.get("target_skills", []),
            "goal_type": data.get("goal_type", "general"),
            "target_date": data.get("target_date"),
        }

        def _query():
            return self.sb.table("user_learning_goals").insert(row).execute()

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return (result.data or [{}])[0]

    async def update_goal(self, user_id: str, goal_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a learning goal."""
        import asyncio

        allowed = {"title", "description", "target_skills", "goal_type", "status", "target_date", "progress_pct"}
        update = {k: v for k, v in data.items() if k in allowed}
        update["updated_at"] = "now()"

        def _query():
            return (
                self.sb.table("user_learning_goals")
                .update(update)
                .eq("id", goal_id)
                .eq("user_id", user_id)
                .select()
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return (result.data or [{}])[0]

    async def delete_goal(self, user_id: str, goal_id: str) -> None:
        """Delete a learning goal."""
        import asyncio

        def _query():
            return (
                self.sb.table("user_learning_goals")
                .delete()
                .eq("id", goal_id)
                .eq("user_id", user_id)
                .execute()
            )

        await asyncio.get_event_loop().run_in_executor(None, _query)

    # ── Profile Summary ──────────────────────────────────────────────────

    async def get_profile_summary(self, user_id: str) -> Dict[str, Any]:
        """Get a combined summary of skills, gaps, and goals for the sidebar."""
        skills = await self.list_skills(user_id)
        gaps = await self.list_gaps(user_id, status="open")
        goals = await self.list_goals(user_id, status="active")

        return {
            "total_skills": len(skills),
            "skills_by_category": _group_by(skills, "category"),
            "open_gaps": len(gaps),
            "critical_gaps": len([g for g in gaps if g.get("gap_severity") == "critical"]),
            "high_gaps": len([g for g in gaps if g.get("gap_severity") == "high"]),
            "top_gaps": gaps[:5],
            "active_goals": len(goals),
            "goals": goals[:5],
        }


def _group_by(items: list, key: str) -> Dict[str, int]:
    """Count items by a given key."""
    counts: Dict[str, int] = {}
    for item in items:
        val = item.get(key) or "other"
        counts[val] = counts.get(val, 0) + 1
    return counts
