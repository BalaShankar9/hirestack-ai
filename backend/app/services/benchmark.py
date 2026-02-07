"""
Benchmark Service
Handles benchmark generation and management with Firestore
"""
from typing import Optional, Dict, Any, List
import structlog

from app.core.database import get_firestore_db, COLLECTIONS, FirestoreDB
from ai_engine.client import AIClient
from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain

logger = structlog.get_logger()


class BenchmarkService:
    """Service for benchmark operations using Firestore."""

    def __init__(self, db: Optional[FirestoreDB] = None):
        self.db = db or get_firestore_db()
        self.ai_client = AIClient()

    async def generate_benchmark(self, user_id: str, job_id: str) -> Dict[str, Any]:
        """Generate a complete benchmark package for a job."""
        job = await self.db.get(COLLECTIONS["jobs"], job_id)
        if not job or job.get("user_id") != user_id:
            raise ValueError("Job description not found")

        # Check for existing benchmark
        existing = await self.db.query(
            COLLECTIONS["benchmarks"],
            filters=[("job_description_id", "==", job_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=1,
        )
        if existing:
            return existing[0]

        # Generate via AI
        builder = BenchmarkBuilderChain(self.ai_client)
        benchmark_data = await builder.build_complete_benchmark(
            job_title=job.get("title", "Target Role"),
            company=job.get("company", "Target Company"),
            job_description=job.get("description", ""),
            company_info=job.get("company_info"),
        )

        record = {
            "job_description_id": job_id,
            "user_id": user_id,
            "ideal_profile": benchmark_data.get("ideal_profile"),
            "ideal_skills": benchmark_data.get("ideal_skills", []),
            "ideal_experience": benchmark_data.get("ideal_experience", []),
            "ideal_education": benchmark_data.get("ideal_education", []),
            "ideal_certifications": benchmark_data.get("ideal_certifications", []),
            "ideal_cv": benchmark_data.get("ideal_cv"),
            "ideal_cover_letter": benchmark_data.get("ideal_cover_letter"),
            "ideal_portfolio": benchmark_data.get("ideal_portfolio", []),
            "ideal_case_studies": benchmark_data.get("ideal_case_studies", []),
            "ideal_action_plan": benchmark_data.get("ideal_action_plan", {}),
            "compatibility_criteria": {
                "soft_skills": benchmark_data.get("soft_skills"),
                "industry_knowledge": benchmark_data.get("industry_knowledge"),
            },
            "scoring_weights": benchmark_data.get("scoring_weights", {}),
            "status": "generated",
        }

        doc_id = await self.db.create(COLLECTIONS["benchmarks"], record)
        logger.info("benchmark_generated", benchmark_id=doc_id, job_id=job_id)
        return await self.db.get(COLLECTIONS["benchmarks"], doc_id)

    async def get_benchmark(self, benchmark_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific benchmark, verifying ownership via linked job."""
        benchmark = await self.db.get(COLLECTIONS["benchmarks"], benchmark_id)
        if not benchmark:
            return None
        # Verify ownership
        job_id = benchmark.get("job_description_id")
        if job_id:
            job = await self.db.get(COLLECTIONS["jobs"], job_id)
            if not job or job.get("user_id") != user_id:
                return None
        return benchmark

    async def get_benchmark_for_job(self, job_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest benchmark for a specific job."""
        results = await self.db.query(
            COLLECTIONS["benchmarks"],
            filters=[("job_description_id", "==", job_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=1,
        )
        if results:
            return results[0]
        return None

    async def regenerate_benchmark(self, benchmark_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Delete old benchmark and generate a fresh one."""
        old = await self.get_benchmark(benchmark_id, user_id)
        if not old:
            return None
        job_id = old.get("job_description_id")
        await self.db.delete(COLLECTIONS["benchmarks"], benchmark_id)
        return await self.generate_benchmark(user_id, job_id)

    async def delete_benchmark(self, benchmark_id: str, user_id: str) -> bool:
        benchmark = await self.get_benchmark(benchmark_id, user_id)
        if not benchmark:
            return False
        await self.db.delete(COLLECTIONS["benchmarks"], benchmark_id)
        return True
