"""
Job Service
Handles job description management and parsing with Firestore
"""
from typing import List, Optional, Dict, Any
import structlog

from app.core.database import get_firestore_db, COLLECTIONS, FirestoreDB
from ai_engine.client import AIClient

logger = structlog.get_logger()

JOB_PARSER_PROMPT = """Parse this job description and extract structured requirements:

JOB DESCRIPTION:
{description}

Return ONLY valid JSON:
```json
{{
  "title": "Extracted job title",
  "company": "Company name if mentioned",
  "location": "Location if mentioned",
  "job_type": "full-time|part-time|contract|remote",
  "experience_level": "entry|mid|senior|lead|executive",
  "salary_range": "If mentioned",
  "required_skills": ["Must-have skills"],
  "preferred_skills": ["Nice-to-have skills"],
  "requirements": ["Specific requirements"],
  "responsibilities": ["Key responsibilities"],
  "benefits": ["Benefits if listed"],
  "company_info": {{
    "industry": "Industry",
    "size": "Company size if mentioned",
    "culture": "Culture hints"
  }}
}}
```"""


class JobService:
    """Service for job description operations using Firestore."""

    ALLOWED_FIELDS = {
        "title", "company", "location", "job_type", "experience_level",
        "salary_range", "description", "source_url",
    }

    def __init__(self, db: Optional[FirestoreDB] = None):
        self.db = db or get_firestore_db()
        self.ai_client = AIClient()

    async def create_job(self, user_id: str, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new job description and optionally parse it."""
        safe = {k: v for k, v in job_data.items() if k in self.ALLOWED_FIELDS}
        safe["user_id"] = user_id
        safe["raw_text"] = safe.get("description", "")

        doc_id = await self.db.create(COLLECTIONS["jobs"], safe)
        created = await self.db.get(COLLECTIONS["jobs"], doc_id)

        # Best-effort AI parsing
        try:
            return await self._parse_and_update(created)
        except Exception as e:
            logger.warning("job_parse_failed", job_id=doc_id, error=str(e))
            return created

    async def get_user_jobs(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.db.query(
            COLLECTIONS["jobs"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )

    async def get_job(self, job_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        job = await self.db.get(COLLECTIONS["jobs"], job_id)
        if job and job.get("user_id") == user_id:
            return job
        return None

    async def update_job(self, job_id: str, user_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        job = await self.get_job(job_id, user_id)
        if not job:
            return None
        safe = {k: v for k, v in update_data.items() if k in self.ALLOWED_FIELDS}
        if not safe:
            return job
        await self.db.update(COLLECTIONS["jobs"], job_id, safe)
        return await self.db.get(COLLECTIONS["jobs"], job_id)

    async def delete_job(self, job_id: str, user_id: str) -> bool:
        job = await self.get_job(job_id, user_id)
        if not job:
            return False
        await self.db.delete(COLLECTIONS["jobs"], job_id)
        return True

    async def parse_job(self, job_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        job = await self.get_job(job_id, user_id)
        if not job:
            return None
        return await self._parse_and_update(job)

    async def _parse_and_update(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse job description with AI and update the Firestore document."""
        description = job.get("description", "")
        if not description:
            return job

        prompt = JOB_PARSER_PROMPT.format(description=description)
        parsed = await self.ai_client.complete_json(prompt=prompt, temperature=0.2, max_tokens=2000)

        update: Dict[str, Any] = {
            "parsed_data": parsed,
            "required_skills": parsed.get("required_skills", []),
            "preferred_skills": parsed.get("preferred_skills", []),
            "requirements": parsed.get("requirements", []),
            "responsibilities": parsed.get("responsibilities", []),
            "benefits": parsed.get("benefits", []),
            "company_info": parsed.get("company_info", {}),
        }
        if not job.get("title") and parsed.get("title"):
            update["title"] = parsed["title"]
        if not job.get("company") and parsed.get("company"):
            update["company"] = parsed["company"]

        await self.db.update(COLLECTIONS["jobs"], job["id"], update)
        return await self.db.get(COLLECTIONS["jobs"], job["id"])
