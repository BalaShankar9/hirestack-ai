"""
Gap Service
Handles gap analysis operations with Firestore
"""
from typing import List, Optional, Dict, Any
import structlog

from app.core.database import get_firestore_db, COLLECTIONS, FirestoreDB
from ai_engine.client import AIClient
from ai_engine.chains.gap_analyzer import GapAnalyzerChain

logger = structlog.get_logger()


class GapService:
    """Service for gap analysis operations using Firestore."""

    def __init__(self, db: Optional[FirestoreDB] = None):
        self.db = db or get_firestore_db()
        self.ai_client = AIClient()

    async def analyze_gaps(
        self,
        user_id: str,
        profile_id: str,
        benchmark_id: str,
    ) -> Dict[str, Any]:
        """Perform comprehensive gap analysis."""
        # Fetch profile
        profile = await self.db.get(COLLECTIONS["profiles"], profile_id)
        if not profile or profile.get("user_id") != user_id:
            raise ValueError("Profile not found")

        # Fetch benchmark
        benchmark = await self.db.get(COLLECTIONS["benchmarks"], benchmark_id)
        if not benchmark:
            raise ValueError("Benchmark not found")

        # Fetch linked job for title/company
        job_id = benchmark.get("job_description_id")
        job = await self.db.get(COLLECTIONS["jobs"], job_id) if job_id else None

        # Build data dicts for AI
        profile_data = {
            "name": profile.get("name"),
            "title": profile.get("title"),
            "summary": profile.get("summary"),
            "skills": profile.get("skills", []),
            "experience": profile.get("experience", []),
            "education": profile.get("education", []),
            "certifications": profile.get("certifications", []),
            "projects": profile.get("projects", []),
        }
        benchmark_data = {
            "ideal_profile": benchmark.get("ideal_profile"),
            "ideal_skills": benchmark.get("ideal_skills", []),
            "ideal_experience": benchmark.get("ideal_experience", []),
            "ideal_education": benchmark.get("ideal_education", []),
            "ideal_certifications": benchmark.get("ideal_certifications", []),
            "scoring_weights": benchmark.get("scoring_weights"),
        }

        # AI analysis
        analyzer = GapAnalyzerChain(self.ai_client)
        analysis = await analyzer.analyze_gaps(
            user_profile=profile_data,
            benchmark=benchmark_data,
            job_title=job.get("title", "Target Role") if job else "Target Role",
            company=job.get("company", "Target Company") if job else "Target Company",
        )

        cats = analysis.get("category_scores", {})
        record = {
            "user_id": user_id,
            "profile_id": profile_id,
            "benchmark_id": benchmark_id,
            "compatibility_score": analysis.get("compatibility_score", 0),
            "skill_score": cats.get("technical_skills", {}).get("score", 0),
            "experience_score": cats.get("experience", {}).get("score", 0),
            "education_score": cats.get("education", {}).get("score", 0),
            "certification_score": cats.get("certifications", {}).get("score", 0),
            "project_score": cats.get("projects_portfolio", {}).get("score", 0),
            "skill_gaps": analysis.get("skill_gaps", []),
            "experience_gaps": analysis.get("experience_gaps", []),
            "education_gaps": analysis.get("education_gaps", []),
            "certification_gaps": analysis.get("certification_gaps", []),
            "project_gaps": analysis.get("project_gaps", []),
            "strengths": analysis.get("strengths", []),
            "recommendations": analysis.get("recommendations", []),
            "priority_actions": analysis.get("quick_wins", []),
            "summary": analysis,
            "status": "completed",
        }

        doc_id = await self.db.create(COLLECTIONS["gap_reports"], record)
        logger.info("gap_analysis_completed", report_id=doc_id, score=record["compatibility_score"])
        return await self.db.get(COLLECTIONS["gap_reports"], doc_id)

    async def get_user_reports(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.db.query(
            COLLECTIONS["gap_reports"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )

    async def get_report(self, report_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        report = await self.db.get(COLLECTIONS["gap_reports"], report_id)
        if report and report.get("user_id") == user_id:
            return report
        return None

    async def get_summary(self, report_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        report = await self.get_report(report_id, user_id)
        if not report:
            return None
        summary_data = report.get("summary", {})
        return {
            "compatibility_score": report.get("compatibility_score", 0),
            "skill_score": report.get("skill_score", 0),
            "experience_score": report.get("experience_score", 0),
            "education_score": report.get("education_score", 0),
            "certification_score": report.get("certification_score", 0),
            "project_score": report.get("project_score", 0),
            "top_gaps": [g.get("skill", g.get("area", "")) for g in (report.get("skill_gaps") or [])[:3]],
            "top_strengths": [s.get("area", "") for s in (report.get("strengths") or [])[:3]],
            "readiness_level": summary_data.get("readiness_level", "needs-work"),
        }

    async def refresh_analysis(self, report_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        old = await self.get_report(report_id, user_id)
        if not old:
            return None
        await self.db.delete(COLLECTIONS["gap_reports"], report_id)
        return await self.analyze_gaps(user_id, old["profile_id"], old["benchmark_id"])

    async def delete_report(self, report_id: str, user_id: str) -> bool:
        report = await self.get_report(report_id, user_id)
        if not report:
            return False
        await self.db.delete(COLLECTIONS["gap_reports"], report_id)
        return True
