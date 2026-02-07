"""
Analytics Service
Handles analytics and tracking with Firestore
"""
from typing import List, Dict, Any, Optional
import structlog

from app.core.database import get_firestore_db, COLLECTIONS, FirestoreDB

logger = structlog.get_logger()


class AnalyticsService:
    """Service for analytics operations using Firestore."""

    def __init__(self, db: Optional[FirestoreDB] = None):
        self.db = db or get_firestore_db()

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
        await self.db.create(COLLECTIONS["analytics"], record)

    async def get_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Get dashboard analytics — counts across collections."""
        profiles = await self.db.query(COLLECTIONS["profiles"], filters=[("user_id", "==", user_id)], limit=100)
        jobs = await self.db.query(COLLECTIONS["jobs"], filters=[("user_id", "==", user_id)], limit=100)
        gap_reports = await self.db.query(COLLECTIONS["gap_reports"], filters=[("user_id", "==", user_id)], limit=100)
        documents = await self.db.query(COLLECTIONS["documents"], filters=[("user_id", "==", user_id)], limit=100)
        roadmaps = await self.db.query(
            COLLECTIONS["roadmaps"],
            filters=[("user_id", "==", user_id)],
            limit=100,
        )

        active_roadmaps = [r for r in roadmaps if r.get("status") == "active"]

        # Latest compatibility score
        latest_score = None
        if gap_reports:
            sorted_gaps = sorted(gap_reports, key=lambda g: g.get("created_at", 0), reverse=True)
            latest_score = sorted_gaps[0].get("compatibility_score")

        return {
            "profiles": len(profiles),
            "jobs_analyzed": len(jobs),
            "gap_analyses": len(gap_reports),
            "documents_generated": len(documents),
            "latest_compatibility_score": latest_score,
            "active_roadmaps": len(active_roadmaps),
            "summary": {
                "has_profile": len(profiles) > 0,
                "has_analyzed_job": len(gap_reports) > 0,
                "has_documents": len(documents) > 0,
                "has_roadmap": len(active_roadmaps) > 0,
            },
        }

    async def get_recent_activity(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent analytics events."""
        events = await self.db.query(
            COLLECTIONS["analytics"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )
        return events

    async def get_progress(self, user_id: str) -> Dict[str, Any]:
        """Get user's score history and improvement trend."""
        gap_reports = await self.db.query(
            COLLECTIONS["gap_reports"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="ASCENDING",
        )
        if not gap_reports:
            return {"has_data": False, "message": "No gap analyses yet."}

        scores = [r.get("compatibility_score", 0) for r in gap_reports]
        return {
            "has_data": True,
            "total_analyses": len(gap_reports),
            "average_score": round(sum(scores) / len(scores), 1),
            "best_score": max(scores),
            "latest_score": scores[-1],
            "improvement": scores[-1] - scores[0] if len(scores) > 1 else 0,
        }
