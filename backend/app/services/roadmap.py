"""
Roadmap Service
Handles career roadmap generation and management with Firestore
"""
from typing import List, Optional, Dict, Any
import structlog

from app.core.database import get_firestore_db, COLLECTIONS, FirestoreDB
from ai_engine.client import AIClient
from ai_engine.chains.career_consultant import CareerConsultantChain

logger = structlog.get_logger()


class RoadmapService:
    """Service for roadmap operations using Firestore."""

    def __init__(self, db: Optional[FirestoreDB] = None):
        self.db = db or get_firestore_db()
        self.ai_client = AIClient()

    async def generate_roadmap(
        self,
        user_id: str,
        gap_report_id: str,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a career improvement roadmap."""
        gap_report = await self.db.get(COLLECTIONS["gap_reports"], gap_report_id)
        if not gap_report or gap_report.get("user_id") != user_id:
            raise ValueError("Gap report not found")

        # Fetch related profile
        profile_id = gap_report.get("profile_id")
        profile = await self.db.get(COLLECTIONS["profiles"], profile_id) if profile_id else None

        # Fetch benchmark + job
        benchmark_id = gap_report.get("benchmark_id")
        benchmark = await self.db.get(COLLECTIONS["benchmarks"], benchmark_id) if benchmark_id else None
        job = None
        if benchmark and benchmark.get("job_description_id"):
            job = await self.db.get(COLLECTIONS["jobs"], benchmark["job_description_id"])

        # Build data for AI
        profile_data = {
            "name": profile.get("name", "User") if profile else "User",
            "title": profile.get("title", "") if profile else "",
            "skills": profile.get("skills", []) if profile else [],
            "experience": profile.get("experience", []) if profile else [],
        }
        gap_data = {
            "compatibility_score": gap_report.get("compatibility_score"),
            "skill_gaps": gap_report.get("skill_gaps", []),
            "experience_gaps": gap_report.get("experience_gaps", []),
            "recommendations": gap_report.get("recommendations", []),
            "strengths": gap_report.get("strengths", []),
        }

        consultant = CareerConsultantChain(self.ai_client)
        roadmap_data = await consultant.generate_roadmap(
            gap_analysis=gap_data,
            user_profile=profile_data,
            job_title=job.get("title", "Target Role") if job else "Target Role",
            company=job.get("company", "Target Company") if job else "Target Company",
        )

        roadmap_content = roadmap_data.get("roadmap", {})
        record = {
            "user_id": user_id,
            "gap_report_id": gap_report_id,
            "title": title or roadmap_content.get("title", "Career Roadmap"),
            "description": roadmap_content.get("overview"),
            "learning_path": roadmap_data.get("learning_resources", []),
            "milestones": roadmap_content.get("milestones", []),
            "timeline": roadmap_content.get("weekly_plans", []),
            "resources": roadmap_data.get("learning_resources", []),
            "skill_development": roadmap_content.get("skill_development", []),
            "certification_path": roadmap_content.get("certification_path", []),
            "experience_recommendations": roadmap_content.get("networking_plan"),
            "progress": {},
            "status": "active",
        }

        doc_id = await self.db.create(COLLECTIONS["roadmaps"], record)
        logger.info("roadmap_generated", roadmap_id=doc_id)
        return await self.db.get(COLLECTIONS["roadmaps"], doc_id)

    async def get_user_roadmaps(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.db.query(
            COLLECTIONS["roadmaps"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )

    async def get_roadmap(self, roadmap_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        roadmap = await self.db.get(COLLECTIONS["roadmaps"], roadmap_id)
        if roadmap and roadmap.get("user_id") == user_id:
            return roadmap
        return None

    async def update_milestone_progress(
        self, roadmap_id: str, user_id: str, milestone_id: str, status: str
    ) -> bool:
        roadmap = await self.get_roadmap(roadmap_id, user_id)
        if not roadmap:
            return False
        progress = roadmap.get("progress", {})
        progress[milestone_id] = status
        await self.db.update(COLLECTIONS["roadmaps"], roadmap_id, {"progress": progress})
        return True

    async def delete_roadmap(self, roadmap_id: str, user_id: str) -> bool:
        roadmap = await self.get_roadmap(roadmap_id, user_id)
        if not roadmap:
            return False
        await self.db.delete(COLLECTIONS["roadmaps"], roadmap_id)
        return True
