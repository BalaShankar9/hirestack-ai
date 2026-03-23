"""
Export routes - PDF/DOCX generation (Supabase)
"""
import uuid as _uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.export import ExportService
from app.api.deps import get_current_user
from app.core.security import limiter

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


class CreateExportRequest(BaseModel):
    document_ids: List[str] = Field(default_factory=list)
    format: Literal["pdf", "docx", "markdown"] = "pdf"
    filename: Optional[str] = Field(None, max_length=255)
    options: Optional[Dict[str, Any]] = None


@router.post("")
@limiter.limit("10/minute")
async def create_export(
    request: Request,
    body: CreateExportRequest,
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
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export failed. Please check your inputs.")


@router.get("")
@limiter.limit("30/minute")
async def list_exports(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's exports."""
    service = ExportService()
    return await service.get_user_exports(current_user["id"])


@router.get("/{export_id}")
@limiter.limit("30/minute")
async def get_export(
    request: Request,
    export_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get export details."""
    _validate_uuid(export_id, "export_id")
    service = ExportService()
    export = await service.get_export(export_id, current_user["id"])
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    return export


@router.get("/{export_id}/download")
@limiter.limit("10/minute")
async def download_export(
    request: Request,
    export_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Download an exported file."""
    _validate_uuid(export_id, "export_id")
    service = ExportService()
    try:
        file_content, filename, content_type = await service.download_export(export_id, current_user["id"])
        safe_filename = filename.replace('"', '').replace('\r', '').replace('\n', '')
        return StreamingResponse(
            iter([file_content]),
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")


@router.delete("/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_export(
    request: Request,
    export_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete an export."""
    _validate_uuid(export_id, "export_id")
    service = ExportService()
    deleted = await service.delete_export(export_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
