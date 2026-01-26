"""
Job Service
Handles job description management and parsing
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.job import JobDescription
from app.schemas.job import JobDescriptionCreate, JobDescriptionUpdate, JobDescriptionResponse
from ai_engine.client import AIClient


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
    """Service for job description operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_client = AIClient()

    async def create_job(
        self,
        user_id: UUID,
        job_data: JobDescriptionCreate
    ) -> JobDescriptionResponse:
        """Create a new job description and parse it."""
        job = JobDescription(
            user_id=user_id,
            title=job_data.title,
            company=job_data.company,
            location=job_data.location,
            job_type=job_data.job_type,
            experience_level=job_data.experience_level,
            salary_range=job_data.salary_range,
            description=job_data.description,
            raw_text=job_data.description,
            source_url=job_data.source_url
        )

        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)

        # Parse the job description
        return await self.parse_job(job.id, user_id)

    async def get_user_jobs(self, user_id: UUID) -> List[JobDescriptionResponse]:
        """Get all jobs for a user."""
        result = await self.db.execute(
            select(JobDescription)
            .where(JobDescription.user_id == user_id)
            .order_by(JobDescription.created_at.desc())
        )
        jobs = result.scalars().all()
        return [JobDescriptionResponse.model_validate(j) for j in jobs]

    async def get_job(
        self,
        job_id: UUID,
        user_id: UUID
    ) -> Optional[JobDescriptionResponse]:
        """Get a specific job."""
        result = await self.db.execute(
            select(JobDescription)
            .where(JobDescription.id == job_id, JobDescription.user_id == user_id)
        )
        job = result.scalar_one_or_none()
        if job:
            return JobDescriptionResponse.model_validate(job)
        return None

    async def update_job(
        self,
        job_id: UUID,
        user_id: UUID,
        job_data: JobDescriptionUpdate
    ) -> Optional[JobDescriptionResponse]:
        """Update a job description."""
        result = await self.db.execute(
            select(JobDescription)
            .where(JobDescription.id == job_id, JobDescription.user_id == user_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return None

        update_dict = job_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            if hasattr(job, field):
                setattr(job, field, value)

        await self.db.commit()
        await self.db.refresh(job)

        return JobDescriptionResponse.model_validate(job)

    async def delete_job(self, job_id: UUID, user_id: UUID) -> bool:
        """Delete a job description."""
        result = await self.db.execute(
            select(JobDescription)
            .where(JobDescription.id == job_id, JobDescription.user_id == user_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return False

        await self.db.delete(job)
        await self.db.commit()
        return True

    async def parse_job(
        self,
        job_id: UUID,
        user_id: UUID
    ) -> Optional[JobDescriptionResponse]:
        """Parse a job description with AI."""
        result = await self.db.execute(
            select(JobDescription)
            .where(JobDescription.id == job_id, JobDescription.user_id == user_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return None

        # Parse with AI
        prompt = JOB_PARSER_PROMPT.format(description=job.description)
        parsed = await self.ai_client.complete_json(
            prompt=prompt,
            temperature=0.2,
            max_tokens=2000
        )

        # Update job with parsed data
        job.parsed_data = parsed
        job.required_skills = parsed.get("required_skills", [])
        job.preferred_skills = parsed.get("preferred_skills", [])
        job.requirements = parsed.get("requirements", [])
        job.responsibilities = parsed.get("responsibilities", [])
        job.benefits = parsed.get("benefits", [])
        job.company_info = parsed.get("company_info", {})

        # Update title/company if not set
        if not job.title and parsed.get("title"):
            job.title = parsed["title"]
        if not job.company and parsed.get("company"):
            job.company = parsed["company"]

        await self.db.commit()
        await self.db.refresh(job)

        return JobDescriptionResponse.model_validate(job)
