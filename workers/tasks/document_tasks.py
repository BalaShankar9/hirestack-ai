"""
Document Generation Tasks
Async tasks for generating documents with AI
"""
import asyncio
import structlog

from workers.celery_app import app

logger = structlog.get_logger()


def _run_async(coro):
    """Run an async coroutine inside a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(bind=True, max_retries=3)
def generate_document_async(self, user_id: str, document_type: str, data: dict):
    """
    Async task to generate a document using AI.

    Args:
        user_id: The user's ID
        document_type: Type of document (cv, cover_letter, etc.)
        data: Document generation data
    """
    try:
        from ai_engine.client import get_ai_client
        from ai_engine.chains.document_generator import DocumentGeneratorChain

        async def _generate():
            client = get_ai_client()
            generator = DocumentGeneratorChain(client)

            if document_type == "cv":
                return await generator.generate_cv(
                    user_profile=data.get("profile", {}),
                    job_title=data.get("job_title", ""),
                    company=data.get("company", ""),
                    job_requirements=data.get("benchmark", {}),
                    gap_insights=data.get("gaps", {}),
                )
            elif document_type == "cover_letter":
                return await generator.generate_cover_letter(
                    user_profile=data.get("profile", {}),
                    job_title=data.get("job_title", ""),
                    company=data.get("company", ""),
                    company_info=data.get("company_info", {}),
                    job_requirements=data.get("job_requirements", {}),
                    strengths=data.get("strengths", []),
                )
            else:
                raise ValueError(f"Unknown document type: {document_type}")

        result = _run_async(_generate())
        return {"success": True, "content": result}

    except Exception as exc:
        logger.error("document_gen_task_failed", document_type=document_type, error=str(exc))
        self.retry(exc=exc, countdown=60)


@app.task(bind=True, max_retries=3)
def analyze_gaps_async(self, user_id: str, profile_id: str, benchmark_id: str):
    """
    Async task to perform gap analysis.
    """
    try:
        from app.services.gap import GapService

        async def _analyze():
            service = GapService()
            return await service.analyze_gaps(
                user_id=user_id,
                profile_id=profile_id,
                benchmark_id=benchmark_id,
            )

        result = _run_async(_analyze())
        return {"success": True, "report_id": result.get("id"), "score": result.get("compatibility_score")}

    except Exception as exc:
        logger.error("gap_analysis_task_failed", user_id=user_id, error=str(exc))
        self.retry(exc=exc, countdown=60)
