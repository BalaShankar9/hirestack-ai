"""
Salary Coach Service
Market salary analysis and negotiation guidance (Supabase)
"""
from typing import Optional, Dict, Any, List
import structlog

from app.core.database import get_db, TABLES, SupabaseDB
from ai_engine.client import get_ai_client
from ai_engine.chains.salary_coach import SalaryCoachChain

logger = structlog.get_logger()


class SalaryService:
    """Service for salary analysis and negotiation coaching."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()
        self.ai_client = get_ai_client()

    async def analyze(
        self,
        user_id: str,
        job_title: str,
        company: str = "",
        location: str = "",
        experience_years: float = 0,
        current_salary: float = 0,
        skills_summary: str = "",
        application_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a comprehensive salary analysis."""
        chain = SalaryCoachChain(self.ai_client)
        result = await chain.analyze_salary(
            job_title=job_title,
            company=company,
            location=location,
            experience_years=experience_years,
            current_salary=current_salary,
            skills_summary=skills_summary,
        )

        record = {
            "user_id": user_id,
            "application_id": application_id,
            "job_title": job_title,
            "company": company,
            "location": location,
            "experience_years": experience_years,
            "current_salary": current_salary,
            "market_data": result.get("market_data", {}),
            "salary_range": result.get("salary_range", {}),
            "negotiation_scripts": result.get("negotiation_scripts", []),
            "counter_offers": result.get("counter_offers", []),
            "talking_points": result.get("talking_points", []),
            "benefits_analysis": result.get("benefits_analysis", {}),
            "confidence_level": result.get("confidence_level", "medium"),
        }

        doc_id = await self.db.create(TABLES["salary_analyses"], record)
        logger.info("salary_analysis_completed", analysis_id=doc_id, job_title=job_title)
        saved = await self.db.get(TABLES["salary_analyses"], doc_id)
        # If table doesn't exist, return the AI result directly
        return saved or {**record, "id": doc_id, **result}

    async def get_analysis(self, analysis_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific salary analysis."""
        analysis = await self.db.get(TABLES["salary_analyses"], analysis_id)
        if analysis and analysis.get("user_id") == user_id:
            return analysis
        return None

    async def get_user_analyses(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent analyses for user."""
        return await self.db.query(
            TABLES["salary_analyses"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )
