"""
Roadmap Service
Handles career roadmap generation and management
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.profile import Profile
from app.models.gap import GapReport
from app.models.roadmap import Roadmap
from app.models.benchmark import Benchmark
from app.models.job import JobDescription
from app.schemas.roadmap import RoadmapResponse
from ai_engine.client import AIClient
from ai_engine.chains.career_consultant import CareerConsultantChain


class RoadmapService:
    """Service for roadmap operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_client = AIClient()

    async def generate_roadmap(
        self,
        user_id: UUID,
        gap_report_id: UUID,
        title: Optional[str] = None
    ) -> RoadmapResponse:
        """Generate a career improvement roadmap."""
        # Get gap report with related data
        result = await self.db.execute(
            select(GapReport)
            .where(GapReport.id == gap_report_id, GapReport.user_id == user_id)
        )
        gap_report = result.scalar_one_or_none()
        if not gap_report:
            raise ValueError("Gap report not found")

        # Get profile
        profile_result = await self.db.execute(
            select(Profile).where(Profile.id == gap_report.profile_id)
        )
        profile = profile_result.scalar_one_or_none()

        # Get benchmark and job
        benchmark_result = await self.db.execute(
            select(Benchmark).where(Benchmark.id == gap_report.benchmark_id)
        )
        benchmark = benchmark_result.scalar_one_or_none()

        job = None
        if benchmark:
            job_result = await self.db.execute(
                select(JobDescription)
                .where(JobDescription.id == benchmark.job_description_id)
            )
            job = job_result.scalar_one_or_none()

        # Build data for AI
        profile_data = {
            "name": profile.name if profile else "User",
            "title": profile.title if profile else "",
            "skills": profile.skills if profile else [],
            "experience": profile.experience if profile else [],
        }

        gap_data = {
            "compatibility_score": gap_report.compatibility_score,
            "skill_gaps": gap_report.skill_gaps,
            "experience_gaps": gap_report.experience_gaps,
            "recommendations": gap_report.recommendations,
            "strengths": gap_report.strengths
        }

        # Generate roadmap with AI
        consultant = CareerConsultantChain(self.ai_client)
        roadmap_data = await consultant.generate_roadmap(
            gap_analysis=gap_data,
            user_profile=profile_data,
            job_title=job.title if job else "Target Role",
            company=job.company if job else "Target Company"
        )

        roadmap_content = roadmap_data.get("roadmap", {})

        # Create roadmap record
        roadmap = Roadmap(
            user_id=user_id,
            gap_report_id=gap_report_id,
            title=title or roadmap_content.get("title", "Career Roadmap"),
            description=roadmap_content.get("overview"),
            learning_path=roadmap_data.get("learning_resources", []),
            milestones=roadmap_content.get("milestones", []),
            timeline=roadmap_content.get("weekly_plans", []),
            resources=roadmap_data.get("learning_resources", []),
            skill_development=roadmap_content.get("skill_development", []),
            certification_path=roadmap_content.get("certification_path", []),
            experience_recommendations=roadmap_content.get("networking_plan"),
            action_items=roadmap_content.get("milestones", []),
            progress={},
            status="active"
        )

        self.db.add(roadmap)
        await self.db.commit()
        await self.db.refresh(roadmap)

        return RoadmapResponse.model_validate(roadmap)

    async def get_user_roadmaps(self, user_id: UUID) -> List[RoadmapResponse]:
        """Get all roadmaps for a user."""
        result = await self.db.execute(
            select(Roadmap)
            .where(Roadmap.user_id == user_id)
            .order_by(Roadmap.created_at.desc())
        )
        roadmaps = result.scalars().all()
        return [RoadmapResponse.model_validate(r) for r in roadmaps]

    async def get_roadmap(
        self,
        roadmap_id: UUID,
        user_id: UUID
    ) -> Optional[RoadmapResponse]:
        """Get a specific roadmap."""
        result = await self.db.execute(
            select(Roadmap)
            .where(Roadmap.id == roadmap_id, Roadmap.user_id == user_id)
        )
        roadmap = result.scalar_one_or_none()
        if roadmap:
            return RoadmapResponse.model_validate(roadmap)
        return None

    async def update_milestone_progress(
        self,
        roadmap_id: UUID,
        user_id: UUID,
        milestone_id: str,
        status: str
    ) -> bool:
        """Update milestone progress."""
        result = await self.db.execute(
            select(Roadmap)
            .where(Roadmap.id == roadmap_id, Roadmap.user_id == user_id)
        )
        roadmap = result.scalar_one_or_none()

        if not roadmap:
            return False

        progress = roadmap.progress or {}
        progress[milestone_id] = status
        roadmap.progress = progress

        await self.db.commit()
        return True

    async def delete_roadmap(self, roadmap_id: UUID, user_id: UUID) -> bool:
        """Delete a roadmap."""
        result = await self.db.execute(
            select(Roadmap)
            .where(Roadmap.id == roadmap_id, Roadmap.user_id == user_id)
        )
        roadmap = result.scalar_one_or_none()

        if not roadmap:
            return False

        await self.db.delete(roadmap)
        await self.db.commit()
        return True
