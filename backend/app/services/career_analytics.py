"""
Career Analytics Service
Timeline snapshots, score trends, and industry benchmarking (Supabase)
"""
from typing import Optional, Dict, Any, List
from datetime import date
import structlog

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger()


class CareerAnalyticsService:
    """Service for career progress tracking and analytics."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def capture_snapshot(self, user_id: str) -> Dict[str, Any]:
        """Capture a daily career progress snapshot."""
        today = date.today().isoformat()

        # Check if snapshot exists for today
        existing = await self.db.query(
            TABLES["career_snapshots"],
            filters=[("user_id", "==", user_id), ("snapshot_date", "==", today)],
            limit=1,
        )
        if existing:
            return existing[0]

        # Gather current scores
        gap_reports = await self.db.query(
            TABLES["gap_reports"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=5,
        )

        applications = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id)],
        )

        interviews = await self.db.query(
            TABLES["interview_sessions"],
            filters=[("user_id", "==", user_id), ("status", "==", "completed")],
        )

        ats_scans = await self.db.query(
            TABLES["ats_scans"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=10,
        )

        # Compute averages
        overall_scores = [r.get("compatibility_score", 0) for r in gap_reports if r.get("compatibility_score")]
        tech_scores = [r.get("skill_score", 0) for r in gap_reports if r.get("skill_score")]
        exp_scores = [r.get("experience_score", 0) for r in gap_reports if r.get("experience_score")]
        edu_scores = [r.get("education_score", 0) for r in gap_reports if r.get("education_score")]
        ats_scores_list = [s.get("ats_score", 0) for s in ats_scans if s.get("ats_score")]

        record = {
            "user_id": user_id,
            "snapshot_date": today,
            "overall_score": sum(overall_scores) / len(overall_scores) if overall_scores else None,
            "technical_score": sum(tech_scores) / len(tech_scores) if tech_scores else None,
            "experience_score": sum(exp_scores) / len(exp_scores) if exp_scores else None,
            "education_score": sum(edu_scores) / len(edu_scores) if edu_scores else None,
            "applications_count": len(applications),
            "interviews_completed": len(interviews),
            "avg_ats_score": sum(ats_scores_list) / len(ats_scores_list) if ats_scores_list else None,
            "metadata": {
                "gap_reports_count": len(gap_reports),
                "ats_scans_count": len(ats_scans),
            },
        }

        doc_id = await self.db.create(TABLES["career_snapshots"], record)
        logger.info("career_snapshot_captured", snapshot_id=doc_id)
        return await self.db.get(TABLES["career_snapshots"], doc_id)

    async def get_timeline(self, user_id: str, days: int = 90) -> List[Dict[str, Any]]:
        """Get career progress timeline."""
        from datetime import timedelta
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        return await self.db.query(
            TABLES["career_snapshots"],
            filters=[("user_id", "==", user_id), ("snapshot_date", ">=", cutoff)],
            order_by="snapshot_date",
        )

    async def get_portfolio_summary(self, user_id: str) -> Dict[str, Any]:
        """Generate a comprehensive career portfolio summary."""
        applications = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id)],
        )
        interviews = await self.db.query(
            TABLES["interview_sessions"],
            filters=[("user_id", "==", user_id), ("status", "==", "completed")],
        )
        evidence = await self.db.query(
            TABLES["evidence"],
            filters=[("user_id", "==", user_id)],
        )
        streaks = await self.db.query(
            TABLES["learning_streaks"],
            filters=[("user_id", "==", user_id)],
            limit=1,
        )

        timeline = await self.get_timeline(user_id, days=90)

        # Compute score trends
        if len(timeline) >= 2:
            first = timeline[0].get("overall_score") or 0
            last = timeline[-1].get("overall_score") or 0
            trend = last - first
        else:
            trend = 0

        return {
            "total_applications": len(applications),
            "total_interviews": len(interviews),
            "total_evidence": len(evidence),
            "avg_interview_score": (
                sum(i.get("overall_score", 0) or 0 for i in interviews) / len(interviews)
                if interviews else 0
            ),
            "learning_streak": streaks[0] if streaks else None,
            "score_trend": trend,
            "timeline": timeline[-30:],  # last 30 data points
        }
