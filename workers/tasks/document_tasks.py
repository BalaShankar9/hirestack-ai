"""
Document Generation Tasks
Async tasks for generating documents with AI
"""
from workers.celery_app import app


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
        # Import here to avoid circular imports
        import asyncio
        from ai_engine.client import AIClient
        from ai_engine.chains.document_generator import DocumentGeneratorChain

        async def _generate():
            client = AIClient()
            generator = DocumentGeneratorChain(client)

            if document_type == "cv":
                return await generator.generate_cv(
                    profile=data.get("profile", {}),
                    benchmark=data.get("benchmark", {}),
                    gaps=data.get("gaps", {}),
                )
            elif document_type == "cover_letter":
                return await generator.generate_cover_letter(
                    profile=data.get("profile", {}),
                    job_title=data.get("job_title", ""),
                    company=data.get("company", ""),
                    job_description=data.get("job_description", ""),
                )
            else:
                raise ValueError(f"Unknown document type: {document_type}")

        result = asyncio.run(_generate())
        return {"success": True, "content": result}

    except Exception as exc:
        self.retry(exc=exc, countdown=60)


@app.task(bind=True, max_retries=3)
def analyze_gaps_async(self, user_id: str, profile_id: str, benchmark_id: str):
    """
    Async task to perform gap analysis.
    """
    try:
        import asyncio
        from ai_engine.client import AIClient
        from ai_engine.chains.gap_analyzer import GapAnalyzerChain

        async def _analyze():
            client = AIClient()
            analyzer = GapAnalyzerChain(client)
            # This would need to fetch profile and benchmark from DB
            # Simplified for now
            return {"success": True, "message": "Analysis queued"}

        return asyncio.run(_analyze())

    except Exception as exc:
        self.retry(exc=exc, countdown=60)
