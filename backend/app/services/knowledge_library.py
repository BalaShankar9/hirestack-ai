"""
Knowledge Library Service — manages curated resources, user progress, and recommendations.
"""
import uuid as _uuid
from typing import Any, Dict, List, Optional

import structlog

from app.core.database import get_supabase

logger = structlog.get_logger()


class KnowledgeLibraryService:
    """Service layer for the Knowledge Library system."""

    def __init__(self):
        self.sb = get_supabase()

    # ── Resources (public catalog) ───────────────────────────────────────

    async def list_resources(
        self,
        category: Optional[str] = None,
        resource_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        skill: Optional[str] = None,
        search: Optional[str] = None,
        featured_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List published knowledge resources with optional filters."""
        import asyncio

        def _query():
            q = self.sb.table("knowledge_resources").select("*").eq("is_published", True)
            if category:
                q = q.eq("category", category)
            if resource_type:
                q = q.eq("resource_type", resource_type)
            if difficulty:
                q = q.eq("difficulty", difficulty)
            if skill:
                q = q.contains("skills", [skill])
            if featured_only:
                q = q.eq("is_featured", True)
            if search:
                q = q.or_(f"title.ilike.%{search}%,description.ilike.%{search}%")
            q = q.order("sort_order").order("created_at", desc=True)
            q = q.range(offset, offset + limit - 1)
            return q.execute()

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return result.data or []

    async def get_resource(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """Get a single knowledge resource by ID."""
        import asyncio

        def _query():
            return (
                self.sb.table("knowledge_resources")
                .select("*")
                .eq("id", resource_id)
                .eq("is_published", True)
                .maybe_single()
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return result.data

    # ── User progress / bookmarks ────────────────────────────────────────

    async def get_user_progress(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all knowledge progress entries for a user."""
        import asyncio

        def _query():
            return (
                self.sb.table("user_knowledge_progress")
                .select("*, knowledge_resources(*)")
                .eq("user_id", user_id)
                .order("updated_at", desc=True)
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return result.data or []

    async def save_progress(
        self, user_id: str, resource_id: str, status: str = "saved", progress_pct: int = 0
    ) -> Dict[str, Any]:
        """Save or update user progress on a resource (upsert)."""
        import asyncio

        now = "now()"
        data = {
            "user_id": user_id,
            "resource_id": resource_id,
            "status": status,
            "progress_pct": progress_pct,
            "updated_at": now,
        }
        if status == "completed":
            data["completed_at"] = now
            data["progress_pct"] = 100

        def _query():
            return (
                self.sb.table("user_knowledge_progress")
                .upsert(data, on_conflict="user_id,resource_id")
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return (result.data or [{}])[0]

    async def rate_resource(self, user_id: str, resource_id: str, rating: int) -> Dict[str, Any]:
        """Rate a knowledge resource."""
        import asyncio

        def _query():
            return (
                self.sb.table("user_knowledge_progress")
                .upsert(
                    {"user_id": user_id, "resource_id": resource_id, "rating": rating, "updated_at": "now()"},
                    on_conflict="user_id,resource_id",
                )
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return (result.data or [{}])[0]

    # ── Recommendations ──────────────────────────────────────────────────

    async def get_recommendations(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get AI-generated resource recommendations for a user."""
        import asyncio

        def _query():
            return (
                self.sb.table("resource_recommendations")
                .select("*, knowledge_resources(*)")
                .eq("user_id", user_id)
                .eq("is_dismissed", False)
                .order("relevance_score", desc=True)
                .limit(limit)
                .execute()
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _query)
        return result.data or []

    async def dismiss_recommendation(self, user_id: str, recommendation_id: str) -> None:
        """Dismiss a recommendation."""
        import asyncio

        def _query():
            return (
                self.sb.table("resource_recommendations")
                .update({"is_dismissed": True})
                .eq("id", recommendation_id)
                .eq("user_id", user_id)
                .execute()
            )

        await asyncio.get_event_loop().run_in_executor(None, _query)

    async def generate_recommendations(self, user_id: str) -> List[Dict[str, Any]]:
        """Generate resource recommendations based on user's skill gaps and goals.

        This cross-references:
        1. User's global skill gaps → find resources matching missing skills
        2. User's learning goals → find resources matching target skills
        3. Application-specific gaps → find resources for high-frequency gaps
        """
        import asyncio

        # 1. Fetch user's open skill gaps
        def _get_gaps():
            return (
                self.sb.table("user_skill_gaps")
                .select("*")
                .eq("user_id", user_id)
                .in_("status", ["open", "in_progress"])
                .order("priority_score", desc=True)
                .limit(20)
                .execute()
            )

        gaps_result = await asyncio.get_event_loop().run_in_executor(None, _get_gaps)
        gaps = gaps_result.data or []

        # 2. Fetch all resources
        resources = await self.list_resources(limit=200)

        # 3. Match resources to gaps by skill overlap
        recommendations = []
        for gap in gaps:
            skill = gap.get("skill_name", "").lower()
            severity = gap.get("gap_severity", "low")
            severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(severity, 1)
            frequency = gap.get("frequency", 1)

            for resource in resources:
                resource_skills = [s.lower() for s in (resource.get("skills") or [])]
                resource_tags = [t.lower() for t in (resource.get("tags") or [])]
                title_lower = (resource.get("title") or "").lower()

                # Check if resource is relevant to this gap
                match = (
                    skill in resource_skills
                    or skill in resource_tags
                    or skill in title_lower
                    or any(skill in s for s in resource_skills)
                )
                if match:
                    relevance = min(severity_weight * frequency * 10, 100)
                    recommendations.append({
                        "id": str(_uuid.uuid4()),
                        "user_id": user_id,
                        "resource_id": resource["id"],
                        "reason": f"Helps close your '{gap.get('skill_name', '')}' skill gap ({severity} priority, needed in {frequency} application{'s' if frequency > 1 else ''})",
                        "source": "skill_gap",
                        "relevance_score": relevance,
                        "linked_skill": gap.get("skill_name"),
                    })

        # 4. Upsert recommendations (skip duplicates)
        if recommendations:
            def _upsert_recs():
                return (
                    self.sb.table("resource_recommendations")
                    .upsert(recommendations, on_conflict="user_id,resource_id,source")
                    .execute()
                )

            await asyncio.get_event_loop().run_in_executor(None, _upsert_recs)

        return await self.get_recommendations(user_id)
