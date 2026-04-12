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

    v2: Routes through AgentPipeline for full quality gates (critic,
    optimizer, fact-checker, validator). Falls back to direct chain
    if pipeline construction fails.

    Args:
        user_id: The user's ID
        document_type: Type of document (cv, cover_letter, etc.)
        data: Document generation data
    """
    try:
        from ai_engine.client import get_ai_client

        async def _generate():
            client = get_ai_client()

            # Try pipeline-based generation first (full quality gates)
            try:
                from ai_engine.agents.pipelines import build_pipeline
                from app.core.database import get_supabase, TABLES

                pipeline_name = {
                    "cv": "cv_generation",
                    "cover_letter": "cover_letter",
                }.get(document_type)

                if pipeline_name:
                    sb = get_supabase()
                    pipeline = build_pipeline(pipeline_name, ai_client=client, db=sb, tables=TABLES)
                    pipeline_context = {
                        "user_id": user_id,
                        "user_profile": data.get("profile", {}),
                        "job_title": data.get("job_title", ""),
                        "company": data.get("company", ""),
                        "jd_text": data.get("job_requirements", {}).get("description", "")
                            or data.get("benchmark", {}).get("description", ""),
                        "company_intel": data.get("company_info", {}),
                        "gap_insights": data.get("gaps", {}),
                    }
                    result = await pipeline.execute(pipeline_context)
                    return result.content
            except Exception as pipeline_err:
                logger.warning(
                    "pipeline_fallback_to_chain",
                    document_type=document_type,
                    error=str(pipeline_err),
                )

            # Fallback: direct chain (no quality gates)
            from ai_engine.chains.document_generator import DocumentGeneratorChain

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
