"""
Export routes - PDF/DOCX generation (Firestore)
"""
import re
from typing import Dict, Any, List, Optional
from urllib.parse import quote

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field

from app.services.export import ExportService
from app.api.deps import get_current_user, validate_uuid
import structlog

logger = structlog.get_logger()

router = APIRouter()


class CreateExportRequest(BaseModel):
    document_ids: List[str] = []
    format: str = Field("pdf", pattern="^(pdf|docx|markdown)$")
    filename: Optional[str] = None
    options: Optional[Dict[str, Any]] = None


@router.post("")
@limiter.limit("20/minute")
async def create_export(
    body: CreateExportRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create an export of documents."""
    service = ExportService()
    try:
        return await service.create_export(
            user_id=current_user["id"],
            document_ids=body.document_ids,
            fmt=body.format,
            filename=body.filename,
            options=body.options,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("unexpected_error", error=str(e), endpoint="create_export")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")


@router.get("")
@limiter.limit("20/minute")
async def list_exports(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's exports."""
    service = ExportService()
    return await service.get_user_exports(current_user["id"], limit=limit, offset=offset)


@router.get("/{export_id}")
@limiter.limit("20/minute")
async def get_export(
    request: Request,
    export_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get export details."""
    validate_uuid(export_id, "export_id")
    service = ExportService()
    export = await service.get_export(export_id, current_user["id"])
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    return export


@router.get("/{export_id}/download")
@limiter.limit("20/minute")
async def download_export(
    request: Request,
    export_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Download an exported file."""
    validate_uuid(export_id, "export_id")
    service = ExportService()
    try:
        file_content, filename, content_type = await service.download_export(export_id, current_user["id"])
        # Sanitize filename to prevent header injection
        safe_name = re.sub(r'[^\w\s\-.]', '', filename or 'export')[:200]
        return StreamingResponse(
            iter([file_content]),
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}"},
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("unexpected_error", error=str(e), endpoint="download_export")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")


@router.delete("/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_export(
    request: Request,
    export_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete an export."""
    validate_uuid(export_id, "export_id")
    service = ExportService()
    deleted = await service.delete_export(export_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")


class DocxExportRequest(BaseModel):
    content: str
    document_type: str = "document"


@router.post("/docx")
@limiter.limit("20/minute")
async def export_docx(
    request: Request,
    body: DocxExportRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate and download a DOCX file from HTML content."""
    from app.services.export import generate_docx_from_html

    if not body.content or not body.content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="content is required and cannot be empty",
        )

    try:
        docx_bytes = generate_docx_from_html(body.content, body.document_type)
        safe_type = re.sub(r'[^\w\s\-]', '', body.document_type or 'document')[:100]
        filename = f"{safe_type}.docx"
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )
    except Exception as e:
        logger.error("unexpected_error", error=str(e), endpoint="export_docx")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")
