"""
Analytics Service
Handles analytics and tracking with Supabase
"""
from typing import List, Dict, Any, Optional
import structlog

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger()


class AnalyticsService:
    """Service for analytics operations using Supabase."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def track_event(
        self,
        user_id: str,
        event_type: str,
        event_data: Optional[Dict[str, Any]] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> None:
        """Track an analytics event."""
        record = {
            "user_id": user_id,
            "event_type": event_type,
            "event_data": event_data or {},
            "entity_type": entity_type,
            "entity_id": entity_id,
        }
        await self.db.create(TABLES["analytics"], record)

    async def get_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Get dashboard analytics — optimized counts + limited fetches."""
        # Fetch only what we actually need to inspect field values
        applications = await self.db.query(TABLES["applications"], filters=[("user_id", "==", user_id)], limit=200)
        tasks = await self.db.query(TABLES["tasks"], filters=[("user_id", "==", user_id)], limit=500)

        # Use lightweight count queries for simple totals
        profiles = await self.db.query(TABLES["profiles"], filters=[("user_id", "==", user_id)], limit=1)
        jobs = await self.db.query(TABLES["jobs"], filters=[("user_id", "==", user_id)], limit=200)
        evidence = await self.db.query(TABLES["evidence"], filters=[("user_id", "==", user_id)], limit=200)

        completed_tasks = [t for t in tasks if t.get("status") in ("done", "skipped")]
        active_apps = [a for a in applications if a.get("status") != "archived"]

        # Latest overall score from applications
        latest_score = None
        for app in sorted(applications, key=lambda a: a.get("updated_at", ""), reverse=True):
            scores = app.get("scores") or {}
            if scores.get("overall"):
                latest_score = scores["overall"]
                break

        return {
            "applications": len(applications),
            "active_applications": len(active_apps),
            "profiles": len(profiles),
            "jobs_analyzed": len(jobs),
            "evidence_items": len(evidence),
            "total_tasks": len(tasks),
            "completed_tasks": len(completed_tasks),
            "latest_score": latest_score,
            "summary": {
                "has_profile": len(profiles) > 0,
                "has_application": len(applications) > 0,
                "has_evidence": len(evidence) > 0,
                "task_completion_rate": round(len(completed_tasks) / max(len(tasks), 1) * 100, 1),
            },
        }

    async def get_recent_activity(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent analytics events."""
        events = await self.db.query(
            TABLES["events"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )
        return events

    async def get_progress(self, user_id: str) -> Dict[str, Any]:
        """Get user progress across applications."""
        applications = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="ASCENDING",
        )
        if not applications:
            return {"has_data": False, "message": "No applications yet."}

        scores = []
        for app in applications:
            app_scores = app.get("scores") or {}
            overall = app_scores.get("overall")
            if overall is not None:
                scores.append(overall)

        if not scores:
            return {"has_data": False, "message": "No scored applications yet."}

        return {
            "has_data": True,
            "total_applications": len(applications),
            "scored_applications": len(scores),
            "average_score": round(sum(scores) / len(scores), 1),
            "best_score": max(scores),
            "latest_score": scores[-1],
            "improvement": round(scores[-1] - scores[0], 1) if len(scores) > 1 else 0,
        }

    async def get_application_stats(self, user_id: str) -> Dict[str, Any]:
        """Get application-related statistics."""
        applications = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id)],
            limit=200,
        )

        status_counts = {"draft": 0, "active": 0, "archived": 0}
        module_completion = {"benchmark": 0, "gaps": 0, "cv": 0, "coverLetter": 0, "personalStatement": 0, "portfolio": 0}
        total_with_modules = 0

        for app in applications:
            st = app.get("status", "draft")
            if st in status_counts:
                status_counts[st] += 1

            modules = app.get("modules") or {}
            has_any = False
            for key in module_completion:
                mod = modules.get(key) or {}
                if mod.get("state") == "ready":
                    module_completion[key] += 1
                    has_any = True
            if has_any:
                total_with_modules += 1

        return {
            "total": len(applications),
            "by_status": status_counts,
            "module_completion": module_completion,
            "applications_with_results": total_with_modules,
        }
