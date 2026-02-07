"""
Export routes - PDF/DOCX generation (Firestore)
"""
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.services.export import ExportService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("")
async def create_export(
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create an export of documents."""
    service = ExportService()
    try:
        return await service.create_export(
            user_id=current_user["id"],
            document_ids=request.get("document_ids", []),
            fmt=request.get("format", "pdf"),
            filename=request.get("filename"),
            options=request.get("options"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("")
async def list_exports(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's exports."""
    service = ExportService()
    return await service.get_user_exports(current_user["id"])


@router.get("/{export_id}")
async def get_export(
    export_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get export details."""
    service = ExportService()
    export = await service.get_export(export_id, current_user["id"])
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    return export


@router.get("/{export_id}/download")
async def download_export(
    export_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Download an exported file."""
    service = ExportService()
    try:
        file_content, filename, content_type = await service.download_export(export_id, current_user["id"])
        return StreamingResponse(
            iter([file_content]),
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_export(
    export_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete an export."""
    service = ExportService()
    deleted = await service.delete_export(export_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
