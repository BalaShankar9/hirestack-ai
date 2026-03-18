"""
Job Sync Service
Job alert management and match scoring (Supabase)
"""
from typing import Optional, Dict, Any, List
import structlog

from app.core.database import get_db, TABLES, SupabaseDB
from ai_engine.client import get_ai_client

logger = structlog.get_logger()


class JobSyncService:
    """Service for job alerts and match scoring."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()
        self.ai_client = get_ai_client()

    async def create_alert(
        self,
        user_id: str,
        keywords: List[str],
        location: str = "",
        job_type: str = "",
        salary_min: float = 0,
        experience_level: str = "",
    ) -> Dict[str, Any]:
        """Create a job alert."""
        record = {
            "user_id": user_id,
            "keywords": keywords,
            "location": location,
            "job_type": job_type,
            "salary_min": salary_min if salary_min else None,
            "experience_level": experience_level,
            "is_active": True,
        }
        doc_id = await self.db.create(TABLES["job_alerts"], record)
        logger.info("job_alert_created", alert_id=doc_id)
        return await self.db.get(TABLES["job_alerts"], doc_id)

    async def get_alerts(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all alerts for a user."""
        return await self.db.query(
            TABLES["job_alerts"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
        )

    async def score_match(
        self,
        user_id: str,
        job_title: str,
        company: str = "",
        description: str = "",
        location: str = "",
        salary_range: str = "",
        source_url: str = "",
        source: str = "manual",
        alert_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Score a job match against the user's profile."""
        # Get user's primary profile
        profiles = await self.db.query(
            TABLES["profiles"],
            filters=[("user_id", "==", user_id), ("is_primary", "==", True)],
            limit=1,
        )
        profile_text = ""
        if profiles:
            p = profiles[0]
            skills = p.get("skills", [])
            if isinstance(skills, list):
                skill_names = [s.get("name", str(s)) if isinstance(s, dict) else str(s) for s in skills]
            else:
                skill_names = []
            profile_text = f"Title: {p.get('title', '')}\nSkills: {', '.join(skill_names)}\nSummary: {p.get('summary', '')}"

        # AI scoring
        result = await self.ai_client.complete_json(
            prompt=f"""Score how well this job matches the candidate's profile.

CANDIDATE PROFILE:
{profile_text or "No profile available"}

JOB:
Title: {job_title}
Company: {company}
Location: {location}
Description: {description[:2000]}

Return ONLY valid JSON:
```json
{{
    "match_score": 0-100,
    "match_reasons": ["Reason 1", "Reason 2", "Reason 3"],
    "missing_skills": ["Skill the candidate lacks"],
    "recommendation": "apply|consider|skip"
}}
```""",
            system="You are a job matching expert. Be honest and specific.",
            max_tokens=1024,
        )

        record = {
            "user_id": user_id,
            "alert_id": alert_id,
            "title": job_title,
            "company": company,
            "location": location,
            "salary_range": salary_range,
            "description": description[:5000],
            "source_url": source_url,
            "source": source,
            "match_score": result.get("match_score", 0),
            "match_reasons": result.get("match_reasons", []),
            "status": "new",
        }

        doc_id = await self.db.create(TABLES["job_matches"], record)
        return await self.db.get(TABLES["job_matches"], doc_id)

    async def get_matches(self, user_id: str, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get job matches for a user."""
        filters = [("user_id", "==", user_id)]
        if status:
            filters.append(("status", "==", status))
        return await self.db.query(
            TABLES["job_matches"],
            filters=filters,
            order_by="match_score",
            order_direction="DESCENDING",
            limit=limit,
        )

    async def update_match_status(self, match_id: str, user_id: str, status: str) -> bool:
        """Update a match status (interested, applied, rejected, saved)."""
        match = await self.db.get(TABLES["job_matches"], match_id)
        if not match or match.get("user_id") != user_id:
            return False
        update_data: Dict[str, Any] = {"status": status}
        if status == "applied":
            from datetime import datetime, timezone
            update_data["applied_at"] = datetime.now(timezone.utc).isoformat()
        await self.db.update(TABLES["job_matches"], match_id, update_data)
        return True


# ── Singleton ─────────────────────────────────────────────────────
_instance: Optional[JobSyncService] = None


def get_job_sync_service() -> JobSyncService:
    """Return a shared JobSyncService singleton (avoids per-request AIClient)."""
    global _instance
    if _instance is None:
        _instance = JobSyncService()
    return _instance
