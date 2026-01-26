"""
Gap Service
Handles gap analysis operations
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.profile import Profile
from app.models.benchmark import Benchmark
from app.models.job import JobDescription
from app.models.gap import GapReport
from app.schemas.gap import GapReportResponse, GapSummary
from ai_engine.client import AIClient
from ai_engine.chains.gap_analyzer import GapAnalyzerChain


class GapService:
    """Service for gap analysis operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_client = AIClient()

    async def analyze_gaps(
        self,
        user_id: UUID,
        profile_id: UUID,
        benchmark_id: UUID
    ) -> GapReportResponse:
        """Perform comprehensive gap analysis."""
        # Get profile
        profile_result = await self.db.execute(
            select(Profile)
            .where(Profile.id == profile_id, Profile.user_id == user_id)
        )
        profile = profile_result.scalar_one_or_none()
        if not profile:
            raise ValueError("Profile not found")

        # Get benchmark with job info
        benchmark_result = await self.db.execute(
            select(Benchmark)
            .join(JobDescription)
            .where(Benchmark.id == benchmark_id)
        )
        benchmark = benchmark_result.scalar_one_or_none()
        if not benchmark:
            raise ValueError("Benchmark not found")

        # Get job details
        job_result = await self.db.execute(
            select(JobDescription)
            .where(JobDescription.id == benchmark.job_description_id)
        )
        job = job_result.scalar_one_or_none()

        # Build profile data for analysis
        profile_data = {
            "name": profile.name,
            "title": profile.title,
            "summary": profile.summary,
            "skills": profile.skills or [],
            "experience": profile.experience or [],
            "education": profile.education or [],
            "certifications": profile.certifications or [],
            "projects": profile.projects or []
        }

        # Build benchmark data
        benchmark_data = {
            "ideal_profile": benchmark.ideal_profile,
            "ideal_skills": benchmark.ideal_skills or [],
            "ideal_experience": benchmark.ideal_experience or [],
            "ideal_education": benchmark.ideal_education or [],
            "ideal_certifications": benchmark.ideal_certifications or [],
            "scoring_weights": benchmark.scoring_weights
        }

        # Perform analysis with AI
        analyzer = GapAnalyzerChain(self.ai_client)
        analysis = await analyzer.analyze_gaps(
            user_profile=profile_data,
            benchmark=benchmark_data,
            job_title=job.title if job else "Target Role",
            company=job.company if job else "Target Company"
        )

        # Create gap report
        report = GapReport(
            user_id=user_id,
            profile_id=profile_id,
            benchmark_id=benchmark_id,
            compatibility_score=analysis.get("compatibility_score", 0),
            skill_score=analysis.get("category_scores", {}).get("technical_skills", {}).get("score", 0),
            experience_score=analysis.get("category_scores", {}).get("experience", {}).get("score", 0),
            education_score=analysis.get("category_scores", {}).get("education", {}).get("score", 0),
            certification_score=analysis.get("category_scores", {}).get("certifications", {}).get("score", 0),
            project_score=analysis.get("category_scores", {}).get("projects_portfolio", {}).get("score", 0),
            skill_gaps=analysis.get("skill_gaps", []),
            experience_gaps=analysis.get("experience_gaps", []),
            education_gaps=analysis.get("education_gaps", []),
            certification_gaps=analysis.get("certification_gaps", []),
            project_gaps=analysis.get("project_gaps", []),
            strengths=analysis.get("strengths", []),
            recommendations=analysis.get("recommendations", []),
            priority_actions=analysis.get("quick_wins", []),
            summary=analysis
        )

        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)

        return GapReportResponse.model_validate(report)

    async def get_user_reports(self, user_id: UUID) -> List[GapReportResponse]:
        """Get all gap reports for a user."""
        result = await self.db.execute(
            select(GapReport)
            .where(GapReport.user_id == user_id)
            .order_by(GapReport.created_at.desc())
        )
        reports = result.scalars().all()
        return [GapReportResponse.model_validate(r) for r in reports]

    async def get_report(
        self,
        report_id: UUID,
        user_id: UUID
    ) -> Optional[GapReportResponse]:
        """Get a specific gap report."""
        result = await self.db.execute(
            select(GapReport)
            .where(GapReport.id == report_id, GapReport.user_id == user_id)
        )
        report = result.scalar_one_or_none()
        if report:
            return GapReportResponse.model_validate(report)
        return None

    async def get_summary(
        self,
        report_id: UUID,
        user_id: UUID
    ) -> Optional[GapSummary]:
        """Get a summary of a gap report."""
        result = await self.db.execute(
            select(GapReport)
            .where(GapReport.id == report_id, GapReport.user_id == user_id)
        )
        report = result.scalar_one_or_none()

        if not report:
            return None

        summary = report.summary or {}

        return GapSummary(
            compatibility_score=report.compatibility_score,
            skill_score=report.skill_score,
            experience_score=report.experience_score,
            education_score=report.education_score,
            certification_score=report.certification_score,
            project_score=report.project_score,
            top_gaps=[g.get("skill", g.get("area", "")) for g in (report.skill_gaps or [])[:3]],
            top_strengths=[s.get("area", "") for s in (report.strengths or [])[:3]],
            readiness_level=summary.get("readiness_level", "needs-work")
        )

    async def refresh_analysis(
        self,
        report_id: UUID,
        user_id: UUID
    ) -> Optional[GapReportResponse]:
        """Refresh a gap analysis."""
        result = await self.db.execute(
            select(GapReport)
            .where(GapReport.id == report_id, GapReport.user_id == user_id)
        )
        old_report = result.scalar_one_or_none()

        if not old_report:
            return None

        profile_id = old_report.profile_id
        benchmark_id = old_report.benchmark_id

        # Delete old report
        await self.db.delete(old_report)
        await self.db.commit()

        # Generate new analysis
        return await self.analyze_gaps(user_id, profile_id, benchmark_id)

    async def delete_report(self, report_id: UUID, user_id: UUID) -> bool:
        """Delete a gap report."""
        result = await self.db.execute(
            select(GapReport)
            .where(GapReport.id == report_id, GapReport.user_id == user_id)
        )
        report = result.scalar_one_or_none()

        if not report:
            return False

        await self.db.delete(report)
        await self.db.commit()
        return True
