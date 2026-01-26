"""
Benchmark Service
Handles benchmark generation and management
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.job import JobDescription
from app.models.benchmark import Benchmark
from app.schemas.benchmark import BenchmarkResponse
from ai_engine.client import AIClient
from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain


class BenchmarkService:
    """Service for benchmark operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_client = AIClient()

    async def generate_benchmark(
        self,
        user_id: UUID,
        job_id: UUID
    ) -> BenchmarkResponse:
        """Generate a complete benchmark for a job."""
        # Get the job description
        result = await self.db.execute(
            select(JobDescription)
            .where(JobDescription.id == job_id, JobDescription.user_id == user_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError("Job description not found")

        # Check if benchmark already exists
        existing = await self.db.execute(
            select(Benchmark)
            .where(Benchmark.job_description_id == job_id)
            .order_by(Benchmark.created_at.desc())
        )
        existing_benchmark = existing.scalar_one_or_none()

        if existing_benchmark:
            return BenchmarkResponse.model_validate(existing_benchmark)

        # Generate benchmark using AI
        builder = BenchmarkBuilderChain(self.ai_client)
        benchmark_data = await builder.build_complete_benchmark(
            job_title=job.title,
            company=job.company or "Target Company",
            job_description=job.description,
            company_info=job.company_info
        )

        # Create benchmark record
        benchmark = Benchmark(
            job_description_id=job_id,
            ideal_profile=benchmark_data.get("ideal_profile"),
            ideal_skills=benchmark_data.get("ideal_skills"),
            ideal_experience=benchmark_data.get("ideal_experience"),
            ideal_education=benchmark_data.get("ideal_education"),
            ideal_certifications=benchmark_data.get("ideal_certifications"),
            ideal_cv=benchmark_data.get("ideal_cv"),
            ideal_cover_letter=benchmark_data.get("ideal_cover_letter"),
            ideal_portfolio=benchmark_data.get("ideal_portfolio"),
            ideal_case_studies=benchmark_data.get("ideal_case_studies"),
            ideal_action_plan=benchmark_data.get("ideal_action_plan"),
            compatibility_criteria={
                "soft_skills": benchmark_data.get("soft_skills"),
                "industry_knowledge": benchmark_data.get("industry_knowledge")
            },
            scoring_weights=benchmark_data.get("scoring_weights"),
            status="generated"
        )

        self.db.add(benchmark)
        await self.db.commit()
        await self.db.refresh(benchmark)

        return BenchmarkResponse.model_validate(benchmark)

    async def get_benchmark(
        self,
        benchmark_id: UUID,
        user_id: UUID
    ) -> Optional[BenchmarkResponse]:
        """Get a specific benchmark."""
        # Join with job to verify user ownership
        result = await self.db.execute(
            select(Benchmark)
            .join(JobDescription)
            .where(
                Benchmark.id == benchmark_id,
                JobDescription.user_id == user_id
            )
        )
        benchmark = result.scalar_one_or_none()

        if benchmark:
            return BenchmarkResponse.model_validate(benchmark)
        return None

    async def get_benchmark_for_job(
        self,
        job_id: UUID,
        user_id: UUID
    ) -> Optional[BenchmarkResponse]:
        """Get benchmark for a specific job."""
        result = await self.db.execute(
            select(Benchmark)
            .join(JobDescription)
            .where(
                Benchmark.job_description_id == job_id,
                JobDescription.user_id == user_id
            )
            .order_by(Benchmark.created_at.desc())
        )
        benchmark = result.scalar_one_or_none()

        if benchmark:
            return BenchmarkResponse.model_validate(benchmark)
        return None

    async def regenerate_benchmark(
        self,
        benchmark_id: UUID,
        user_id: UUID
    ) -> Optional[BenchmarkResponse]:
        """Regenerate an existing benchmark."""
        # Get existing benchmark
        result = await self.db.execute(
            select(Benchmark)
            .join(JobDescription)
            .where(
                Benchmark.id == benchmark_id,
                JobDescription.user_id == user_id
            )
        )
        old_benchmark = result.scalar_one_or_none()

        if not old_benchmark:
            return None

        job_id = old_benchmark.job_description_id

        # Delete old benchmark
        await self.db.delete(old_benchmark)
        await self.db.commit()

        # Generate new benchmark
        return await self.generate_benchmark(user_id, job_id)

    async def delete_benchmark(
        self,
        benchmark_id: UUID,
        user_id: UUID
    ) -> bool:
        """Delete a benchmark."""
        result = await self.db.execute(
            select(Benchmark)
            .join(JobDescription)
            .where(
                Benchmark.id == benchmark_id,
                JobDescription.user_id == user_id
            )
        )
        benchmark = result.scalar_one_or_none()

        if not benchmark:
            return False

        await self.db.delete(benchmark)
        await self.db.commit()
        return True
