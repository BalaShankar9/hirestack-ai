"""
Analytics Service
Handles analytics and tracking
"""
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.analytics import Analytics
from app.models.profile import Profile
from app.models.job import JobDescription
from app.models.benchmark import Benchmark
from app.models.gap import GapReport
from app.models.document import Document
from app.models.roadmap import Roadmap


class AnalyticsService:
    """Service for analytics operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def track_event(
        self,
        user_id: UUID,
        event_type: str,
        event_data: Dict[str, Any] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[UUID] = None
    ) -> None:
        """Track an analytics event."""
        event = Analytics(
            user_id=user_id,
            event_type=event_type,
            event_data=event_data or {},
            entity_type=entity_type,
            entity_id=entity_id
        )
        self.db.add(event)
        await self.db.commit()

    async def get_dashboard(self, user_id: UUID) -> Dict[str, Any]:
        """Get dashboard analytics."""
        # Count profiles
        profiles_result = await self.db.execute(
            select(func.count(Profile.id))
            .where(Profile.user_id == user_id)
        )
        profiles_count = profiles_result.scalar() or 0

        # Count jobs
        jobs_result = await self.db.execute(
            select(func.count(JobDescription.id))
            .where(JobDescription.user_id == user_id)
        )
        jobs_count = jobs_result.scalar() or 0

        # Count gap reports
        gaps_result = await self.db.execute(
            select(func.count(GapReport.id))
            .where(GapReport.user_id == user_id)
        )
        gaps_count = gaps_result.scalar() or 0

        # Count documents
        docs_result = await self.db.execute(
            select(func.count(Document.id))
            .where(Document.user_id == user_id)
        )
        docs_count = docs_result.scalar() or 0

        # Get latest compatibility score
        latest_gap = await self.db.execute(
            select(GapReport)
            .where(GapReport.user_id == user_id)
            .order_by(GapReport.created_at.desc())
            .limit(1)
        )
        latest = latest_gap.scalar_one_or_none()
        latest_score = latest.compatibility_score if latest else None

        # Get active roadmaps
        roadmaps_result = await self.db.execute(
            select(func.count(Roadmap.id))
            .where(Roadmap.user_id == user_id, Roadmap.status == "active")
        )
        roadmaps_count = roadmaps_result.scalar() or 0

        return {
            "profiles": profiles_count,
            "jobs_analyzed": jobs_count,
            "gap_analyses": gaps_count,
            "documents_generated": docs_count,
            "latest_compatibility_score": latest_score,
            "active_roadmaps": roadmaps_count,
            "summary": {
                "has_profile": profiles_count > 0,
                "has_analyzed_job": gaps_count > 0,
                "has_documents": docs_count > 0,
                "has_roadmap": roadmaps_count > 0
            }
        }

    async def get_recent_activity(
        self,
        user_id: UUID,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get recent activity for a user."""
        since = datetime.utcnow() - timedelta(days=days)

        result = await self.db.execute(
            select(Analytics)
            .where(
                Analytics.user_id == user_id,
                Analytics.created_at >= since
            )
            .order_by(Analytics.created_at.desc())
            .limit(50)
        )
        events = result.scalars().all()

        return [
            {
                "event_type": e.event_type,
                "event_data": e.event_data,
                "created_at": e.created_at.isoformat()
            }
            for e in events
        ]

    async def get_progress(self, user_id: UUID) -> Dict[str, Any]:
        """Get user's overall progress."""
        # Get all gap reports
        result = await self.db.execute(
            select(GapReport)
            .where(GapReport.user_id == user_id)
            .order_by(GapReport.created_at.asc())
        )
        reports = result.scalars().all()

        if not reports:
            return {
                "has_data": False,
                "message": "No gap analyses yet. Upload your resume and analyze a job to get started."
            }

        scores = [r.compatibility_score for r in reports]

        return {
            "has_data": True,
            "total_analyses": len(reports),
            "score_history": [
                {
                    "date": r.created_at.isoformat(),
                    "score": r.compatibility_score
                }
                for r in reports
            ],
            "average_score": sum(scores) / len(scores),
            "best_score": max(scores),
            "latest_score": scores[-1],
            "improvement": scores[-1] - scores[0] if len(scores) > 1 else 0
        }

    async def get_application_stats(self, user_id: UUID) -> Dict[str, Any]:
        """Get application-related statistics."""
        # Documents by type
        docs_result = await self.db.execute(
            select(Document.document_type, func.count(Document.id))
            .where(Document.user_id == user_id)
            .group_by(Document.document_type)
        )
        docs_by_type = {row[0]: row[1] for row in docs_result.fetchall()}

        # Jobs by company
        jobs_result = await self.db.execute(
            select(JobDescription.company, func.count(JobDescription.id))
            .where(JobDescription.user_id == user_id)
            .group_by(JobDescription.company)
        )
        jobs_by_company = {row[0] or "Unknown": row[1] for row in jobs_result.fetchall()}

        return {
            "documents_by_type": docs_by_type,
            "jobs_by_company": jobs_by_company
        }
