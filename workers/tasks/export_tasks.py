"""
Export Tasks
Async tasks for generating PDF/DOCX exports
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
def generate_pdf_export(self, user_id: str, document_ids: list, options: dict):
    """
    Async task to generate PDF export.

    Args:
        user_id: The user's ID
        document_ids: List of document IDs to export
        options: Export options (include cover page, etc.)
    """
    try:
        async def _export():
            from app.services.export import ExportService

            service = ExportService()
            result = await service.create_export(
                user_id=user_id,
                document_ids=document_ids,
                fmt="pdf",
                options=options,
            )
            return {"success": True, "export_id": result.get("id")}

        return _run_async(_export())

    except Exception as exc:
        logger.error("pdf_export_failed", user_id=user_id, error=str(exc))
        self.retry(exc=exc, countdown=60)


@app.task(bind=True, max_retries=3)
def generate_docx_export(self, user_id: str, document_ids: list, options: dict):
    """
    Async task to generate DOCX export.
    """
    try:
        async def _export():
            from app.services.export import ExportService

            service = ExportService()
            result = await service.create_export(
                user_id=user_id,
                document_ids=document_ids,
                fmt="docx",
                options=options,
            )
            return {"success": True, "export_id": result.get("id")}

        return _run_async(_export())

    except Exception as exc:
        logger.error("docx_export_failed", user_id=user_id, error=str(exc))
        self.retry(exc=exc, countdown=60)


@app.task(bind=True, max_retries=3)
def generate_zip_package(self, user_id: str, document_ids: list, options: dict):
    """
    Async task to generate a ZIP package with all documents.
    """
    try:
        async def _export():
            from app.services.export import ExportService

            service = ExportService()
            # Generate all formats
            results = []
            for fmt in ["pdf", "docx"]:
                result = await service.create_export(
                    user_id=user_id,
                    document_ids=document_ids,
                    fmt=fmt,
                    options=options,
                )
                results.append(result.get("id"))
            return {"success": True, "export_ids": results}

        return _run_async(_export())

    except Exception as exc:
        logger.error("zip_export_failed", user_id=user_id, error=str(exc))
        self.retry(exc=exc, countdown=60)
