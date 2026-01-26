"""
Export Tasks
Async tasks for generating PDF/DOCX exports
"""
from workers.celery_app import app


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
        import asyncio

        async def _export():
            # Import here to avoid circular imports
            from backend.app.services.export import ExportService
            from backend.app.core.database import async_session

            async with async_session() as session:
                service = ExportService(session)
                # This would generate the actual PDF
                return {"success": True, "message": "Export queued"}

        return asyncio.run(_export())

    except Exception as exc:
        self.retry(exc=exc, countdown=60)


@app.task(bind=True, max_retries=3)
def generate_docx_export(self, user_id: str, document_ids: list, options: dict):
    """
    Async task to generate DOCX export.
    """
    try:
        import asyncio

        async def _export():
            return {"success": True, "message": "Export queued"}

        return asyncio.run(_export())

    except Exception as exc:
        self.retry(exc=exc, countdown=60)


@app.task(bind=True, max_retries=3)
def generate_zip_package(self, user_id: str, document_ids: list, options: dict):
    """
    Async task to generate a ZIP package with all documents.
    """
    try:
        import asyncio

        async def _export():
            return {"success": True, "message": "Package generation queued"}

        return asyncio.run(_export())

    except Exception as exc:
        self.retry(exc=exc, countdown=60)
